#!/usr/bin/env python3
# run_pe.py - run a Windows .exe on an emulated CPU, strictly.
#
# Wine is not a fair test for Sovren: Wine runs on Linux, so a raw
# `syscall` instruction inside the program falls straight through to
# the Linux kernel and appears to work. On real Windows there is no
# Linux kernel underneath and the program dies quietly.
#
# This emulator plays the part of Windows itself. It implements the
# kernel32 functions the program imports, and it REFUSES a raw
# syscall instruction, which is exactly what real Windows does.
import sys, struct
from unicorn import *
from unicorn.x86_const import *

path = sys.argv[1]
args = sys.argv[2:]
d = open(path, 'rb').read()

if d[:2] != b'MZ':
    print("not a PE file", file=sys.stderr); sys.exit(2)
pe = struct.unpack_from('<I', d, 0x3c)[0]
if d[pe:pe+4] != b'PE\0\0':
    print("bad PE signature", file=sys.stderr); sys.exit(2)

nsec = struct.unpack_from('<H', d, pe + 6)[0]
opt = pe + 24
entry_rva = struct.unpack_from('<I', d, opt + 16)[0]
base = struct.unpack_from('<Q', d, opt + 24)[0]
sizeimg = struct.unpack_from('<I', d, opt + 56)[0]
dd = opt + 112
imp_rva = struct.unpack_from('<I', d, dd + 8)[0]

secs = []
so = pe + 24 + 240
for i in range(nsec):
    o = so + i * 40
    nm = d[o:o+8].rstrip(b'\0').decode(errors='replace')
    vs, va, rs, ra = struct.unpack_from('<IIII', d, o + 8)
    secs.append((nm, va, vs, ra, rs))

mu = Uc(UC_ARCH_X86, UC_MODE_64)
IMG = (sizeimg + 0xFFFF) & ~0xFFFF
mu.mem_map(base, max(IMG, 0x400000))
for nm, va, vs, ra, rs in secs:
    if rs:
        mu.mem_write(base + va, d[ra:ra+rs])


def rd(rva, n):
    for nm, va, vs, ra, rs in secs:
        if va <= rva < va + max(vs, rs):
            off = ra + (rva - va)
            return d[off:off+n]
    return b''


def cstr_at_rva(rva):
    b = rd(rva, 256)
    return b.split(b'\0')[0].decode(errors='replace')


# ---- fake kernel32 ----
THUNK = 0x70000000
mu.mem_map(THUNK, 0x10000)
HEAP = 0x200000000
mu.mem_map(HEAP, 0x20000000)
heap_next = [HEAP]
STACK = 0x7F000000
mu.mem_map(STACK, 0x400000)
mu.reg_write(UC_X86_REG_RSP, STACK + 0x300000)

cmdline = (path + (' ' + ' '.join(args) if args else '')).encode() + b'\0'
CMD_ADDR = heap_next[0]; heap_next[0] += 0x1000
mu.mem_write(CMD_ADDR, cmdline)

out = bytearray()
err = bytearray()
files = {}
next_fd = [0x100]
rc = [0]
used_syscall = [False]
missing = []


def w32(v):
    return v & 0xFFFFFFFF


