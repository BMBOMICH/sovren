#!/usr/bin/env python3
"""Nested include freshness: with caches gone, every compile reads current
sources; editing a nested include must change the next build immediately.
Temporary library fixtures are removed in finally; no existing file is changed.
"""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
P=argparse.ArgumentParser();P.add_argument('--compiler',default=str(R/'compilers/linux/compiler'))
P.add_argument('--output',default='/tmp/dependency-freshness.json');a=P.parse_args();B=Path(a.compiler).resolve();rows=[]
def run(args):return subprocess.run([str(B),*map(str,args)],cwd=R,capture_output=True,timeout=30)
def check(label,src,out,want):
 out.unlink(missing_ok=True);r=run([src,'-o',out]);got=None
 if r.returncode==0 and out.is_file():
  q=subprocess.run([str(out)],capture_output=True,timeout=10);got=[q.returncode,q.stdout.decode(errors='replace'),q.stderr.decode(errors='replace')]
 ok=r.returncode==0 and got==[0,str(want)+'\n',''];rows.append(dict(test=label,pass_test=ok,build_rc=r.returncode,runtime=got,expected=want));print(label,'PASS' if ok else 'FAIL',got,flush=True)
with tempfile.TemporaryDirectory(prefix='sovren-dependency-freshness-') as td:
 W=Path(td);stem=f'__dep_parent_{os.getpid()}';leaf=f'__dep_leaf_{os.getpid()}';par=R/'library'/f'{stem}.sov';child=R/'library'/f'{leaf}.sov'
 assert not par.exists() and not child.exists()
 try:
  child.write_text('deepcalc x:\n    return x + 2\n');par.write_text(f'include {leaf}.sov\n');src=W/'library-input.sov';src.write_text(f'use {stem}\nmain:\n    print deepcalc(1)\n')
  check('library-include-initial',src,W/'output',3)
  child.write_text('deepcalc x:\n    return x + 7\n');check('library-include-child-only-edit',src,W/'output',8)
  assert not any(Path(R/'library').glob(stem+'.sov.*')),'compile must not write library sidecars'
 finally:
  for p in R.joinpath('library').glob(stem+'.sov*'):p.unlink()
  for p in R.joinpath('library').glob(leaf+'.sov*'):p.unlink()
 child=W/'local.sov';child.write_text('deepcalc x:\n    return x + 2\n');src=W/'user-input.sov';src.write_text('include local.sov\nmain:\n    print deepcalc(1)\n')
 check('user-include-initial',src,W/'output',3)
 child.write_text('deepcalc x:\n    return x + 7\n');check('user-include-child-only-edit',src,W/'output',8)
Path(a.output).write_text(json.dumps(rows,indent=2));raise SystemExit(0 if all(r['pass_test'] for r in rows) else 1)
