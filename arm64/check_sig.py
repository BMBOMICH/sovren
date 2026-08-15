#!/usr/bin/env python3
"""Validate the ad-hoc code signature Sovren writes into --ios binaries."""
import sys, struct, hashlib
d=open(sys.argv[1],'rb').read()
ncmds=struct.unpack('<I',d[16:20])[0]
off=32; sig=None
for _ in range(ncmds):
    cmd,sz=struct.unpack('<II',d[off:off+8])
    if cmd==0x1d:
        sig=struct.unpack('<II',d[off+8:off+16])
    off+=sz
if not sig:
    print("no LC_CODE_SIGNATURE"); sys.exit(1)
dataoff,datasize=sig
blob=d[dataoff:dataoff+datasize]
magic,length,count=struct.unpack('>III',blob[0:12])
t,o=struct.unpack('>II',blob[12:20])
cd=blob[o:]
cmagic,clen,ver,flags=struct.unpack('>IIII',cd[0:16])
hoff,ioff,nsp,ncs=struct.unpack('>IIII',cd[16:32])
climit,=struct.unpack('>I',cd[32:36])
hsize,htype,plat,pgsz=cd[36],cd[37],cd[38],cd[39]
ident=cd[ioff:cd.index(0,ioff)].decode()
ok = magic==0xfade0cc0 and cmagic==0xfade0c02 and flags&2 and htype==2 and hsize==32
for p in range(ncs):
    plen=min(4096, climit-p*4096)
    if hashlib.sha256(d[p*4096:p*4096+plen]).digest()!=bytes(cd[hoff+p*32:hoff+p*32+32]):
        ok=False
print(f"SuperBlob     {magic:#x}")
print(f"CodeDirectory {cmagic:#x} version {ver:#x} flags {flags:#x}")
print(f"identifier '{ident}'  pages {ncs}  codeLimit {climit}  SHA-256")
print("VALID AD-HOC SIGNATURE" if ok else "INVALID")
sys.exit(0 if ok else 1)
