from pathlib import Path
import subprocess,os,ctypes,signal,struct
from capstone import *
R=Path(__file__).resolve().parents[1];os.chdir(R);p=R/'compilers/linux/compiler.sov';s=p.read_text()
new=s.replace('    off: intern_nz(s)\n','''    off: intern_nz(s)
    if n is 6
        if peek_byte(s, 0) is 67
            p0db: _sov_heap_alloc(8)
            poke_i64(p0db, 0, strb + 16 + off)
            syscall(1, 2, p0db, 8, 0, 0, 0)
            syscall(62, syscall(39, 0, 0, 0, 0, 0, 0), 19, 0, 0, 0)
''',1)
p.write_text(new)
try:
 c=subprocess.run(['./compilers/linux/compiler',str(p),'-o','work/p0/watch'],capture_output=True);assert c.returncode==0
finally:p.write_text(s)
libc=ctypes.CDLL(None,use_errno=True);libc.ptrace.restype=ctypes.c_long
class Regs(ctypes.Structure):_fields_=[(n,ctypes.c_ulonglong) for n in 'r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()]
def ptr(req,pid,addr=0,data=0):
 r=libc.ptrace(req,pid,ctypes.c_void_p(addr),ctypes.c_void_p(data))
 if r==-1 and ctypes.get_errno():raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
 return r
child=subprocess.Popen(['work/p0/watch','/home/user/investigation/deeper/library_str.sov','-o','work/p0/watch.bin'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,preexec_fn=lambda:libc.ptrace(0,0,0,0))
pid=child.pid;os.waitpid(pid,0);ptr(7,pid);_,status=os.waitpid(pid,0);print('stop',status,flush=True)
if os.WIFSTOPPED(status):
 raw=os.read(child.stderr.fileno(),8);addr=struct.unpack('<Q',raw)[0];print('watch',hex(addr),flush=True)
 ptr(6,pid,848,addr & ~7);ptr(6,pid,904,0x90001)
 for i in range(10):
  ptr(7,pid);_,st=os.waitpid(pid,0)
  if not os.WIFSTOPPED(st):print('exit',st);break
  reg=Regs();ptr(12,pid,0,ctypes.addressof(reg));print('event',os.WSTOPSIG(st),hex(reg.rip),flush=True)
  if os.WSTOPSIG(st)==5:
   maps=Path(f'/proc/{pid}/maps').read_text();Path('work/p0/watch.maps').write_text(maps)
   for line in maps.splitlines():
    if '/work/p0/watch' in line:
     a,b=map(lambda x:int(x,16),line.split()[0].split('-'))
     if a<=reg.rip<b:
      off=reg.rip-a+int(line.split()[2],16);d=(R/'work/p0/watch').read_bytes();print('file offset',hex(off));md=Cs(CS_ARCH_X86,CS_MODE_64)
      for x in md.disasm(d[max(0,off-40):off+30],off-40):print(hex(x.address),x.mnemonic,x.op_str)
      print('registers',{n:hex(getattr(reg,n)) for n in ['rax','rbx','rcx','rdx','rdi','rsi','r8','r9','r10','r11']})
   break
 ptr(8,pid)
