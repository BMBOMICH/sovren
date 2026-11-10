#!/usr/bin/env python3
"""Trace native Linux children, including fork workers. No compiler cache or replay.
The initial exec is outside measurement. All later exec/network/ptrace/wall-clock
calls fail policy. Monotonic time is permitted for explicit profiling/scheduling.
"""
import argparse,collections,ctypes,json,os,signal,subprocess,time,hashlib
from pathlib import Path
LIB=ctypes.CDLL(None,use_errno=True)
LIB.ptrace.restype=ctypes.c_long
class Regs(ctypes.Structure):
 _fields_=[(x,ctypes.c_ulonglong) for x in 'r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()]
def ptrace(request,pid,addr=0,data=0):
 ctypes.set_errno(0);r=LIB.ptrace(request,pid,ctypes.c_void_p(addr),data if not isinstance(data,int) else ctypes.c_void_p(data))
 if r==-1 and ctypes.get_errno():raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
 return r
def trace(command,cwd):
 def child():ptrace(0,0)
 p=subprocess.Popen(command,cwd=cwd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=child)
 pid,status=os.waitpid(p.pid,0)
 if not os.WIFSTOPPED(status):raise RuntimeError('traced child did not stop')
 ptrace(0x4200,pid,0,1|2|4|8|0x100000)
 live={pid};enter={pid:True};counts=collections.Counter();calls=[];rc=None
 ptrace(24,pid)
 try:
  while live:
   pid,status=os.waitpid(-1,0)
   if os.WIFEXITED(status) or os.WIFSIGNALED(status):
    live.discard(pid)
    if pid==p.pid:rc=os.waitstatus_to_exitcode(status)
    continue
   sig=os.WSTOPSIG(status);event=status>>16
   if event in (1,2,3):
    new=ctypes.c_ulonglong();ptrace(0x4201,pid,0,ctypes.byref(new));live.add(new.value);enter[new.value]=True
   elif sig==signal.SIGTRAP|0x80:
    if enter.get(pid,True):
     regs=Regs();ptrace(12,pid,0,ctypes.byref(regs));n=int(regs.orig_rax);counts[n]+=1
     calls.append({'pid':pid,'nr':n,'arg0':int(regs.rdi)})
    enter[pid]=not enter.get(pid,True)
   deliver=0 if sig in (signal.SIGTRAP,signal.SIGTRAP|0x80,signal.SIGSTOP) else sig
   ptrace(24,pid,0,deliver)
 finally:
  for pid in live:
   try:os.kill(pid,signal.SIGKILL)
   except ProcessLookupError:pass
 p.returncode=rc
 return {'rc':rc,'syscalls':dict(sorted(counts.items())),'calls':calls}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--flag',action='append',default=[]);ap.add_argument('--output',default='work/p0/syscall-gate.json');a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];cc=str(Path(a.compiler).resolve());rows=[]
 for name,source,flags in [('ordinary-hello','tests/hello.sov',[]),('profiled-hello','tests/hello.sov',['--prof']),('ordinary-parallel','tests/all.sov',[])]:
  out=root/'work/p0'/('syscall-'+name+'.bin');out.unlink(missing_ok=True)
  row=trace([cc,str(root/source),*a.flag,*flags,'-o',str(out)],root);row['name']=name
  violations=[x for x in row['calls'] if 41<=x['nr']<=55 or x['nr'] in (58,59,96,101,201) or (x['nr']==228 and x['arg0']!=1)]
  if name=='ordinary-hello':violations += [x for x in row['calls'] if x['nr'] in (56,57,228)]
  if name=='profiled-hello' and not row['syscalls'].get(228):violations.append({'missing':'explicit profiling clock'})
  row['violations']=violations;row['ok']=row['rc']==0 and out.is_file() and not violations;rows.append(row)
  print(('PASS ' if row['ok'] else 'FAIL ')+name,flush=True)
 dest=root/a.output;dest.write_text(json.dumps({'schema':1,'flags':a.flag,'compiler_sha256':hashlib.sha256(Path(cc).read_bytes()).hexdigest(),'initial_exec_excluded':True,'fork_workers_traced':True,'cases':rows,'all_pass':all(x['ok'] for x in rows)},indent=2)+'\n')
 raise SystemExit(not all(x['ok'] for x in rows))
if __name__=='__main__':main()
