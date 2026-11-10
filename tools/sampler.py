#!/usr/bin/env python3
"""ptrace sampler with names: attribute a Sovren compiler's run to functions.

Function starts come from the `endbr64` markers the code generator emits; names
come from the `.map` file a `--bytes` build writes (`<out>.map`: name, offset of
the function inside the emitted code).  The emitted code sits at file offset
0x140 (the compiler's HDR) inside the ELF, so

    offset_in_emitted_code = offset_in_file - 0x140

Usage: sampler.py <binary> <map> <args...>
"""
import bisect
import ctypes
import os
import re
import struct
import sys
import time

libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.ptrace.restype = ctypes.c_long

PTRACE_SEIZE, PTRACE_INTERRUPT, PTRACE_CONT, PTRACE_GETREGS = 0x4206, 0x4207, 7, 12

libc.process_vm_readv.restype = ctypes.c_ssize_t


class iovec(ctypes.Structure):
    _fields_ = [("iov_base", ctypes.c_void_p), ("iov_len", ctypes.c_size_t)]


def peek_word(pid, addr):
    buf = ctypes.c_uint64(0)
    local = iovec(ctypes.cast(ctypes.byref(buf), ctypes.c_void_p), 8)
    remote = iovec(ctypes.c_void_p(addr), 8)
    n = libc.process_vm_readv(pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
    return buf.value if n == 8 else 0
CODE_OFF = 0x140


class regs(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi "
                 "orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs").split()]


def endbr_starts(path):
    d = open(path, "rb").read()
    assert d[:4] == b"\x7fELF" and d[4] == 2
    e_phoff, = struct.unpack_from("<Q", d, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)
    starts = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from("<II", d, off)
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<QQQQQ", d, off + 8)
        if p_type == 1 and (p_flags & 1):
            blob = d[p_offset:p_offset + p_filesz]
            i2 = blob.find(b"\xf3\x0f\x1e\xfa")
            while i2 >= 0:
                starts.append(p_offset + i2)
                i2 = blob.find(b"\xf3\x0f\x1e\xfa", i2 + 1)
    return sorted(set(starts))


def load_map(path):
    toks = open(path).read().split()
    pairs = sorted(((int(toks[i + 1]), toks[i]) for i in range(0, len(toks), 2)))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def mapping_for(pid, path):
    for line in open(f"/proc/{pid}/maps"):
        parts = line.split()
        if len(parts) >= 6 and parts[-1] == path and "x" in parts[1] and parts[2] == "00000000":
            lo, hi = parts[0].split("-")
            return int(lo, 16), int(parts[2], 16)
    return None, None


def main():
    binary = os.path.abspath(sys.argv[1])
    mapfile = sys.argv[2]
    args = sys.argv[3:]
    starts = endbr_starts(binary)
    map_offs, map_names = load_map(mapfile)
    names = []
    for a in starts:
        co = a - CODE_OFF
        k = bisect.bisect_right(map_offs, co) - 1
        names.append(map_names[k] if k >= 0 else "?")

    pid = os.fork()
    if pid == 0:
        os.execv(binary, [binary] + args)
        os._exit(127)
    if libc.ptrace(PTRACE_SEIZE, pid, None, None) != 0:
        raise SystemExit("PTRACE_SEIZE failed")
    status = ctypes.c_int(0)
    counts, pairs, total, t0, base, foff = {}, {}, 0, time.perf_counter(), None, None
    reaped = False
    while True:
        if libc.ptrace(PTRACE_INTERRUPT, pid, None, None) != 0:
            break
        w = libc.waitpid(pid, ctypes.byref(status), 0)
        if w != pid and w != 0:
            reaped = True
            break
        if os.WIFEXITED(status.value) or os.WIFSIGNALED(status.value):
            reaped = True
            break
        if base is None:
            base, foff = mapping_for(pid, binary)
        r = regs()
        if libc.ptrace(PTRACE_GETREGS, pid, None, ctypes.byref(r)) == 0 and base:
            fo = r.rip - base + foff
            k = bisect.bisect_right(starts, fo) - 1
            nm = names[k] if k >= 0 else "outside"
            counts[nm] = counts.get(nm, 0) + 1
            ra = peek_word(pid, r.rsp) if r.rsp else 0
            if ra:
                fo2 = ra - base + foff
                k2 = bisect.bisect_right(starts, fo2) - 1
                cnm = names[k2] if k2 >= 0 else "outside"
            else:
                cnm = "?"
            pairs[(nm, cnm)] = pairs.get((nm, cnm), 0) + 1
            total += 1
        libc.ptrace(PTRACE_CONT, pid, None, None)
    if not reaped:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    dt = time.perf_counter() - t0
    print(f"# {total} samples in {dt:.3f} s  ({total/max(dt,1e-9):.0f} Hz)", file=sys.stderr)
    self_time = sum(counts.values())
    for nm, n in sorted(counts.items(), key=lambda kv: -kv[1])[:30]:
        print(f"{n:7d} {100.0*n/max(self_time,1):6.2f}%  {nm}")
    print("\n# top call sites (callee <- caller)")
    for (cal, cur), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:30]:
        print(f"{n:7d} {100.0*n/max(self_time,1):6.2f}%  {cal} <- {cur}")


if __name__ == "__main__":
    main()
