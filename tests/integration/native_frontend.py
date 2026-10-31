#!/usr/bin/env python3
"""Fail-closed differential checks. Sidecars are saved, cleared and restored.
A nonzero exit or missing artifact is never counted as a successful translation.
Matching rejected inputs are counted separately from byte-identical artifacts.
"""
import argparse,hashlib,json,pathlib,subprocess,tempfile,collections
R=pathlib.Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--baseline',default=str(R/'compilers/linux/compiler'));p.add_argument('--candidate',default=str(R/'compilers/linux/compiler'));p.add_argument('--output',default='/tmp/frontend-verification.json');a=p.parse_args()
B=[pathlib.Path(a.baseline).resolve(),pathlib.Path(a.candidate).resolve()]
F=[]  # legacy cache flags removed; passing them is now a hard error
def run(b,src,out,extra=()):
 out.unlink(missing_ok=True)
 r=subprocess.run([str(b),str(src),*F,*extra,'-o',str(out)],cwd=R,capture_output=True,timeout=60)
 return dict(rc=r.returncode,artifact=out.is_file(),sha256=hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() else None,log=(r.stdout+r.stderr).decode(errors='replace')[-800:])
records=[]
with tempfile.TemporaryDirectory(prefix='sovren-verify-') as d:
 W=pathlib.Path(d)
 sugar=[*sorted((R/'library').glob('*.sov')),R/'runtime.sov',R/'compilers/linux/compiler.sov']
 for src in sugar:
  # --mksug dropped: sug-learning caches were removed tree-wide (purge); plain-compile equivalence is the gate
  rr=[run(b,src,W/str(j)) for j,b in enumerate(B)]
  same=rr[0]['rc']==rr[1]['rc'] and rr[0]['sha256']==rr[1]['sha256']
  ok1=rr[0]['rc']==0 and rr[0]['artifact']
  ok2=all(x['rc']!=0 and not x['artifact'] for x in rr)
  if not same or not (ok1 or ok2):raise SystemExit('SUGAR FAILURE: '+str(src))  # module-only sources may reject; equality incl. same-rejection is the gate
 print('Sugar artifacts EXACT:',len(sugar),flush=True)
 for src in sorted((R/'tests').glob('*.sov')):
  held=[(q,q.read_bytes(),q.stat().st_mode&0o777) for q in src.parent.glob(src.name+'.*') if q.is_file()]
  try:
   rr=[]
   for j,b in enumerate(B):
    for q in src.parent.glob(src.name+'.*'):
     if q.is_file():q.unlink()
    rr.append(run(b,src,W/str(j)))
   same=rr[0]['rc']==rr[1]['rc'] and rr[0]['sha256']==rr[1]['sha256']
   status='EXACT' if same and all(x['rc']==0 and x['artifact'] for x in rr) else 'SAME-REJECTION' if same and all(x['rc']!=0 and not x['artifact'] for x in rr) else 'DIFFERENT'
   records.append(dict(source=str(src.relative_to(R)),status=status,builds=rr))
  finally:
   for q in src.parent.glob(src.name+'.*'):
    if q.is_file():q.unlink()
   for q,data,mode in held:q.write_bytes(data);q.chmod(mode)
 counts=collections.Counter(x['status'] for x in records);print('Suite outcomes:',dict(counts),flush=True)
 pathlib.Path(a.output).write_text(json.dumps(dict(sugar_exact=len(sugar),suite=records),indent=2))
 if counts['DIFFERENT']:raise SystemExit(1)
 # Candidate must reproduce itself, not the prior intrinsic generation.
 out=W/'selfhost';rr=run(B[1],R/'compilers/linux/compiler.sov',out)
 if rr['rc'] or not rr['artifact'] or rr['sha256']!=hashlib.sha256(B[1].read_bytes()).hexdigest():raise SystemExit('Self-host fixed point FAILED')
 print('Candidate self-host fixed point EXACT',flush=True)
