#!/usr/bin/env python3
"""Rotating fresh-process A/B timings on exactly the same current input tree.
Outputs must match byte-for-byte across both compilers on every round.
SA is a separately labelled byte-throughput comparator, not equivalent work.
"""
import argparse,hashlib,json,os,platform,statistics,sys,tempfile
from pathlib import Path
from speed_gate import Command,checked,source_manifest
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('baseline');ap.add_argument('candidate');ap.add_argument('--baseline-flag',action='append',default=[]);ap.add_argument('--candidate-flag',action='append',default=[]);ap.add_argument('--runs',type=int,default=21);ap.add_argument('--output',default='work/p1/ab-speed.json');ap.add_argument('--allow-layout-diff',action='store_true',help='permit baseline/candidate artifacts to differ in codegen layout; each must still be byte-stable across its own rounds, and both must exit 0');a=ap.parse_args()
 if a.runs<1:ap.error('runs must be positive')
 SA_ROOT=R.parent/'sovren-assembler'
 if not SA_ROOT.exists():SA_ROOT=R.parent/'downloads'/'sovren-assembler'
 sys.path.insert(0,str(SA_ROOT/'t'))
 import srcs as _srcs
 bins={'baseline':(R/a.baseline).resolve(),'candidate':(R/a.candidate).resolve(),'sa':(SA_ROOT/'sa').resolve()};sa=Path(_srcs.ensure('bench6.sa.asm')).resolve();pins={str(p):sha(p) for p in [*bins.values(),sa]};impl=source_manifest();rows=[]
 with tempfile.TemporaryDirectory(prefix='sovren-ab-') as td:
  d=Path(td)
  for name,source in [('x86ins','tests/x86ins.sov'),('all','tests/all.sov'),('self','compilers/linux/compiler.sov')]:
   src=R/source;pins[str(src)]=sha(src);flat=d/'expanded';checked(Command([str(bins['candidate']),str(src),*a.candidate_flag,'--flat','-o',str(flat)],flat));expanded=flat.stat().st_size;flat_hash=sha(flat)
   times={k:[] for k in bins};hashes={k:[] for k in bins};names=list(bins)
   for n in range(a.runs):
    for label in names[n%3:]+names[:n%3]:
     out=d/(label+'.bin');argv=[str(bins[label]),str(sa),str(out)] if label=='sa' else [str(bins[label]),str(src),*(a.baseline_flag if label=='baseline' else a.candidate_flag),'-o',str(out)]
     times[label].append(checked(Command(argv,out),cwd=R));hashes[label].append(sha(out))
    if not a.allow_layout_diff and hashes['baseline'][-1]!=hashes['candidate'][-1]:raise RuntimeError('A/B output differs: '+name)
   if any(len(set(v))!=1 for v in hashes.values()):raise RuntimeError('artifact not stable')
   row={'name':name,'source':source,'expanded_bytes':expanded,'expanded_sha256':flat_hash,'runs':a.runs,'timings':{k:{'samples_seconds':v,'median_ms':statistics.median(v)*1000,'best_ms':min(v)*1000,'quartiles_ms':[q*1000 for q in statistics.quantiles(v,n=4)] if len(v)>1 else []} for k,v in times.items()},'artifacts_sha256':{k:v[0] for k,v in hashes.items()},'byte_identical_every_round':True,'layout_diff_allowed':bool(a.allow_layout_diff),'baseline_over_candidate':statistics.median(times['baseline'])/statistics.median(times['candidate']),'candidate_median_MBps':expanded/statistics.median(times['candidate'])/1e6,'sa_median_MBps':sa.stat().st_size/statistics.median(times['sa'])/1e6};rows.append(row)
   print(name,{k:round(v['median_ms'],3) for k,v in row['timings'].items()},'speedup',round(row['baseline_over_candidate'],3),flush=True)
 if impl!=source_manifest() or any(sha(p)!=h for p,h in pins.items()):raise RuntimeError('inputs changed')
 result={'schema':1,'flags':{'baseline':a.baseline_flag,'candidate':a.candidate_flag},'host':platform.uname()._asdict(),'cpu_affinity':sorted(os.sched_getaffinity(0)),'cpuinfo_sha256':sha('/proc/cpuinfo'),'pins':pins,'implementation_sources_sha256':impl,'policy':{'fresh_process':True,'outputs_deleted_before_every_translation':True,'rotating_order':True,'compiler_artifact_reuse':False,'os_pages_evicted':False,'sa_comparison':'different assembly corpus, byte throughput only; shipped SA may reuse internally','ab_comparison':'same source, explicitly recorded flags; output byte identity required every round'},'workloads':rows,'all_outputs_byte_identical':not a.allow_layout_diff,'speed_parity_claimed':False}
 (R/a.output).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
