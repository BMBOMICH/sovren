#!/usr/bin/env python3
"""Validate retained source layout and recorded file identities without launching binaries."""
import argparse,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from backend_support import load,integrity
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('/tmp/physical-layout.json'));a=p.parse_args();rows=[]
for e in load():
    errors=integrity(e,views=True)
    for key in ['source','compatibility_source']:
        path=R/e[key]
        if not path.is_file() or path.is_symlink():errors.append('invalid regular source: '+e[key])
    rows.append(dict(target=e['id'],errors=errors,pass_test=not errors))
actual={p.relative_to(R).as_posix() for p in (R/'compilers').rglob('compiler.sov')}
declared={e['source'] for e in load()}
rows.append(dict(case='source-discovery',unregistered=sorted(actual-declared),missing=sorted(declared-actual),pass_test=actual==declared))
report=dict(pass_all=all(x['pass_test'] for x in rows),results=rows,note='The 29 pre-existing missing native binaries fail this gate. This is static identity checking, not execution validation.')
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Physical layout',sum(x['pass_test'] for x in rows),'/',len(rows));raise SystemExit(0 if report['pass_all'] else 1)
