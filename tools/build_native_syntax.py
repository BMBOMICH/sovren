#!/usr/bin/env python3
"""Reproduce the Linux native primary-parser byte emitter. Not a runtime tool."""
import argparse,hashlib,subprocess,tempfile,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1]
FLAGS='-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -fcf-protection=none -fno-builtin -ffreestanding -fPIC'.split()
# NOTE: gcc blobs may use r8-r11: in the Sovren call convention rdi,rsi,rdx,
# rcx,r8,r9,r10 are the arg registers (copyargs), so they are dead across
# calls, and r11 is syscall-scratch like rcx. The real twin ABI requirement
# is on the WALK side: nt_fl/no_frame/fn_save_n must be set for every name
# try_native_body plants (see the sx_force_native list in walk_range).
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--statements',action='store_true');ap.add_argument('--uscan',action='store_true');ap.add_argument('--emit',action='store_true');ap.add_argument('--cxread',action='store_true');ap.add_argument('--collect',action='store_true');ap.add_argument('--stbuild',action='store_true');ap.add_argument('--lord',action='store_true');ap.add_argument('--dstores',action='store_true');ap.add_argument('--dlitter',action='store_true');ap.add_argument('--dce',action='store_true');ap.add_argument('--kgrow',action='store_true');ap.add_argument('--listfind',action='store_true');ap.add_argument('--linesfast',action='store_true');a=ap.parse_args()
 modes={'statements':('native_statements.c','emit_nt_syntax_statements','syntax_statement_build_native','statements_native.sov'),'uscan':('native_uscan.c','emit_nt_u_scan_core','u_scan_core_native','uscan_native.sov'),'emit':('native_emit.c','emit_nt_syntax_emit_tw','sov_emit_tw_native','emit_native.sov'),'cxread':('native_cxread.c','emit_nt_cx_read','cx_read_native','cxread_native.sov'),'collect':('native_collect.c','emit_nt_collect_body','collect_body_native','collect_native.sov'),'stbuild':('native_stbuild.c','emit_nt_st_build','st_build_native','stbuild_native.sov'),'lord':('native_lord.c','emit_nt_lord_build','lord_build_native','lord_native.sov'),'dstores':('native_dstores.c','emit_nt_dce_stores','dstores_native','dstores_native.sov'),'dlitter':('native_dlitter.c','emit_nt_dce_litter','dlitter_native','dlitter_native.sov'),'dce':('native_dce.c','emit_nt_dce','dce_native','dce_native.sov'),'kgrow':('native_kgrow.c','emit_nt_kgrow_ht','kgrow_native','kgrow_native.sov'),'listfind':('native_listfind.c','emit_nt_list_find','emit_nt_list_find','listfind_native.sov'),'linesfast':('native_linesfast.c','emit_nt_lines_of_fast','lines_of_fast_native','linesfast_native.sov')}
 sel=[(k,v) for k,v in modes.items() if getattr(a,k)]
 if not sel: sel=[('default',('native_syntax.c','emit_nt_syntax_build','syntax_build_native','syntax_native.sov'))]
 source,symbol,entry,outname=sel[0][1]
 with tempfile.TemporaryDirectory() as td:
  obj=Path(td)/'syntax.o';binary=Path(td)/'syntax.bin'
  subprocess.run(['gcc','-c',str(R/'tools'/source),'-o',str(obj),*FLAGS],check=True)
  assert not subprocess.check_output(['nm','-u',str(obj)]).strip(),'external references are forbidden'
  rel=subprocess.check_output(['readelf','-r',str(obj)],text=True)
  assert 'There are no relocations' in rel,'unresolved code/data relocation'
  subprocess.run(['objcopy','-O','binary','-j','.text',str(obj),str(binary)],check=True);b=binary.read_bytes()
  symbols=subprocess.check_output(['nm','-n',str(obj)],text=True).splitlines()
  offset=int(next(line.split()[0] for line in symbols if line.split()[-1]==entry),16)
  assert 0<=offset<len(b),'entry point outside code section'
  if offset:b=b'\xe9'+struct.pack('<i',offset)+b
 # emit8-packed group: one emit8() call per 8 bytes (8x fewer interpreted
 # calls when the self-compile walks this body), emit4/emit tail keeps the
 # byte count exact; same bytes in the same order as the old emit: rows.
 import struct as _st
 words=[_st.unpack('<Q',b[i:i+8])[0] for i in range(0,len(b)-7,8)]
 rem=b[len(b)&~7:]
 s='# unsafe-module\n# Generated from tools/'+source+'; allocation-free frontend.\n'+symbol+':\n    emit8:\n'
 s+=''.join('        '+' '.join(str(w) for w in words[i:i+2])+'\n' for i in range(0,len(words),2))
 if len(rem)>=4:
  s+='    emit4:\n        '+str(_st.unpack('<I',rem[:4])[0])+'\n'
  rem=rem[4:]
 if rem:
  s+='    emit:\n        '+' '.join(str(x) for x in rem)+'\n'
 s+='    return 1\n'
 out=R/('compilers/linux/'+outname)
 if a.check:assert out.read_text()==s,'native emitter is stale'
 else:out.write_text(s)
 print('PASS native parser emitter',len(b),'bytes, no relocations/external symbols; SHA256',hashlib.sha256(b).hexdigest())

if __name__=='__main__':main()
