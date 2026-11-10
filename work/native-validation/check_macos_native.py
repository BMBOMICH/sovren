"""Execute candidate Mach-O programs and real compiler generations on macOS."""
import hashlib,json,pathlib,platform,subprocess,sys
root=pathlib.Path(__file__).resolve().parent
report={'schema':1,'platform':platform.platform(),'architecture':platform.machine(),
        'checks':[],'passed':False,'translation_speed_claim':False}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def command(name,args,expected=0,stdout=None,timeout=180):
    try:
        q=subprocess.run([str(a) for a in args],cwd=root,capture_output=True,timeout=timeout)
        row={'name':name,'exit_code':q.returncode,'stdout':q.stdout.decode(errors='replace'),
             'stderr':q.stderr.decode(errors='replace'),'passed':q.returncode==expected}
        if stdout is not None:row['passed'] &= row['stdout']==stdout
    except (OSError,subprocess.TimeoutExpired) as error:
        row={'name':name,'passed':False,'error':str(error)}
    report['checks'].append(row)
    (root/'macos-native-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(name,row,flush=True)
    if not row['passed']:raise SystemExit(1)
    return row
assert platform.system()=='Darwin' and platform.machine()=='x86_64'
for name in ('tiny.macho','hello.macho','self.macho'):(root/name).chmod(0o700)
command('tiny',[root/'tiny.macho'],7)
command('hello',[root/'hello.macho'],stdout='Hello from Sovren! Fully self-hosted!\n30\nz is big\nloop\nloop\nloop\n')
cc=root/'self.macho';identities=[]
source=root/'compilers/apple/macos/compiler.sov'
for generation in range(1,4):
    out=root/f'generation-{generation}.macho';out.unlink(missing_ok=True)
    command(f'self-generation-{generation}',[cc,source,'-o',out])
    assert out.is_file() and out.stat().st_size>1000000
    out.chmod(0o700);identities.append(sha(out));cc=out
    command(f'compile-tiny-generation-{generation}',[cc,root/'tiny.sov','-o',root/'generated-tiny.macho'])
    (root/'generated-tiny.macho').chmod(0o700)
    command(f'execute-tiny-generation-{generation}',[root/'generated-tiny.macho'],7)
report['generation_sha256']=identities
assert len(set(identities))==1 and identities[0]==sha(root/'self.macho'),identities
report['language_cases']=[]
for case in json.loads((root/'corpus.json').read_text()):
    src=root/'corpus'/case['source'];out=root/'case.macho';out.unlink(missing_ok=True)
    row={'name':case['name'],'passed':False}
    try:
        q=subprocess.run([cc,src,'-o',out],cwd=root,capture_output=True,timeout=30)
        row['build_exit_code']=q.returncode
        if q.returncode==0 and out.is_file():
            out.chmod(0o700)
            q=subprocess.run([out,*case['argv']],cwd=root,capture_output=True,timeout=90)
            row.update(exit_code=q.returncode,stdout=q.stdout.decode(errors='replace'),stderr=q.stderr.decode(errors='replace'))
            row['passed']=q.returncode==case['exit_code'] and (row['stdout']+row['stderr']).strip()==case['stdout']
        else:row['diagnostic']=(q.stdout+q.stderr).decode(errors='replace')[-3000:]
    except (OSError,subprocess.TimeoutExpired) as error:row['error']=str(error)
    report['language_cases'].append(row)
    if not row['passed']:print('Language failure',row,flush=True)
    (root/'macos-native-report.json').write_text(json.dumps(report,indent=2)+'\n')
report['language_passed']=sum(r['passed'] for r in report['language_cases'])
report['passed']=all(r['passed'] for r in report['language_cases'])
(root/'macos-native-report.json').write_text(json.dumps(report,indent=2)+'\n')
print('Native macOS language cases',report['language_passed'],'/',len(report['language_cases']),flush=True)
raise SystemExit(0 if report['passed'] else 1)
