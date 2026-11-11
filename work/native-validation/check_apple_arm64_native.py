from pathlib import Path
import hashlib,importlib.util,json,platform,subprocess,time
R=Path(__file__).resolve().parent
report={'platform':platform.platform(),'architecture':platform.machine(),'checks':[],'passed':False,'translation_speed_claim':False}
def save(): (R/'macos-arm64-report.json').write_text(json.dumps(report,indent=2))
def run(name,args,code=0,out=None,timeout=240):
    start=time.monotonic()
    try:
        q=subprocess.run(list(map(str,args)),cwd=R,capture_output=True,timeout=timeout)
        row={'name':name,'rc':q.returncode,'stdout':q.stdout.decode(errors='replace')[-3000:],'stderr':q.stderr.decode(errors='replace')[-3000:],'seconds':round(time.monotonic()-start,3)}
        row['passed']=q.returncode==code and (out is None or row['stdout']==out)
    except (OSError,subprocess.TimeoutExpired) as ex:row={'name':name,'passed':False,'error':str(ex)}
    report['checks'].append(row);save();print(json.dumps(row),flush=True)
    if not row['passed']:raise SystemExit(1)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
save();assert platform.system()=='Darwin' and platform.machine()=='arm64',platform.platform()
for name in ('tiny.macho','hello.macho','self.macho'):(R/name).chmod(0o755)
run('tiny',[R/'tiny.macho'],7,'')
run('hello',[R/'hello.macho'],0,'Hello from Sovren! Fully self-hosted!\n30\nz is big\nloop\nloop\nloop\n')
compiler=R/'self.macho';generations=[sha(compiler)]
source=R/'compilers/apple/macos-arm64/compiler.sov'
for i in range(1,4):
    out=R/f'gen-{i}.macho';out.unlink(missing_ok=True)
    run(f'self-{i}',[compiler,source,'-o',out],timeout=480)
    out.chmod(0o755);generations.append(sha(out));compiler=out
    fixture=R/f'tiny-{i}.macho'
    run(f'compile-tiny-{i}',[compiler,R/'tiny.sov','-o',fixture])
    fixture.chmod(0o755);run(f'execute-tiny-{i}',[fixture],7,'')
report['generation_sha256']=generations;report['fixed_point']=len(set(generations))==1;save()
assert report['fixed_point'],generations
run('native-positive-corpus',['python3',R/'tests/conformance/native.py','--native',compiler,'--output',R/'positive.json'],timeout=600)
spec=importlib.util.spec_from_file_location('corpus',R/'tests/conformance/language_conformance.py');corpus=importlib.util.module_from_spec(spec);spec.loader.exec_module(corpus)
for case,want in corpus.EXPECTED.items():
    out=R/'case.macho';out.unlink(missing_ok=True)
    run('compile-'+case,[compiler,corpus.CORPUS/case,'-o',out])
    out.chmod(0o755)
    run('execute-'+case,[out,*corpus.CASE_ARGV.get(case,[])],0,'\n'.join(want)+'\n')
report['passed']=True;save()
