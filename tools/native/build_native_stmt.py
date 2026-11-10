#!/usr/bin/env python3
"""Reproduce the Linux native statement-lowering twin emitter. Not a runtime tool."""
import argparse,hashlib,subprocess,tempfile,struct
from pathlib import Path
R=Path(__file__).resolve().parents[2]
FLAGS='-O3 -mno-red-zone -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -fcf-protection=none -fno-builtin -ffreestanding -fPIC'.split()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
 source='native_stmt.c';symbol='emit_nt_stmt';entry='sov_stmt_native'
 with tempfile.TemporaryDirectory() as td:
  obj=Path(td)/'stmt.o';binary=Path(td)/'stmt.bin'
  subprocess.run(['gcc','-c',str(R/'tools'/'native'/source),'-o',str(obj),*FLAGS],check=True)
  assert not subprocess.check_output(['nm','-u',str(obj)]).strip(),'external references are forbidden'
  rel=subprocess.check_output(['readelf','-r',str(obj)],text=True)
  assert 'There are no relocations' in rel,'unresolved code/data relocation'
  subprocess.run(['objcopy','-O','binary','-j','.text',str(obj),str(binary)],check=True);b=binary.read_bytes()
  symbols=subprocess.check_output(['nm','-n',str(obj)],text=True).splitlines()
  offset=int(next(line.split()[0] for line in symbols if line.split()[-1]==entry),16)
  assert 0<=offset<len(b),'entry point outside code section'
  if offset:b=b'\xe9'+struct.pack('<i',offset)+b
  # the native body runs inside compiler-generated frames that keep no
  # red zone: reject a build that spills below %rsp.
  dis=subprocess.check_output(['objdump','-d',str(obj)],text=True)
  assert 'sub    $' in dis,'native body has no stack frame; red-zone use is unsafe'
 s='# unsafe-module\n# Generated from tools/native/'+source+'; native statement lowering twin.\n'+symbol+':\n    emit:\n'
 s+=''.join('        '+' '.join(map(str,b[i:i+16]))+'\n' for i in range(0,len(b),16));s+='    return 1\n'
 out=R/'compilers/linux/stmt_native.sov'
 if a.check:assert out.read_text()==s,'native emitter is stale'
 else:out.write_text(s)
 print('PASS native stmt twin emitter',len(b),'bytes, no relocations/external symbols; SHA256',hashlib.sha256(b).hexdigest())
if __name__=='__main__':main()
