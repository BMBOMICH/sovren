#!/usr/bin/env python3
"""Discover and safely invoke registered backends; legacy paths stay available."""
import argparse,json,subprocess
from pathlib import Path
from backend_support import ROOT,load,integrity,select
p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
l=s.add_parser('list');l.add_argument('--kind',choices=['native','transpiler','ir-emitter','evaluator','partial'])
d=s.add_parser('describe');d.add_argument('target')
b=s.add_parser('build');b.add_argument('--allow-experimental',action='store_true');b.add_argument('--require-feature',action='append',default=[]);b.add_argument('target');b.add_argument('args',nargs=argparse.REMAINDER)
s.add_parser('verify');s.add_parser('prepare');a=p.parse_args();entries=load()
if a.cmd=='prepare':
 for e in entries:
  paths=[e['executable']]+[n for n in e.get('entrypoint_sha256',{}) if Path(n).name=='compiler']
  for name in paths:
   f=ROOT/name;f.chmod(f.stat().st_mode|0o111)
 print('Executable permissions restored for registered binaries and real-file entry points')
elif a.cmd=='list':
 for e in entries:
  if not a.kind or a.kind==e['kind']:print(f"{e['id']:65} {e['kind']:12} {e['availability']}")
elif a.cmd=='verify':
 failures={e['id']:errors for e in entries if (errors:=integrity(e,views=True))}
 actual={str(x.relative_to(ROOT)) for x in (ROOT/'compilers').rglob('compiler.sov')}
 declared={e['compatibility_source'] for e in entries}
 if actual!=declared:failures['discovery']={'unregistered':sorted(actual-declared),'missing':sorted(declared-actual)}
 print('PASS: '+str(len(entries))+' registered backends' if not failures else json.dumps(failures,indent=2));raise SystemExit(bool(failures))
elif a.cmd=='describe':
 e=next((e for e in entries if e['id']==a.target),None)
 if e is None:p.error('unknown backend')
 print(json.dumps(e,indent=2))
else:
 try:e=select(a.target,a.allow_experimental,a.require_feature)
 except (ValueError,OSError) as ex:p.error(str(ex))
 args=a.args
 if args and args[0]=='--':args=args[1:]
 if not args:p.error('build requires a source path and optional compiler arguments')
 raise SystemExit(subprocess.run([str(ROOT/e['executable']),*args]).returncode)
