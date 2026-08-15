import sys, struct
from unicorn import *
from unicorn.arm64_const import *

def run(code, mem_size=0x200000, base=0x10000, stack=0x100000, trace=False, maxinstr=200000):
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, mem_size)
    mu.mem_write(base, code)
    mu.reg_write(UC_ARM64_REG_SP, stack)
    mu.reg_write(UC_ARM64_REG_X29, stack)
    out = bytearray()
    def hook_intr(uc, intno, ud):
        # SVC: linux aarch64 syscall, x8=nr
        nr = uc.reg_read(UC_ARM64_REG_X8)
        if nr == 64:  # write
            fd = uc.reg_read(UC_ARM64_REG_X0)
            buf = uc.reg_read(UC_ARM64_REG_X1)
            n   = uc.reg_read(UC_ARM64_REG_X2)
            out.extend(uc.mem_read(buf, n))
            uc.reg_write(UC_ARM64_REG_X0, n)
        elif nr == 93:  # exit
            uc.emu_stop()
        elif nr == 214: # brk
            uc.reg_write(UC_ARM64_REG_X0, 0x180000)
        elif nr == 222: # mmap
            uc.reg_write(UC_ARM64_REG_X0, 0x150000)
        else:
            uc.reg_write(UC_ARM64_REG_X0, 0)
    mu.hook_add(UC_HOOK_INTR, hook_intr)
    if trace:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
        md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        def hc(uc, addr, size, ud):
            d = uc.mem_read(addr, size)
            for i in md.disasm(bytes(d), addr):
                print(f"  {addr:#x} {i.mnemonic} {i.op_str}  x0={uc.reg_read(UC_ARM64_REG_X0)}")
        mu.hook_add(UC_HOOK_CODE, hc)
    try:
        mu.emu_start(base, base+len(code), count=maxinstr)
    except UcError as e:
        return None, bytes(out), f"{e} pc={mu.reg_read(UC_ARM64_REG_PC):#x}"
    return mu.reg_read(UC_ARM64_REG_X0), bytes(out), None
