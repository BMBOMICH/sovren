#!/usr/bin/env python3
"""Full-language completion is distinct from a passing declared-subset release."""
import argparse,json
from pathlib import Path
from backend_support import ROOT,load,integrity,source_snapshot,digest
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default='/tmp/language-completeness.json');p.add_argument('--coverage',type=Path,default='/tmp/language-coverage.json');a=p.parse_args()
contract=json.loads((ROOT/'targets/capabilities.json').read_text());blockers=[];entries=load()
coverage_path=a.coverage
coverage=json.loads(coverage_path.read_text()) if coverage_path.is_file() else {}
bound=coverage.get('implementation_sources_sha256')==source_snapshot()
coverage_cells=coverage.get('cells',[])
for e in entries:
 missing=[f for f in contract['required_full_language_features'] if contract['profiles'][e['capability_profile']]['features'].get(f)!='tested']
 unproven=[]
 for feature in contract['required_full_language_features']:
  proof=[c for c in coverage_cells if c.get('target')==e['id'] and c.get('feature')==feature]
  valid=bound and len(proof)==1 and proof[0].get('pass_test') is True and proof[0].get('executed') is True and proof[0].get('compiler_sha256')==e['executable_sha256'] and bool(proof[0].get('case_ids'))
  if not valid:unproven.append(feature)
 if missing or unproven or not e.get('full_language_certified'):blockers.append(dict(target=e['id'],missing_or_unverified_features=missing,missing_source_binary_bound_execution_evidence=unproven,full_language_certified=e.get('full_language_certified',False)))
 errors=integrity(e)
 if errors:blockers.append(dict(target=e['id'],integrity_errors=errors))
report=dict(full_language_complete=not blockers,backend_count=len(entries),scope='Language/backend completeness only. Speed and actual-host matrices are separate gates.',blockers=blockers)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print('COMPLETE' if not blockers else 'NOT COMPLETE: '+str(len(blockers))+' blockers');raise SystemExit(bool(blockers))
