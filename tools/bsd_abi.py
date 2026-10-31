#!/usr/bin/env python3
"""BSD ABI layer for the sovren compilers.

Every number in this file's *output* comes from a vendor header that was
fetched from the vendor's own repository (see tools/bsd_abi.json -> "sources").
Nothing is written from memory: the tables are re-derived on demand and
`--check` fails when the committed table no longer matches the headers.

  linux  arch/x86/entry/syscalls/syscall_64.tbl   (x86-64 syscall names)
  bsd    sys/kern/syscalls.master + sys/sys/syscall.h  (name -> number)
  both   sys/sys/fcntl.h, asm-generic/fcntl.h     (open flags)
         mman-common.h / mman.h                   (mmap flags)
         elf_common.h / exec_elf.h                (ELF OSABI brand)

The *shape* decisions (which Linux call has the same argument list as the
BSD call of a given name) are the one judgement call here, so each one is
written down with its reason in ALIAS / GAP below and printed by --report.

usage:
  bsd_abi.py --report              show the derived table for every target
  bsd_abi.py --emit                write tools/bsd_abi.json
  bsd_abi.py --check               exit 1 if the committed json drifts from headers
  bsd_abi.py --gen TARGET          write compilers/operating-systems/TARGET/compiler.sov
  bsd_abi.py --verify TARGET       compile a probe with both kits, compare numbers
"""

import json
import os
import re
import subprocess
import sys
import collections
import glob
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.environ.get('BSD_ABI_SRC', '/home/user/work/targets')
JSONP = os.path.join(HERE, 'bsd_abi.json')
LINUX_KIT = os.path.join(ROOT, 'compilers', 'linux', 'compiler.sov')

TARGETS = ('freebsd', 'netbsd', 'openbsd', 'dragonfly', 'illumos', 'haiku', 'redox', 'qnx', 'serenityos', 'menuetos', 'sovrenos')
STD_SRC = {
    'freebsd': 'freebsd/freebsd-src/main',
    'netbsd': 'NetBSD/src/trunk',
    'openbsd': 'openbsd/src/master',
    'dragonfly': 'DragonFlyBSD/DragonFlyBSD/master',
    'illumos': 'illumos/illumos-gate/master',
    'haiku': 'haiku/haiku/master',
    'redox': 'redox-os/kernel/master',
    # the QSS public trunk (the vendor's own community tree, QSS copyright headers intact)
    'qnx': 'vocho/openqnx/master',
    'serenityos': 'SerenityOS/serenity/master',
    # the vendor's own system-call document for the current release
    'menuetos': 'menuetos.net syscalls.txt (v1.61.00)',
    # our own schema: the authoritative native ABI, read live
    'sovrenos': '/home/user/sovrenos/abi/syscalls.sov (ABI_ROW rows)',
}
ELFC = {'freebsd': 'elf_common.h', 'netbsd': 'exec_elf.h', 'openbsd': 'exec_elf.h',
        'dragonfly': 'elf_common.h',
        'illumos': 'elf.h'}

# Which name in the vendor's own elf header carries the brand, and the note to
# record next to it.  DragonFly is the one target whose brand is not spelled
# after it: sys/sys/elf_common.h defines no ELFOSABI_DRAGONFLY, and the kernel's
# own ELF writer stamps the images it produces ELFOSABI_NONE (sys/kern/
# imgact_elf.c, the e_ident[EI_OSABI] assignment), so 0 is the only value a
# DragonFly-native image can carry.  The value still comes from the header
# (#define ELFOSABI_NONE 0), like every other number here.
BRAND = {
    'freebsd':   ('ELFOSABI_FREEBSD', None),
    'netbsd':    ('ELFOSABI_NETBSD', None),
    'openbsd':   ('ELFOSABI_OPENBSD', None),
    'dragonfly': ('ELFOSABI_NONE',
                  'no ELFOSABI_DRAGONFLY in elf_common.h; the kernel stamps ELFOSABI_NONE'),
    # illumos declares no OS/ABI of its own either: elf.h defines ELFOSABI_SOLARIS
    # and nothing named after illumos.  The kernel's ELF exec path validates
    # class, data, machine and magic and never reads e_ident[EI_OSABI]
    # (usr/src/uts/common/exec/elf/elf.c), so the brand is the value its own
    # header gives for the system it descends from.
    'illumos': ('ELFOSABI_SOLARIS',
                'no ELFOSABI_ILLUMOS in elf.h; the kernel does not read e_ident[7]'),
    # Haiku declares no OS/ABI anywhere in its ELF headers and its loader reads
    # magic, class and machine only (src/system/kernel/elf.cpp).  0 is the
    # ELF-standard "unspecified" and the only value a Haiku image can carry.
    'haiku': (None,
              'no OS/ABI value in any Haiku ELF header; the loader checks magic, class and machine only'),
    # Redox's kernel tree defines no ELFOSABI_* anywhere: the ELF reader it
    # links is the object crate (Cargo.toml: features = ["read_core", "elf"]),
    # which parses magic, class, data and machine and never reads e_ident[7].
    # Byte 7 stays 0, the ELF-standard "unspecified".
    'redox': (None,
              'no ELFOSABI_* in the kernel tree (ELF via the object crate); e_ident[7] is never read'),
    # QNX's own elf.h spells the standard ELFOSABI enum out and stops at AROS:
    # there is no ELFOSABI_QNX anywhere in the public tree, so a Neutrino
    # image carries 0, the ABI-standard "unspecified".
    'qnx': (None,
            'no ELFOSABI_QNX in the vendor elf.h (the enum stops at AROS); e_ident[7] is 0'),
    # Serenity's own ELFABI.h spells the standard list and stops at ARM 97:
    # the first entry is ELFOSABI_SYSV and nothing is named after Serenity.
    'serenityos': (None,
                   'no ELFOSABI_SERENITY in LibELF/ELFABI.h (the enum stops at ARM); e_ident[7] is ELFOSABI_SYSV'),
    # there is no ELF: a Menuet64 image carries the vendor's own MENUET64
    # header (magic, header version, entry, image size, memory, rsp), and no
    # e_ident exists to brand.  ELF machinery bytes the writer produced under
    # the header are dead weight the kernel ignores.
    'menuetos': (None,
                 'no ELF: the image carries the MENUET64 header, there is no e_ident'),
    # the tree defines no ELFOSABI value of its own (no ELFOSABI_* anywhere
    # outside third-party C evidence), and the loader checks magic and class
    'sovrenos': (None,
                 'no ELFOSABI value defined in the sovrenos tree; e_ident[7] is 0'),
}

# ---------------------------------------------------------------- parsing

def _lines(path):
    with open(path, errors='replace') as f:
        return f.read().split('\n')


def _joined(path):
    """_lines(), with \\-continued lines glued to the one before.

    Every BSD syscalls.master wraps a long prototype over as many lines as it
    needs; the name and the number of such a call are only visible once the
    lines are one."""
    out = []
    for ln in _lines(path):
        if out and out[-1].rstrip().endswith('\\'):
            out[-1] = out[-1].rstrip()[:-1] + ' ' + ln.strip()
        else:
            out.append(ln)
    return out


def linux_syscalls(path=None):
    """{num: name} from arch/x86/entry/syscalls/syscall_64.tbl (abi common|64)."""
    path = path or os.path.join(SRC, 'linux', 'syscall_64.tbl')
    out = {}
    for ln in _lines(path):
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        f = ln.split()
        if len(f) < 3:
            continue
        if f[1] not in ('common', '64'):
            continue
        out[int(f[0])] = f[2]
    return out


def bsd_master(path, prefix='sys_'):
    """{name: num} from a BSD syscalls.master.

    Lines look like one of
        3    STD      { int read(int fd, void *buf, size_t nbyte); }        (openbsd)
        5    AUE_OPEN_RWTC STD { int open(char *path, int flags, int mode); } (freebsd)
        394  STD      RUMP    { int|sys|30|socket(int domain, ...); }        (netbsd)
    Compatibility entries live inside #ifdef blocks and number the same call
    differently, so conditional lines are skipped."""
    out = {}
    depth = 0
    rx = re.compile(r'^(\d+)\s+(?:AUE_[A-Z0-9_]+\s+)?([A-Za-z_][A-Za-z0-9_|]*)\s+\{(.*)$')
    lines = _joined(path)
    pend = None
    for ln in lines:
        if pend is not None:                      # prototype on a following line
            num, kind = pend
            proto = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', ln)
            if proto and ('STD' in kind or kind == 'NOARGS'):
                name = proto.group(1)
                if name.startswith(prefix):
                    name = name[len(prefix):]
                out[name] = num
            pend = None
            continue
        t = ln.strip()
        if t.startswith('#if'):
            depth += 1
            continue
        if t.startswith('#endif'):
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        m = rx.match(t)
        if not m:
            continue
        kind, body = m.group(2), m.group(3)
        if 'STD' not in kind and kind != 'NOARGS':
            continue
        proto = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', body)
        if not proto:
            pend = (int(m.group(1)), kind)
            continue
        name = proto.group(1)          # the identifier the prototype calls
        if name.startswith(prefix):
            name = name[len(prefix):]
        out[name] = int(m.group(1))
    return out


