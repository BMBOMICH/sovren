#!/usr/bin/env python3
"""Correctness-qualified matched-observable-work latency measurements.
Every timing is a new translator process and a newly removed/rebuilt output.
Execution checking is outside translation timing, repeated after EVERY build.
These small workloads do not establish bulk MB/s or whole-language parity.
"""
import argparse,hashlib,json,os,platform,statistics,subprocess,tempfile
from pathlib import Path
from speed_gate import Command,checked
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--baseline',default='work/p0/qualified.g2');ap.add_argument('--sa',default='/home/user/baseline/sa');ap.add_argument('--runs',type=int,default=21);ap.add_argument('--output',default='work/p0/paired-workloads.json');a=ap.parse_args()
 if a.runs<1:ap.error('runs must be positive')
 bins={'baseline':(ROOT/a.baseline).resolve(),'candidate':(ROOT/a.compiler).resolve(),'sa':Path(a.sa).resolve()};pins={str(p):sha(p) for p in bins.values()};rows=[]
 with tempfile.TemporaryDirectory(prefix='sovren-paired-') as td:
  d=Path(td)
  for name,expected in [('exit7',7),('sum',sum(range(5000))%256),('calls',sum(range(64))%256)]:
   sv=ROOT/'tests/performance'/(name+'.sov');sa=sv.with_suffix('.sa');pins.update({str(p):sha(p) for p in (sv,sa)})
   times={k:[] for k in bins};hashes={k:[] for k in bins};names=list(bins)
   for n in range(a.runs):
    for label in names[n%3:]+names[:n%3]:
     out=d/(label+'.bin');cc=bins[label];argv=[str(cc),str(sa),str(out)] if label=='sa' else [str(cc),str(sv),'-o',str(out)]
     elapsed=checked(Command(argv,out),cwd=ROOT)
     os.chmod(out,0o755);p=subprocess.run([str(out)],capture_output=True,timeout=5)
     if p.returncode!=expected or p.stdout or p.stderr:raise RuntimeError(f'wrong output: {name}/{label}: {p.returncode}/{p.stdout!r}/{p.stderr!r}')
     times[label].append(elapsed);hashes[label].append(sha(out))
   stable=all(len(set(h))==1 for h in hashes.values())
   if not stable:raise RuntimeError('nondeterministic output')
   row={'name':name,'source_sovren':str(sv),'source_sa':str(sa),'expected_exit':expected,'expected_stdout':'','expected_stderr':'','correctness_qualified':True,'runs':a.runs,'timings':{k:{'samples_seconds':v,'median_ms':statistics.median(v)*1000,'best_ms':min(v)*1000} for k,v in times.items()},'artifact_hashes':{k:v[0] for k,v in hashes.items()},'artifact_stability_checked_each_round':True}
   row['candidate_over_sa_latency']=statistics.median(times['candidate'])/statistics.median(times['sa']);row['candidate_over_baseline_latency']=statistics.median(times['candidate'])/statistics.median(times['baseline']);rows.append(row)
   print(name,{k:round(v['median_ms'],3) for k,v in row['timings'].items()},flush=True)
 if any(sha(p)!=h for p,h in pins.items()):raise RuntimeError('inputs changed during measurement')
 report={'schema':1,'candidate_compiler_sha256':sha(bins['candidate']),'host':platform.uname()._asdict(),'policy':{'fresh_process':True,'outputs_removed_before_each_translation':True,'execution_checked_after_each_translation':True,'compiler_artifact_reuse':False,'os_pages_evicted':False,'shipped_sa_may_reuse_in_process':True,'metric':'matched-observable-work latency, not bulk byte throughput','optimization_parity_claimed':False},'pins':pins,'workloads':rows,'all_pass':all(x['correctness_qualified'] for x in rows)}
 (ROOT/a.output).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
