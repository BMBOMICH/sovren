"""Registry access shared by discovery, builds, integrity checks and CI."""
import hashlib,json,platform
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load():
 data=json.loads((ROOT/'compilers/registry.json').read_text(encoding='utf-8'));entries=data['entries']
 if data.get('schema')!=2 or len({e['id'] for e in entries})!=len(entries):raise ValueError('invalid registry or duplicate identities')
 return entries
def integrity(entry,views=False):
 errors=[]
 for key in ['source','executable']:
  p=ROOT/entry[key]
  if not p.is_file():errors.append('missing '+key+': '+entry[key])
  elif digest(p)!=entry[key+'_sha256']:errors.append(key+' hash mismatch')
 for name,sha in entry.get('shared_source_sha256',{}).items():
  p=ROOT/name
  if not p.is_file() or digest(p)!=sha:errors.append('shared source mismatch: '+name)
 if views:
  for name,sha in entry.get('entrypoint_sha256',{}).items():
   p=ROOT/name
   if not p.is_file() or p.is_symlink() or digest(p)!=sha:errors.append('invalid physical entry point: '+name)
  p=ROOT/entry['compatibility_source']
  if not p.is_file() or p.is_symlink() or digest(p)!=entry['compatibility_source_sha256']:errors.append('invalid compatibility source')
 return errors
def select(name,allow_experimental=False,features=()):
 entry=next((e for e in load() if e['id']==name),None)
 if not entry:raise ValueError('unknown backend: '+name)
 errors=integrity(entry)
 if errors:raise ValueError('; '.join(errors))
 if platform.system()!='Linux' or platform.machine().lower() not in ['x86_64','amd64']:raise ValueError('these driver binaries require a Linux x86-64 host; output target is not a compiler-host port')
 if entry['availability']=='experimental' and not allow_experimental:raise ValueError('uncertified backend; explicitly pass --allow-experimental to use legacy output without a semantics guarantee')
 if features:
  evidence=ROOT/'targets/capabilities.json'
  if not evidence.is_file():raise ValueError('feature certification evidence is missing')
  profiles=json.loads(evidence.read_text(encoding='utf-8'))['profiles'];profile=profiles.get(entry['capability_profile'],{})
  for feature in features:
   if profile.get('features',{}).get(feature)!='tested':raise ValueError('required feature is not certified: '+feature)
 return entry
def source_snapshot():
 paths=[ROOT/'runtime.sov']
 for root in ['compilers','library','frontend','runtime']:
  paths.extend(p for p in (ROOT/root).rglob('*.sov') if p.is_file() and not p.is_symlink())
 return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(set(paths))}

def layout_integrity():
 errors=[]
 base=ROOT/'compilers'
 allowed={base,base/'shared'}
 for entry in load():
  folder=ROOT/entry['canonical_directory']
  while folder!=ROOT:
   allowed.add(folder)
   if folder==base:break
   folder=folder.parent
 for folder in base.rglob('*'):
  if folder.is_dir() and not folder.is_relative_to(base/'shared') and '__pycache__' not in folder.parts and folder not in allowed:
   errors.append('unregistered compiler directory: '+folder.relative_to(ROOT).as_posix())
 return errors