def handle_call(name, uc):
    a1 = uc.reg_read(UC_X86_REG_RCX)
    a2 = uc.reg_read(UC_X86_REG_RDX)
    a3 = uc.reg_read(UC_X86_REG_R8)
    a4 = uc.reg_read(UC_X86_REG_R9)
    sp = uc.reg_read(UC_X86_REG_RSP)
    a5 = struct.unpack('<Q', uc.mem_read(sp + 40, 8))[0]
    a6 = struct.unpack('<Q', uc.mem_read(sp + 48, 8))[0]

    if name == 'GetStdHandle':
        h = {0xFFFFFFF6: 10, 0xFFFFFFF5: 11, 0xFFFFFFF4: 12}.get(w32(a1), 11)
        uc.reg_write(UC_X86_REG_RAX, h)
    elif name == 'WriteFile':
        buf = uc.mem_read(a2, a3) if a3 else b''
        if a1 == 11:
            out.extend(buf)
        elif a1 == 12:
            err.extend(buf)
        else:
            f = files.get(a1)
            if f is not None:
                f['data'] += bytes(buf)
        if a4:
            uc.mem_write(a4, struct.pack('<I', a3))
        uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'ReadFile':
        f = files.get(a1)
        if f is None:
            if a4:
                uc.mem_write(a4, struct.pack('<I', 0))
            uc.reg_write(UC_X86_REG_RAX, 1)
        else:
            chunk = f['data'][f['pos']:f['pos'] + a3]
            f['pos'] += len(chunk)
            if chunk:
                uc.mem_write(a2, chunk)
            if a4:
                uc.mem_write(a4, struct.pack('<I', len(chunk)))
            uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'CreateFileA':
        nm = bytes(uc.mem_read(a1, 512)).split(b'\0')[0].decode(errors='replace')
        access, disp = w32(a2), w32(a5)
        fd = next_fd[0]; next_fd[0] += 1
        if disp in (2, 1):                 # CREATE_ALWAYS / CREATE_NEW
            files[fd] = {'name': nm, 'data': b'', 'pos': 0, 'w': True}
        else:
            try:
                data = open(nm, 'rb').read()
            except Exception:
                uc.reg_write(UC_X86_REG_RAX, 0xFFFFFFFFFFFFFFFF)
                return
            files[fd] = {'name': nm, 'data': data, 'pos': 0, 'w': False}
        uc.reg_write(UC_X86_REG_RAX, fd)
    elif name == 'CloseHandle':
        f = files.pop(a1, None)
        if f and f.get('w'):
            try:
                open(f['name'], 'wb').write(f['data'])
            except Exception:
                pass
        uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'VirtualAlloc':
        size = (a2 + 0xFFFF) & ~0xFFFF
        p = heap_next[0]
        heap_next[0] += max(size, 0x10000)
        uc.reg_write(UC_X86_REG_RAX, p)
    elif name == 'ExitProcess':
        rc[0] = w32(a1)
        uc.emu_stop()
    elif name == 'GetCommandLineA':
        uc.reg_write(UC_X86_REG_RAX, CMD_ADDR)
    elif name == 'SetFilePointerEx':
        f = files.get(a1)
        if f is not None:
            whence = w32(a4)
            if whence == 0:
                f['pos'] = a2
            elif whence == 1:
                f['pos'] += a2
            else:
                f['pos'] = len(f['data']) + a2
            if a3:
                uc.mem_write(a3, struct.pack('<q', f['pos']))
        uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'DeleteFileA':
        uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'CreateDirectoryA':
        uc.reg_write(UC_X86_REG_RAX, 1)
    elif name == 'GetFileSizeEx':
        f = files.get(a1)
        if f is not None and a2:
            uc.mem_write(a2, struct.pack('<q', len(f['data'])))
        uc.reg_write(UC_X86_REG_RAX, 1)
    else:
        missing.append(name)
        uc.reg_write(UC_X86_REG_RAX, 0)


# walk the import table and point every slot at a thunk we control
thunks = {}
if imp_rva:
    k = 0
    while True:
        desc = rd(imp_rva + k * 20, 20)
        if len(desc) < 20 or desc == b'\0' * 20:
            break
        ilt, _, _, namerva, iat = struct.unpack('<IIIII', desc)
        if namerva == 0:
            break
        j = 0
        while True:
            slot = iat + j * 8
            v = struct.unpack('<Q', rd(slot, 8))[0]
            if v == 0:
                break
            fname = cstr_at_rva((v & 0x7FFFFFFF) + 2)
            addr = THUNK + len(thunks) * 16
            thunks[addr] = fname
            mu.mem_write(base + slot, struct.pack('<Q', addr))
            mu.mem_write(addr, b'\xc3')          # ret
            j += 1
        k += 1


def on_code(uc, address, size, ud):
    if address in thunks:
        handle_call(thunks[address], uc)


def on_syscall(uc, ud):
    used_syscall[0] = True
    uc.emu_stop()


mu.hook_add(UC_HOOK_CODE, on_code, None, THUNK, THUNK + 0x10000)
mu.hook_add(UC_HOOK_INSN, on_syscall, None, 1, 0, UC_X86_INS_SYSCALL)

try:
    mu.emu_start(base + entry_rva, base + IMG, 0, 200_000_000)
except UcError as e:
    if not used_syscall[0]:
        print(f"\ncpu fault: {e}", file=sys.stderr)

sys.stdout.write(out.decode('utf-8', errors='replace'))
sys.stderr.write(err.decode('utf-8', errors='replace'))

if used_syscall[0]:
    print("\nREJECTED: the program used a raw `syscall` instruction.\n"
          "Windows has no Linux kernel behind it, so this does nothing on a\n"
          "real machine. Wine hides this because Wine runs on Linux.",
          file=sys.stderr)
    sys.exit(3)
if missing:
    print(f"\nunimplemented kernel32 calls: {sorted(set(missing))}", file=sys.stderr)
sys.exit(rc[0])
