#!/usr/bin/env python3
"""Verify the Sovren AArch64 runtime helpers by executing them on an emulated ARM64 CPU.
   pip install unicorn capstone ; python3 arm64/verify_runtime.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rt import *
from unicorn import *
from unicorn.arm64_const import *

EXIT = movz(8,93)+SVC
HEAP = 0x200000
HP   = 0x9E00
NL   = 0x9F00

def call(code, mem=None, cnt=400000):
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM); mu.mem_map(0, 0x400000)
    mu.mem_write(0x10000, code)
    for a,d in (mem or []): mu.mem_write(a,d)
    mu.reg_write(UC_ARM64_REG_SP, 0x100000)
    out = bytearray()
    def hi(uc, i, u):
        nr = uc.reg_read(UC_ARM64_REG_X8)
        if nr == 64:
            b_=uc.reg_read(UC_ARM64_REG_X1); n=uc.reg_read(UC_ARM64_REG_X2)
            out.extend(uc.mem_read(b_,n)); uc.reg_write(UC_ARM64_REG_X0,n)
        elif nr == 93: uc.emu_stop()
        elif nr == 222: uc.reg_write(UC_ARM64_REG_X0, HEAP)
        else: uc.reg_write(UC_ARM64_REG_X0, 0)
    mu.hook_add(UC_HOOK_INTR, hi)
    try: mu.emu_start(0x10000, 0x10000+len(code), count=cnt)
    except UcError as e: return None, bytes(out), str(e)
    return mu.reg_read(UC_ARM64_REG_X0), bytes(out), None

def f_strlen():
    c  = mov_reg(9,0)+movz(0,0)
    top=len(c)
    c += add_r(10,9,0)+ldrb(11,10)+cmpw_i(11,0)
    ex=len(c); c += bcond(EQ,0)
    c += add_i(0,0,1)
    bp=len(c); c += b(top-bp)
    end=len(c); c = c[:ex]+bcond(EQ,end-ex)+c[ex+4:]
    return c+RET

def f_streq():
    c  = mov_reg(9,0)+mov_reg(10,1)+movz(11,0)
    top=len(c)
    c += add_r(12,9,11)+add_r(13,10,11)+ldrb(14,12)+ldrb(15,13)+cmpw_r(14,15)
    ne=len(c); c += bcond(NE,0)
    c += cmpw_i(14,0)
    eq=len(c); c += bcond(EQ,0)
    c += add_i(11,11,1)
    bp=len(c); c += b(top-bp)
    neo=len(c); c += movz(0,0)+RET
    eqo=len(c); c += movz(0,1)+RET
    c = c[:ne]+bcond(NE,neo-ne)+c[ne+4:]
    c = c[:eq]+bcond(EQ,eqo-eq)+c[eq+4:]
    return c

def f_print():
    c  = w(0xA9BF7BFD)+w(0x910003FD)+mov_reg(19,0)
    c += mov_reg(9,19)+movz(20,0)
    top=len(c)
    c += add_r(10,9,20)+ldrb(11,10)+cmpw_i(11,0)
    ex=len(c); c += bcond(EQ,0)
    c += add_i(20,20,1)
    bp=len(c); c += b(top-bp)
    end=len(c); c = c[:ex]+bcond(EQ,end-ex)+c[ex+4:]
    c += movz(0,1)+mov_reg(1,19)+mov_reg(2,20)+movz(8,64)+SVC
    c += setreg(9,NL)+movz(11,10)+strb(11,9)
    c += movz(0,1)+setreg(1,NL)+movz(2,1)+movz(8,64)+SVC
    c += w(0xA8C17BFD)+RET
    return c

def f_print_int():
    c  = w(0xA9BF7BFD)+w(0x910003FD)
    c += mov_reg(9,0)+setreg(10,NL+0x40)+movz(11,10)
    c += sub_i(10,10,1)+strb(11,10)+movz(12,10)
    d=len(c)
    c += udiv(13,9,12)+msub(14,13,12,9)+add_i(14,14,48)
    c += sub_i(10,10,1)+strb(14,10)+mov_reg(9,13)+cmp_i(9,0)
    c += bcond(NE, d-len(c))
    c += movz(0,1)+mov_reg(1,10)+setreg(2,NL+0x40)+sub_r(2,2,10)
    c += movz(8,64)+SVC+w(0xA8C17BFD)+RET
    return c

def f_alloc():
    c  = mov_reg(19,0)+setreg(9,HP)+ldr(10,9)+cmp_i(10,0)
    nz=len(c); c += bcond(NE,0)
    c += movz(0,0)+setreg(1,0x1000000)+movz(2,3)+movz(3,34)+w(0x92800004)+movz(5,0)+movz(8,222)+SVC
    c += mov_reg(10,0)
    nzo=len(c); c = c[:nz]+bcond(NE,nzo-nz)+c[nz+4:]
    c += str_(19,10)+add_i(11,10,8)+add_r(12,11,19)+add_i(12,12,7)
    c += w(0x927DF18C)+setreg(9,HP)+str_(12,9)+mov_reg(0,11)
    return c+RET

def call1(fn, x0=None, x1=None, mem=None):
    pre = b''
    if x0 is not None: pre += setreg(0,x0)
    if x1 is not None: pre += setreg(1,x1)
    code = pre + bl(4+len(EXIT)) + EXIT + fn
    return call(code, mem)

R=[]
def chk(name, got, want):
    ok = got==want; R.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name:32s} got={got!r} want={want!r}")

for s in [b"", b"a", b"hello", b"x"*33]:
    r,_,_ = call1(f_strlen(), x0=0x9000, mem=[(0x9000, s+b"\0")])
    chk(f"strlen len={len(s)}", r, len(s))

for a,bb,wnt in [(b"abc",b"abc",1),(b"abc",b"abd",0),(b"",b"",1),(b"ab",b"abc",0),(b"abc",b"ab",0)]:
    r,_,_ = call1(f_streq(), x0=0x9000, x1=0x9100, mem=[(0x9000,a+b"\0"),(0x9100,bb+b"\0")])
    chk(f"str_eq {a!r},{bb!r}", r, wnt)

for s in [b"hello arm", b"", b"a longer line"]:
    _,o,_ = call1(f_print(), x0=0x9000, mem=[(0x9000, s+b"\0")])
    chk(f"print {s[:12]!r}", o, s+b"\n")

for n in [0,7,42,12345,999999,2147483647]:
    _,o,_ = call1(f_print_int(), x0=n)
    chk(f"print_int {n}", o, (str(n)+"\n").encode())

r,_,_ = call1(f_alloc(), x0=100)
chk("alloc returns data ptr", r, HEAP+8)

body=f_alloc()
c=bytearray(); c+=movz(0,100); b1=len(c); c+=bl(0); c+=mov_reg(21,0)
c+=movz(0,48); b2=len(c); c+=bl(0); c+=mov_reg(22,0); c+=sub_r(0,22,21); c+=EXIT
fs=len(c); c+=body; c[b1:b1+4]=bl(fs-b1); c[b2:b2+4]=bl(fs-b2)
r,_,_=call(bytes(c))
chk("alloc gap 8-aligned", r, 112)

c=bytearray(); c+=movz(0,100); bb2=len(c); c+=bl(0); c+=sub_i(1,0,8)+ldr(0,1)+EXIT
fs=len(c); c+=body; c[bb2:bb2+4]=bl(fs-bb2)
r,_,_=call(bytes(c))
chk("alloc size header", r, 100)

print()
print(f"{sum(R)}/{len(R)} ARM64 runtime helpers verified on emulated CPU")
sys.exit(0 if all(R) else 1)
