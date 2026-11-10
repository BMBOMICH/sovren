#!/usr/bin/env python3
"""Maintain a real-file layout. No symlinks or duplicated implementations."""
import hashlib,json,os
from pathlib import Path
R=Path(__file__).resolve().parents[1];path=R/'compilers/registry.json';manifest=json.loads(path.read_text());entries=manifest['entries'];ids=set()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def facade(dst,source):
 dst.parent.mkdir(parents=True,exist_ok=True)
 text='# Compatibility facade; the implementation is a real file at '+str(source.relative_to(R))+'.\ninclude '+'../'+str(source.relative_to(R))+'\n'
 if dst==source:raise RuntimeError('cannot overwrite implementation')
 if dst.is_symlink():dst.unlink()
 dst.write_text(text)
def launcher(directory,executable):
 dst=directory/'compiler';relative=os.path.relpath(executable,directory)
 if dst==executable:return
 dst.write_text('#!/bin/sh\n# Real-file entry point; the installed binary is not duplicated.\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$HERE/'+relative+'" "$@"\n');dst.chmod(0o755)
for e in entries:
 name=e['id']
 if name in ids:raise RuntimeError('duplicate backend '+name)
 ids.add(name);source=R/e['source'];binary=R/e['executable'];directory=R/e['canonical_directory']
 assert source.is_file() and not source.is_symlink()
 facade(R/e['compatibility_source'],source)
 launcher(directory,binary)
 e['source_sha256']=sha(source);e['executable_sha256']=sha(binary);e['compatibility_source_sha256']=sha(R/e['compatibility_source'])
 e['shared_source_sha256']={s:sha(R/s) for s in e.get('shared_sources',[])}
 e['entrypoint_sha256']={str((directory/'compiler').relative_to(R)):sha(directory/'compiler')}
 for view in e.get('views',[]):
  folder=R/view;folder.mkdir(parents=True,exist_ok=True);facade(folder/'compiler.sov',source);launcher(folder,binary)
  for f in ['compiler.sov','compiler']:e['entrypoint_sha256'][str((folder/f).relative_to(R))]=sha(folder/f)
manifest['generated_note']='Real implementation files and regular-file compatibility facades; hashes do not certify full semantics.'
path.write_text(json.dumps(manifest,indent=2)+'\n')
for directory,kinds in [('compilers',['native','ir-emitter','evaluator','partial']),('transpilers',['transpiler'])]:
 folder=R/directory;folder.mkdir(parents=True,exist_ok=True)
 text=['# '+directory,'','This directory contains real files, not directory symlinks. Transpiler implementations live under top-level `transpilers/`; `backends/transpilers/` contains shared lowering and compatibility entry points. Other backend implementations live in their respective `backends/` families. Installed binaries remain under `compilers/` for existing launchers.','', 'The authoritative inventory is `compilers/registry.json`. No incomplete implementation is renamed to claim completeness.','', '| Backend | Availability |','|---|---|']
 for e in entries:
  if e['kind'] in kinds:text.append(f"| [{e['id']}]({e['id']}/compiler.sov) | {e['availability']} |")
 (folder/'README.md').write_text('\n'.join(text)+'\n')
print('Verified/refreshed',len(entries),'physical implementations and real-file compatibility entry points')
