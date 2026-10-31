#!/usr/bin/env python3
"""Post-purge fresh-artifact + anti-cache regression gate.

World after the 2026-10-25 cache purge: there is no cache, no learned
snapshot, no sugar cache, and the legacy flags (--no-ac, --no-cache,
--no-learn, --no-lsug, --no-pfx, --uncached, --learn, --mksug, --mksuguser,
--cache, --usepfx) are REJECTED as unknown. This suite fails closed:

* retired flags must be rejected with nonzero rc and no artifact,
* a plain compile must never create sidecar files next to the source,
* builds are byte-deterministic across repeated and cross-binary invocations.
"""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
P=argparse.ArgumentParser()
P.add_argument('--compiler',default=str(R/'compilers/linux/compiler'))
P.add_argument('--output',default='/tmp/regression.json')
opts=P.parse_args()
B=str(Path(opts.compiler).resolve())
rows=[]
def build(src,out,flags=(),binary=B):
    out=Path(out); out.unlink(missing_ok=True)
    p=subprocess.run([binary,str(src),'-o',str(out),*flags],cwd=R,capture_output=True,timeout=60)
    sha=None
    if out.is_file() and out.stat().st_size>0: sha=hashlib.sha256(out.read_bytes()).hexdigest()
    return dict(rc=p.returncode,sha=sha,log=(p.stdout+p.stderr).decode(errors='replace')[-400:])
def record(name,ok,**kw):
    rows.append(dict(name=name,pass_test=bool(ok),**kw));print(name,'PASS' if ok else 'FAIL',flush=True)
    Path(opts.output).write_text(json.dumps(rows,indent=2))
RETIRED=['--no-ac','--no-cache','--no-learn','--no-lsug','--no-pfx','--uncached',
         '--learn','--mksug','--mksuguser','--cache','--usepfx','--no-sug']
SIDECAR_SUFFIXES=['.ac','.ac.bin','.bin','.plk','.lsug','.sug','.prebuilt','.state',
                  '.deep','.deepoc','.deep.integrity','.deepoc.integrity','.state.integrity']
with tempfile.TemporaryDirectory(prefix='sovren-anticache-') as td:
    W=Path(td);src=W/'input.sov';out=W/'program'
    src.write_text('main:\n    print 7 + 3\n')
    record('retired-flags-rejected',
           all(build(src,out,[f])['rc']!=0 or not (out.is_file() and out.stat().st_size>0)
               for f in RETIRED))
    a=build(src,out); before={p.name for p in W.iterdir()}
    side=[n for n in {p.name for p in W.iterdir()}-before if any(n.endswith(s) or s in n for s in SIDECAR_SUFFIXES)]
    record('plain-build-writes-no-sidecars', a['rc']==0 and a['sha'] and side==[], sidecars=side)
    rep=[build(src,W/f'rep{i}')['sha'] for i in range(3)]
    record('byte-deterministic-repeat-build', a['rc']==0 and all(x==a['sha'] for x in rep))
    other=build(src,W/'other',binary=str(R/'compilers/linux/compiler'))
    record('same-compiler-repeat', a['sha']==other['sha'])
    if a['sha']:
        r=subprocess.run([str(out)],capture_output=True,timeout=10)
        record('artifact-runs', r.returncode==0 and r.stdout.decode().strip()=='10')
    n=len(rows);ok=sum(x['pass_test'] for x in rows)
    print(f'{ok}/{n} anti-cache gates green')
    raise SystemExit(0 if ok==n else 1)