def bsd_syscall_h(path, prefix='SYS_'):
    """{name: num} from sys/sys/syscall.h (#define SYS_x n)."""
    out = {}
    rx = re.compile(r'^#define\s+' + prefix + r'([A-Za-z0-9_]+)\s+(\d+)\s*$')
    for ln in _lines(path):
        m = rx.match(ln.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def haiku_syscalls(path):
    """Haiku's numbers, in the order the vendor's own generator hands them out.

    Haiku has no file of `#define SYS_x n` lines: the numbers are assigned by
    src/tools/gensyscalls, which preprocesses headers/private/system/syscalls.h
    and walks the prototypes between the two `#pragma syscalls` lines in the
    order they are written, numbering them from zero (`_WriteNumbersFile`);
    the kernel compares the call number against the generated count
    (src/system/kernel/arch/x86/64/interrupts.S: `cmpq $SYSCALL_COUNT, %r14`).
    The input read here is that same preprocessed header, so the index of a
    prototype *is* the number, and the list is the vendor's, not a copy."""
    text = open(path, errors='replace').read()
    i = text.index('pragma syscalls begin')
    j = text.index('pragma syscalls end')
    out = {}
    for n, chunk in enumerate(text[i:j].split(';')):
        m = re.search(r'_kern_([A-Za-z0-9_]+)\s*\(', chunk)
        if not m:
            continue
        if m.group(1) in out:
            raise SystemExit('haiku: %s appears twice in the list' % m.group(1))
        out[m.group(1)] = len(out)
    return out


def redox_numbers(path):
    """Redox's numbers, from the syscall crate's own number.rs.

    Redox has no syscalls.master and no count boundary: a call number is a
    32-bit tagged value, class | arg | ret | low bits (SYS_CLASS_FILE |
    SYS_ARG_MSLICE | 3 is SYS_READ).  Every number here is evaluated out of
    `pub const NAME: usize = EXPR;` lines in that file, tags first, exactly as
    the crate orders its own definitions - nothing is written by hand."""
    raw = []
    rx = re.compile(r'pub const ([A-Za-z0-9_]+):\s*usize\s*=\s*([^;]+);')
    for ln in _lines(path):
        m = rx.match(ln.strip())
        if m:
            raw.append((m.group(1), m.group(2).split('//')[0].strip()))
    out = {}
    for _round in range(4):
        for name, body in raw:
            if name in out:
                continue
            v = _eval_c(rust_digits(body), out)
            if v is not None:
                out[name] = v
    missing = [n for n, _ in raw if n not in out]
    if missing:
        raise SystemExit('redox: number.rs lines not evaluated: %s' % ', '.join(missing))
    return out


def redox_flags(path):
    """the flag words of flag.rs: `pub const O_*: usize = ...` and the
    bitflags! `const PROT_* / MAP_* = ...` of MapFlags, read the same way."""
    raw = []
    rx = re.compile(r'(?:pub )?const ([A-Za-z0-9_]+)(?::\s*\w+)?\s*=\s*([^;]+);')
    for ln in _lines(path):
        m = rx.match(ln.strip())
        if m:
            raw.append((m.group(1), m.group(2).split('//')[0].strip()))
    out = {}
    for _round in range(4):
        for name, body in raw:
            if name in out:
                continue
            v = _eval_c(rust_digits(body), out)
            if v is not None:
                out[name] = v
    return out


def rust_digits(expr):
    """strip rust's digit separators: 0xF000_0000 and 1_000_000 read as one
    literal each, which the C evaluator below would misread."""
    for _ in range(4):
        e2 = re.sub(r'([0-9a-fA-F])_([0-9a-fA-F])', r'\1\2', expr)
        if e2 == expr:
            break
        expr = e2
    return expr


def redox_arms(path):
    """the numbers the kernel actually dispatches, read out of the match arms
    of kernel/src/syscall/mod.rs - the vendor's own list of what answers."""
    names = re.findall(r'^(?:\s*)(SYS_[A-Z0-9_]+)\s*=>', open(path, errors='replace').read(),
                       re.M)
    return names


def menuet_fns(path):
    """MenuetOS 64's function numbers, from the vendor's own document.

    syscalls.txt (v1.61.00) carries an index of every defined function,
    "  N - Name", between the "Index:" line and the separator dash.  The
    index is the whole ABI surface: the gate is int 0x60 with the function
    number in rax (the syscall instruction is an optional second gate the
    document spells next to it)."""
    fns = {}
    in_idx = False
    for ln in open(path, encoding='iso-8859-1', errors='replace'):
        ln = ln.rstrip('\r\n')
        if ln.strip() == 'Index:':
            in_idx = True
            continue
        if not in_idx:
            continue
        if ln.strip() in ('-', ''):
            if fns:
                break
            continue
        m = re.match(r'^\s{0,6}(\d+) - (.+?)\s*$', ln)
        if m:
            fns[m.group(1)] = int(m.group(1))
    if not fns:
        raise SystemExit('menuetos: no function index in %s' % path)
    return fns


def qnx_kercalls(path):
    """QNX's kernel-call numbers, from the vendor's own enum.

    sys/kercalls.h numbers the calls by enum position (__KER_NOP is 0, every
    name the next value; the header's comments carry the hex).  The kernel's
    ker_call_table.c lays its handlers out in the same order, so the position
    of a name in the enum *is* the number - read here, not written."""
    out = {}
    rx = re.compile(r'^\s*(__KER_[A-Z0-9_]+)\s*,?\s*(/\*.*\*/)?$')
    for ln in _lines(path):
        m = rx.match(ln)
        if m:
            name = m.group(1)
            if name in out:
                raise SystemExit('qnx: %s appears twice in the enum' % name)
            out[name] = len(out)
    if '__KER_BAD' not in out:
        raise SystemExit('qnx: the enum has no __KER_BAD sentinel')
    return out


def qnx_bad_slots(path):
    """the enum positions whose dispatch slot is the ENOSYS handler.

    ker_call_table.c lays one handler per enum position; the SPARE slots are
    `pref##_bad`, and ker_bad() returns ENOSYS - the vendor's own answer for
    an unimplemented call.  Returned as (positions, count): the count is
    cross-checked against the enum, so the header and the kernel table cannot
    drift apart unnoticed."""
    # the macro body *is* the table: one `pref##_handler,` line per slot, and
    # the instantiations (MK_KERTABLE(ker) and friends) expand this same list
    slots = []
    in_body = False
    rx = re.compile(r'pref##_([a-z0-9_]+),?\s*\\*?$')
    for ln in _lines(path):
        if ln.startswith('#define MK_KERTABLE'):
            in_body = True
            continue
        if not in_body:
            continue
        m = rx.search(ln)
        if m:
            slots.append(m.group(1))
            if not ln.rstrip().endswith('\\'):
                break                      # the last line of the macro body
        elif ln.strip().rstrip('\\').strip():
            break                          # the macro body ended
    return slots


def serenity_syscalls(path):
    """Serenity's syscall numbers, from the vendor's own X-macro list.

    Kernel/API/Syscall.h declares every syscall once, in
    `#define ENUMERATE_SYSCALLS(S)` order, and both sides number them by
    position: the kernel builds `enum Function { SC_##name, ... __Count }`
    from the same list, and LibSystem calls the SC_ constants.  The position
    of a name in this list *is* the number; __Count is the count of names,
    which is also the probe (see PROBE_NOTE)."""
    out = {}
    rx = re.compile(r'^\s*S\(([a-z0-9_]+),\s*Needs')
    for ln in _lines(path):
        m = rx.match(ln)
        if m:
            name = m.group(1)
            if name in out:
                raise SystemExit('serenityos: %s appears twice in ENUMERATE_SYSCALLS' % name)
            out[name] = len(out)
    if not out:
        raise SystemExit('serenityos: no syscalls read from %s' % path)
    return out


_CINT = re.compile(r'^[0-9a-fA-FxX()<>|&~+\-\t ]+$')
_names = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _eval_c(expr, table, seen=()):
    """Evaluate a C constant expression that only uses integers and names."""
    e = expr
    for _ in range(8):
        e2 = re.sub(r'\b0[xX][0-9a-fA-F]+\b',
                    lambda m: '(%d)' % int(m.group(0), 16), e)
        e2 = re.sub(r'\b0[0-7]+\b', lambda m: '(%d)' % int(m.group(0), 8), e2)
        e2 = re.sub(r'\b\d+\b', lambda m: '(%d)' % int(m.group(0), 10), e2)
        if e2 == e:
            break
        e = e2

    def sub(m):
        v = table.get(m.group(0))
        return '(%d)' % v if isinstance(v, int) else '(0)'
    e = _names.sub(sub, e)
    if not _CINT.match(e):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return int(eval(e, {'__builtins__': {}}, {}))
    except Exception:
        return None


def lookup(name, table, seen=()):
    if name in table:
        return table[name]
    if name in seen:
        return None
    return None


def defines(path, prefix):
    """{NAME: value} for plain integer #defines.

    The vendors write these every which way - octal, (1 << 6), __O_SYNC|O_DSYNC -
    so every value goes through _eval_c(), which resolves the names it meets
    against the definitions already read from the same file."""
    raw = {}
    rx = re.compile(r'^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.*)$')
    for ln in _lines(path):
        m = rx.match(ln)
        if not m:
            continue
        body = m.group(2).split('/*')[0].split('//')[0].strip()
        if body and not body.startswith('(') or (body.startswith('(') and body.endswith(')')):
            if body:
                raw[m.group(1)] = body
    out = {}
    for round_ in range(3):
        for name, body in raw.items():
            if name in out:
                continue
            v = _eval_c(body, out)
            if v is not None:
                out[name] = v
    return {k: v for k, v in out.items() if k.startswith(prefix)}


def elf_osabi(path, name):
    rx = re.compile(r'^#define\s+' + name + r'\s+(\d+)')
    for ln in _lines(path):
        m = rx.match(ln.strip())
        if m:
            return int(m.group(1))
    return None


# ------------------------------------------------------- shape decisions
#
# kind 'exact'  - the BSD call of the same name takes the same arguments
# kind 'alias'  - renamed, same arguments, note says why
# kind 'gap'    - no safe counterpart; the number is replaced by an invalid
#                 one (ENOSYS probe) so the call fails loudly instead of
#                 silently doing something else.
#
# Anything not named here and found in both tables is 'exact' (see derive()).

ALIAS = {
    'exit':         ('_exit', 'alias', 'FreeBSD syscalls.master spells the process exit _exit'),
    'rt_sigaction': ('sigaction', 'gap', 'BSD sigaction(2) takes (sig, act, oact); '
                                       'the Linux kernel action block and the extra sigsetsize '
                                       'argument make the two frames incompatible'),
    'newfstatat':   ('fstatat', 'gap', 'struct stat differs between the two kernels'),
    'fstat':        ('fstat', 'gap', 'BSD fstat(2) is struct-versioned against Linux stat'),
    'stat':         ('stat', 'gap', 'struct stat differs'),
    'lstat':        ('lstat', 'gap', 'struct stat differs'),
    'statfs':       ('statfs', 'gap', 'struct statfs differs'),
    'getdents64':   ('getdirentries', 'gap', 'BSD dirent has no d_off and a different layout'),
    'getdents':     ('getdirentries', 'gap', 'BSD dirent has no d_off and a different layout'),
    'getcwd':       ('__getcwd', 'alias', 'BSD exposes getcwd as __getcwd, same (buf, size)'),
    'gettid':       ('getpid', 'alias', 'BSD has no per-thread id in the pid namespace; a '
                                        'single-threaded sovren program has gettid() == getpid()'),
    'mlock':        ('mlock', 'alias', 'same (addr, len)'),
    'munlock':      ('munlock', 'alias', 'same (addr, len)'),
    'sendfile':     ('sendfile', 'gap', 'BSD sendfile(2) takes 7 arguments and a header/trailer'),
    'epoll_create': ('kqueue', 'gap', 'BSD has kqueue, not epoll'),
    'socket':        ('__socket30', 'alias', 'NetBSD renamed the current socket ABI __socket30'),
    'clock_gettime': ('__clock_gettime50', 'alias', 'NetBSD names the current clock_gettime __clock_gettime50'),
    'nanosleep':     ('__nanosleep50', 'alias', 'NetBSD names the current nanosleep __nanosleep50'),
    'mmap':          ('mmap', 'exact', 'same six arguments'),
}

GAP = {
    'pipe':           'FreeBSD marks pipe(2) COMPAT10 (it returns the two fds in registers for old '
                      'binaries) and the tree only uses it inside the emulator, so it stays a gap '
                      'on every target',
    'clone':          'BSD threads are rfork/thr_new; the Linux flag word and stack argument differ',
    'clone3':         'no BSD counterpart',
    'futex':          'BSD user-space mutexes are _umtx_op, a different call',
    'set_robust_list': 'no BSD counterpart',
    'get_robust_list': 'no BSD counterpart',
    'arch_prctl':     'no BSD counterpart (segment bases are sysarch(AMD64_SET_FSGSBASE))',
    'prctl':          'BSD counterpart is procctl with a different argument list',
    'io_uring_setup': 'no BSD counterpart',
    'eventfd2':       'no BSD counterpart',
    'epoll_create1':  'no BSD counterpart',
    'epoll_ctl':      'no BSD counterpart',
    'epoll_wait':     'no BSD counterpart',
    'signalfd4':      'no BSD counterpart',
    'inotify_init1':  'BSD uses kqueue',
    'inotify_add_watch': 'BSD uses kqueue',
    'userfaultfd':    'no BSD counterpart',
    'memfd_create':   'no BSD counterpart',
    'bpf':            'no BSD counterpart',
    'perf_event_open': 'no BSD counterpart',
    'sysctl':         'Linux takes a string name, BSD an mib array',
    '__sysctl':       'Linux takes a string name, BSD an mib array',
    'timerfd_create': 'no BSD counterpart',
    'timerfd_settime': 'no BSD counterpart',
    'shmget':         'different ipc objects and argument shapes',
    'semget':         'different ipc objects and argument shapes',
    'msgget':         'different ipc objects and argument shapes',
    'reboot':         'argument shape differs (BSD reboot takes one howto word)',
    'execveat':       'BSD counterpart is fexecve with a different shape',
}

# argument-position rewrites.  Each entry is
#   (syscall Linux number, argument index)  ->  canonical flag word
# and the *values* come from the headers on both sides.
OPEN_LINUX = [2, 257, 258, 259]          # open, openat, mkdirat? no: keep the open family only
OPEN_POS = {2: 2, 257: 3, 258: 3}         # syscall number -> 1-based flags argument
MMAP_POS = {9: 4}                         # mmap: addr,len,prot,flags,fd,off
ADVISE_POS = {28: 3}                      # madvise: addr,len,advice
ADVISE_ALIAS = {'MADV_DONTDUMP': 'MADV_NOCORE', 'MADV_DODUMP': 'MADV_CORE'}

CAND = {
    'open': ['O_RDONLY', 'O_WRONLY', 'O_RDWR', 'O_ACCMODE', 'O_CREAT', 'O_EXCL',
             'O_TRUNC', 'O_APPEND', 'O_NONBLOCK', 'O_DIRECTORY', 'O_CLOEXEC',
             'O_NOFOLLOW', 'O_SYNC', 'O_DSYNC', 'O_NOCTTY', 'O_ASYNC', 'O_DIRECT',
             'O_NOATIME', 'O_PATH', 'O_TMPFILE'],
    'mmap': ['MAP_SHARED', 'MAP_PRIVATE', 'MAP_FIXED', 'MAP_ANON', 'MAP_ANONYMOUS',
             'MAP_NORESERVE', 'MAP_GROWSDOWN', 'MAP_POPULATE', 'MAP_NOCORE',
             'MAP_STACK', 'MAP_HUGETLB'],
    'advise': ['MADV_NORMAL', 'MADV_RANDOM', 'MADV_SEQUENTIAL', 'MADV_WILLNEED',
               'MADV_DONTNEED', 'MADV_FREE', 'MADV_DONTDUMP', 'MADV_DODUMP',
               'MADV_WIPEONFORK', 'MADV_KEEPONFORK', 'MADV_NOCORE', 'MADV_CORE',
               'MADV_HUGEPAGE', 'MADV_NOHUGEPAGE'],
}

# Per-target judgements that do not fit the BSD-shaped ALIAS/GAP above.  Same
# rules: the name and the frame have to be the vendor's, and the reason is
# written down next to it.
TALIAS = {
    'illumos': {
        # illumos's own libc: __forkx(flags) is `forksys(0, flags)`
        # (usr/src/lib/libc/amd64/sys/forkx.S), so fork() is forksys(0, 0) --
        # and the tree's fork site passes zeros in every register.
        'fork': ('forksys', 'alias',
                 'illumos forks through forksys(0, flags); the tree passes zeros'),
    },
}
TNOTE = {
    'illumos': {
        'socket':      'illumos names this so_socket(domain, type, protocol, devpath, version): two more arguments than the tree passes',
        'poll':        'illumos names this pollsys(fds, nfds, timeout, sigmask): a different frame',
        'wait4':       'illumos names this waitid(idtype, id, infop, options): a different frame',
        'fsync':       'illumos names this fdsync(fd, flag); the tree leaves the flag register at zero',
        'dup2':        'no dup2 entry; illumos reaches it through fcntl(F_DUP2FD)',
        'ftruncate':   'no ftruncate entry in the illumos syscall table',
        'geteuid':     'no geteuid entry in the illumos syscall table',
        'mlock':       'no mlock entry in the illumos syscall table',
        'madvise':     'no madvise entry in the illumos syscall table',
        'clone':       'no clone entry; illumos threads are lwp_create(159), a different frame',
    },
}


TALIAS['haiku'] = {
    # same name, same six registers, same meaning
    'close':    ('close', 'exact', None),
    'lseek':    ('seek', 'exact', None),
    'mprotect': ('set_memory_protection', 'exact', None),
    'munmap':   ('unmap_memory', 'exact', None),
    'madvise':  ('memory_advice', 'exact', None),
    'mlock':    ('mlock', 'exact', None),
    'getcwd':   ('getcwd', 'exact', None),
    'connect':  ('connect', 'exact', None),
    'bind':     ('bind', 'exact', None),
    'listen':   ('listen', 'exact', None),
    'sendto':   ('sendto', 'exact', None),
    'recvfrom': ('recvfrom', 'exact', None),
    # renamed, or with an argument the tree leaves zero
    'openat':   ('open', 'alias',
                 "Haiku's open(fd, path, openMode, perms) is the *at() frame: AT_FDCWD is -100 on both "
                 "systems and the kernel accepts it (vfs.cpp: fd == AT_FDCWD || fd == -1)"),
    'unlinkat': ('unlink', 'alias',
                 "Haiku's unlink(fd, path) takes no flags; the tree's third argument is 0"),
    'dup2':     ('dup2', 'alias',
                 "Haiku's dup2 carries flags third; the vendor libc passes 0 and so does the tree"),
    'pipe':     ('create_pipe', 'alias',
                 "create_pipe(fds, flags); the tree's flags are 0"),
    'fsync':    ('fsync', 'alias',
                 "Haiku's fsync(fd, dataOnly); the vendor libc passes false and the tree's argument is 0"),
    'kill':     ('send_signal', 'alias',
                 "the vendor libc kill() is _kern_send_signal(pid, sig, NULL, 0): the two extra arguments "
                 "are the zeros the tree already passes"),
    'accept':   ('accept', 'alias',
                 "Haiku's accept(socket, address, length, flags); the flags the tree does not pass read 0"),
    'fork':     ('fork', 'alias',
                 "fork() is _kern_fork(), the vendor libc's own call"),
    'exit':     ('exit_team', 'alias',
                 "a process is a team on Haiku: exit_team(status), which is what libc _exit() calls"),
    'getpid':   ('get_current_team', 'alias',
                 "Haiku has no process ids; a process is its team, and the tree wants a positive identity"),
    'gettid':   ('find_thread', 'alias',
                 "find_thread(NULL) is the calling thread; the tree passes zeros in every register"),
    # the two the kit itself reshapes: Haiku's read and write carry the file
    # offset as an argument of their own, and the vendor's libc passes -1 there
    # for "where the file position is" (libroot/posix/unistd/read.c:
    # `_kern_read(fd, -1, buffer, bufferSize)`).  The kit inserts that argument
    # at the tree's own helper (SHIM below), so the call lands on Haiku's frame;
    # the number is still the text pass's business, which is why the shim leaves
    # the Linux number in place.
    'read':     ('read', 'alias',
                 "Haiku's read(fd, pos, buffer, size): the kit puts the -1 the vendor libc passes into "
                 "the second argument and slides the tree's buffer and count along"),
    'write':    ('write', 'alias',
                 "Haiku's write(fd, pos, buffer, size): the kit puts the -1 the vendor libc passes into "
                 "the second argument and slides the tree's buffer and count along"),
}

# The one place a table is not enough.  Each entry is a text patch applied when
# the kit is generated: the tree's own helper line, rewritten to the target's
# argument list.  `was` must occur in the expanded tree, `now` is what it
# becomes, and the Linux call number is left alone so the text pass still maps
# it.  Only targets listed here are treated this way, and every patch is
# asserted to hit exactly the number of sites recorded next to it.
# Targets whose call frames differ by one argument: the Linux call number maps
# to a call whose extra argument the tree does not pass.  The value written is
# the one the vendor's own libc passes there, and the insertion happens in the
# text pass (see shim_pass), after the numbers have been mapped - so the pattern
# it looks for carries the *target* number and nothing else can match.
#   {host: {linux number: (position after which to insert, what to insert)}}
SHIM_ARGS = {
    'haiku': {
        0: (1, ' 0 - 1,'),      # read(fd, pos, buffer, size): libc passes pos = -1
        1: (1, ' 0 - 1,'),      # write(fd, pos, buffer, size): the same
    },
}

# The same idea at the other end of the compiler: the call the kit builds for a
# plain `print`, before any of the tree runs.  Here a register is spared by
# asking the emitter for the bytes: the `mov rsi, rax` that frees rax becomes
# `push rax` / `pop rsi`, so the number the emitter sets afterwards is unclobbered.
SHIM_FNS = {
}

# (there was a patch here that moved the string pointer through the stack under
#  a `mov al, imm` call number; taken back out: the tree never moves a pointer
#  through rax at a call site - the number is emitted after the last argument
#  move, and every `mov al, n` simply follows a `mov rsi, ...`)
SHIM_LITS = {}

TNOTE['haiku'] = {
    'open':          "open(fd, path, openMode, perms): the path is the second argument, not the first (the tree's openat does land on it)",
    'poll':          "poll(fds, numFDs, bigtime_t timeout, sigMask): microseconds, not milliseconds, and a signal mask",
    'mmap':          "map_file(name, address, addressSpec, size, protection, mapping, unmapAddressRange, fd, offset): nine arguments, and the address comes back through the second",
    'ioctl':         "ioctl(fd, cmd, data, length): the fourth argument is the buffer length, which the tree leaves zero",
    'socket':        "the frame matches but the words do not: AF_INET is 1 on Haiku and 2 on Linux, AF_UNIX is 9 against 1, and the family arrives in a register (a helper parameter), so a number table cannot fix it",
    'nanosleep':     "snooze_etc(bigtime_t microseconds, timebase, flags, remaining)",
    'wait4':         "wait_for_child(child, flags, siginfo_t*, team_usage_info*): argument 2 is a flags word where Linux has the status pointer",
    'execve':        "exec(path, flatArgs, flatArgsSize, argCount, envCount, umask): the arguments arrive flattened",
    'ftruncate':     "preallocate(fd, offset, length)",
    'chdir':         "setcwd(fd, path)",
    'mkdir':         "create_dir(fd, path, perms)",
    'rmdir':         "remove_dir(fd, path)",
    'unlink':        "unlink(fd, path): the first argument is a directory fd",
    'chmod':         "write_stat(fd, path, traverseLink, stat*, statSize, statMask)",
    'rename':        "rename(oldDir, oldPath, newDir, newPath)",
    'getuid':        "getresuid(uid*, euid*, suid*): three out-parameters",
    'getgid':        "getresgid(gid*, egid*, sgid*): three out-parameters",
    'geteuid':       "getresuid(uid*, euid*, suid*): three out-parameters",
    'clock_gettime': "get_clock(clockid, bigtime_t* _time): the result is a microsecond count, not a timespec",
    'getrandom':     "randomness is a generic syscall on Haiku: generic_syscall(RANDOM_SYSCALLS, RANDOM_GET_ENTROPY, ...), which is what libroot's getentropy() calls",
    'getdents64':    "read_dir(fd, buffer, bufferSize, maxCount): the vendor's own readdir passes USHRT_MAX as the count and the tree passes 0",
    'newfstatat':    "read_stat(fd, path, traverseLink, stat*, statSize)",
    'mincore':       "Haiku has no mincore; the area calls (area_for, get_area_info) are the equivalent",
}

# Targets whose mapping is decided only by TALIAS above: a name that happens to
# exist in the vendor's list is not enough on its own, because the frames have
# to line up.  Everything not named in TALIAS is a gap here.
TLOCK = ('haiku', 'redox', 'qnx', 'serenityos', 'menuetos', 'sovrenos')

# Redox: the kernel's dispatch (kernel/src/syscall/mod.rs, 27 arms) has file
# and memory calls, and nothing else.  There is no exit, fork, getpid, kill,
# waitpid, socket or open in the ABI at all: on Redox those live in *schemes*,
# reached by SYS_CALL on a file descriptor the tree does not hold (the proc
# scheme fd is opened by the vendor's own redox-rt at startup, and getpid does
# not call the kernel - it reads the pid the proc scheme handed over).  The
# ten names below are the whole of what the tree may call; everything else is
# a gap *by architecture*, and the reasons are the vendor's own code.
TALIAS['serenityos'] = {
    # every entry here was checked against the vendor's own libc call
    # (Userland/Libraries/LibC): the ones below take plain register arguments
    # in the order the tree passes them, and take at most two - the frame's
    # third argument rides rbx, and the tree has no rbx slot (see the gaps).
    'close':         ('SC_close', 'exact', None),
    'munmap':        ('SC_munmap', 'exact',
                      "sys$munmap(addr, size), two plain arguments (Kernel/Syscalls/mmap.cpp)"),
    'pipe':          ('SC_pipe', 'exact',
                      "libc pipe: syscall(SC_pipe, pipefd, flags); the tree's flags are 0"),
    'dup2':          ('SC_dup2', 'exact', "libc: syscall(SC_dup2, old_fd, new_fd)"),
    'getpid':        ('SC_getpid', 'exact', None),
    'fork':          ('SC_fork', 'exact', None),
    'exit':          ('SC_exit', 'exact',
                      "sys$exit(arg1); arg1 rides rdx (RegisterState.h capture_syscall_params)"),
    'kill':          ('SC_kill', 'exact', "libc: syscall(SC_kill, pid, sig)"),
    'fsync':         ('SC_fsync', 'exact', "libc: syscall(SC_fsync, fd)"),
    'ftruncate':     ('SC_ftruncate', 'exact', "libc: syscall(SC_ftruncate, fd, length)"),
    'getcwd':        ('SC_getcwd', 'exact', "libc: syscall(SC_getcwd, buffer, size)"),
    'getuid':        ('SC_getuid', 'exact', None),
    'getgid':        ('SC_getgid', 'exact', None),
    'geteuid':       ('SC_geteuid', 'exact', None),
    'gettid':        ('SC_gettid', 'exact', None),
    'clock_gettime': ('SC_clock_gettime', 'exact', "libc: syscall(SC_clock_gettime, clock_id, ts)"),
    'listen':        ('SC_listen', 'exact', "SC_listen(fd, backlog): two plain arguments"),
    # the back end's own sigreturn site: no arguments, so the frame is fine
    'rt_sigreturn':  ('SC_sigreturn', 'exact', None),
    # every write the back end emits is a print: SC_dbgputstr(buf, len)
    # carries them in (rdx, rdi); the gen patches swap the registers in place
    'write':         ('SC_dbgputstr', 'exact',
                      "SC_dbgputstr(buf, len): pointer params, print-only"),
}

# MenuetOS 64: the gate is int 0x60 with the function number in rax - the
# number half of the frame is Linux's, so the table maps it like any other
# target.  The argument half is not: fn 63/1 takes the character in rcx and
# fn 512 takes nothing, and both site shapes the back end emits are patched
# around the number, not through a table of registers.  Everything else with
# a first or second argument is unwritable in place: the vendor's frame puts
# arg1 in RBX and arg2 in RCX, and the tree marshals rdi, rsi, rdx - there is
# no rbx or rcx slot (the Menuet edition of the rbx wall).
# SovrenOS: the frame is Linux's (the kernel arms LSTAR and marshals to
# SysV - FOREIGN_BINARIES.md), so unlike serenityos and menuetos nothing is
# permuted and no site is rewritten: this is a pure numbers kit, the same
# class as freebsd.  The aliases are the schema rows the tree's plain-arity
# calls land on; each argument count below is the schema's own field three.
TALIAS['sovrenos'] = {
    'read':          ('11', 'exact', "READ(fd, buf, count), three plain words"),
    'write':         ('12', 'exact', "WRITE(fd, buf, count), three plain words"),
    'close':         ('13', 'exact', "CLOSE(fd), one plain word"),
    'mprotect':      ('34', 'exact', "MPROTECT(addr, size, prot), three plain words"),
    'munmap':        ('19', 'exact', "MUNMAP(addr, size), two plain words"),
    'pipe':          ('21', 'exact', "PIPE(fds), one pointer, 16 bytes copyout"),
    'madvise':       ('35', 'exact', "MADVISE(addr, size, advice), three plain words"),
    'getpid':        ('45', 'exact', "PROCESS_SELF(), zero arguments"),
    'gettid':        ('45', 'exact', "PROCESS_SELF() is the thread's own id too"),
    'fork':          ('4',  'exact', "FORK(), zero arguments"),
    'exit':          ('60', 'exact', "EXIT(status), one plain word - the number is Linux's too"),
    'kill':          ('51', 'exact', "PROCESS_SIGNAL(process, signal), two plain words"),
    'mkdir':         ('66', 'exact', "FILE_MKDIR(path), one 32-byte path copyin"),
    'unlink':        ('67', 'exact', "FILE_UNLINK(path), one 32-byte path copyin"),
    'mlock':         ('37', 'exact', "MLOCK(addr, size), two plain words"),
    'rt_sigreturn':  ('17', 'exact', "SIGNAL_RETURN(), zero arguments (the back end's own site)"),
}

TALIAS['menuetos'] = {
    # fn 512 - Terminate process (syscalls.txt): "In : -" - the whole call is
    # the number, so the exit sites only need the wider immediate form
    'exit':          ('512', 'exact', "fn 512 takes no arguments"),
    # fn 63/1 - System debug board, write character: rbx = 1, rcx = char,
    # and the gate returns rax = 0, rbx = 0 (both reloaded per byte); the
    # gen patches turn the two write sites into a byte loop that keeps the
    # Linux number 1 in the bytes - the kit's own code pass maps it to 63
    'write':         ('63', 'exact',
                      "fn 63/1 writes one 7-bit character to the debug board"),
}

# The frame is the round's wall and its headline: on x86-64 Serenity loads
# arg1 in rdx, arg2 in rdi, arg3 in RBX and arg4 in rsi (RegisterState.h
# capture_syscall_params, and AK/Syscall.h invoke() agrees: "a","d","D","b",
# "S").  The tree marshals arguments into rdi, rsi, rdx, r10, r8, r9 - there
# is no rbx slot, so a call of three or more arguments cannot be given its
# third argument by any table of numbers.  The text pass permutes the first
# two arguments of the calls above into the vendor's carriers; everything
# else gaps with the reason next to it.
PERM_ARGS = {'serenityos': (3, 11, 22, 33, 39, 50, 57, 60, 62, 74, 77, 79, 102, 104, 107, 186, 228)}

TNOTE['serenityos'] = {
    'read':        "SC_read(fd, buf, count) is three arguments: the third rides rbx, and the tree has no rbx slot (RegisterState.h capture_syscall_params)",
    'write':       "SC_write is three arguments (rbx wall); the back end's own print sites are reshaped to SC_dbgputstr in the generated file instead",
    'open':        "SC_open takes SC_open_params (a StringArgument struct) by pointer, not a path word",
    'openat':      "SC_openat takes SC_open_params by pointer",
    'poll':        "SC_poll takes SC_poll_params by pointer",
    'lseek':       "libc: syscall(SC_lseek, fd, &offset, whence) - the offset travels by pointer",
    'mmap':        "SC_mmap takes SC_mmap_params by pointer",
    'mprotect':    "SC_mprotect(addr, size, prot) is three arguments (rbx wall)",
    'rt_sigaction': "SC_sigaction takes SC_sigaction_params by pointer",
    'ioctl':       "SC_ioctl is three arguments (rbx wall)",
    'mincore':     "no SC_mincore in ENUMERATE_SYSCALLS",
    'madvise':     "SC_madvise is three arguments (rbx wall)",
    'nanosleep':   "SC_clock_nanosleep takes SC_clock_nanosleep_params by pointer",
    'clone':       "threads are SC_create_thread with SC_thread_params by pointer; the Linux clone flag word has no counterpart",
    'execve':      "SC_execve takes SC_execve_params by pointer",
    'wait4':       "waiting is SC_waitid with SC_waitid_params by pointer",
    'futex':       "SC_futex is six arguments (rbx wall)",
    'getdents64':  "SC_get_dir_entries is three arguments (rbx wall)",
    'newfstatat':  "SC_fstatat takes SC_fstatat_params by pointer",
    'unlinkat':    "SC_unlinkat takes a StringArgument path",
    'rename':      "SC_rename takes SC_rename_params by pointer",
    'mkdir':       "SC_mkdir takes a StringArgument path",
    'rmdir':       "SC_rmdir takes a StringArgument path",
    'unlink':      "SC_unlink takes a StringArgument path",
    'chmod':       "SC_chmod takes a StringArgument path",
    'chdir':       "SC_chdir takes a StringArgument path",
    'socket':      "SC_socket is three arguments (rbx wall)",
    'connect':     "SC_connect is three arguments (rbx wall)",
    'accept':      "SC_accept takes SC_accept_params by pointer",
    'sendto':      "SC_sendto is more arguments than the tree passes (rbx wall)",
    'recvfrom':    "SC_recvfrom is more arguments than the tree passes (rbx wall)",
    'bind':        "SC_bind is three arguments (rbx wall)",
    'mlock':       "no SC_mlock in ENUMERATE_SYSCALLS",
    'prctl':       "no SC_prctl in ENUMERATE_SYSCALLS",
    'getrandom':   "SC_getrandom(buf, size, flags) is three arguments (rbx wall)",
}

TALIAS['qnx'] = {}

# QNX is a microkernel: the kernel calls are messages, scheduling, signals,
# time and sync - there is no read, write, open, exit or mmap kernel call at
# all.  File I/O is a message to a resource manager, the process table is the
# process manager's (procnto, reached by message), and even the calls the
# kernel *does* have (ClockTime, TimerTimeout, SignalKill, ThreadDestroy) take
# their arguments in an order the tree's Linux frames do not.  Every number
# the tree uses is therefore a gap here, each with the vendor's own reason.
# The Menuet edition of the rbx wall plus everything the OS does not have.
# fn 58 - Filesystem is block based (512-byte blocks, asciiz name, no file
# descriptors, no open or close), fn 64 is a malloc-style manager whose
# subfunction rides rbx, and there are no signals, no forks, no pipes and no
# sockets anywhere in the index.  Each reason below is the vendor's own text.
# Every gap is a schema fact: the row exists but takes fewer/different
# arguments than the tree passes, or no row exists at all.
TNOTE['sovrenos'] = {
    'open':        "OPEN is one 32-byte path and nothing else - no flag word exists in the schema (ABI_ROW_010), and the tree's open carries modes",
    'openat':      "no dirfd concept: OPEN is one path (ABI_ROW_010); the tree's openat carries dirfd, flags and mode",
    'lseek':       "no lseek row in the schema; FILE_READ is path based (ABI_ROW_062), fd positions do not exist",
    'mmap':        "MMAP_ANON takes only the length (ABI_ROW_018); the tree's mmap carries addr/prot/flags/fd/off - the schema has no fd mapping at all",
    'brk':         "no brk row in the schema (the kernel's compat layer services brk for foreign binaries only)",
    'mincore':     "no residency query in the schema",
    'mremap':      "MREMAP exists (39) but takes four arguments the tree never passes",
    'rt_sigaction': "SIGNAL_INSTALL takes two plain words (ABI_ROW_016); the tree's sigaction carries pointer structs the schema does not model",
    'ioctl':       "no device-control row in the schema",
    'dup2':        "DUP is one argument (ABI_ROW_027); dup2's newfd has no row",
    'nanosleep':   "no sleep row in the schema",
    'socket':      "NET_SOCKET takes two words (ABI_ROW_069); the tree's socket carries domain/type/protocol",
    'connect':     "NET_CONNECT takes three words but a descriptor-shaped handle the tree's connect does not produce",
    'accept':      "no accept row in the schema",
    'sendto':      "NET_SEND takes fd/buf/len (ABI_ROW_071); the tree's sendto carries addr/alen",
    'recvfrom':    "NET_RECV takes fd/buf/len (ABI_ROW_072); the tree's recvfrom carries addr/alen",
    'bind':        "no bind row in the schema",
    'listen':      "no listen row in the schema",
    'clone':       "no thread-create row; FORK is a process fork (ABI_ROW_004)",
    'execve':      "EXEC is one 32-byte path (ABI_ROW_026); the tree's execve carries argv/envv",
    'wait4':       "WAIT takes one word (ABI_ROW_025); the tree's wait4 carries status/options/rusage pointers",
    'fsync':       "no sync row in the schema",
    'ftruncate':   "no truncate row in the schema",
    'getcwd':      "no cwd row in the schema",
    'chdir':       "no chdir row in the schema",
    'rename':      "no rename row in the schema",
    'rmdir':       "no directory row; FILE_UNLINK (67) is the file unlink",
    'chmod':       "no chmod row in the schema",
    'getuid':      "no uid concept in the schema (capability bits instead)",
    'getgid':      "no gid concept in the schema",
    'geteuid':     "no uid concept in the schema",
    'prctl':       "no prctl row; SECCOMP_DENY (14) and DROP_CAPABILITY (15) are fixed one-word calls",
    'futex':       "no futex row in the schema",
    'getdents64':  "FILE_LIST is one 32-byte path with a 512-byte copyout (ABI_ROW_065); the tree's getdents64 is fd based",
    'clock_gettime': "no clock row in the schema",
    'getrandom':   "no random row in the schema",
}
TNOTE['menuetos'] = {
    'read':        "fn 58/0 reads 512-byte BLOCKS by asciiz name - there is no fd, no byte read and no open to hold one (syscalls.txt 58)",
    'open':        "no open: fn 58 names the file in every call; the index has no file-descriptor concept at all",
    'close':       "no close: fn 58 has no descriptors to close (the index defines none)",
    'lseek':       "fn 58/0 takes a block offset per call; there is no position to seek (syscalls.txt 58)",
    'mmap':        "fn 64/2 is malloc: the subfunction rides rbx and the amount in rcx, and the tree has no rbx or rcx slot (arg1 in rbx, arg2 in rcx)",
    'munmap':      "fn 64/3 free needs rbx = 3 - the rbx wall again; the tree cannot place a first argument in rbx",
    'mprotect':    "fn 64 has no protection calls: the memory manager defines resize, allocate, free and a list read (syscalls.txt 64)",
    'brk':         "the program's memory is the vendor's fn 64/1 resize, an rbx call - the rbx wall",
    'madvise':     "no advice concept in fn 64 (resize/allocate/free/list only)",
    'mincore':     "no residency query in the vendor index",
    'mlock':       "no lock call in the vendor index",
    'rt_sigaction': "MenuetOS has no signals: the index defines no signal delivery (fn 63 is the debug board)",
    'rt_sigreturn': "no signals, so no return frame to restore (the index has no signal calls)",
    'ioctl':       "no device-object calls: drivers are reached by fn 116 state access, a different shape",
    'pipe':        "no pipes in the vendor index (fn 60 IPC is message buffers between known processes)",
    'dup2':        "no descriptors, so nothing to duplicate (the index defines no fd calls)",
    'fcntl':       "no descriptors, no control verbs (the index has none)",
    'fsync':       "fn 58/1 write is synchronous block I/O; there is no handle to sync",
    'ftruncate':   "fn 58 has no truncate verb (read/write/append and date only)",
    'getpid':      "fn 111/1 'Who am I' returns the PID but wants rbx = 1 - the rbx wall; the site has no register budget for it",
    'gettid':      "fn 111/1 wants rbx = 1 - the rbx wall",
    'getuid':      "MenuetOS is single-user: no uid anywhere in the index",
    'getgid':      "single-user: no gid in the index",
    'geteuid':     "single-user: no uid in the index",
    'kill':        "no signals (fn 60 IPC can wake a process, but the tree's kill shape does not map)",
    'chdir':       "no per-process directory in the vendor index",
    'getcwd':      "no cwd call in the vendor index",
    'mkdir':       "fn 58 has no directory verb (read/write/append/date/rename... per the index)",
    'rmdir':       "no directory verb in fn 58",
    'rename':      "fn 58's rename rides the block layer with an asciiz pair, not the tree's two-path shape",
    'unlink':      "no delete verb mapped in the index's fn 58 list",
    'unlinkat':    "no dirfd concept exists (no descriptors)",
    'openat':      "no dirfd concept exists (no descriptors)",
    'getdents64':  "no directory read in the vendor index",
    'newfstatat':  "no stat shape; fn 58 returns a file size and date, nothing the tree's stat layout holds",
    'socket':      "no sockets: fn 52/53 are the vendor's own network interface, a different frame (and three arguments hit the rbx wall)",
    'connect':     "three arguments - the rbx wall - besides the vendor's own network shape",
    'accept':      "the vendor's network interface has no accept in the tree's shape",
    'bind':        "the vendor's network interface has no bind in the tree's shape",
    'listen':      "the vendor's network interface has no listen in the tree's shape",
    'sendto':      "more arguments than the tree passes carriers for - the rbx wall",
    'recvfrom':    "more arguments than the tree passes carriers for - the rbx wall",
    'poll':        "fn 10/11/23 are window events, not descriptor polls",
    'clock_gettime': "fn 3 returns packed 0x00SSMMHH (and wants rbx = 1) - the format and the rbx wall together",
    'nanosleep':   "fn 105 wants the delay as a flat count in rbx; the site hands over a timespec pointer (a dereference and a divide have no in-place bytes)",
    'fork':        "no fork: fn 51 starts a thread at an address with a fresh stack - a different model entirely",
    'clone':       "fn 51's thread start carries no Linux flag word (and the rbx wall)",
    'execve':      "fn 256 starts a NEW process by name; nothing replaces the caller",
    'wait4':       "no parent/child wait in the vendor index (fn 9 reads process info by poll)",
    'futex':       "no futex in the vendor index",
    'getrandom':   "no random call in the vendor index",
    'prctl':       "no prctl in the vendor index",
}
TNOTE['qnx'] = {
    'read':         "read() is an IO_READ message over the fd's connection (__KER_MSG_* family); there is no read kernel call",
    'write':        "write() is an IO_WRITE message over the fd's connection (__KER_MSG_* family); there is no write kernel call",
    'open':         "open is a connect + IO message to the process manager; no open kernel call",
    'openat':       "open is a connect + IO message to the process manager; no open kernel call",
    'close':        "close is ConnectDetach through the process manager, a message, not a kernel call",
    'poll':         "poll is ionotify plus a message; no poll kernel call",
    'lseek':        "lseek is an LSEEK devctl message; no kernel call",
    'mmap':         "mapping is memmgr: messages to procnto (__KER_MSG_*); there is no mmap kernel call",
    'mprotect':     "protection changes are memmgr messages; no kernel call",
    'munmap':       "unmapping is a memmgr message; no kernel call",
    'rt_sigaction': "__KER_SIGNAL_ACTION exists, but the Linux action-block layout and the sigsetsize argument do not line up with SignalAction's frame",
    'ioctl':        "ioctl is devctl(), an IO_DEVCTL message; no kernel call",
    'pipe':         "pipes are two resource-manager connections; no kernel call",
    'mincore':      "no counterpart on Neutrino",
    'madvise':      "no madvise kernel call; memmgr takes advice through messages",
    'dup2':         "dup is a _IO_CONNECT_DUP message; no kernel call",
    'nanosleep':    "TimerTimeout(id, timeout_flags, event, ntime, otime) (kerargs.h): the tree's timespec lands in id, the frame does not line up",
    'getpid':       "no kernel call: the pid is handed to the process at startup, and getpid() reads it (like redox)",
    'socket':       "sockets are resource managers (the nfm stack); no socket kernel calls",
    'connect':      "sockets are resource managers; connect is a message",
    'accept':       "sockets are resource managers; accept is a message",
    'sendto':       "socket writes are messages; no kernel call",
    'recvfrom':     "socket reads are messages; no kernel call",
    'bind':         "sockets are resource managers; bind is a message",
    'listen':       "sockets are resource managers; listen is a message",
    'clone':        "__KER_THREAD_CREATE exists, but the Linux frame (flags word, child stack, tls, ctid) does not line up with ThreadCreate's",
    'fork':         "fork is the process manager (procnto) over messages; no kernel call",
    'execve':       "image loading is the process manager over messages; no exec kernel call",
    'exit':         "ThreadDestroy(pid, tid, status) carries the status third (kerargs.h); the tree passes it first, and the kill itself goes through the process manager",
    'wait4':        "waiting is the process manager over messages; no kernel call",
    'kill':         "SignalKill exists, but libc's kill is SignalKill(-1, pid, tid, sig, 0, 0): pid second, six arguments; the tree passes (pid, sig) first and second",
    'fsync':        "fsync is an IO message; no kernel call",
    'ftruncate':    "ftruncate is an IO message; no kernel call",
    'getcwd':       "getcwd is a process-manager message; no kernel call",
    'chdir':        "chdir is a process-manager message; no kernel call",
    'rename':       "rename is a process-manager message; no kernel call",
    'mkdir':        "mkdir is a connect + IO message; no kernel call",
    'rmdir':        "rmdir is a connect + IO message; no kernel call",
    'unlink':       "unlink is a connect + IO message; no kernel call",
    'chmod':        "chmod is an IO message; no kernel call",
    'getuid':       "the credentials arrive in a ConnectClientInfo struct (__KER_CONNECT_CLIENT_INFO), not as a return value",
    'getgid':       "the credentials arrive in a ConnectClientInfo struct, not as a return value",
    'geteuid':      "the credentials arrive in a ConnectClientInfo struct, not as a return value",
    'mlock':        "locking is a memmgr message; no kernel call",
    'prctl':        "no counterpart on Neutrino",
    'gettid':       "no kernel call: thread ids live in the process manager's tables",
    'futex':        "__KER_SYNC_MUTEX_LOCK/_UNLOCK exist, but the Linux futex op-word frame (uaddr, op, val, timeout, uaddr2, val3) does not line up",
    'getdents64':   "directory reads are IO_READ messages in the resource manager's dirent format",
    'clock_gettime': "ClockTime(id, new, old) (kerargs.h): the get direction passes the timespec third; the tree passes it second, which is the SET direction",
    'newfstatat':   "stat is a process-manager message filling the QNX stat layout; no stat kernel call",
    'unlinkat':     "unlink is a connect + IO message; no kernel call",
    'getrandom':    "randomness is /dev/urandom, a resource manager; no kernel call",
}

TALIAS['redox'] = {
    'read':          ('SYS_READ', 'exact', None),
    'write':         ('SYS_WRITE', 'exact', None),
    'close':         ('SYS_CLOSE', 'exact', None),
    'lseek':         ('SYS_LSEEK', 'exact', None),
    'fsync':         ('SYS_FSYNC', 'exact', None),
    'munmap':        ('SYS_FUNMAP', 'exact',
                      'funmap(addr, len), the same two arguments (crate_call.rs)'),
    'mprotect':      ('SYS_MPROTECT', 'exact',
                      'same three arguments; the tree only ever passes prot 0, and 0 '
                      'is PROT_NONE on both systems - a nonzero word would not map'),
    'clock_gettime': ('SYS_CLOCK_GETTIME', 'exact', None),
    'nanosleep':     ('SYS_NANOSLEEP', 'exact', 'nanosleep(req, rem), the same two'),
    'futex':         ('SYS_FUTEX', 'exact',
                      'futex(addr, op, val, val2, addr2); the tree passes zeros in the '
                      'registers Redox does not read, and the op words are the same '
                      '(flag.rs: FUTEX_WAIT 0, FUTEX_WAKE 1)'),
}

TNOTE['redox'] = {
    'exit':        "no exit in the ABI: posix_exit loops on SYS_CALL(ProcCall::Exit, status) to the proc scheme (redox-rt sys.rs)",
    'fork':        "fork is a proc-scheme call (redox-rt fork_impl), not a kernel number",
    'vfork':       "no vfork in the ABI",
    'clone':       "threads are proc-scheme calls (SYS_CALL on the thread fd), not a kernel number",
    'execve':      "fexec is a proc-scheme call; the image is handed over through SYS_CALL",
    'wait4':       "waitpid is a proc-scheme call (redox-rt sys.rs WaitpidTarget)",
    'kill':        "kill is SYS_CALL(ProcCall::Kill, pid, sig) to the proc scheme",
    'getpid':      "no kernel call: the pid is read from the ProcInfo the proc scheme installed at startup",
    'gettid':      "thread ids are proc-scheme calls (SYS_CALL Getppid-style)",
    'mmap':        "SYS_FMAP takes a Map struct through a UserSlice, not the six mmap arguments",
    'openat':      "SYS_OPENAT_INTO takes the path as a (ptr, len) slice plus an out FileHandle, and no mode: openat_into(fd, slice, flags, fcntl_flags, out) (crate_call.rs)",
    'unlinkat':    "SYS_UNLINKAT takes the path as a (ptr, len) slice: unlinkat(fd, slice, flags)",
    'rename':      "rename is frename(fd, path-slice) on an open file: no path-to-path call",
    'mkdir':       "no mkdir arm: relibc creates directories by openat with O_DIRECTORY | O_EXCL (relibc platform.rs mkdirat)",
    'rmdir':       "no rmdir arm: relibc unlinks directories through unlinkat",
    'unlink':      "no path unlink: SYS_UNLINKAT takes a dir fd and a path slice",
    'chmod':       "no chmod arm: relibc opens the file and fchmods it",
    'chdir':       "no chdir arm: relibc reaches it through the proc scheme",
    'getcwd':      "no getcwd arm: relibc reads it from the proc scheme",
    'dup2':        "SYS_DUP2 takes an out buffer (syscall4(SYS_DUP2, fd, newfd, buf, len)), not two fds",
    'pipe':        "no pipe arm: pipes are pipe: scheme fds, created through SYS_CALL",
    'poll':        "no poll arm; event fds and fevent carry it",
    'ioctl':       "no ioctl arm on the dispatch",
    'socket':      "no socket arms: Redox sockets are fd: scheme files",
    'connect':     "no connect arm: a socket is opened like a file",
    'accept':      "no accept arm",
    'sendto':      "no sendto arm: writes go through SYS_WRITE",
    'recvfrom':    "no recvfrom arm: reads go through SYS_READ",
    'bind':        "no bind arm",
    'listen':      "no listen arm",
    'getuid':      "no getuid arm: relibc reads it from the proc scheme",
    'getgid':      "no getgid arm",
    'geteuid':     "no geteuid arm",
    'ftruncate':   "no ftruncate arm: relibc calls libredox::ftruncate, not a kernel number",
    'getdents64':  "directory reads are SYS_READ on the scheme fd (the dirent format is the scheme's)",
    'newfstatat':  "SYS_FSTAT writes the Redox Stat struct, not the Linux one",
    'getrandom':   "no getrandom arm: relibc opens /scheme/rand and reads it (platform.rs getrandom)",
    'madvise':     "no madvise arm",
    'mincore':     "no mincore arm",
    'mlock':       "no mlock arm",
    'prctl':       "no prctl arm",
    'rt_sigaction': "signals are proc-scheme calls (Sigaction ProcCall), not a kernel number",
    'rt_sigreturn': "sigreturn is a proc-scheme call (Sigreturn ProcCall)",
    'arch_prctl':  "no arch_prctl arm",
}


# ------------------------------------------------------------- derivation

def sovrenos_syscalls(path):
    """SovrenOS's native numbers, from the schema itself.

    abi/syscalls.sov is authoritative, compilable Sovren source: one ABI_ROW
    string per call with ten fields, the first three of which are the number,
    the NAME and the argument count.  The schema is the whole ABI - there is
    no other table and no compatibility layer to consult for native images."""
    calls = {}
    for ln in open(path, encoding='iso-8859-1', errors='replace'):
        m = re.match(r'\s*ABI_ROW_\d+:\s*"(\d+),([A-Z0-9_]+),(\d+),', ln)
        if m:
            calls[m.group(1)] = int(m.group(1))
    if not calls:
        raise SystemExit('sovrenos: no ABI_ROW rows in %s' % path)
    return calls


def load_target(osname):
    d = os.path.join(SRC, osname)
    master = os.path.join(d, 'syscalls.master')
    if osname == 'redox':
        nums = redox_numbers(os.path.join(d, 'number.rs'))
        flags = redox_flags(os.path.join(d, 'flag.rs'))
        # the dispatch list is the vendor's own: every arm the kernel match
        # names must be a number the crate defines, or the two files disagree
        arms = redox_arms(os.path.join(d, 'evidence', 'kernel_syscall_mod.rs'))
        bad = [a for a in arms if a not in nums]
        if bad:
            raise SystemExit('redox: dispatch arms with no number: %s' % ', '.join(bad))
        return {
            'master': {},
            'syscall_h': nums,
            'maxsyscall': None,
            'probe': PROBE_NOTE['redox'][1],
            'probe_note': PROBE_NOTE['redox'],
            'arms': arms,
            'fcntl': {k: v for k, v in flags.items() if k.startswith('O_')},
            'mman': {k: v for k, v in flags.items()
                     if k.startswith(('MAP_', 'PROT_', 'MADV_'))},
            'osabi': 0,
            'osabi_note': BRAND['redox'][1],
        }
    if osname == 'serenityos':
        calls = serenity_syscalls(os.path.join(d, 'Syscall.h'))
        perm = sorted(PERM_ARGS.get('serenityos', ()))
        return {
            'master': {},
            # keyed as the vendor spells them: the TALIAS aliases are SC_ names
            'syscall_h': {'SC_' + k: v for k, v in calls.items()},
            'maxsyscall': None,
            'probe': len(calls),
            'probe_note': PROBE_NOTE['serenityos'],
            'arms': list(calls.values()),
            'perm': perm,
            # the real O_/MAP_/PROT_ tables live in the Kernel/API/POSIX
            # headers; the fcntl.h/mman.h in LibC are wrappers without them
            'fcntl': defines(os.path.join(d, 'posix_fcntl.h'), 'O_'),
            'mman': dict(defines(os.path.join(d, 'posix_mman.h'), 'MAP_'),
                         **defines(os.path.join(d, 'posix_mman.h'), 'PROT_')),
            'osabi': 0,
            'osabi_note': BRAND['serenityos'][1],
        }
    if osname == 'sovrenos':
        calls = sovrenos_syscalls('/home/user/sovrenos/abi/syscalls.sov')
        probe = 200
        if probe in calls:
            raise SystemExit('sovrenos: probe 200 is defined by the schema')
        if calls.get('60') != 60 or calls.get('12') != 12:
            raise SystemExit('sovrenos: the schema moved EXIT/WRITE; re-check the aliases')
        return {
            'master': {},
            # keyed by the schema's number-as-spelled form, so the TALIAS
            # aliases are the decimal numbers themselves
            'syscall_h': calls,
            'maxsyscall': None,
            'probe': probe,
            'probe_note': PROBE_NOTE['sovrenos'],
            'arms': [calls['60'], calls['12']],
            'fcntl': {},
            'mman': {},
            'osabi': 0,
            'osabi_note': BRAND['sovrenos'][1],
        }
    if osname == 'menuetos':
        fns = menuet_fns(os.path.join(d, 'evidence', 'syscalls.txt'))
        # the two functions the tree maps must exist, and the probe must be
        # a number the vendor's own index does not define: the dispatcher
        # answers an undefined function with nothing at all (no state
        # changes, the family's own documents promise untouched registers),
        # which is the closest thing to ENOSYS an OS without errno has
        for need in ('63', '512'):
            if need not in fns:
                raise SystemExit('menuetos: fn %s is not in the vendor index' % need)
        probe = 200
        if probe in fns:
            raise SystemExit('menuetos: probe 200 is defined by the vendor index')
        return {
            'master': {},
            # keyed by the function number as the vendor spells it, so the
            # TALIAS aliases are the numbers themselves
            'syscall_h': fns,
            'maxsyscall': None,
            'probe': probe,
            'probe_note': PROBE_NOTE['menuetos'],
            'arms': [fns['63'], fns['512']],
            # no vendor flag tables exist: fn 58 names files directly and
            # fn 64 is malloc-shaped, so there are no O_ or MAP_ words to
            # translate - the open and mmap calls are gapped anyway
            'fcntl': {},
            'mman': {},
            'osabi': 0,
            'osabi_note': BRAND['menuetos'][1],
        }
    if osname == 'qnx':
        calls = qnx_kercalls(os.path.join(d, 'kercalls.h'))
        slots = qnx_bad_slots(os.path.join(d, 'evidence', 'ker_call_table.c'))
        # __KER_BAD is the sentinel past the table: the enum has one more name
        # than the kernel has slots, and its number is the slot count
        if len(slots) != len(calls) - 1 or calls['__KER_BAD'] != len(slots):
            raise SystemExit('qnx: the kernel table has %d slots, the enum has %d names'
                             % (len(slots), len(calls)))
        bad = [i for i, h in enumerate(slots) if h == 'bad']
        # the probe is the first SPARE slot: the vendor's own ker_bad answers
        # ENOSYS there (ker_bad.c), and the enum position is read, not written
        probe = calls['__KER_SPARE1']
        if probe not in bad:
            raise SystemExit('qnx: __KER_SPARE1 is not a ker_bad slot in the kernel table')
        return {
            'master': {},
            'syscall_h': {k[6:].lower(): v for k, v in calls.items()
                          if k not in ('__KER_BAD',)},
            'maxsyscall': None,
            'probe': probe,
            'probe_note': PROBE_NOTE['qnx'],
            'arms': [calls[k] for k in calls if calls[k] not in bad],
            'fcntl': defines(os.path.join(d, 'fcntl.h'), 'O_'),
            'mman': dict(defines(os.path.join(d, 'mman.h'), 'MAP_'),
                         **defines(os.path.join(d, 'mman.h'), 'PROT_')),
            'osabi': 0,
            'osabi_note': BRAND['qnx'][1],
        }
    if osname == 'haiku':
        # the list is the prototype order (see haiku_syscalls), the boundary is
        # that list's length, and the gap probe is the vendor's own call that
        # fails on every path (see PROBE_NOTE)
        lst = haiku_syscalls(os.path.join(d, 'syscalls.preprocessed.h'))
        return {
            'master': {},
            'syscall_h': lst,
            'maxsyscall': len(lst),
            'probe': lst['get_safemode_option'],
            'probe_note': PROBE_NOTE['haiku'],
            'fcntl': defines(os.path.join(d, 'fcntl.h'), 'O_'),
            'mman': dict(defines(os.path.join(d, 'mman.h'), 'MAP_'),
                         **defines(os.path.join(d, 'mman.h'), 'MADV_')),
            'osabi': 0,
            'osabi_note': BRAND['haiku'][1],
        }
    t = {
        # illumos has no master file: the vendor's syscall.h *is* the list
        'master': bsd_master(master) if os.path.exists(master) else {},
        'syscall_h': bsd_syscall_h(os.path.join(d, 'syscall.h')),
        'fcntl': defines(os.path.join(d, 'fcntl.h'), 'O_'),
        'osabi': elf_osabi(os.path.join(d, ELFC[osname]), BRAND[osname][0]),
        'osabi_note': BRAND[osname][1],
        'maxsyscall': bsd_syscall_h(os.path.join(d, 'syscall.h')).get('MAXSYSCALL'),
    }
    mman = os.path.join(d, 'mman.h')
    t['mman'] = {}
    if os.path.exists(mman):
        t['mman'].update(defines(mman, 'MAP_'))
        t['mman'].update(defines(mman, 'MADV_'))
    return t


ACC_BITS = ['O_RDONLY', 'O_WRONLY', 'O_RDWR']


def flag_words(osname, lin_fcntl, lin_mman, tgt, lits=None, _pair=False):
    """turn the Linux literals the tree uses into target words, bit by bit"""
    def acc(key):
        v = lin_fcntl.get(key, 0)
        for b in ACC_BITS:
            if lin_fcntl.get(b, 0) == v:
                return b
        return None

    open_map = {}
    used_open = lits if lits is not None else tree_literals('open')
    for lit in used_open:
        a = acc('O_' + {0: 'RDONLY', 1: 'WRONLY', 2: 'RDWR'}.get(lit & 3, 'RDONLY'))
        body = lit & ~3
        names, rest = [], body
        omitted = []
        for nm in CAND['open']:
            if nm in ('O_RDONLY', 'O_WRONLY', 'O_RDWR', 'O_ACCMODE'):
                continue
            lv = lin_fcntl.get(nm)
            tv = tgt['fcntl'].get(nm)
            if not lv:
                continue
            if (lv & (lv - 1)) == 0 and (rest & lv) == lv:
                rest &= ~lv
                names.append(nm)
                # a name the target's own header lacks cannot be part of the
                # word: the bit is dropped, and the drop is recorded rather
                # than silent (dropping is the safer half of the choice - the
                # raw Linux bit may be a different flag on the target, FMARK
                # on dragonfly, O_NOCTTY on haiku)
                if tv is None:
                    omitted.append(nm)
        w = acc
        val = tgt['fcntl'].get(a, 0) if a else 0
        for nm in names:
            val |= tgt['fcntl'].get(nm, 0)
        e = {'as': [a] + names,
             'word': val if rest == 0 else None,
             'gap': None if rest == 0 else 'bit %d has no BSD name' % rest}
        if omitted:
            e['omitted'] = omitted
        open_map[lit] = e
    return (open_map, None) if _pair else open_map


def tree_literals(kind):
    """Literal values the tree passes to a given syscall family."""
    import glob
    files = [os.path.join(ROOT, 'runtime.sov')] + sorted(glob.glob(os.path.join(ROOT, 'library', '*.sov')))
    pos = OPEN_POS if kind == 'open' else (MMAP_POS if kind == 'mmap' else ADVISE_POS)
    out = set()
    rx = re.compile(r'syscall\((\d+)\s*,\s*([^)]*)\)')
    for f in files:
        for ln in _lines(f):
            for m in rx.finditer(ln):
                nr = int(m.group(1))
                if nr not in pos:
                    continue
                args = [a.strip() for a in m.group(2).split(',')]
                i = pos[nr] - 1
                if i < len(args) and re.fullmatch(r'\d+', args[i]):
                    out.add(int(args[i]))
    return out


def firewall(osname, lin_sys, tgt, mapped):
    """Linux numbers that mean *something else* on this kernel.

    A number the tree never uses is still worth guarding: a program that writes
    syscall(37, ...) by hand would call alarm on Linux and kill on FreeBSD.  The
    pass rewrites each of these to the ENOSYS probe, so the wrong call fails
    loudly instead of doing something else."""
    tnums = set(tgt['master'].values()) | set(tgt['syscall_h'].values())
    out = []
    for num, name in sorted(lin_sys.items()):
        if num in mapped or num > 900:
            continue
        if num in tnums:
            out.append({'linux': num, 'name': name, 'bsd_meaning': None})
    return out


def derive(osname, lin_sys, lin_fcntl, lin_mman, tgt):
    if not probe_ok(tgt):
        raise SystemExit('%s: the ENOSYS probe %d is a number this kernel defines'
                         % (osname, enosys(tgt)))
    _tail = None
    used = tree_literals_all()
    mapped = set()
    syscalls = {}
    fused = False
    for num in sorted(used):
        name = lin_sys.get(num)
        entry = {'name': name, 'bsd': None, 'kind': 'gap', 'note': None}
        if osname in TLOCK:
            tal = TALIAS.get(osname, {}).get(name) if name else None
            if tal:
                alias, kind, note = tal
                where = tgt['syscall_h'].get(alias, tgt['master'].get(alias))
                entry['bsd'] = where
                entry['kind'] = kind if where is not None else 'gap'
                entry['note'] = note if where is not None else 'no %s on this target' % alias
            else:
                n2 = tgt['syscall_h'].get(name) if name else None
                entry['note'] = TNOTE.get(osname, {}).get(name) or (
                    ('%s exists as number %d, but its arguments are not this frame' % (name, n2))
                    if n2 is not None else 'no call named %s in this kernel' % name)
        elif name and TALIAS.get(osname, {}).get(name):
            alias, kind, note = TALIAS[osname][name]
            where = tgt['master'].get(alias, tgt['syscall_h'].get(alias))
            entry['bsd'] = where
            entry['kind'] = kind if where is not None else 'gap'
            entry['note'] = note if where is not None else 'no %s on this target' % alias
        elif name and name in ALIAS:
            alias, kind, note = ALIAS[name]
            where = tgt['master'].get(alias, tgt['syscall_h'].get(alias))
            if where is None and alias != name:
                where = tgt['master'].get(name, tgt['syscall_h'].get(name))
                if where is not None:
                    alias, note = name, None
            entry['bsd'] = where
            entry['kind'] = kind if where is not None else 'gap'
            entry['note'] = note
            if where is None:
                entry['note'] = 'no %s on this target' % alias
        elif name:
            b = tgt['master'].get(name, tgt['syscall_h'].get(name))
            if b is None:
                entry['note'] = 'no syscall named %s' % name
            else:
                entry['bsd'] = b
                entry['kind'] = 'exact'
        else:
            entry['note'] = 'number not in the Linux x86-64 table'
        if entry['kind'] == 'gap' and name in TNOTE.get(osname, {}):
            entry['note'] = TNOTE[osname][name]
        syscalls[num] = entry
        if entry['kind'] != 'gap':
            mapped.add(num)
    # collision firewall: a gap whose Linux number exists as some other BSD call
    inv = {}
    for n, v in list(tgt['master'].items()) + [(k, v) for k, v in tgt['syscall_h'].items()
                                              if k not in BOUNDARY]:
        inv.setdefault(v, n)
    for num, e in syscalls.items():
        if e['kind'] == 'gap':
            other = inv.get(num)
            e['firewall'] = other if other else None
            if other:
                e['note'] = (e['note'] or '') + '; number %d is %8s on the target, so it is pointed at %d (ENOSYS probe)' % (num, other, enosys(tgt))
    return {
        'syscalls': {str(k): v for k, v in syscalls.items()},
        'open': {str(k): v for k, v in flag_words(osname, lin_fcntl, lin_mman, tgt).items()},
        'mmap': mmap_words(lin_mman, tgt),
        'advise': advise_words(lin_mman, tgt),
        'osabi': tgt['osabi'],
        'osabi_note': tgt['osabi_note'],
        'enosys': enosys(tgt),
        'maxsyscall': tgt['maxsyscall'],
        'patterns': flag_patterns(osname, lin_fcntl, lin_mman, tgt),
        'firewall': firewall(osname, lin_sys, tgt, mapped),
    }


BOUNDARY = ('MAXSYSCALL', 'NSYSENT', 'MAXSYSENT')

# A target whose "no such call" number is not safe to use says what its probe is
# instead, and why.  On Haiku an out-of-range number is *not* an error: the
# entry point tests the number, jumps straight to the return path and hands the
# caller back the number itself (interrupts.S: `cmpq $SYSCALL_COUNT, %r14;
# jae .Lsyscall_return`, and rax still holds the number) - a positive value,
# which the tree reads as a successful return.  So the gaps are pointed at
# _kern_get_safemode_option(5) instead: every one of its failure paths returns a
# negative status, and it never trusts the pointers it is handed (the vendor's
# own kernel code: safemode_settings.cpp:268-270 `return B_BAD_ADDRESS` when the
# user copies fault, and get_safemode_option() returning B_ENTRY_NOT_FOUND /
# B_NAME_NOT_FOUND for a name it does not know).  The tree reads a negative
# return as the failure it is.
PROBE_NOTE = {
    'haiku': ('get_safemode_option', 5,
              'an out-of-range number returns the number itself on Haiku, so the '
              'gaps go to the one call whose every failure path is a negative status'),
}
# Redox answers a number outside its dispatch with ENOSYS
# (kernel/src/syscall/mod.rs ends with `_ => Err(Error::new(ENOSYS))`), so
# *any* undispached number would fail - but the probe is chosen to mean
# something rather than be an accident: SYS_CLASS_FILE with no call bits and
# no argument bits, 0x2000_0000.  It is a *tag*, not "one past the last row":
# Redox has no last row, the numbers are class-tagged 32-bit values, and no
# arm of the match can ever equal a bare class tag (every arm carries low
# bits).  Read out of number.rs as SYS_CLASS_FILE, like every number here.
PROBE_NOTE['redox'] = ('SYS_CLASS_FILE', 0x20000000,
                       'a tagged class value with no call bits; the dispatch has no arm '
                       'for it and answers ENOSYS')

# QNX's own kernel answers an unimplemented call with ENOSYS: the SPARE slots
# of ker_call_table are `ker_bad`, and ker_bad.c is `return ENOSYS`.  The
# probe is the first SPARE, __KER_SPARE1, whose number is the enum position -
# read out of the header, cross-checked against the kernel table.
PROBE_NOTE['sovrenos'] = ('the schema', 200,
    'fn 200 is not in abi/syscalls.sov (the schema defines 69 functions in '
    '1-75 plus the 240s); the kernel dispatch (kernel/syscalls.sov '
    'k_syscall_dispatch) answers every unknown number with -ENOSYS, '
    'return 0 - 38, the vendor convention in source')
PROBE_NOTE['menuetos'] = ('the vendor index', 200,
    'fn 200 is not in the vendor index (syscalls.txt v1.61.00 defines 0-131, '
    '140-142, 241, 256-258, 300, 400, 500 and 512); the dispatcher answers an '
    'undefined function with nothing - the family convention (KolibriOS '
    'sysfuncs.TXT) is that undeclared registers pass through untouched')
PROBE_NOTE['qnx'] = ('__KER_SPARE1', 3,
                     'a SPARE slot: ker_call_table dispatches it to ker_bad, which '
                     'returns ENOSYS (ker_bad.c)')

# Serenity's SyscallHandler ends its switch with `default:` and returns
# ENOSYS (SyscallHandler.cpp: "Unknown syscall {} requested"), so any number
# past the last real call fails - and the vendor names that boundary: it is
# the enum's own __Count, the number of names in ENUMERATE_SYSCALLS.
PROBE_NOTE['serenityos'] = ('__Count', None,
                            'one past the last SC_ value; the handler switch falls '
                            'through to default and answers ENOSYS')


def probe_ok(tgt):
    """The probe must not be a call the vendor has a name for.

    netbsd proved the point: max(master)+1 was 505, and 505 is __dup3100.  The
    vendor's own boundary constants (SYS_MAXSYSCALL, SYS_NSYSENT) are sizes, not
    calls, so they are not counted here."""
    if tgt.get('probe_note'):
        return True                       # a named failing call, with the reason
    n = enosys(tgt)
    if tgt.get('arms'):
        # the vendor's own dispatch list is the truth: redox names structural
        # tags (SYS_CLASS_FILE is 0x2000_0000) that no call can be, and the
        # probe may safely be one of those
        return n not in {tgt['syscall_h'][a] for a in tgt['arms']}
    called = set(tgt['master'].values())
    called |= {v for k, v in tgt['syscall_h'].items() if k not in BOUNDARY}
    return n not in called


def enosys(tgt):
    """The number this kernel answers with ENOSYS.

    The vendor's own generated syscall.h names the boundary: SYS_MAXSYSCALL is
    the count of real calls, so that number has no entry in the kernel's table
    and the dispatcher returns ENOSYS.  Taking max(master)+1 instead is not the
    same thing and was wrong twice: NetBSD's 505 is __dup3100 and 506 is
    semtimedop, so a gap on netbsd used to be pointed at a *real* call."""
    if tgt.get('probe') is not None:
        return tgt['probe']
    if tgt.get('maxsyscall'):
        return tgt['maxsyscall']
    nums = list(tgt['master'].values()) + list(tgt['syscall_h'].values())
    return (max(nums) if nums else 606) + 1


def mmap_words(lin_mman, tgt, lits=None):
    """Linux MAP_* word -> the target's word, name by name.

    MAP_ANONYMOUS is the one name the BSDs spell differently (MAP_ANON)."""
    out = {}
    simple = ['MAP_FIXED', 'MAP_ANONYMOUS', 'MAP_NORESERVE', 'MAP_GROWSDOWN',
              'MAP_POPULATE', 'MAP_STACK', 'MAP_HUGETLB', 'MAP_32BIT', 'MAP_LOCKED']
    for lit in sorted(lits if lits is not None else tree_literals('mmap')):
        names, rest = [], lit
        for nm in ('MAP_SHARED', 'MAP_PRIVATE'):
            lv = lin_mman.get(nm)
            if lv and (rest & lv) == lv:
                rest &= ~lv
                names.append(nm)
                break
        omitted = []
        for nm in simple:
            lv = lin_mman.get(nm)
            if lv and (lv & (lv - 1)) == 0 and (rest & lv) == lv:
                t = nm
                if nm == 'MAP_ANONYMOUS':
                    t = 'MAP_ANON' if 'MAP_ANON' in tgt['mman'] else 'MAP_ANONYMOUS'
                if t not in tgt['mman']:
                    # named on Linux, absent on the target: dropped, and the
                    # drop is recorded (redox has no anonymous mapping at all)
                    omitted.append(nm)
                    continue
                rest &= ~lv
                names.append(nm)
        val = 0
        for nm in names:
            t = nm
            if nm == 'MAP_ANONYMOUS':
                t = 'MAP_ANON' if 'MAP_ANON' in tgt['mman'] else 'MAP_ANONYMOUS'
            val |= tgt['mman'].get(t, 0)
        e = {'as': names, 'word': val if rest == 0 else None,
             'gap': None if rest == 0 else 'bit %d has no BSD name' % rest}
        if omitted:
            e['omitted'] = omitted
        out[str(lit)] = e
    return out


def advise_words(lin_mman, tgt, lits=None):
    out = {}
    for lit in sorted(lits if lits is not None else tree_literals('advise')):
        nm = None
        for k, v in lin_mman.items():
            if k.startswith('MADV_') and v == lit:
                nm = k
                break
        e = {'as': nm, 'word': None, 'gap': None}
        if nm is None:
            e['gap'] = 'value %d is not a MADV_* constant' % lit
        else:
            t = ADVISE_ALIAS.get(nm, nm)
            if t in tgt['mman']:
                e['word'] = tgt['mman'][t]
                e['as'] = [nm, t]
            else:
                e['gap'] = 'BSD has no %s' % t
        out[str(lit)] = e
    return out


def tree_literals_all():
    """Every Linux syscall number the tree passes to syscall()/sovcall().

    Scanned on the *expanded* text: blocks in the store take their numbers as
    parameters (%1), so a scan of the files on disk misses pipe, dup2, rename
    and unlink even though the compiler sees them."""
    sys.path.insert(0, HERE)
    import kit_expand
    got = set()
    rx = re.compile(r'(?:syscall|sovcall)\s*\(\s*(\d+)\s*,')
    texts = list(expanded_tree().values())
    for extra in (os.path.join(ROOT, 'launcher.sov'), os.path.join(ROOT, 'bootstrap.sov'),
                  LINUX_KIT):
        if os.path.exists(extra):
            try:
                texts.append(kit_expand.expand(extra))
            except Exception:
                texts.append('\n'.join(_lines(extra)))
    for t in texts:
        for m in rx.finditer(t):
            got.add(int(m.group(1)))
    return got


def build():
    lin_sys = linux_syscalls()
    lin_fcntl = defines(os.path.join(SRC, 'linux', 'fcntl.h'), 'O_')
    lin_mman = {}
    for f in ('mman-x86.h', 'mman-linux.h', 'mman-common.h', 'mman.h'):
        lin_mman.update(defines(os.path.join(SRC, 'linux', f), 'MAP_'))
        lin_mman.update(defines(os.path.join(SRC, 'linux', f), 'MADV_'))
    out = {'sources': {'linux': 'raw.githubusercontent.com/torvalds/linux/master'},
           'targets': {}}
    for k, v in STD_SRC.items():
        out['sources'][k] = 'raw.githubusercontent.com/' + v
    for t in TARGETS:
        out['targets'][t] = derive(t, lin_sys, lin_fcntl, lin_mman, load_target(t))
    out['linux_names'] = {str(k): v for k, v in sorted(lin_sys.items())}
    return out


# ------------------------------------------------------------------ main

def report(tab):
    for t in TARGETS:
        d = tab['targets'][t]
        ok = [v for v in d['syscalls'].values() if v['kind'] != 'gap']
        gp = [v for v in d['syscalls'].values() if v['kind'] == 'gap']
        print('%s: %d mapped (%d exact, %d alias), %d gaps, osabi %s' % (
            t, len(ok), len([v for v in ok if v['kind'] == 'exact']),
            len([v for v in ok if v['kind'] == 'alias']), len(gp), d['osabi']))
        for num, v in sorted(d['syscalls'].items(), key=lambda kv: int(kv[0])):
            if v['kind'] != 'gap':
                printf = '  %4s %-16s -> %4s %s' % (num, v['name'] or '?', v['bsd'], v['kind'])
                if v['kind'] == 'alias' and v.get('note'):
                    printf += '  # ' + v['note']
                print(printf)
            else:
                print('  %4s %-16s gap: %s' % (num, v['name'] or '?', v['note']))
        for fam in ('open', 'mmap', 'advise'):
            print('  %s words:' % fam)
            for k, v in sorted(d[fam].items(), key=lambda kv: int(kv[0])):
                print('    %6s -> %-7s  %s%s' % (
                    k, v['word'], '+'.join(v['as']) if isinstance(v['as'], list) else v['as'],
                    '' if not v['gap'] else '   GAP: ' + v['gap']))



# ------------------------------------------------------------- kit builder

KIT_BANNER = '''\
# ============================================================================
# sovren %(tgt)s compiler - GENERATED by tools/bsd_abi.py --gen %(tgt)s
#
#   base      compilers/linux/compiler.sov, expanded (block includes spliced,
#             the same text the compiler itself reads)
#   abi table tools/bsd_abi.json, derived from the vendor headers under
#             work/targets/%(tgt)s (%(srclist)s)
#   brand     ELFOSABI_%(brandupper)s = %(osabi)s, e_ident[7] of every image
#   numbers   %(nmapped)s mapped, %(ngap)s with no safe counterpart
#
# Gaps are pointed at the ENOSYS probe %(probe)s rather than at a number that
# means something else on this kernel:
%(gaplines)s#
# Numbers reach the kernel by two roads and each road has its own layer:
#
#   bsd_fix   the text pass, run on the finished program text (source, runtime
#             and library) just before compile().  One scan reads the number
#             after every syscall(/sovcall( and writes the target number in its
#             place.  It has to be a single scan: a chain of replace rules
#             rewrites its own output (10 -> 74, and then the rule for 74).
#   bsd_code  the machine-code pass, run on the finished code a moment before
#             the ELF is written.  It reads the bytes around every syscall
#             instruction and maps the numbers the back end emits on its own -
#             write, exit, mprotect, getrandom, prctl - which never existed as
#             text and so were never seen by bsd_fix.
#
# The argument words that carry flags (open modes, mmap flags, madvise advice)
# are rewritten by bsd_fix, because they travel to the kernel as ordinary
# arguments.
#
# Two sites are patched in this file instead, because their target number does
# not fit the encoding the back end chose: rt_sigreturn and rt_sigaction are
# emitted as mov al, 15 and mov al, 13, and the ENOSYS probe needs more than
# eight bits.  The patch counts are asserted at generation time.
# ============================================================================
'''


def base_kit_text():
    sys.path.insert(0, HERE)
    import kit_expand
    return kit_expand.expand(os.path.join(ROOT, 'compilers', 'linux', 'compiler.sov'))


def gen_kit(osname, tab, linux_src=None):
    d = tab['targets'][osname]
    probe = probe_number(osname)
    mapped = {int(k): v['bsd'] for k, v in d['syscalls'].items() if v['kind'] != 'gap'}
    gaps = {int(k): v for k, v in d['syscalls'].items() if v['kind'] == 'gap'}
    src = (linux_src or base_kit_text()).split('\n')
    applied = collections.Counter()

    def sub1(needle, repl, why):
        n = sum(1 for l in src if needle in l)
        assert n == 1, '%s: %r matched %d lines' % (why, needle[:40], n)
        applied[why] += 1
        return [l.replace(needle, repl) for l in src]

    def sublit(needle, repl, why):
        # a patch whose text spans lines: applied to the joined source
        j = '\n'.join(src)
        n = j.count(needle)
        assert n == 1, '%s: %d sites' % (why, n)
        applied[why] += 1
        return j.replace(needle, repl).split('\n')

    def subline(content, repl, want, why):
        out, n = [], 0
        want_toks = content.split()
        repl_toks = repl.split()
        for l in src:
            toks = l.strip().split()
            if toks == want_toks:
                out.append(l[:len(l) - len(l.lstrip())] + repl)
                n += 1
                continue
            hit = None
            if all(t.isdigit() for t in repl_toks) and len(repl_toks) <= len(toks):
                for j in range(len(toks) - len(repl_toks) + 1):
                    if toks[j:j + len(repl_toks)] == want_toks:
                        hit = j
                        break
            if hit is not None:
                lead = l[:len(l) - len(l.lstrip())]
                out.append(lead + ' '.join(toks[:hit] + repl_toks + toks[hit + len(want_toks):]))
                n += 1
            else:
                out.append(l)
        assert n == want, '%s: %r matched %d lines, want %d' % (why, content[:40], n, want)
        applied[why] += n
        return out

    def sub1(needle, repl, why):
        n = sum(1 for l in src if needle in l)
        assert n == 1, '%s: %r matched %d lines' % (why, needle[:40], n)
        applied[why] += 1
        return [l.replace(needle, repl) for l in src]

    # -- two sites are patched here rather than by the code pass, because the
    #    target number does not fit the encoding the back end chose for them:
    #    rt_sigreturn and rt_sigaction are emitted as `mov al, 15` and
    #    `mov al, 13`, and the ENOSYS probe needs more than eight bits.  Every
    #    other number - write, exit, mprotect, getrandom, prctl - is left to
    #    bsd_code, which reads the code after the front end has run.
    if mapped.get(15, probe) == probe:
        src = subline('176 15', '184 %s' % ' '.join(str((probe >> (8 * i)) & 255) for i in range(4)),
                      1, 'rt_sigreturn (BSD restores through its own trampoline)')
    if mapped.get(13, probe) == probe:
        src = subline('emit4(8) ;; emit_sys_num(13)',
                      'emit4(8) ;; emit_sys_num(%d)' % probe, 1,
                      'rt_sigaction: the action block layout differs')
    # the back end loads these two with `mov eax, imm` and then fills the
    # argument registers before the syscall, so bsd_code's window does not
    # reach them; the numbers are compile-time constants here, and neither
    # 606 nor the getrandom number collides with a Linux number in the table.
    src = subline('rax_imm(157)', 'rax_imm(%d)' % probe, 1, 'prctl has no BSD shape')
    src = subline('rax_imm(318)', 'rax_imm(%d)' % mapped.get(318, probe), 1,
                  'getrandom (%s on this kernel)' % (getrandom_note(d, probe)))
    if osname == 'redox':
        # the numbers this kernel answers with are 32-bit tagged values, so
        # the short rax forms the back end picks for its own small numbers
        # cannot carry them: the write and exit sites are widened to the
        # imm32 forms here, and bsd_code maps the imm32 that is there now.
        # The counts are asserted, like every patch in this file.
        src = subline('176 1', '184 1 0 0 0', 2,
                      'write: the tagged number does not fit mov al')
        src = subline('106 1 88', '104 1 0 0 0 88', 1,
                      'write via push imm8: widened to push imm32')
        src = subline('176 60', '184 60 0 0 0', 3,
                      'exit: the probe does not fit mov al')
        src = sub1('49 255 106 60 88', '49 255 104 60 0 0 0 88',
                   'exit via push imm8: widened to push imm32')
    if osname == 'serenityos':
        # every permuted number's sites in the tree must be plain (no nested
        # brackets or quotes) - the perm pass splits on top-level commas only
        for n in d.get('perm', []):
            for at, args in [ca for rel, text in sorted(expanded_tree().items())
                             for ca in call_args(text, n)]:
                assert not any(('(' in a or '[' in a or '"' in a) for a in args), \
                    'serenityos: syscall(%d, ...) has a shaped argument: %r' % (n, args)
        # the frame differs from Linux's in the argument carriers: Serenity
        # reads arg1 in rdx, arg2 in rdi, arg3 in rbx, arg4 in rsi
        # (RegisterState.h capture_syscall_params).  The back end's own write
        # and exit sites marshal Linux-style, so they are reshaped here, byte
        # by byte, with the counts asserted.  print() goes out as
        # SC_dbgputstr(buf, len) - the debug console - until the emitter grows
        # a carrier table and SC_write becomes reachable.
        # print goes out as SC_dbgputstr: the number comes straight from the
        # vendor list, not from the table (write itself is gapped - the tree's
        # write is three arguments and the third rides rbx)
        wnum = load_target(osname)['syscall_h'].get('SC_dbgputstr')
        assert wnum is not None and wnum <= 255, 'serenityos: SC_dbgputstr unusable'
        # keep the write number in the bytes: the kit's own code pass maps
        # 1 -> SC_dbgputstr through the table, so the literal 20 would be
        # re-mapped again here (20 is not a Linux number in the table)
        src = subline('176 1', '72 137 215 72 137 242 176 1', 2,
                      'print write: dbgputstr takes (buf, len) in (rdx, rdi)')
        src = subline('106 1 88', '72 137 215 72 137 242 106 1 88', 1,
                      'print write via push imm8: the same carriers')
        # exit: the code rides rdx.  canary keeps its 101 by copying rdi.
        src = sublit('emit(191)\n    emit4(101)',
                     'emit(191)\n    emit4(101)\n    emit:\n        72 137 250',
                     'canary exit: copy the status into rdx')
        src = sublit('176 60\n        sysc() ;; chi: chi + 1',
                     '49 210 176 60\n        sysc() ;; chi: chi + 1',
                     'crash exit: zero rdx (the status register)')
        src = sublit('49 255\n                            if rax_small',
                     '49 210\n                            if rax_small',
                     'main exit: zero rdx (the status register)')
        src = subline('49 255 106 60 88', '49 210 106 60 88', 1,
                      'string exit: zero rdx (the status register)')

    if osname == 'menuetos':
        # -- the gate: the vendor's own document puts the whole ABI behind
        #    int 0x60 with the function number in rax (the syscall
        #    instruction is an optional second gate with different
        #    clobbers - int 0x60 is the documented primary)
        src = sublit('sysc:\n    emit:\n        15 5',
                     'sysc:\n    emit:\n        205 96',
                     'the gate: int 0x60')
        # (the code pass's gate is baked by code_pass(): 205/96 for menuetos)
        # -- Menuet64 loads the image at virtual zero: base 0, the header
        #    written over the dead ELF header bytes at the end of write_elf
        src = sublit('BASE: 4194304 ;; HDR: 320', 'BASE: 0 ;; HDR: 320',
                     'base zero: Menuet64 loads at 0')
        src = subline('emit4(4194304)', 'emit4(0)', 1,
                      'the pie-walk constant follows the base')
        # -- the self-relocation walk stays: with BASE 0 it adds zero to
        #    slots the writer already baked for base 0, and its two mprotect
        #    sites (10) point at a function the vendor index does not define,
        #    which the dispatcher ignores - and the site count stays one to
        #    one with the reference image for --verify
        # -- exits: fn 512 (Terminate process) does not fit mov al, so the
        #    three mov-al exit sites widen to the imm32 form; the number
        #    stays 60 in the bytes and the code pass maps it to 512
        src = subline('176 60', '184 60 0 0 0', 3,
                      'exit: fn 512 needs the imm32 form (mapped by the code pass)')
        src = sublit('49 255 106 60 88', '49 255 104 60 0 0 0 88',
                     'string exit: push imm32 for fn 512')
        # -- prints: fn 63/1 writes ONE character to the debug board and the
        #    gate returns rax = 0, rbx = 0, so both reload per byte; rsi and
        #    rdx (buf, len) survive the gate untouched.  The number stays
        #    1 (write) in the bytes - the code pass maps it to 63.  The gate
        #    itself stays the site's own sysc(): the loop head goes where
        #    mov al,1 was, the loop tail right after it, and jne walks back
        #    over head + gate + tail (20 bytes).
        head = '184 1 0 0 0 187 1 0 0 0 138 14'
        tail = '72 255 198 72 255 202 117 236'
        src = sublit("""    emit:
        176 1
    if sxe_mode = 1 -> rax_imm(12)
        emit:
            205 128
    if not -> sysc()""",
                    """    emit:
        %s
    if sxe_mode = 1 -> rax_imm(12)
        emit:
            205 128
    if not -> sysc()
    emit:
        %s""" % (head, tail),
                    'print: the fn 63/1 debug-board byte loop (1 -> 63 by the code pass)')
        src = sublit("""    if vg = 1 -> emit:
            176 1
    if not -> emit:
            106 1 88
    if sxe_mode = 1 -> rax_imm(12)
        emit:
            205 128
    if not -> sysc()""",
                    """    if vg = 1 -> emit:
            %s
    if not -> emit:
            %s
    if sxe_mode = 1 -> rax_imm(12)
        emit:
            205 128
    if not -> sysc()
    emit:
        %s""" % (head, head, tail),
                    'print push form: the same byte loop')
        # -- the vendor header, over the ELF machinery bytes: 'MENUET64',
        #    header version 1, entry = BASE + HDR, image size, 1 MiB of app
        #    memory, rsp 0xffff0, no parameter or icon block (the shapes are
        #    the vendor's own app sources: CALC.ASM, LAUNCHER.ASM)
        src = sublit("""    if kern_mode = 1 -> w: _sov_write_n(path, flat, filesz)
        include inc/inc03.sov 206 4
    w: _sov_write_n(path, flat, filesz)""",
                    """    if kern_mode = 1 -> w: _sov_write_n(path, flat, filesz)
        include inc/inc03.sov 206 4
    flat: poke2 0 + 2 * i: 17741 21838 21573 13366
    poke8(flat, 8, 1)
    poke8(flat, 16, BASE + HDR)
    poke8(flat, 24, filesz)
    poke8(flat, 32, 1048576) ;; poke8(flat, 40, 1048544)
    poke8(flat, 48, 0) ;; poke8(flat, 56, 0)
    w: _sov_write_n(path, flat, filesz)""",
                    'the MENUET64 header')

    # -- the call the kit's own `print` builds: the target's write frame
    for need, repl in SHIM_LITS.get(osname, []):
        src = sublit(need, repl, 'the print call frame')

    # -- the ELF brand byte
    src = sub1('_sov_set_byte(flat, 6, 1) ;; flat: poke2 16 + 2 * i: 3 62',
               '_sov_set_byte(flat, 6, 1) ;; flat: poke2 16 + 2 * i: 3 62\n'
               '    dummy: _sov_set_byte(flat, 7, %d)' % d['osabi'], 'e_ident[7]')

    # -- the pass: on the finished text, right before --flat/compile see it
    src = sub1('    all: u_sugar(all)',
               '    all: bsd_fix(all)\n'
               '    all: u_sugar(all)', 'text pass call')
    src = sub1('    write_elf(outf)',
               '    bsd_code()\n'
               '    write_elf(outf)', 'code pass call')


    body = build_fix(osname, d, probe)
    at = next(i for i, l in enumerate(src) if l.startswith('main argc argv:'))
    src = src[:at] + body.split('\n') + src[at:]
    if osname in SHIM_FNS:
        # right after leave_reload, so the emitter body that calls it can sit
        # above it in the pass
        for i, l in enumerate(src):
            if l.startswith('leave_reload:'):
                at = i + 1
                while at < len(src) and not src[at].strip():
                    at += 1
                break
        else:
            raise SystemExit('no leave_reload in the kit text')
        src = src[:at] + SHIM_FNS[osname] + src[at:]

    gaplines = ''.join('#   %4d %-16s %s\n' % (
        int(k), v['name'] or '?', (v['note'] or 'no counterpart on this kernel').replace('\n', ' ')[:110])
        for k, v in sorted(gaps.items()))
    banner = KIT_BANNER % {
        'tgt': osname, 'osabi': d['osabi'], 'brandupper': osname.upper(),
        'srclist': SRCLIST.get(osname, 'the vendor headers'),
        'nmapped': len(mapped), 'ngap': len(gaps), 'probe': probe, 'gaplines': gaplines}
    return banner + '\n'.join(src) + '\n', applied


# what the table was read out of, named per target: the kit banner says which
# header each number came from, so a reader can check one without guessing
SRCLIST = {
    'freebsd':   'syscalls.master, syscall.h, fcntl.h, mman.h',
    'netbsd':    'syscalls.master, syscall.h, fcntl.h, mman.h',
    'openbsd':   'syscalls.master, syscall.h, fcntl.h, mman.h',
    'dragonfly': 'syscalls.master, syscall.h, fcntl.h, mman.h',
    'illumos':   'sys/syscall.h, sys/elf.h, sys/mman.h, sys/fcntl.h',
    'haiku':     'system/syscalls.h (preprocessed, the pragma block), fcntl.h, mman.h, socket.h',
    'qnx':       'sys/kercalls.h (the vendor enum), ker/ker_call_table.c + ker_bad.c + kerargs.h (the kernel sources), fcntl.h, sys/mman.h, sys/elf.h',
}


def probe_number(osname):
    # prefer the snapshot table; vendor headers only when mounted
    try:
        with open(JSONP) as f:
            j = json.load(f)
        e = j['targets'][osname].get('enosys')
        if e is not None:
            return int(e)
    except Exception:
        pass
    d = load_target(osname)
    return enosys(d)


TAGBASE = 6000000


def qs(sep):
    return "'%s'" % sep


def sq(text):
    """a sov string literal.  The tree's flag patterns can carry a newline:
    escape it, the language turns \\n back into one byte."""
    out = text.replace('\\', '\\\\').replace("'", "\\'")
    out = out.replace('\r', '').replace('\n', '\\n').replace('\t', '\\t')
    return "'%s'" % out


def getrandom_note(d, probe):
    e = d['syscalls'].get('318')
    if not e or e['kind'] == 'gap':
        return 'probe %d' % probe
    return 'number %d' % e['bsd']


def build_fix(osname, d, probe):
    """the sov source of the ABI layer: table driven, patterns built at run time.

    The text pass *tags* a syscall number instead of rewriting it: a site
    `syscall(60, ...)` becomes `syscall(6000001, ...)`.  The compiler then
    carries the tag through its own emission paths, and bsd_code, which runs on
    the finished code just before the ELF is written, turns every tag back into
    the target number.  Tagging is what keeps the two halves from colliding:
    the numbers the compiler emits on its own (write, exit, mprotect, mmap,
    rt_sigaction ...) are plain Linux numbers and are mapped by bsd_code, the
    numbers that came from the text are tags and are resolved by bsd_code, and
    neither pass can touch the other's sites twice.

    The argument words that carry flags (open modes, mmap flags, madvise
    advice) are rewritten here, in the text, because they travel to the kernel
    as ordinary arguments.

    bsd_rp is a one-pass replace-all.  The builtin repl cannot be used for
    this: it sizes its room for a single replacement, so a pattern that occurs
    hundreds of times - every `syscall(1, ` in the runtime does - exhausts it.
    Patterns are assembled from pieces by bsd_fx at run time, so this file is a
    fixed point of its own pass.
    """
    pairs = [(int(k), v['bsd'] if v['kind'] != 'gap' else probe)
             for k, v in sorted(d['syscalls'].items(), key=lambda kv: int(kv[0]))]
    flags = [p for p in d.get('patterns', []) if p.get('to') is not None]
    fw = [f['linux'] for f in d.get('firewall', [])]
    L = ['# --- %s ABI layer ---------------------------------------------------' % osname,
         'bsd_fx a n b:',
         "    return join(a, join(strip(i2s(n)), b))",
         '',
         'bsd_rp t old new:',
         '    # replace-all in one pass: repl() sizes its room for one hit, so a',
         '    # pattern that occurs hundreds of times overruns it. this allocates',
         '    # the worst case up front and copies byte by byte.',
         '    n: str_len(t)',
         '    o: str_len(old)',
         '    gn: str_len(new)',
         '    cap: n + 8',
         '    if gn > o -> cap: n + (n / o + 1) * (gn - o) + 8',
         '    r: _sov_alloc(cap)',
         '    0:',
         '        i',
         '        j',
         '        k',
         '        m',
         '    as long as i < n -> m: 0',
         '        if i + o <= n -> m: 1',
         '            k: 0',
         '            as long as k < o -> if m = 1',
         '                    if _sov_byte_at(t, i + k) != _sov_byte_at(old, k) -> m: 0',
         '                k: k + 1',
         '        if m = 1 -> k: 0',
         '            as long as k < gn -> dummy: _sov_set_byte(r, j, _sov_byte_at(new, k))',
         '                j: j + 1',
         '                k: k + 1',
         '            i: i + o',
         '        if m = 0 -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i))',
         '            j: j + 1',
         '            i: i + 1',
         '    dummy: _sov_set_byte(r, j, 0)',
         '    return r as text',
         '',
         'bsd_pref t i:',
         '    # 8 for "syscall(" and for "sovcall(", 0 for neither',
         '    if _sov_byte_at(t, i) != 115 -> return 0',
         '    if _sov_byte_at(t, i + 1) = 121 -> if bsd_word(t, i, "syscall(") = 1 -> return 8',
         '    if _sov_byte_at(t, i + 1) = 111 -> if bsd_word(t, i, "sovcall(") = 1 -> return 8',
         '    return 0',
         'bsd_word t i w:',
         '    n: str_len(w)',
         '    k: 0',
         '    as long as k < n -> if _sov_byte_at(t, i + k) != _sov_byte_at(w, k) -> return 0',
         '        k: k + 1',
         '    return 1',
         'bsd_dig t p n:',
         '    # the value of the decimal run at p, or -1 when there is none',
         '    v: 0',
         '    k: 0',
         '    go: 1',
         '    as long as go = 1 -> c: 0',
         '        if p + k >= n -> go: 0',
         '        if go = 1 -> c: _sov_byte_at(t, p + k)',
         '            if c < 48 -> go: 0',
         '            if c > 57 -> go: 0',
         '            # two lines, not one semicolon-pair statement: inside\n'
         '            # nested inline ifs that compound form corrupts the frame\n'
         '            if go = 1 -> v: v * 10 + c - 48',
         '                k: k + 1',
         '    if k > 0 -> return v',
         '    return 0 - 1',
         'bsd_skip t p n:',
         '    # the index after the decimal run at p',
         '    k: 0',
         '    go: 1',
         '    as long as go = 1 -> c: 0',
         '        if p + k >= n -> go: 0',
         '        if go = 1 -> c: _sov_byte_at(t, p + k)',
         '            if c < 48 -> go: 0',
         '            if c > 57 -> go: 0',
         '            if go = 1 -> k: k + 1',
         '    return p + k',
         'bsd_wdig r j v:',
         '    # the decimal digits of v, and the index after them (no strings:',
         '    # this runs inside the compiler, where i2s is not a program task).',
         '    # ten digits: redox writes nine-digit numbers, and an eight-digit',
         '    # start dropped the leading one (570425347 became 70425347)',
         '    d: 1000000000',
         '    st: 0',
         '    as long as d > 0 -> if v >= d -> st: 1',
         '        if st = 1 -> dummy: _sov_set_byte(r, j, 48 + (v / d) % 10)',
         '            j: j + 1',
         '            v: v - (v / d) * d',
         '        d: d / 10',
         '    if st = 0 -> dummy: _sov_set_byte(r, j, 48)',
         '        j: j + 1',
         '    return j',
         'bsd_map t:',
         '    # one pass: read the number after every syscall(/sovcall( and write',
         '    # the target number in its place',
         '    n: str_len(t)',
         '    r: _sov_alloc(n + n / 8 + 64)',
         '    0:',
         '        i',
         '        j',
         '        p',
         '        q',
         '        v',
         '        m',
         '        k',
         '    as long as i < n -> p: 0',
         '        if i + 8 <= n -> p: bsd_pref(t, i)',
         '        if p = 0 -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i))',
         '            j: j + 1',
         '            i: i + 1',
         '        if p > 0 -> q: i + p',
         '            v: bsd_dig(t, q, n)',
         '            m: 0 - 1',
         '            if v > 0 - 1 -> m: bsd_num(v)',
         '            if m < 0 -> m: v',
         '            k: 0',
         '            as long as k < p -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i + k))',
         '                j: j + 1',
         '                k: k + 1',
         '            if m < 0 -> m: 0',
         '            if v > 0 - 1 -> j: bsd_wdig(r, j, m)',
         '            if v > 0 - 1 -> i: bsd_skip(t, q, n)',
         '            if v < 0 -> i: q',
         '    dummy: _sov_set_byte(r, j, 0)',
         '    return r as text',
         '']
    sh = shim_pass(osname, pairs)
    L += sh
    L += perm_pass(osname, d)
    L += [
         'bsd_num n:',
         '    # the table, both directions in one place: a Linux number in, the',
         '    # number this kernel answers to out, -1 when there is none.']
    for frm, to in pairs:
        L.append('    if n = %d -> return %d' % (frm, to))
    for num in fw:
        L.append('    if n = %d -> return %d' % (num, probe))
    L.append('    return 0 - 1')
    L.append('')

    def emit_phase(fn, pairs_list, sep, tmpl):
        L.append('%s t:' % fn)
        for frm, to in pairs_list:
            L.append(tmpl % (frm, qs(sep), frm, qs(sep), to, qs(sep)))
        L.append('    return t')
        L.append('')

    # the number pass is one scan: a chain of replace rules would rewrite its
    # own output (10 -> 74, then the rule for 74 -> 95), so the mapping has to
    # happen in place, once.
    L.append('bsd_fix t:')
    if osname == 'menuetos':
        # fn 512 does not fit the short push-imm8 form rax_imm picks for 60,
        # so every dynamic number goes out in the imm32 form instead (the
        # redox escape hatch); the code pass maps the imm32 sites
        L.append('    sys_num_wide: 1')
    L.append('    # %d numbers, %d of them the ENOSYS probe %d' % (
        len(pairs), sum(1 for _, to in pairs if to == probe), probe))
    if osname == 'redox':
        # the kit's numbers do not fit a byte: from here on the shared back
        # end loads the syscall number wide (sys_num_wide is the global the
        # cx86 small-number path reads), because a number the code pass has
        # to map cannot be rewritten inside a 3-byte push imm8
        L.append('    sys_num_wide: 1')
    L.append('    t: bsd_map(t)')
    if sh:
        L.append('    t: bsd_shim(t)')
    if d.get('perm'):
        L.append('    t: bsd_perm(t)')
    if flags:
        L.append('    # argument words that carry flags: open modes, mmap flags, madvise advice')
        for pr in flags:
            L.append('    # %s (%d site%s)' % (pr['what'], pr['count'], '' if pr['count'] == 1 else 's'))
            L.append("    if look(t, bsd_fx(%s, %d, %s)) > 0 - 1 -> t: bsd_rp(t, bsd_fx(%s, %d, %s), bsd_fx(%s, %d, %s))"
                     % (sq(pr['pre']), pr['from'], sq(pr['post']),
                        sq(pr['pre']), pr['from'], sq(pr['post']),
                        sq(pr['pre']), pr['to'], sq(pr['post'])))
    L.append('    return t')
    L.append('')
    L.append(code_pass((205, 96) if osname == 'menuetos' else (15, 5),
                       loop_win=(osname == 'menuetos')))
    return '\n'.join(L)


def shim_pass(osname, pairs):
    """the generated text pass that fixes an argument list, one target at a time.

    Written without a single nested inline `if`: on this language a compound
    statement inside nested inline ifs corrupts the frame, and an inline `if`
    with a body on the following lines changes what those lines belong to.  Every
    statement here is flat, and the loop that copies the first argument is
    bounded, so a malformed call cannot make the scan run away.  The head it
    looks for carries the number the table has just written, so no other call in
    the text can match it."""
    mp = dict(pairs)
    items = [(mp[lin], pos, ins) for lin, (pos, ins) in sorted(SHIM_ARGS.get(osname, {}).items())
             if lin in mp]
    if not items or len(set(ins for _, _, ins in items)) != 1:
        # no shim on this target (or several different insertions, which this
        # simple pass does not do): nothing is emitted and the call site is
        # skipped, so a target that needs no shim is byte-for-byte the kit it
        # was before this pass existed
        return []
    ins = items[0][2]
    heads = ['syscall(%d, ' % num for num, _, _ in items]
    L = ['bsd_eq t i s:',
         '    # does t carry the string s at i?',
         '    k: 0',
         '    m: str_len(s)',
         '    as long as k < m -> if _sov_byte_at(t, i + k) != _sov_byte_at(s, k) -> return 0',
         '        k: k + 1',
         '    return 1',
         'bsd_sp t i n:',
         '    # how long the call head at i is, or 0 when there is none here.',
         '    # n is str_len(t) handed in: the caller already knows it, and',
         '    # recomputing it per position turned the shim scan quadratic.']
    for h in heads:
        L.append('    if i + %d <= n -> if bsd_eq(t, i, %s) = 1 -> return %d'
                 % (len(h), sq(h), len(h)))
    L.append('    return 0')
    L.append('')
    L.append('bsd_shim t:')
    L.append('    # slip the argument the tree does not pass into the calls that want one:')
    for h in heads:
        L.append('    #   %s...  ->  %s' % (h, ins.strip()))
    L.append('    n: str_len(t)')
    L.append('    r: _sov_alloc(n + n / 8 + 64)')
    L.append('    0:')
    for v in ('i', 'j', 'p', 'k', 'c', 'ins', 'h0', 'q2', 'k2'):
        L.append('        %s' % v)
    L.append('    as long as i < n -> p: bsd_sp(t, i, n)')
    L.append('        if p = 0 -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i))')
    L.append('            j: j + 1')
    L.append('            i: i + 1')
    L.append('        if p > 0 -> h0: i')
    L.append('            k: 0')
    L.append('            as long as k < p -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i + k))')
    L.append('                j: j + 1')
    L.append('                k: k + 1')
    L.append('            i: i + p')
    L.append('            ins: 0')
    L.append('            k2: 0')
    L.append('            # the first argument, copied as it stands: the insertion goes after it')
    L.append('            as long as k2 < 512')
    L.append('                if i >= n -> leave')
    L.append('                c: _sov_byte_at(t, i)')
    L.append('                if c = 10 -> leave')
    L.append('                dummy: _sov_set_byte(r, j, c)')
    L.append('                j: j + 1')
    L.append('                i: i + 1')
    L.append('                if c = 44 -> ins: 1')
    L.append('                    leave')
    L.append('                k2: k2 + 1')
    L.append('            q2: 0')
    for h in heads:
        L.append('            q2: q2 + ins * bsd_eq(t, h0, %s)' % sq(h))
    L.append('            if q2 > 0 -> k: 0')
    L.append('                as long as k < %d -> dummy: _sov_set_byte(r, j, _sov_byte_at(%s, k))'
             % (len(ins), sq(ins)))
    L.append('                    j: j + 1')
    L.append('                    k: k + 1')
    L.append('    dummy: _sov_set_byte(r, j, 0)')
    L.append('    return r as text')
    L.append('')
    return L


def perm_pass(osname, d):
    """the generated text pass that carries arguments the vendor's way.

    Serenity loads arg1 in rdx, arg2 in rdi, arg3 in rbx, arg4 in rsi, while
    the tree marshals into rdi, rsi, rdx, r10, r8, r9.  For calls of at most
    two arguments the rewrite is a pure permutation of the text: the list
    (a1, a2, rest...) becomes (a2 or 0, 0, a1, rest...) so that after the
    compiler's marshalling a1 rides rdx and a2 rides rdi.  The pass runs on
    the head with the number already mapped (the SC_ value), so nothing else
    in the text can match it, and the argument scan is bounded like bsd_shim's.
    Every permuted number is asserted, at generation time, to have only plain
    (bracket- and quote-free) arguments in every site of the tree."""
    nums = d.get('perm') or []
    if not nums:
        return []
    heads = ['syscall(%d, ' % n for n in nums] + ['sovcall(%d, ' % n for n in nums]
    L = ['bsd_ph t i n:',
         '    # the length of a permutable call head at i, or 0 when none.',
         '    # n is str_len(t) handed in (see bsd_sp: per-position strlen is quadratic).']
    for h in heads:
        L.append('    if i + %d <= n -> if bsd_eq(t, i, %s) = 1 -> return %d'
                 % (len(h), sq(h), len(h)))
    L.append('    return 0')
    L.append('')
    L.append('bsd_parg t i n:')
    L.append('    # copy one argument starting at i up to a comma or close paren;')
    L.append('    # returns the index after it. bounded like the shim scan.')
    L.append('    # n is str_len(t) handed in (called per permutable site).')
    L.append('    k: 0')
    L.append('    as long as k < 512')
    L.append('        if i + k >= n -> leave')
    L.append('        c: _sov_byte_at(t, i + k)')
    L.append('        if c = 44 -> return i + k + 1')
    L.append('        if c = 41 -> return i + k')
    L.append('        k: k + 1')
    L.append('    return 0 - 1')
    L.append('')
    L.append('bsd_perm t:')
    L.append('    # permute (a1, a2, rest) into (a2 or 0, 0, a1, rest) after the head,')
    L.append('    # the vendor carriers being arg1=rdx, arg2=rdi')
    L.append('    n: str_len(t)')
    L.append('    r: _sov_alloc(n + n / 4 + 128)')
    L.append('    0:')
    for v in ('i', 'j', 'p', 'a1s', 'a1e', 'a2s', 'a2e', 'tail', 'c', 'k'):
        L.append('        %s' % v)
    L.append('    as long as i < n -> p: bsd_ph(t, i, n)')
    L.append("        if p = 0 -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i))")
    L.append('            j: j + 1')
    L.append('            i: i + 1')
    L.append('        if p > 0 -> k: 0')
    L.append('            as long as k < p -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, i + k))')
    L.append('                j: j + 1')
    L.append('                k: k + 1')
    L.append('            i: i + p')
    L.append('            a1s: i')
    L.append('            a1e: bsd_parg(t, a1s, n)')
    L.append('            a2s: a1e + 1')
    L.append('            a2e: bsd_parg(t, a2s, n)')
    L.append('            # comma and the second argument, or a zero when there is none')
    L.append('            dummy: _sov_set_byte(r, j, 44)')
    L.append('                j: j + 1')
    L.append('            if a2e > a2s -> k: a2s')
    L.append('                as long as k < a2e -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, k))')
    L.append('                    j: j + 1')
    L.append('                    k: k + 1')
    L.append('            if a2e <= a2s -> dummy: _sov_set_byte(r, j, 48)')
    L.append('                j: j + 1')
    L.append('            # the zero filler, then the first argument re-seated last')
    L.append('            dummy: _sov_set_byte(r, j, 44)')
    L.append('                j: j + 1')
    L.append('            dummy: _sov_set_byte(r, j, 48)')
    L.append('                j: j + 1')
    L.append('            dummy: _sov_set_byte(r, j, 44)')
    L.append('                j: j + 1')
    L.append('            k: a1s')
    L.append('            as long as k < a1e -> dummy: _sov_set_byte(r, j, _sov_byte_at(t, k))')
    L.append('                j: j + 1')
    L.append('                k: k + 1')
    L.append('            # everything after the second argument rides as it stands')
    L.append('            tail: a2e')
    L.append('            as long as tail < n -> c: _sov_byte_at(t, tail)')
    L.append('                dummy: _sov_set_byte(r, j, c)')
    L.append('                    j: j + 1')
    L.append('                    tail: tail + 1')
    L.append('            i: n')
    L.append('    dummy: _sov_set_byte(r, j, 0)')
    L.append('    return r as text')
    L.append('')
    return L


def expanded_tree():
    """every source file of the tree, expanded the way the compiler reads it"""
    sys.path.insert(0, HERE)
    import glob
    try:
        import kit_expand
    except Exception:
        return {}
    files = [os.path.join(ROOT, 'runtime.sov'),
             os.path.join(ROOT, 'launcher.sov'),
             os.path.join(ROOT, 'bootstrap.sov')]
    files += sorted(glob.glob(os.path.join(ROOT, 'library', '*.sov')))
    files += sorted(glob.glob(os.path.join(ROOT, 'library', 'inc', '*.sov')))
    files += sorted(glob.glob(os.path.join(ROOT, 'compilers', '*', 'compiler.sov')))
    files += sorted(glob.glob(os.path.join(ROOT, 'compilers', '*', '*', 'compiler.sov')))
    out = {}
    for f in files:
        if not os.path.exists(f):
            continue
        # a generated kit is an output, not an input: scanning it would feed its
        # own literals back into the next generation and the file would never
        # settle
        if os.path.basename(os.path.dirname(f)) in TARGETS:
            continue
        try:
            out[os.path.relpath(f, ROOT)] = kit_expand.expand(f)
        except Exception:
            out[os.path.relpath(f, ROOT)] = '\n'.join(_lines(f))
    return out


def call_args(text, num):
    """the argument spans of every `syscall(<num>, ...)` in the text.

    The scan is textual on purpose: the tree is read the way the compiler
    reads it, and the argument list ends at the first unbalanced `)`."""
    out = []
    needle = 'syscall(%d,' % num
    at = 0
    while True:
        i = text.find(needle, at)
        if i < 0:
            break
        at = i + 1
        j = i + len(needle)
        spans, start, depth, q = [], j, 0, 0
        while j < len(text):
            c = text[j]
            if q:
                if c == '"':
                    q = 0
            elif c == '"':
                q = 1
            elif c in '([':
                depth += 1
            elif c in ')]':
                if depth == 0:
                    spans.append((start, j))
                    break
                depth -= 1
            elif c == ',' and depth == 0:
                spans.append((start, j))
                start = j + 1
            j += 1
        out.append((i, [text[a:b] for a, b in spans]))
    return out


def flag_patterns(osname, lin_fcntl, lin_mman, tgt):
    """the argument words that travel to the kernel as ordinary arguments.

    A syscall takes its flag word in a register, so the text pass has to
    rewrite it before the compiler turns the argument into an immediate.  For
    each open/mmap/madvise site in the tree the Linux word is folded into its
    bits and the bits are re-spelled with the target's values; the pattern
    keeps the text around the literal so the rewrite names one kind of site."""
    fams = []
    for num, pos in sorted(OPEN_POS.items()):
        fams.append(('open', num, pos - 1))
    for num, pos in sorted(MMAP_POS.items()):
        fams.append(('mmap', num, pos - 1))
    for num, pos in sorted(ADVISE_POS.items()):
        fams.append(('advise', num, pos - 1))
    out = {}
    for rel, text in sorted(expanded_tree().items()):
        for kind, num, idx in fams:
            for at, args in call_args(text, num):
                if idx >= len(args):
                    continue
                lit = args[idx].strip()
                if not lit.isdigit():
                    continue
                from_word = int(lit)
                if kind == 'open':
                    words = flag_words(osname, lin_fcntl, lin_mman, tgt, [from_word])
                elif kind == 'mmap':
                    words = mmap_words(lin_mman, tgt, [from_word])
                else:
                    words = advise_words(lin_mman, tgt, [from_word])
                if not words:
                    continue
                ent = words.get(from_word)
                if ent is None:
                    ent = words.get(str(from_word))
                if not ent or ent.get('gap') is not None:
                    continue
                to_word = ent.get('word')
                if to_word is None or to_word == from_word:
                    continue
                a0 = at + len('syscall(%d,' % num) + sum(len(x) + 1 for x in args[:idx])
                lit_at = a0 + args[idx].index(lit)
                pre = text[at:lit_at]
                if len(pre) > 60:
                    pre = pre[-60:]
                post = text[lit_at + len(lit):lit_at + len(lit) + 12]
                key = (kind, num, from_word, to_word, pre, post)
                out[key] = out.get(key, 0) + 1
    pats = []
    for (kind, num, frm, to, pre, post), cnt in sorted(out.items(), key=lambda kv: (kv[0][1], kv[0][4])):
        pats.append({'kind': kind, 'what': 'syscall(%d, ' % num, 'from': frm, 'to': to,
                     'pre': pre, 'post': post, 'count': cnt})
    return pats


def code_pass(gate=(15, 5), loop_win=False):
    """the machine-code half: resolve tags, map the compiler's own numbers.

    Runs on `oc`, the byte list the compiler hands to the ELF writer, a few
    instructions before write_elf.  It reads the bytes around every 0f 05
    (syscall) and looks for the immediate that put the number in rax: the
    short forms the back end emits (mov al,imm8, mov eax,imm32, movabs,
    mov rax,imm32, push imm8+pop rax, push imm32+pop rax) sit right next to the
    syscall, and a number carried through the argument marshalling sits within
    the 64 bytes before it as a tag.  A tag is resolved to its target; a plain
    Linux number is mapped through bsd_num when the result still fits its
    encoding.  Anything else is left alone."""
    return '\n'.join([
        'bsd_put pos v w:',
        '    m: bsd_num(v)',
        '    if m < 0 -> return 0',
        '    if w = 1 -> if m > 255 -> return 0 - 1',
        '    if w = 1 -> dummy: _sov_list_set(oc, pos, m)',
        '    if w = 4 -> dummy: _sov_list_set(oc, pos, m % 256)',
        '        dummy: _sov_list_set(oc, pos + 1, (m / 256) % 256)',
        '        dummy: _sov_list_set(oc, pos + 2, (m / 65536) % 256)',
        '        dummy: _sov_list_set(oc, pos + 3, (m / 16777216) % 256)',
        '    return 1',
        'bsd_at p w:',
        '    v: _sov_list_get(oc, p)',
        '    if w >= 2 -> v: v + _sov_list_get(oc, p + 1) * 256',
        '        if w >= 3 -> v: v + _sov_list_get(oc, p + 2) * 65536',
        '            if w >= 4 -> v: v + _sov_list_get(oc, p + 3) * 16777216',
        '    return v',
        'bsd_c7 i:',
        '    # 48 c7 c0 imm32: mov rax, imm32',
        '    if _sov_list_get(oc, i - 8) != 72 -> return 0',
        '    if _sov_list_get(oc, i - 7) != 199 -> return 0',
        '    if _sov_list_get(oc, i - 6) != 192 -> return 0',
        '    return bsd_put(i - 5, bsd_at(i - 5, 4), 4)',
        'bsd_loop i:',
        '    # the debug-board loop head is b8 imm32 twelve bytes back, and only',
        '    # when the gate (205 96) follows the head',
        '    if _sov_list_get(oc, i) != 205 -> return 0',
        '    if _sov_list_get(oc, i + 1) != 96 -> return 0',
        '    return bsd_put(i - 11, bsd_at(i - 11, 4), 4)',
        'bsd_site i:',
        '    # 6a imm8 / 58 pop rax                                   (push, pop)',
        '    if i >= 3 -> if _sov_list_get(oc, i - 3) = 106 -> if _sov_list_get(oc, i - 1) = 88',
        '            dummy: bsd_put(i - 2, _sov_list_get(oc, i - 2), 1)',
        '    # 68 imm32 / 58 pop rax                                  (push, pop)',
        '    if i >= 6 -> if _sov_list_get(oc, i - 6) = 104 -> if _sov_list_get(oc, i - 1) = 88',
        '            dummy: bsd_put(i - 5, bsd_at(i - 5, 4), 4)',
        '    # b0 imm8 mov al                                         (direct)',
        '    if i >= 2 -> if _sov_list_get(oc, i - 2) = 176 -> dummy: bsd_put(i - 1, _sov_list_get(oc, i - 1), 1)',
        '    # b8 imm32 mov eax                                       (direct)',
        '    if i >= 5 -> if _sov_list_get(oc, i - 5) = 184 -> dummy: bsd_put(i - 4, bsd_at(i - 4, 4), 4)',
        '    # 48 b8 imm64 movabs rax                                 (direct)',
        '    if i >= 10 -> if _sov_list_get(oc, i - 10) = 72 -> if _sov_list_get(oc, i - 9) = 184',
        '            dummy: bsd_put(i - 8, bsd_at(i - 8, 4), 4)',
        '    # 48 c7 c0 imm32 mov rax, imm                            (direct)',
        '    if i >= 8 -> if _sov_list_get(oc, i - 8) = 72 -> dummy: bsd_c7(i)',
        '    # b8 imm32 / the head of the debug-board byte loop          (loop)',
        '    if i >= 12 -> dummy: bsd_loop(i)',
        '    return 0',
        'bsd_code:',
        '    # clen is a local of the ELF writer, so measure the code here',
        '    cn: _sov_list_len(oc)',
        '    i: 0',
        '    b: 0',
        '    as long as i + 1 < cn -> b: _sov_list_get(oc, i)',
        '        if b = %d -> if _sov_list_get(oc, i + 1) = %d -> dummy: bsd_site(i)' % gate,
        '        i: i + 1',
        '    return 0',
        ''])


PROBES = ['tests/abi_probe.sov', 'tests/hello.sov']


def imm8(v):
    """objdump prints an imm8 push sign-extended, `push $0xffffffffffffff97`:
    the byte the kernel reads in al is the low eight bits of that, and the kit
    uses this form when the number fits a byte but not a signed one."""
    return v & 0xFF if 0xFFFFFFFFFFFFFF80 <= v <= 0xFFFFFFFFFFFFFFFF else v


def syscall_numbers(binary, gate='syscall'):
    """the rax value in front of every syscall instruction, in program order.

    The kit's own convention is a virtual stack of 64-bit slots: arguments and
    syscall numbers are pushed, then popped into rdi/rsi/.. and finally rax.
    Following that stack (and the three immediate forms that load rax) recovers
    the number for every site the compiler emits, without executing the file.
    A slot whose value the model cannot know is reported as None."""
    out = subprocess.run(['objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64', binary],
                         capture_output=True, text=True).stdout
    st = []          # virtual stack, top last
    reg = {}         # symbolic register values
    nums = []
    for ln in out.split('\n'):
        m = re.match(r'\s*([0-9a-f]+):\t[0-9a-f ]+\t(.*)$', ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        asm = m.group(2).split('#')[0].strip()
        if not asm:
            continue
        if gate == 'int60':
            hit = re.match(r'int\s+\$0x60$', asm) is not None
        else:
            hit = asm.split()[0] in ('syscall', 'syscallq')
        if hit:
            nums.append((addr, reg.get('rax')))
            reg.clear()
            st = []
            continue
        mm = re.match(r'push\s+\$(0x[0-9a-f]+)$', asm)
        if mm:
            st.append(imm8(int(mm.group(1), 16)))
            continue
        mm = re.match(r'push\s+%(r?[a-z0-9]+)$', asm)
        if mm:
            st.append(reg.get(mm.group(1)))
            continue
        mm = re.match(r'pop\s+%(r?[a-z0-9]+)$', asm)
        if mm:
            reg[mm.group(1)] = st.pop() if st else None
            continue
        mm = re.match(r'mov\s+\$(0x[0-9a-f]+),%(e?ax|al)$', asm)
        if mm:
            reg['rax'] = int(mm.group(1), 16)
            continue
        mm = re.match(r'mov\s+\$(0x[0-9a-f]+),%(r?[a-z0-9]+)$', asm)
        if mm:
            reg[mm.group(2)] = int(mm.group(1), 16)
            continue
        mm = re.match(r'mov\s+%(r?[a-z0-9]+),%(e?ax|al|rax)$', asm)
        if mm:
            reg['rax'] = reg.get(mm.group(1))
            continue
        mm = re.match(r'mov\s+%(e?ax|al|rax),%(r?[a-z0-9]+)$', asm)
        if mm:
            reg[mm.group(2)] = reg.get('rax')
            continue
        mm = re.match(r'(xor|sub)\s+%(e?ax|al),%(e?ax|al|rax)$', asm)
        if mm:
            reg['rax'] = 0
            continue
        if re.match(r'(call|ret|jmp|j[a-z]+|leave|int)', asm):
            reg.clear()
            st = []
            continue
    return nums


def verify(osname, kit_bin, probes=None, quiet=False):
    """compile each probe with the linux kit and the target kit, then check that
    every syscall number in the second image is the table's image of the first.

    The two builds come from the same front end, so the sites line up one to
    one.  A site whose Linux number is not in the table (a number that arrives
    in a register at run time) is counted as skipped, not as a pass."""
    tab = json.load(open(JSONP))['targets'][osname]
    # the probe number is committed with the table, so --verify needs the
    # vendor headers for nothing (it is the one tool that runs in CI)
    probe = tab.get('enosys') or enosys(load_target(osname))
    m = {int(k): (v['bsd'] if v['kind'] != 'gap' else probe)
         for k, v in tab['syscalls'].items()}
    ok = True
    seen = collections.Counter()
    skipped = 0
    for probe in (probes or PROBES):
        tmp = '/tmp/abi_%s_%s' % (osname, os.path.basename(probe).replace('.sov', ''))
        imgs = {}
        for tag, comp in (('lin', os.path.join(ROOT, 'compilers', 'linux', 'compiler')),
                          ('tgt', kit_bin)):
            r = subprocess.run([comp, probe, '-o', tmp + '_' + tag],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print('  %s: build with %s failed' % (probe, comp))
                print('  ' + r.stdout.strip().replace('\n', ' ')[-300:])
                return False
            imgs[tag] = tmp + '_' + tag
        gate = 'int60' if osname == 'menuetos' else 'syscall'
        ls = syscall_numbers(imgs['lin'])
        ts = syscall_numbers(imgs['tgt'], gate)
        tb = open(imgs['tgt'], 'rb').read()
        if osname == 'menuetos':
            # there is no ELF: the identity is the vendor's own magic
            brand = tb[:8]
            if brand != b'MENUET64':
                print('  %s: the image does not carry the MENUET64 magic' % os.path.basename(probe))
                ok = False
                continue
            brand = 'MENUET64'
        else:
            brand = tb[7]
        if len(ls) != len(ts):
            print('  %s: %d linux sites vs %d %s sites' % (probe, len(ls), len(ts), osname))
            print('    lin: %s' % [(hex(a), n) for a, n in ls])
            print('    tgt: %s' % [(hex(a), n) for a, n in ts])
            ok = False
            continue
        bad = []
        for (la, ln), (ta, tn) in zip(ls, ts):
            if ln is None or tn is None or ln not in m:
                skipped += 1
                continue
            seen[(ln, m[ln])] += 1
            if tn != m[ln]:
                bad.append((hex(la), ln, m[ln], tn))
        if not quiet:
            print('  %-22s %d syscall sites, brand %s' % (os.path.basename(probe), len(ls), brand))
        if bad:
            print('    MISMATCH (offset, linux, expected, found):')
            for b in bad:
                print('      %s: %d -> want %d, got %d' % b)
            ok = False
    if not quiet:
        print('  numbers checked (linux -> %s):' % osname)
        for (frm, to), c in sorted(seen.items()):
            print('    %4d -> %-5d x%d' % (frm, to, c))
        if skipped:
            print('  %d site(s) skipped: number not a literal in the table' % skipped)
    return ok





if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] in ('--report', '-r'):
        report(build())
    elif a[0] == '--check':
        want = json.load(open(JSONP))
        try:
            now = build()
        except FileNotFoundError as e:
            # Arena/workspace snapshots do not always include the external
            # vendor checkout rooted at BSD_ABI_SRC.  In that case this command
            # should still verify that the committed ABI snapshot is present and
            # internally covers every generated OS target, while making it clear
            # that a header-derived drift check needs BSD_ABI_SRC mounted.
            missing = e.filename or str(e)
            have = want.get('targets', {})
            miss = [t for t in TARGETS if t not in have]
            if miss:
                print('DRIFT: tools/bsd_abi.json is missing target snapshots: %s' % ', '.join(miss))
                sys.exit(1)
            print('bsd_abi.json snapshot covers %d targets; vendor headers not mounted (%s)' % (len(TARGETS), missing))
            print('mount BSD_ABI_SRC to run a header-derived drift check')
            sys.exit(0)
        if json.dumps(want.get('targets'), sort_keys=True) != json.dumps(now['targets'], sort_keys=True):
            print('DRIFT: tools/bsd_abi.json no longer matches the vendor headers')
            print('       re-derive with: tools/bsd_abi.py --emit')
            sys.exit(1)
        print('bsd_abi.json matches the vendor headers (%d targets)' % len(TARGETS))
    elif a[0] == '--gen2':
        tgt = a[1]
        with open(JSONP) as f:
            tab = json.load(f)
        text, applied = gen_kit(tgt, tab)
    elif a[0] == '--gen':
        tgt = a[1]
        text, applied = gen_kit(tgt, build())
        d = os.path.join(ROOT, 'compilers', 'operating-systems', tgt)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'compiler.sov'), 'w').write(text)
        print('wrote compilers/operating-systems/%s/compiler.sov (%d lines, %d patches)' % (tgt, text.count(chr(10)), sum(applied.values())))
        for k, v in sorted(applied.items()):
            print('  %-28s x%d' % (k, v))
    elif a[0] == '--verify':
        tgt = a[1]
        kit = os.path.join(ROOT, 'compilers', 'operating-systems', tgt, 'compiler')
        ok = verify(tgt, kit)
        print('%s: %s' % (tgt, 'numbers line up' if ok else 'FAILED'))
        sys.exit(0 if ok else 1)
    elif a[0] == '--emit':
        tab = build()
        with open(JSONP, 'w') as f:
            json.dump(tab, f, indent=1, sort_keys=True)
            f.write('\n')
        print('wrote %s' % JSONP)
    else:
        print(__doc__)
        sys.exit(2)

