"""Native CPU/Darwin compatibility checks; platform metadata is adapted only
in disposable launch copies. Original target images are retained and compared.
This does not qualify iOS/watchOS/tvOS/visionOS device or simulator deployment.
"""
from pathlib import Path
import hashlib,importlib.util,json,platform,shutil,struct,subprocess,sys,time
R=Path(__file__).resolve().parent;rows=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text_segment(data):
 at=32
 for i in range(struct.unpack_from('<I',data,16)[0]):
  cmd,size=struct.unpack_from('<II',data,at)
  if cmd==25 and data[at+8:at+24].rstrip(b'\0')==b'__TEXT':
   off,length=struct.unpack_from('<QQ',data,at+40);return data[off+16384:off+length]
  at+=size
 raise ValueError('no text segment')
def launch_copy(p):
 data=bytearray(p.read_bytes());before=text_segment(data);at=32
 for i in range(struct.unpack_from('<I',data,16)[0]):
  cmd,size=struct.unpack_from('<II',data,at)
  if cmd==50:struct.pack_into('<III',data,at+8,1,11*65536,15*65536)
  at+=size
 # arm64e also gets an ordinary ARM64 CPU metadata copy for this CPU-only
 # compatibility check. Pointer-authenticated ABI deployment remains pending.
 struct.pack_into('<I',data,8,0)
 out=p.with_name(p.name+'.launch');out.write_bytes(data);out.chmod(0o755)
 q=subprocess.run(['codesign','--force','--sign','-','--timestamp=none',str(out)],capture_output=True)
 assert q.returncode==0,q.stderr.decode()
 assert before==text_segment(out.read_bytes()),'signing changed emitted instructions'
 return out
def run(args,timeout=300):
 try:
  q=subprocess.run(list(map(str,args)),cwd=R,capture_output=True,timeout=timeout)
  return {'rc':q.returncode,'stdout':q.stdout.decode(errors='replace'),'stderr':q.stderr.decode(errors='replace')[-3000:]}
 except subprocess.TimeoutExpired:return {'rc':124,'stderr':'timeout'}
assert platform.system()=='Darwin' and platform.machine()=='arm64'
spec=importlib.util.spec_from_file_location('corpus',R/'tests/conformance/language_conformance.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
targets=['ios','tvos','watchos','visionos','ios-simulator','tvos-simulator','watchos-simulator','visionos-simulator','arm64e']
for target in targets:
 d=R/'targets'/target;src=R/'compilers/apple'/target/'compiler.sov';image=d/'self-0.macho';row={'target':'apple/'+target,'native_platform_validated':False,'validation':'native ARM64 CPU and Darwin runtime with disposable macOS metadata launch copies','source_sha256':sha(src),'generations':[sha(image)],'cases':[],'checks':[]}
 rows.append(row)
 def save():(R/'apple-compatibility-native.json').write_text(json.dumps({'platform':platform.platform(),'rows':rows},indent=2))
 save()
 for i in range(1,4):
  compiler=launch_copy(image);out=d/f'gen-{i}.macho';out.unlink(missing_ok=True);q=run([compiler,src,'-o',out]);row['checks'].append({'name':f'self-{i}',**q});save()
  if q['rc']!=0 or not out.is_file():break
  row['generations'].append(sha(out));image=out;save()
 row['fixed_point']=len(row['generations'])==4 and len(set(row['generations']))==1
 compiler=launch_copy(image)
 for name,want in c.EXPECTED.items():
  out=d/'case.macho';out.unlink(missing_ok=True);q=run([compiler,c.CORPUS/name,'-o',out]);cell={'name':name,'build':q,'passed':False}
  if q['rc']==0 and out.is_file():
   launch=launch_copy(out);e=run([launch,*c.CASE_ARGV.get(name,[])]);cell['execution']=e;cell['passed']=e['rc']==0 and e['stdout']=='\n'.join(want)+'\n'
  row['cases'].append(cell);save()
 row['corpus_passed']=sum(x['passed'] for x in row['cases']);row['passed']=row['fixed_point'] and row['corpus_passed']==16;save();print(json.dumps({k:v for k,v in row.items() if k not in ('cases','checks')}),flush=True)
raise SystemExit(0 if all(r['passed'] for r in rows) else 1)
