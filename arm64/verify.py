#!/usr/bin/env python3
"""Verify Sovren's AArch64 encodings by executing them on an emulated ARM64 CPU.
Requires: pip install unicorn capstone
Run:      python3 arm64/verify.py
"""
import struct, sys
from unicorn import *
from unicorn.arm64_const import *

def w(v): return struct.pack('<I', v & 0xFFFFFFFF)
def movz(d,i,s=0): return w(0xD2800000 + (s<<21) + ((i&0xFFFF)<<5) + d)
def movk(d,i,s):   return w(0xF2800000 + (s<<21) + ((i&0xFFFF)<<5) + d)
def mov_reg(d,s):  return w(0xAA0003E0 + (s<<16) + d)
def bl(off):       return w(0x94000000 | ((off//4) & 0x03FFFFFF))
def bcond(c,off):  return w(0x54000000 | (((off//4)&0x7FFFF)<<5) | c)
EXIT = movz(8,93)+w(0xD4000001)
RET  = w(0xD65F03C0)
PRO  = w(0xA9BF7BFD)+w(0x910003FD)
EPI  = w(0xA8C17BFD)

def run(code, base=0x10000):
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, 0x200000)
    mu.mem_write(base, code)
    mu.reg_write(UC_ARM64_REG_SP, 0x100000)
    out = bytearray()
    def hi(uc, intno, ud):
        nr = uc.reg_read(UC_ARM64_REG_X8)
        if nr == 64:
            b = uc.reg_read(UC_ARM64_REG_X1); n = uc.reg_read(UC_ARM64_REG_X2)
            out.extend(uc.mem_read(b, n)); uc.reg_write(UC_ARM64_REG_X0, n)
        elif nr == 93:
            uc.emu_stop()
        else:
            uc.reg_write(UC_ARM64_REG_X0, 0)
    mu.hook_add(UC_HOOK_INTR, hi)
    try:
        mu.emu_start(base, base+len(code), count=500000)
    except UcError as e:
        return None, bytes(out), str(e)
    return mu.reg_read(UC_ARM64_REG_X0), bytes(out), None

R = []
def t(name, code, want, isout=False):
    r, out, err = run(code)
    got = out if isout else r
    if r is not None and not isout and r > 2**63: r -= 2**64; got = r
    ok = (got == want and err is None)
    R.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name:26s} got={got!r} want={want!r} {err or ''}")

MOD = w(0x9AC10C02) + w(0x9B018040)

t("movz",            movz(0,42)+EXIT, 42)
t("movz+movk",       movz(0,0x5678)+movk(0,0x1234,1)+EXIT, 0x12345678)
t("add",             movz(0,40)+movz(1,2)+w(0x8B010000)+EXIT, 42)
t("sub",             movz(0,50)+movz(1,8)+w(0xCB010000)+EXIT, 42)
t("mul",             movz(0,6)+movz(1,7)+w(0x9B017C00)+EXIT, 42)
t("sdiv",            movz(0,84)+movz(1,2)+w(0x9AC10C00)+EXIT, 42)
t("mod 7%3",         movz(0,7)+movz(1,3)+MOD+EXIT, 1)
t("mod 100%7",       movz(0,100)+movz(1,7)+MOD+EXIT, 2)
t("cset eq true",    movz(0,5)+movz(1,5)+w(0xEB01001F)+w(0x9A9F17E0)+EXIT, 1)
t("cset eq false",   movz(0,5)+movz(1,6)+w(0xEB01001F)+w(0x9A9F17E0)+EXIT, 0)
t("cset ne",         movz(0,5)+movz(1,6)+w(0xEB01001F)+w(0x9A9F07E0)+EXIT, 1)
t("cset lt",         movz(0,3)+movz(1,5)+w(0xEB01001F)+w(0x9A9FA7E0)+EXIT, 1)
t("cset gt",         movz(0,9)+movz(1,5)+w(0xEB01001F)+w(0x9A9FD7E0)+EXIT, 1)
t("cset ge",         movz(0,5)+movz(1,5)+w(0xEB01001F)+w(0x9A9FB7E0)+EXIT, 1)
t("cset le",         movz(0,5)+movz(1,5)+w(0xEB01001F)+w(0x9A9FC7E0)+EXIT, 1)
t("xor_rax",         movz(0,99)+w(0xAA1F03E0)+EXIT, 0)
t("push/pop",        movz(0,7)+w(0xF81F0FE0)+movz(0,0)+w(0xF84107E0)+EXIT, 7)
t("pop into x1",     movz(0,9)+w(0xF81F0FE0)+w(0xF84107E1)+mov_reg(0,1)+EXIT, 9)
t("local reg x19",   movz(0,33)+mov_reg(19,0)+movz(0,0)+mov_reg(0,19)+EXIT, 33)
t("stack local",     movz(0,55)+w(0xF90003A0)+movz(0,0)+w(0xF94003A0)+EXIT, 55)
t("test zero",       movz(0,0)+w(0xF100001F)+w(0x9A9F17E0)+EXIT, 1)
t("test nonzero",    movz(0,5)+w(0xF100001F)+w(0x9A9F17E0)+EXIT, 0)
t("bl + ret",        bl(4+len(EXIT))+EXIT+movz(0,99)+RET, 99)
t("prolog/epilog",   bl(4+len(EXIT))+EXIT+PRO+movz(0,7)+w(0xF90003A0)+movz(0,0)+w(0xF94003A0)+EPI+RET, 7)

init = movz(19,1)+movz(20,0)
body = mov_reg(0,20)+mov_reg(1,19)+w(0x8B010000)+mov_reg(20,0)
body+= mov_reg(0,19)+movz(1,1)+w(0x8B010000)+mov_reg(19,0)
cmpx = mov_reg(0,19)+movz(1,11)+w(0xEB01001F)
delta= len(init) - (len(init)+len(body)+len(cmpx))
t("loop sum 1..10",  init+body+cmpx+bcond(1,delta)+mov_reg(0,20)+EXIT, 55)

print()
print(f"{sum(R)}/{len(R)} ARM64 encodings verified on emulated CPU")
print()

# ---- runtime helper verification (print_int, strlen, str_eq) ----
def _setreg(d,v):
    c=movz(d, v & 0xFFFF)
    if (v>>16)&0xFFFF: c+=movk(d,(v>>16)&0xFFFF,1)
    if (v>>32)&0xFFFF: c+=movk(d,(v>>32)&0xFFFF,2)
    return c
def _sub_i(d,n,i):  return w(0xD1000000|(i<<10)|(n<<5)|d)
def _add_i(d,n,i):  return w(0x91000000|(i<<10)|(n<<5)|d)
def _strb(rt,rn):   return w(0x39000000|(rn<<5)|rt)
def _ldrb(rt,rn):   return w(0x39400000|(rn<<5)|rt)
def _cmp_i(n,i):    return w(0xF1000000|(i<<10)|(n<<5)|31)
def _cmpb_i(n,i):   return w(0x71000000|(i<<10)|(n<<5)|31)
def _b(off):        return w(0x14000000|((off//4)&0x03FFFFFF))
END=0x9800

def print_int(n):
    c  = _setreg(0,n)+mov_reg(9,0)+_setreg(10,END)+movz(11,10)
    c += _sub_i(10,10,1)+_strb(11,10)+movz(12,10)
    d=len(c)   # loop top: udiv must be inside the loop
    c += w(0x9AC0092D|(12<<16))+w(0x9B00A5AE|(12<<16))
    c += _add_i(14,14,48)+_sub_i(10,10,1)+_strb(14,10)+mov_reg(9,13)
    br=len(c)+4
    c += _cmp_i(9,0)
    c += bcond(1, d-len(c))
    c += movz(0,1)+mov_reg(1,10)+_setreg(2,END)+w(0xCB0A0042)+movz(8,64)+w(0xD4000001)
    return c+EXIT

R2=[]
for n in [0,7,42,12345,999999,2147483647]:
    _,o,e = run(print_int(n))
    ok = o == (str(n)+"\n").encode()
    R2.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} print_int({n})".ljust(34) + f"got={o!r}")

print()
print(f"{sum(R2)}/{len(R2)} runtime helpers verified")
sys.exit(0 if (all(R) and all(R2)) else 1)
