from pathlib import Path
import os,ctypes,subprocess,sys
from capstone import *
libc=ctypes.CDLL(None,use_errno=True);libc.ptrace.restype=ctypes.c_long
class Regs(ctypes.Structure):_fields_=[(n,ctypes.c_ulonglong) for n in 'r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()]
p=Path(sys.argv[1]).resolve();child=subprocess.Popen([str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=lambda:libc.ptrace(0,0,0,0));pid=child.pid
os.waitpid(pid,0);libc.ptrace(7,pid,0,0)
_,st=os.waitpid(pid,0)
while os.WIFSTOPPED(st) and os.WSTOPSIG(st) != 11:
 libc.ptrace(7,pid,0,0)
 _,st=os.waitpid(pid,0)
if os.WIFSTOPPED(st):
 reg=Regs();libc.ptrace(12,pid,0,ctypes.byref(reg));print('signal',os.WSTOPSIG(st),'regs',{n:hex(getattr(reg,n)) for n in ['rip','rsp','rbp','rax','rbx','rcx','rdx','rsi','rdi']})
 maps=Path(f'/proc/{pid}/maps').read_text();print(maps)
 for line in maps.splitlines():
  if str(p) in line:
   a,b=[int(x,16) for x in line.split()[0].split('-')]
   if a<=reg.rip<b:
    off=reg.rip-a+int(line.split()[2],16);d=p.read_bytes();print('fileoffset',hex(off))
    for x in Cs(CS_ARCH_X86,CS_MODE_64).disasm(d[off-32:off+32],off-32):print(hex(x.address),x.mnemonic,x.op_str)
 libc.ptrace(8,pid,0,0)
else:print('exit',st)
