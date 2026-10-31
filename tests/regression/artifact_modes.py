#!/usr/bin/env python3
"""Deep function-call chains must run correctly at any depth (guards the
entry-task / call-return emission path), and repeated plain builds are
byte-identical. Cache-era mode comparison was removed with the caches."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
P=argparse.ArgumentParser();P.add_argument('--compiler',default=str(R/'compilers/linux/compiler'))
P.add_argument('--output',default='/tmp/artifact-modes.json');a=P.parse_args();B=str(Path(a.compiler).resolve());rows=[]
def build(src,out):
 out=Path(out);out.unlink(missing_ok=True)
 p=subprocess.run([B,str(src),'-o',str(out)],cwd=R,capture_output=True,timeout=60)
 sha=hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() else None
 rt=None
 if sha:
  q=subprocess.run([str(out)],capture_output=True,timeout=10);rt=[q.returncode,q.stdout.decode(errors='replace'),q.stderr.decode(errors='replace')]
 return dict(rc=p.returncode,sha=sha,runtime=rt)
with tempfile.TemporaryDirectory(prefix='sovren-modes-') as td:
 W=Path(td)
 for n in [4,40,400]:
  src=W/f'chain{n}.sov'
  src.write_text(''.join(f'f{i} x:\n    return '+(f'f{i+1}(x + {i})' if i<n-1 else f'x + {i}')+'\n' for i in range(n))+'main:\n    print f0(1)\n')
  want=1+sum(range(n))
  a0=build(src,W/'a');b0=build(src,W/'b')
  ok=a0['rc']==b0['rc']==0 and a0['sha']==b0['sha'] and a0['runtime']==[0,f'{want}\n','']
  rows.append(dict(chain_depth=n,pass_test=bool(ok)))
  print('chain',n,'PASS' if ok else 'FAIL',a0['runtime'],flush=True)
Path(a.output).write_text(json.dumps(rows,indent=2));raise SystemExit(0 if all(r['pass_test'] for r in rows) else 1)
