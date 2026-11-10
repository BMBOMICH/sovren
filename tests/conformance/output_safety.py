#!/usr/bin/env python3
"""Real output faults, inode aliases, and same-output concurrent writers."""
import argparse,concurrent.futures,hashlib,json,os,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2];p=argparse.ArgumentParser();p.add_argument('--native',type=Path,default=R/'compilers/linux/compiler');p.add_argument('--output',default=str('/tmp/output-safety.json'));a=p.parse_args();rows=[]
def invoke(cmd):
 try:
  q=subprocess.run(list(map(str,cmd)),cwd=R,capture_output=True,timeout=30);return q.returncode,(q.stdout+q.stderr).decode(errors='replace')[-2000:]
 except subprocess.TimeoutExpired:return 124,'timeout'
def h(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
with tempfile.TemporaryDirectory(prefix='sovren-output-safety-') as td:
 w=Path(td);inject=w/'inject';subprocess.run(['cc','-O2',R/'tests/conformance/inject_write.c','-o',inject],check=True)
 for target in ['native']:
  exe=a.native
  src=w/'input.sov';src.write_text('main:\n'+''.join(f'    print {i}\n' for i in range(200)));out=w/'artifact'
  rc,log=invoke([exe,src,'-o',out]);assert rc==0 and out.stat().st_size>0;gold=h(out)
  for mode in ['short','eintr','io','kill']:
   out.write_text('STALE');rc,log=invoke([inject,mode,exe,src,'-o',out])
   ok=(rc==0 and h(out)==gold) if mode in ['short','eintr'] else (rc not in [0,124,125] and not out.exists())
   rows.append(dict(target=target,case='injected-'+mode,rc=rc,pass_test=ok,log=log,artifact_sha256=h(out)))
   for tmp in w.glob('artifact.tmp.*'):tmp.unlink()
  for alias_type in ['same-path','relative-alias','hardlink','symlink']:
   before=src.read_bytes();alias=src
   if alias_type in ['hardlink','symlink']:
    alias=w/'alias';alias.unlink(missing_ok=True)
    if alias_type=='hardlink':os.link(src,alias)
    else:alias.symlink_to(src)
   if alias_type=='relative-alias':alias=str(w)+'/./input.sov'
   rc,log=invoke([exe,src,'-o',alias]);rows.append(dict(target=target,case=alias_type,rc=rc,pass_test=rc not in [0,124] and src.read_bytes()==before,log=log))
  out.write_text('stale');rc,log=invoke([exe,src,'--unsupported-mode','-o',out]);rows.append(dict(target=target,case='unsupported-mode',rc=rc,pass_test=rc not in [0,124] and not out.exists(),log=log))
  inputs=[];allowed=set()
  for i in range(16):
   s=w/f'parallel-{i}.sov';s.write_text('main:\n'+''.join(f'    print {i+j}\n' for j in range(1+i*17)));inputs.append(s)
   rc,log=invoke([exe,s,'-o',out]);assert rc==0;allowed.add(h(out))
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda s:invoke([exe,s,'-o',out]),inputs))
  rows.append(dict(target=target,case='16-same-output-writers',returncodes=[x[0] for x in results],artifact_sha256=h(out),pass_test=all(x[0]==0 for x in results) and h(out) in allowed and not list(w.glob('artifact.tmp.*'))))
Path(a.output).write_text(json.dumps(dict(results=rows,pass_all=all(x['pass_test'] for x in rows)),indent=2));print('Output safety',sum(x['pass_test'] for x in rows),'/',len(rows));raise SystemExit(0 if all(x['pass_test'] for x in rows) else 1)
