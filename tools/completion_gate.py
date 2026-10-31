#!/usr/bin/env python3
"""Fail-closed global completion accounting. A local subset can never turn it green."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,default='/tmp/v58');a=p.parse_args();D=a.evidence_dir;D.mkdir(parents=True,exist_ok=True);blockers=[]
def read(path):
 if not path.is_file():blockers.append({'missing_evidence':str(path.relative_to(R))});return None
 try:return json.loads(path.read_text())
 except (ValueError,OSError) as e:blockers.append({'invalid_evidence':str(path.relative_to(R)),'error':str(e)});return None
registry=read(R/'compilers/registry.json');policy=read(R/'compilers/required-matrix.json');H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();hosted=read(D/'host-coverage.json')
if registry:
 for e in registry['entries']:
  if not e.get('full_language_certified'):blockers.append({'backend':e['id'],'reason':'full required language semantics not certified'})
  if not (R/e['executable']).is_file() or H(R/e['executable'])!=e['executable_sha256']:blockers.append({'backend':e['id'],'reason':'stale binary binding'})
if policy:
 for host in policy['required_hosts']:
  entry=(hosted or {}).get('hosts',{}).get(host,{})
  if not entry.get('full_required_matrix_passed',False):blockers.append({'host':host,'reason':'complete real-host matrix absent or failing'})
for filename,count,key in [('parity.json',20,'pass'),('edited-parity.json',16,'pass_test')]:
 result=read(D/filename)
 if result:
  digest=(result.get('compiler') or {}).get('sha256',result.get('compiler_sha256'))
  if digest!=H(R/'compilers/linux/compiler'):blockers.append({'gate':filename,'reason':'compiler identity mismatch'})
  cells=result.get('cells',[])
  if len(cells)!=count:blockers.append({'gate':filename,'reason':'missing required cells','expected':count,'actual':len(cells)})
  for cell in cells:
   if not cell.get(key,False):blockers.append({'gate':filename,'mode':cell.get('mode'),'functions':cell.get('functions'),'reason':'per-cell parity threshold not met'})
for filename in ['conformance.json','output-safety.json','parallel-sugar.json']:
 result=read(D/filename)
 if result and not result.get('pass_all',False):blockers.append({'gate':filename,'reason':'correctness failure or missing tool'})
# Completeness evidence must enumerate coverage, not merely set a certification flag.
coverage=read(D/'coverage-cells.json')
if coverage and registry and policy:
 from itertools import product
 cells=coverage.get('cells',[]);seen={};pinned=H('/tmp/sa')
 for c in cells:
  key=tuple(c.get(k) for k in ['target','host','workload','mode'])
  if key in seen:blockers.append({'reason':'duplicate coverage cell','cell':key})
  valid=c.get('semantics_pass',False) and c.get('artifact_valid',False) and c.get('latency_upper_95ci',float('inf'))<=1 and c.get('throughput_lower_95ci',0)>=1 and c.get('sa_sha256')==pinned
  seen[key]=valid
 expected=product([e['id'] for e in registry['entries']],policy['required_hosts'],policy['workload_families'],policy['modes'])
 missing=[key for key in expected if not seen.get(key,False)]
 if missing:blockers.append({'reason':'required full matrix cells absent or failing','count':len(missing),'sample':missing[:12]})
else:blockers.append({'reason':'full workload/backend/host coverage is not supplied by the measured Linux subset'})
report=dict(schema=1,all_14_complete=not blockers,universal_SA_parity=not blockers,blockers=blockers,policy='compilers/required-matrix.json')
(D/'completion-status.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS' if not blockers else f'NOT COMPLETE: {len(blockers)} explicit blockers');raise SystemExit(0 if not blockers else 1)
