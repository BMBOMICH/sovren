#!/usr/bin/env python3
"""Install a preverified fleet; file replacements are atomic, not power-loss durable."""
import argparse,json,os,shutil,subprocess,tarfile,tempfile
from pathlib import Path
from backend_support import ROOT,load,digest,source_snapshot
p=argparse.ArgumentParser();p.add_argument('--staged',required=True,type=Path);p.add_argument('--evidence',required=True,type=Path);a=p.parse_args();D=a.evidence.resolve();W=a.staged.resolve()
report=json.loads((D/'conformance.json').read_text());fleet=json.loads((W/'verification.json').read_text());entries=load();byid={e['id']:e for e in entries}
assert report['pass_all'] and not report['skipped'] and all(x['oracle_agrees'] for x in report['native_oracle_comparisons'])
assert report['implementation_sources_sha256']==source_snapshot(),'implementation changed since semantic tests'
assert len(fleet)==len(entries) and {x['target'] for x in fleet}==set(byid)
for name in ['output-safety','shared-ir','parallel-sugar','constant-evaluation','physical-layout']:assert json.loads((D/(name+'.json')).read_text())['pass_all'],name
for name in ['cache-regressions','dependency-caches','artifact-modes']:assert all(x['pass_test'] for x in json.loads((D/(name+'.json')).read_text())),name
front=json.loads((D/'frontend.json').read_text());assert front['sugar_exact']>=220 and all(x['status'] in ['EXACT','SAME-REJECTION'] for x in front['suite'])
assert 'fixed point EXACT' in (D/'frontend.log').read_text()
assert 'MATRIX 11/11 PASS' in (D/'edit-matrix.log').read_text()
changes=[]
for row in fleet:
 e=byid[row['target']];src=W/row['target']/'compiler';dst=ROOT/e['executable'];sha=digest(src)
 assert row['pass'] and row['build1']['sha256']==row['build2']['sha256']==sha,row['target']
 assert row['source_sha256']==digest(ROOT/e['source'])
 assert row['builder_sha256']==report['compiler_sha256']['native']
 changes.append((src,dst,sha))
for name,key in [('c-language','c'),('javascript','js'),('typescript','ts'),('linux','native')]:assert digest(W/name/'compiler')==report['compiler_sha256'][key]
# Durable compact rollback material, with no copies in aliases.
backup=D/'previous-fleet.tar.gz'
with tarfile.open(backup,'w:gz') as tar:
 for _,dst,sha in changes:
  if digest(dst)!=sha:tar.add(dst,arcname=str(dst.relative_to(ROOT)),recursive=False)
installed=[]
try:
 for src,dst,sha in changes:
  fd,tmp=tempfile.mkstemp(prefix='.compiler-install-',dir=dst.parent);os.close(fd)
  try:
   shutil.copyfile(src,tmp);os.chmod(tmp,0o755);os.replace(tmp,dst)
  finally:Path(tmp).unlink(missing_ok=True)
  assert digest(dst)==sha;installed.append(str(dst.relative_to(ROOT)))
except BaseException:
 with tarfile.open(backup) as tar:
  for member in tar.getmembers():
   if member.name in installed:
    dest=ROOT/member.name;dest.write_bytes(tar.extractfile(member).read());dest.chmod(0o755)
 raise
subprocess.run(['python3','tools/backend_registry.py'],cwd=ROOT,check=True)
record=dict(release=D.name,installed=len(installed),native_sha256=report['compiler_sha256']['native'],backends={e['id']:digest(ROOT/e['executable']) for e in entries},implementation_sources_sha256=source_snapshot(),semantic_evidence_sha256=digest(D/'conformance.json'),rollback_archive=str(backup.relative_to(ROOT)),full_language_complete=False,universal_SA_parity=False)
(D/'deployment.json').write_text(json.dumps(record,indent=2)+'\n');print('Installed',len(installed),'verified driver binaries')
