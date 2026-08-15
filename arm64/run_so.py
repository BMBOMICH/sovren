#!/usr/bin/env python3
"""Load a Sovren .so by symbol name and run it on an emulated ARM64 CPU."""
import sys, struct, lief
from unicorn import *
from unicorn.arm64_const import *
path=sys.argv[1]; name=sys.argv[2] if len(sys.argv)>2 else 'sovren_main'
b=lief.parse(path)
entry=[s.value for s in b.dynamic_symbols if s.name==name]
if not entry:
    print("no symbol",name); sys.exit(1)
entry=entry[0]
d=open(path,'rb').read(); base=0x400000
mu=Uc(UC_ARCH_ARM64,UC_MODE_ARM); mu.mem_map(base,0x2000000); mu.mem_write(base,d)
mu.mem_map(0x20000000,0x40000000)
SP=base+0x1000000; mu.reg_write(UC_ARM64_REG_SP,SP)
mu.mem_write(SP,struct.pack('<Q',1))
out=bytearray()
def hi(uc,i,u):
    nr=uc.reg_read(UC_ARM64_REG_X8)
    if nr==93: uc.emu_stop()
    elif nr==222: uc.reg_write(UC_ARM64_REG_X0,0x20000000)
    elif nr==64:
        bb=uc.reg_read(UC_ARM64_REG_X1); n=uc.reg_read(UC_ARM64_REG_X2)
        out.extend(uc.mem_read(bb,n)); uc.reg_write(UC_ARM64_REG_X0,n)
mu.hook_add(UC_HOOK_INTR,hi)
try: mu.emu_start(entry,0,count=50000000)
except UcError as e: print("ERR",e)
sys.stdout.write(out.decode('utf8','replace'))
