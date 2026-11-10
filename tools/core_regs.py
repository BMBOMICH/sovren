#!/usr/bin/env python3
"""Minimal ELF core parser: dump NT_PRSTATUS registers (rip, rsp, etc.)."""
import struct, sys

path = sys.argv[1] if len(sys.argv) > 1 else "/home/z/my-project/work-v4/sovren-projects/sovren/core"
d = open(path, "rb").read()
assert d[:4] == b"\x7fELF"
# 64-bit ELF header
e_phoff = struct.unpack_from("<Q", d, 0x20)[0]
e_phentsize = struct.unpack_from("<H", d, 0x36)[0]
e_phnum = struct.unpack_from("<H", d, 0x38)[0]

REG = ["r15","r14","r13","r12","rbp","rbx","r11","r10","r9","r8","rax","rcx",
       "rdx","rsi","rdi","orig_rax","rip","cs","eflags","rsp","ss",
       "fs_base","gs_base","ds","es","fs","gs"]

prstatus = []
for i in range(e_phnum):
    off = e_phoff + i * e_phentsize
    p_type = struct.unpack_from("<I", d, off)[0]
    if p_type != 4:  # PT_NOTE
        continue
    p_offset = struct.unpack_from("<Q", d, off + 8)[0]
    p_filesz = struct.unpack_from("<Q", d, off + 32)[0]
    no = p_offset
    end = p_offset + p_filesz
    while no < end:
        namesz, descsz, ntype = struct.unpack_from("<III", d, no)
        name = d[no+12:no+12+namesz].rstrip(b"\0")
        desc = d[no+12+((namesz+3)//4*4):no+12+((namesz+3)//4*4)+descsz]
        if name == b"CORE" and ntype == 1:  # NT_PRSTATUS
            prstatus.append(desc)
        no += 12 + ((namesz+3)//4*4) + ((descsz+3)//4*4)

print(f"{len(prstatus)} PRSTATUS entries")
for k, desc in enumerate(prstatus):
    # prstatus: siginfo(16) ... actually: si_signo, si_code, si_errno (ints) + padding,
    # then 14 ints (cur/sig), then pid, ppid... layout: struct elf_prstatus
    # Simpler: user_regs_struct sits at offset 112 (x86_64) in elf_prstatus
    regs = struct.unpack_from("<27Q", desc, 112)
    print(f"--- thread {k} (pid {struct.unpack_from('<i', desc, 32)[0] if len(desc)>36 else '?'}) ---")
    for j, r in enumerate(regs):
        print(f"  {REG[j]:8s} = {r:#018x}")
    print(f"  sig = {struct.unpack_from('<i', desc, 0)[0]}")
    break
