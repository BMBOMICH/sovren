#!/usr/bin/env python3
"""Real-file persistence and identity checks. A directory link cannot pass."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from backend_support import load,integrity
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default='/tmp/physical-layout.json');a=p.parse_args();rows=[]
for e in load():
 source=R/e['source'];legacy=R/e['compatibility_source'];folders=[R/e['canonical_directory'],*(R/v for v in e.get('views',[]))]
 assert source.is_file() and not source.is_symlink() and source.stat().st_size>100,e['id']
 assert legacy.is_file() and not legacy.is_symlink() and 'include ' in legacy.read_text()
 for folder in folders:
  assert folder.is_dir() and not folder.is_symlink(),folder
  for name in ['compiler.sov','compiler']:assert (folder/name).is_file() and not (folder/name).is_symlink(),folder
 assert not integrity(e,views=True),(e['id'],integrity(e,views=True))
 rows.append(dict(target=e['id'],implementation=e['source'],regular_files=True,pass_test=True))
# Direct real-file launchers must work, not merely point at metadata.
with tempfile.TemporaryDirectory(prefix='sovren-layout-') as td:
 w=Path(td);src=w/'input.sov';src.write_text('main:\n    print 42\n')
 for name in ['c-language','javascript','typescript','linux']:
  e=next(e for e in load() if e['id']==name);hashes=[]
  for folder in [R/e['canonical_directory'],*(R/v for v in e.get('views',[])),(R/e['executable']).parent]:
   exe=folder/'compiler';exe.chmod(exe.stat().st_mode|0o111);out=w/'output';out.unlink(missing_ok=True)
   q=subprocess.run([str(exe),str(src),'--uncached','-o',str(out)],cwd=R,capture_output=True,timeout=30);assert q.returncode==0,(exe,q.stdout,q.stderr)
   hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
  assert len(set(hashes))==1,name
  rows.append(dict(target=name,case='physical-entrypoints-byte-identical',pass_test=True))
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(dict(pass_all=True,results=rows),indent=2)+'\n');print('Physical layout:',len(rows),'checks PASS')
