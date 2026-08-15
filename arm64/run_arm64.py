import sys, struct
from unicorn import *
from unicorn.arm64_const import *
path=sys.argv[1]
d=open(path,'rb').read()
entry=struct.unpack('<Q', d[24:32])[0]
base =struct.unpack('<Q', d[80:88])[0]
mu=Uc(UC_ARCH_ARM64, UC_MODE_ARM)
LOAD = base & ~0xFFF
mu.mem_map(LOAD, 0x1000000)
mu.mem_write(base, d)
STACK=LOAD+0xC00000
MMAP_BASE=0x10000000
mu.mem_map(MMAP_BASE, 0x40000000)      # 1GB heap region for mmap
mu.reg_write(UC_ARM64_REG_SP, STACK)
mu.mem_write(STACK, struct.pack('<Q',1))
out=bytearray(); code=[0]
def hi(uc,intno,ud):
    nr=uc.reg_read(UC_ARM64_REG_X8)
    if nr==64:
        b=uc.reg_read(UC_ARM64_REG_X1); n=uc.reg_read(UC_ARM64_REG_X2)
        try: out.extend(uc.mem_read(b,n))
        except: pass
        uc.reg_write(UC_ARM64_REG_X0,n)
    elif nr==93:
        code[0]=uc.reg_read(UC_ARM64_REG_X0); uc.emu_stop()
    elif nr==222:
        uc.reg_write(UC_ARM64_REG_X0, MMAP_BASE)
    elif nr==214:
        uc.reg_write(UC_ARM64_REG_X0, MMAP_BASE)
    else:
        uc.reg_write(UC_ARM64_REG_X0,0)
mu.hook_add(UC_HOOK_INTR, hi)
try:
    mu.emu_start(entry, 0, count=5000000)
except UcError as e:
    print("RUNTIME ERROR:", e, "pc=",hex(mu.reg_read(UC_ARM64_REG_PC)))
    print("output so far:", bytes(out))
    sys.exit(1)
sys.stdout.write(out.decode('utf8','replace'))
sys.exit(0)
