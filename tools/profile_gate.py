#!/usr/bin/env python3
"""Build and qualify a separate untimed instrumented compiler.
The production compiler emits no counter probes. Counters have an explicit
scope, not an assertion that every memory access in every scanner is covered.
"""
import argparse,hashlib,json,subprocess,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args):
 p=subprocess.run(list(map(str,args)),cwd=R,capture_output=True,timeout=90)
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).decode(errors='replace')[-4000:])
 return p
KEYS=['bytes_scanned','bytes_copied','allocations','allocation_requested_bytes','hash_probes','fallbacks']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--flag',action='append',default=[]);ap.add_argument('--output',default='work/p0/profile-qualification.json');ap.add_argument('--workdir',default='work/p0');a=ap.parse_args();cc=(R/a.compiler).resolve();w=R/a.workdir;w.mkdir(parents=True,exist_ok=True);instrument=w/'compiler-profile';instrument.unlink(missing_ok=True)
 run([cc,R/'compilers/linux/compiler.sov',*a.flag,'--instrument-compiler','-o',instrument]);rows=[]
 for name,source in [('hello','tests/hello.sov'),('x86ins','tests/x86ins.sov'),('all','tests/all.sov'),('self','compilers/linux/compiler.sov')]:
  outputs=[]
  for label,compiler in [('ordinary',cc),('instrumented',instrument)]:
   out=w/('profile-'+name+'-'+label+'.bin');out.unlink(missing_ok=True)
   p=run([compiler,R/source,*a.flag,'--prof','-o',out]);j=json.loads(p.stderr)
   (w/('profile-'+name+'-'+label+'.stdout')).write_bytes(p.stdout);(w/('profile-'+name+'-'+label+'.stderr')).write_bytes(p.stderr)
   outputs.append({'label':label,'artifact_sha256':sha(out),'profile':j})
  normal,measured=outputs;counter=measured['profile']['counters']
  if normal['artifact_sha256']!=measured['artifact_sha256']:raise RuntimeError('instrumentation changed emitted program: '+name)
  if normal['profile']['instrumented']!=0 or measured['profile']['instrumented']!=1:raise RuntimeError('wrong counter availability')
  if not all(isinstance(counter[k],int) and counter[k]>0 for k in KEYS):raise RuntimeError('missing counter work')
  totals={k:sum(m['counters'][k] for m in measured['profile']['marks']) for k in KEYS}
  if any(totals[k]>counter[k] or totals[k]<0 for k in KEYS):raise RuntimeError('phase counters overlap or are negative')
  rows.append({'name':name,'source':source,'source_sha256':sha(R/source),'outputs':outputs,'byte_identical':True,'phase_totals':totals,'initialization_outside_first_interval':{k:counter[k]-totals[k] for k in KEYS}})
  print('PASS profile '+name,flush=True)
 oracle=w/'counter-oracles';oracle.unlink(missing_ok=True);run([cc,R/'tests/performance/counters.sov','--instrument-compiler','-o',oracle]);p=run([oracle]);want='0\n2096\n1\n2\n320\n7\n'
 if p.stdout.decode()!=want:raise RuntimeError('exact scan/allocation/copy oracle failed: '+repr(p.stdout))
 print('PASS 2096 scan alignment/length oracles; exact allocator/copy oracle',flush=True)
 # The instrumented compiler must not change counters as a function of timing.
 repeat=w/'profile-hello-instrumented.bin';repeat.unlink(missing_ok=True)
 p=run([instrument,R/'tests/hello.sov',*a.flag,'--prof','-o',repeat]);again=json.loads(p.stderr)
 if again['counters']!=rows[0]['outputs'][1]['profile']['counters']:raise RuntimeError('operation counts are not repeatable')
 report={'schema':1,'flags':a.flag,'ordinary_compiler_sha256':sha(cc),'instrumented_compiler_sha256':sha(instrument),'ordinary_timed_path_instrumented':False,'all_pass':True,'oracle_cases':2096,'allocator_oracle':{'calls':2,'requested_bytes':320},'copy_oracle_bytes':7,'workloads':rows,'scope':{'bytes_scanned':'Actual load widths in native SWAR/vector length routines and native interner hash/compare loops; other scanners are not claimed to be counted. Aligned prefix/terminator reads are included.','bytes_copied':'Payload bytes requested of memcpy and native concat/substring copies; overlapping tail implementation writes count once. Other hand-written copy loops are not claimed to be counted.','allocations':'Runtime heap allocator entries, including its fast return path; not kernel mmap call count.','hash_probes':'Native intern_kid and intern_fast table slot reads; other symbol tables are not claimed to be counted.','fallbacks':'Entries into intern_kid_full and intern_fast_do.','phase_intervals':'Disjoint consecutive mark endpoints aggregated by label; timings are for the instrumented serial process, not ordinary translation speed. Startup bookkeeping before first interval is explicitly separate.'}}
 owner='';contract=[];lines=(R/'compilers/linux/compiler.sov').read_text().splitlines()
 for index,line in enumerate(lines):
  if re.fullmatch(r'\w+(?: \w+)*:',line):owner=line
  for label in re.findall(r'mark\("([^"\n]+)"\)',line):
   contract.append({'endpoint':label,'owner_function':owner,'line':index+1,'preceding_source':lines[max(0,index-2):index],'following_source':lines[index+1:index+3]})
 report['phase_endpoint_contract']=contract
 report['phase_ownership_note']='Endpoint intervals partition the serial execution timeline; labels aggregate repeated visits. Ownership is anchored to exact source call sites, not inferred parser/lexer costs. Initialization outside the first interval is reported separately.'
 (R/a.output).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
