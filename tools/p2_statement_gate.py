#!/usr/bin/env python3
"""Independent structured-statement metadata and block-edge oracle."""
from pathlib import Path
import argparse,ctypes,json,random,subprocess,tempfile,hashlib
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',default='work/p2/current-statement-gate.json');a=ap.parse_args();rng=random.Random(172813);cases=0
 with tempfile.TemporaryDirectory() as td:
  so=Path(td)/'statements.so';subprocess.run(['gcc','-shared','-fPIC','-O3','-fno-tree-vectorize',str(R/'tools/native_statements.c'),str(R/'tools/native_syntax.c'),'-o',str(so)],check=True)
  lib=ctypes.CDLL(str(so));build=lib.syntax_statement_build_native;build.argtypes=[ctypes.POINTER(ctypes.c_uint64),ctypes.POINTER(ctypes.c_uint64),ctypes.c_void_p,ctypes.c_void_p];build.restype=ctypes.c_uint64
  for batch in range(200):
   lines=[]
   for i in range(rng.randrange(0,80)):
    line=b' '*rng.randrange(0,25)+rng.choice([b'',b'# note : = "',b'if x is 1',b'if not',b'return f(1, 2)',b'xx: "x : = y"',b'xx: "q\\\" : = x"',b'xx: "unterminated\\',b'\tbad: 3',bytes(rng.randrange(1,256) for _ in range(rng.randrange(0,60)))])+rng.choice([b'',b' ',b'\t',b'\r'])
    lines.append(line)
   n=len(lines);buffers=[ctypes.create_string_buffer(s) for s in lines];lv=(ctypes.c_uint64*(n+2))(n,n,*[ctypes.addressof(b) for b in buffers]);out=(ctypes.c_uint64*(2+14*n))()
   assert build(lv,None,None,None)==sum(128+(len(x)+1)*64 for x in lines)
   assert build(lv,out,None,None)==n;expected=[]
   for s in lines:
    inside=False;col=eq=quote=-1;tab=0;j=0;ind=len(s)-len(s.lstrip(b' '))
    while j<len(s):
     c=s[j]
     if inside:
      if c==92 and j+1<len(s):j+=1
      elif c==34:inside=False
     elif c==9:tab=1
     elif c==34:
      inside=True
      if quote<0:quote=j
     elif c==58 and col<0:col=j
     elif c==61 and eq<0:eq=j
     j+=1
    first=ind
    while first<len(s) and s[first]<=32:first+=1
    head=first
    while head<len(s) and s[head]>32 and s[head] not in (58,40):head+=1
    expected.append([quote,ind,col,eq,tab,int(bool(s) and s[-1]<33),len(s),-1,n,int(first<len(s) and s[first]!=35),head,0,0,0])
   stack=[];bad=0
   for i,row in enumerate(expected):
    if row[9]:
     while stack and expected[stack[-1]][1]>=row[1]:expected[stack.pop()][8]=i
     if stack:row[7]=stack[-1]
     stack.append(i)
    bad+=bool(row[4]);row[11]=bad
   for i,row in enumerate(expected):
    for col,value in enumerate(row):assert out[2+col*n+i]==value%(2**64),(batch,i,col,value,out[2+col*n+i],lines)
   budget=build(lv,None,None,None);arena=ctypes.create_string_buffer(budget+32);ctypes.memset(ctypes.addressof(arena)+budget,0xa7,32)
   build(lv,out,arena,ctypes.cast(lib.syntax_build_native,ctypes.c_void_p))
   for i,row in enumerate(expected):
    for col,value in enumerate(row[:12]):assert out[2+col*n+i]==value%(2**64),(batch,i,col,value,out[2+col*n+i],lines)
   assert bytes(arena)[budget:budget+32]==b'\xa7'*32
   cases+=n
  lines=[b'xx: 1+2',b'if id(3) != 0',b'as long as x < 4',b'print f(1,2)',b'return x+2',b'f(1)',b'join hh',b'wipe ptr',b'raise err(3)',b'stop 2',b'if not',b'xx: "bad']
  n=len(lines);buffers=[ctypes.create_string_buffer(s) for s in lines];lv=(ctypes.c_uint64*(n+2))(n,n,*[ctypes.addressof(b) for b in buffers]);out=(ctypes.c_uint64*(2+14*n+2))();out[-1]=out[-2]=0xdeadbeef
  budget=build(lv,None,None,None);arena=ctypes.create_string_buffer(budget+32);ctypes.memset(ctypes.addressof(arena)+budget,0xa7,32)
  build(lv,out,arena,ctypes.cast(lib.syntax_build_native,ctypes.c_void_p));cursor=ctypes.addressof(arena)
  for i,role in enumerate([1,2,2,3,4,5,6,7,8,9,0,0]):
   address=out[2+12*n+i];assert out[2+13*n+i]==role,(i,lines[i],role,out[2+13*n+i])
   if role:
    assert address==cursor and address%16==0
    h=(ctypes.c_uint64*16).from_address(address);assert h[7]==0x4e4154495645 and h[6]<h[2]
    cursor+=(128+h[2]*40+15)&~15
   else:assert address==0
  assert cursor<=ctypes.addressof(arena)+budget and bytes(arena)[budget:budget+32]==b'\xa7'*32
  assert out[-1]==out[-2]==0xdeadbeef
 result={'parsed_roles_and_packed_arena':True,'batches':200,'statements':cases,'seed':172813,'columns_per_statement':14,'all_pass':True,'source_sha256':hashlib.sha256((R/'tools/native_statements.c').read_bytes()).hexdigest()};(R/a.output).write_text(json.dumps(result,indent=2)+'\n');print('PASS',cases,'statement records; 14 columns, quotes/escapes, tabs, parents and exclusive block ends')
if __name__=='__main__':main()
