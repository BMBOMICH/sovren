#!/usr/bin/env python3
# run_macho.py - run a Mach-O x86-64 binary on an emulated CPU.
#
# This machine is Linux, so a Mac binary cannot be run directly.
# Unicorn emulates the CPU; this script plays the part of the XNU
# kernel. It is deliberately strict: macOS syscall numbers carry the
# BSD class bit 0x2000000, and a raw Linux number is rejected the way
# a real Mac rejects it, instead of silently working.
import sys, struct
from unicorn import *
from unicorn.x86_const import *

BSD = 0x2000000            # syscall class for unix calls on macOS
SYS_EXIT, SYS_READ, SYS_WRITE = 1, 3, 4
SYS_OPEN, SYS_CLOSE, SYS_MMAP = 5, 6, 197

path = sys.argv[1]
d = open(path, 'rb').read()

magic = struct.unpack_from('<I', d, 0)[0]
if magic != 0xfeedfacf:
    print(f"not a 64-bit Mach-O (magic {magic:#x})", file=sys.stderr)
    sys.exit(2)

ncmds = struct.unpack_from('<I', d, 16)[0]
entry = None
segs = []
off = 32
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack_from('<II', d, off)
    if cmd == 0x19:                                   # LC_SEGMENT_64
        name = d[off + 8:off + 24].rstrip(b'\0').decode(errors='replace')
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', d, off + 24)
        segs.append((name, vmaddr, vmsize, fileoff, filesize))
    elif cmd == 0x80000028:                           # LC_MAIN
        entry = struct.unpack_from('<Q', d, off + 8)[0]
    elif cmd == 0x5:                                  # LC_UNIXTHREAD
        # x86_THREAD_STATE64: rip is the 17th 64-bit register in the
        # state block, which starts 16 bytes into the command.
        entry = struct.unpack_from('<Q', d, off + 144)[0]
    off += cmdsize

if entry is None:
    print("no entry point (need LC_MAIN or LC_UNIXTHREAD)", file=sys.stderr)
    sys.exit(2)

real = [s for s in segs if s[0] != '__PAGEZERO' and s[2] > 0]
base = min((s[1] for s in real), default=0x100000000)
mu = Uc(UC_ARCH_X86, UC_MODE_64)
LOAD = base & ~0xFFF
mu.mem_map(LOAD, 0x2000000)
for name, vmaddr, vmsize, fileoff, filesize in real:
    if filesize:
        mu.mem_write(vmaddr, d[fileoff:fileoff + filesize])

STACK = LOAD + 0x1800000
HEAP = 0x200000000
mu.mem_map(HEAP, 0x40000000)
mu.reg_write(UC_X86_REG_RSP, STACK)
mu.mem_write(STACK, struct.pack('<Q', 1))             # argc

out = bytearray()
rc = [0]
heap_next = [HEAP]
bad = []


def on_syscall(uc, ud):
    nr = uc.reg_read(UC_X86_REG_RAX)
    if not (nr & BSD):
        bad.append(nr)
        print(f"\nMac rejects syscall {nr}: missing the 0x2000000 class bit. "
              f"On macOS this is a Linux number, not a Mac one.", file=sys.stderr)
        uc.emu_stop()
        return
    n = nr & 0xFFFFFF
    if n == SYS_WRITE:
        buf = uc.reg_read(UC_X86_REG_RSI)
        cnt = uc.reg_read(UC_X86_REG_RDX)
        try:
            out.extend(uc.mem_read(buf, cnt))
        except Exception:
            pass
        uc.reg_write(UC_X86_REG_RAX, cnt)
    elif n == SYS_EXIT:
        rc[0] = uc.reg_read(UC_X86_REG_RDI)
        uc.emu_stop()
    elif n == SYS_MMAP:
        p = heap_next[0]
        heap_next[0] += 0x1000000
        uc.reg_write(UC_X86_REG_RAX, p)
    elif n in (SYS_OPEN, SYS_READ, SYS_CLOSE):
        uc.reg_write(UC_X86_REG_RAX, 0)
    else:
        uc.reg_write(UC_X86_REG_RAX, 0)


mu.hook_add(UC_HOOK_INSN, on_syscall, None, 1, 0, UC_X86_INS_SYSCALL)

try:
    mu.emu_start(entry, LOAD + 0x2000000, 0, 40_000_000)
except UcError as e:
    if not bad:
        print(f"\ncpu fault: {e}", file=sys.stderr)

sys.stdout.write(out.decode('utf-8', errors='replace'))
sys.exit(1 if bad else rc[0])
