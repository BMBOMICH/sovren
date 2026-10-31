#!/usr/bin/env python3
"""Serial/parallel byte equivalence, real syscall faults, and CPU-affinity scaling."""
import argparse,hashlib,json,os,statistics,subprocess,tempfile,time
from pathlib import Path
R=Path(__file__).resolve().parents[2];p=argparse.ArgumentParser();p.add_argument('--compiler',default=str(R/'compilers/linux/compiler'));p.add_argument('--output',default='/tmp/parallel-sugar.json');a=p.parse_args();B=Path(a.compiler).resolve();rows=[];timings=[]
def run(cmd,out,affinity=None):
 out.unlink(missing_ok=True);start=time.perf_counter_ns()
 try:q=subprocess.run(list(map(str,cmd)),cwd=R,capture_output=True,timeout=60,preexec_fn=(lambda:os.sched_setaffinity(0,affinity)) if affinity else None)
 except subprocess.TimeoutExpired:return dict(rc=124,sha=None,ms=60000,log='timeout')
 return dict(rc=q.returncode,sha=hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() else None,ms=(time.perf_counter_ns()-start)/1e6,log=q.stderr.decode(errors='replace')[-1000:])
with tempfile.TemporaryDirectory(prefix='sovren-parallel-') as td:
 W=Path(td);inj=W/'inject';subprocess.run(['cc','-O2',R/'tests/conformance/inject_worker.c','-o',inj],check=True)
 line='    x: 2 ;; if x = 2 -> x: x + 1\n';text='main:\n'+line*20000
 src=W/'input.sov';out=W/'sugar';src.write_text(text)
 args=[B,src,'--mksug','--uncached','-o',out]
 serial=run([*args,'--serial-sugar'],out);assert serial['rc']==0 and serial['sha']
 for mode in ['plain','fork-second','pipe-second','worker-kill','worker-partial','read-eintr','wait-eintr']:
  cmd=[*args,'--parallel-sugar'] if mode=='plain' else [inj,mode,*args,'--parallel-sugar']
  r=run(cmd,out);ok=r['rc']==0 and r['sha']==serial['sha'];rows.append(dict(case=mode,result=r,pass_test=ok));print(mode,'PASS' if ok else 'FAIL',r['log'],flush=True)
 # Stateful constructs must produce exactly the serial representation. No
 # threshold widening; these cases belong to the conservative fallback path.
 for label,body in [('block-sugar','main:\n    print:\n'+"        'hello'\n"*14000),('multiline-quote','main:\n    print "start\n'+'inside ;; -> text\n'*12000+'end"\n'),('comments','main:\n'+line*6000+'    ;; # comment\n'+line*6000),('CRLF',text.replace('\n','\r\n')),('no-final-newline',text.rstrip('\n'))]:
  src.write_text(body);s=run([*args,'--serial-sugar'],out);r=run(args,out);ok=s['rc']==r['rc']==0 and s['sha']==r['sha'];rows.append(dict(case=label,serial=s,parallel=r,pass_test=ok));print(label,'PASS' if ok else 'FAIL',flush=True)
 cpus=sorted(os.sched_getaffinity(0));available=sorted({n for n in [1,2,4] if n<=len(cpus)})
 for n in [65536,262144,786432,1572864]:
  content='main:\n'+line*(n//len(line));src.write_text(content)
  for count in available:
   samples={}
   for mode,flags in [('serial',['--serial-sugar']),('default',[]),('forced-parallel',['--parallel-sugar'])]:
    results=[run([*args,*flags],out,cpus[:count]) for _ in range(3)]
    samples[mode]=results
   good=all(r['rc']==0 for rs in samples.values() for r in rs) and len({r['sha'] for rs in samples.values() for r in rs})==1
   timings.append(dict(source_bytes=len(content),affinity_cpus=count,samples=samples,median_ms={k:statistics.median(r['ms'] for r in v) for k,v in samples.items()},pass_test=good))
report=dict(compiler_sha256=hashlib.sha256(B.read_bytes()).hexdigest(),results=rows,scaling=timings,notes=['Actual CPU-affinity restrictions, not measurements on different physical hosts.','Process wall time under ptrace is not a speed benchmark. Scaling samples do not use ptrace.','No memory-pressure/power-loss test; conservative stateful fallback; default worker eligibility starts at two affinity CPUs.'],pass_all=all(r['pass_test'] for r in rows+timings))
Path(a.output).write_text(json.dumps(report,indent=2));raise SystemExit(0 if report['pass_all'] else 1)
