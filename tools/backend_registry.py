#!/usr/bin/env python3
"""Refresh file identities without overwriting implementations or creating aliases."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];p=R/'compilers/registry.json'
data=json.loads(p.read_text(encoding='utf-8'));entries=data['entries']
assert len({e['id'] for e in entries})==len(entries)
def sha(name):
    f=R/name
    if f.is_symlink():raise ValueError('unexpected link: '+name)
    return hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else None
for e in entries:
    assert (R/e['source']).is_file(),e['id']
    for k in ['source','executable','compatibility_source']:e[k+'_sha256']=sha(e[k])
    e['shared_source_sha256']={s:sha(s) for s in e.get('shared_sources',e.get('shared_source_sha256',{}))}
    e['entrypoint_sha256']={s:sha(s) for s in {e['source'],e['executable'],e['compatibility_source']}}
    if e['executable_sha256'] is None:e['full_language_certified']=False
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print('Refreshed',len(entries),'retained entries; missing binaries remain uncertified')
