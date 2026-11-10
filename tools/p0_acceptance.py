#!/usr/bin/env python3
"""Fail-closed Linux-only P0 acceptance over executed, pinned evidence.
This does not turn unsupported legacy cells into passes or assert speed parity.
"""
import argparse,hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads((R/p).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',default='work/p0/p0-input-manifest.json');ap.add_argument('--output',default='work/p0/P0-ACCEPTANCE.json');a=ap.parse_args();checks=[]
 def check(name,ok,**details):
  checks.append({'name':name,'pass':bool(ok),**details});print(('PASS ' if ok else 'FAIL ')+name)
 pins=load(a.manifest);check('source-and-binary-pins',all((R/p).is_file() and sha(R/p)==h for p,h in pins.items()))
 cc=sha(R/'compilers/linux/compiler');g=load('work/p0/gate.json');ig=load('work/p0/instrumented-gate.json');profile=load('work/p0/profile-qualification.json');syscalls=load('work/p0/syscall-gate.json');paired=load('work/p0/paired-workloads.json')
 check('ordinary-linux-correctness',g['all_pass'] and g['sha256']==cc,cells=len(g['cells']))
 fixed=[x for x in g['cells'] if x['name']=='ordinary-g2-equals-g3'];check('ordinary-fixed-point',len(fixed)==1 and fixed[0]['ok'] and len(set(fixed[0]['generations']))==1 and fixed[0]['generations'][0]==cc)
 check('instrumented-correctness',ig['all_pass'] and ig['sha256']==profile['instrumented_compiler_sha256'],cells=len(ig['cells']))
 check('counter-oracles-and-byte-identity',profile['all_pass'] and profile['ordinary_compiler_sha256']==cc and profile['oracle_cases']==2096 and all(w['byte_identical'] for w in profile['workloads']))
 check('executed-syscall-policy',syscalls['all_pass'] and syscalls['compiler_sha256']==cc and syscalls['fork_workers_traced'])
 check('matched-workloads',paired['all_pass'] and all(w['correctness_qualified'] and w['runs']>=21 for w in paired['workloads']) and paired['pins'].get(str(R/'work/p0/final.g2'))==cc)
 check('battery', 'ALL PASS (5/5)' in (R/'work/p0/battery-p0.log').read_text())
 check('timing-harness-unit-tests',bool(re.search(r'Ran 5 tests.*\n\nOK', (R/'work/p0/speed-tests-p0.log').read_text(),re.S)))
 check('no-cache-guards',all(x['ok'] for x in g['cells'] if x['name'] in ('no-cache-source-tripwire','no-new-sidecars','fresh-source-mutation')))
 scope=load('tools/linux_scope.json');allowed={x['name']:x for x in scope['excluded_assertions']};integration=load('work/p0/full-suite-p0.json');ledger=[]
 for suite in integration:
  text=(R/('work/p0/'+suite['name']+'-p0.stdout')).read_text();failures=re.findall(r'^FAIL (.*)$',text,re.M);unknown=sorted(set(failures)-set(allowed))
  consistent=suite['rc']==(1 if failures else 0) and suite['failed']==len(failures) and suite['passed']>=300
  check(suite['name']+'-integration-no-unexpected-linux-failures',consistent and not unknown,legacy_passed=suite['passed'],legacy_failed=suite['failed'],legacy_not_run=suite['not_run'],unexpected=unknown)
  for name in failures:ledger.append({'suite':suite['name'],'name':name,'legacy_result':'FAIL','scope':'non-Linux','reason':allowed.get(name,{}).get('reason','UNCLASSIFIED')})
  if 'launcher binaries are byte-fresh' in failures:
   block=text.split('FAIL launcher binaries are byte-fresh',1)[1].split('\nok ',1)[0]
   check(suite['name']+'-launcher-failure-is-windows-prerequisite','compilers/windows/compiler' in block and 'no compiler at' in block)
  if 'the x86 back ends share one copy of the folded tasks' in failures:
   block=text.split('FAIL the x86 back ends share one copy of the folded tasks',1)[1].split('\nok ',1)[0]
   check(suite['name']+'-source-architecture-failure-is-non-linux','windows back end' in block)
 report={'schema':1,'P0_linux_complete':all(x['pass'] for x in checks),'project_speed_parity_complete':False,'scope':'Linux compiler correctness and measurement baseline; non-Linux implementations are explicitly outside user scope','compiler_sha256':cc,'checks':checks,'legacy_non_linux_failures_retained':ledger,'profile_scope':profile['scope'],'speedup_or_parity_claimed':False}
 (R/a.output).write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(not report['P0_linux_complete'])
if __name__=='__main__':main()
