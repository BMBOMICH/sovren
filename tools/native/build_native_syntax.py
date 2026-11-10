#!/usr/bin/env python3
"""Reproduce the Linux native primary-parser byte emitter. Not a runtime tool."""
import argparse,hashlib,subprocess,tempfile,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1]
FLAGS='-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -fcf-protection=none -fno-builtin -ffreestanding -fPIC'.split()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--statements',action='store_true');a=ap.parse_args()
 source='native_statements.c' if a.statements else 'native_syntax.c'
 symbol='emit_nt_syntax_statements' if a.statements else 'emit_nt_syntax_build'
 with tempfile.TemporaryDirectory() as td:
  obj=Path(td)/'syntax.o';binary=Path(td)/'syntax.bin'
  subprocess.run(['gcc','-c',str(R/'tools'/source),'-o',str(obj),*FLAGS],check=True)
  assert not subprocess.check_output(['nm','-u',str(obj)]).strip(),'external references are forbidden'
  rel=subprocess.check_output(['readelf','-r',str(obj)],text=True)
  assert 'There are no relocations' in rel,'unresolved code/data relocation'
  subprocess.run(['objcopy','-O','binary','-j','.text',str(obj),str(binary)],check=True);b=binary.read_bytes()
  entry='syntax_statement_build_native' if a.statements else 'syntax_build_native'
  symbols=subprocess.check_output(['nm','-n',str(obj)],text=True).splitlines()
  offset=int(next(line.split()[0] for line in symbols if line.split()[-1]==entry),16)
  assert 0<=offset<len(b),'entry point outside code section'
  if offset:b=b'\xe9'+struct.pack('<i',offset)+b
 s='# unsafe-module\n# Generated from tools/'+source+'; allocation-free frontend.\n'+symbol+':\n    emit:\n'
 s+=''.join('        '+' '.join(map(str,b[i:i+16]))+'\n' for i in range(0,len(b),16));s+='    return 1\n'
 out=R/('compilers/linux/statements_native.sov' if a.statements else 'compilers/linux/syntax_native.sov')
 if a.check:assert out.read_text()==s,'native emitter is stale'
 else:out.write_text(s)
 print('PASS native parser emitter',len(b),'bytes, no relocations/external symbols; SHA256',hashlib.sha256(b).hexdigest())
if __name__=='__main__':main()
