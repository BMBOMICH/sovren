import struct
def w(v): return struct.pack('<I',v&0xFFFFFFFF)
def movz(d,i,s=0): return w(0xD2800000+(s<<21)+((i&0xFFFF)<<5)+d)
def movk(d,i,s):   return w(0xF2800000+(s<<21)+((i&0xFFFF)<<5)+d)
def setreg(d,v):
    c=movz(d, v & 0xFFFF)
    if (v>>16)&0xFFFF: c+=movk(d,(v>>16)&0xFFFF,1)
    if (v>>32)&0xFFFF: c+=movk(d,(v>>32)&0xFFFF,2)
    if (v>>48)&0xFFFF: c+=movk(d,(v>>48)&0xFFFF,3)
    return c
def mov_reg(d,s):  return w(0xAA0003E0+(s<<16)+d)
def bcond(c,off):  return w(0x54000000|(((off//4)&0x7FFFF)<<5)|c)
def b(off):        return w(0x14000000|((off//4)&0x03FFFFFF))
def bl(off):       return w(0x94000000|((off//4)&0x03FFFFFF))
def sub_i(d,n,i):  return w(0xD1000000|(i<<10)|(n<<5)|d)
def add_i(d,n,i):  return w(0x91000000|(i<<10)|(n<<5)|d)
def ldrb(rt,rn):   return w(0x39400000|(rn<<5)|rt)
def strb(rt,rn):   return w(0x39000000|(rn<<5)|rt)
def cmp_i(n,i):    return w(0xF1000000|(i<<10)|(n<<5)|31)
def cmp_r(n,m):    return w(0xEB00001F|(m<<16)|(n<<5))
def cmpb_i(n,i):   return w(0x71000000|(i<<10)|(n<<5)|31)  # 32-bit cmp
RET=w(0xD65F03C0)
EXIT=movz(8,93)+w(0xD4000001)

def strlen():
    # x0 = ptr -> x0 = length
    c  = mov_reg(9,0)
    c += movz(10,0)
    top = len(c)
    c += w(0x8B0A0134)          # add x20,x9,x10
    c += ldrb(11,20)
    c += cmpb_i(11,0)
    end_at = len(c)
    c += bcond(0,0)             # b.eq end (patch)
    c += add_i(10,10,1)
    c += b(top-len(c))
    endoff = len(c)
    c = c[:end_at] + bcond(0, endoff-end_at) + c[end_at+4:]
    c += mov_reg(0,10)
    return c

def streq():
    # x0,x1 -> 1 if equal
    c  = mov_reg(9,0)+mov_reg(10,1)+movz(12,0)
    top=len(c)
    c += w(0x8B0C0134)          # add x20,x9,x12
    c += w(0x8B0C0155)          # add x21,x10,x12
    c += ldrb(13,20)
    c += ldrb(14,21)
    c += w(0x6B0E01BF)          # cmp w13,w14
    ne_at=len(c); c += bcond(1,0)   # b.ne notequal
    c += cmpb_i(13,0)
    eq_at=len(c); c += bcond(0,0)   # b.eq equal
    c += add_i(12,12,1)
    c += b(top-len(c))
    ne_off=len(c)
    c += movz(0,0); c += RET
    eq_off=len(c)
    c += movz(0,1)
    c = c[:ne_at]+bcond(1,ne_off-ne_at)+c[ne_at+4:]
    c = c[:eq_at]+bcond(0,eq_off-eq_at)+c[eq_at+4:]
    return c
