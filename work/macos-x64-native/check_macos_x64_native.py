from pathlib import Path
import hashlib,importlib.util,json,platform,subprocess,sys
R=Path(__file__).resolve().parent
src=R/'compilers/apple/macos/compiler.sov';image=R/'self.macho'
row={'target':'apple/macos','platform':platform.platform(),'architecture':platform.machine(),'native_platform_validated':True,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'checks':[],'cases':[],'generations':[],'passed':False}
def save():(R/'macos-x64-report.json').write_text(json.dumps(row,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,t=240):
 try:
  q=subprocess.run(list(map(str,args)),cwd=R,capture_output=True,timeout=t);return {'rc':q.returncode,'stdout':q.stdout.decode(errors='replace'),'stderr':q.stderr.decode(errors='replace')[-5000:]}
 except (subprocess.TimeoutExpired,OSError) as ex:return {'rc':125,'stdout':'','stderr':str(ex)}
save();assert platform.system()=='Darwin' and platform.machine()=='x86_64'
row['generations'].append(sha(image));image.chmod(0o755)
row['tiny']=run([R/'tiny.macho']);save()
if row['tiny']['rc']!=7 or row['tiny']['stdout'] or row['tiny']['stderr']:raise SystemExit(1)
for i in range(1,4):
 out=R/f'gen-{i}.macho';out.unlink(missing_ok=True);q=run([image,src,'-o',out],600);row['checks'].append(q);save()
 if q['rc']!=0 or not out.is_file():raise SystemExit(1)
 row['generations'].append(sha(out));out.chmod(0o755);image=out;save()
row['fixed_point']=len(row['generations'])==4 and len(set(row['generations']))==1;save()
row['positive']=run([sys.executable,R/'tests/conformance/native.py','--native',image,'--output',R/'positive.json'],900);save()
spec=importlib.util.spec_from_file_location('corpus',R/'tests/conformance/language_conformance.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
for name,want in c.EXPECTED.items():
 out=R/'case.macho';out.unlink(missing_ok=True);q=run([image,c.CORPUS/name,'-o',out]);cell={'name':name,'build':q,'passed':False}
 if q['rc']==0 and out.is_file():
  out.chmod(0o755);e=run([out,*c.CASE_ARGV.get(name,[])]);cell['execution']=e;cell['passed']=e['rc']==0 and e['stdout']=='\n'.join(want)+'\n' and e['stderr']==''
 row['cases'].append(cell);save()
row['passed']=row['fixed_point'] and row['positive']['rc']==0 and all(x['passed'] for x in row['cases']);save();print(json.dumps({k:row[k] for k in ('target','fixed_point','passed')}),flush=True)
raise SystemExit(0 if row['passed'] else 1)
