#!/usr/bin/env python3
"""Full dynamic suites in an isolated AST-default-on project, never installs."""
from pathlib import Path
import argparse,shutil,subprocess,tempfile,time,json,re,hashlib
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--prefix',default='work/p2/current');a=ap.parse_args();cc=(R/a.compiler).resolve();rows=[]
 with tempfile.TemporaryDirectory(prefix='syntax-suites-') as td:
  d=Path(td)
  for directory in ['compilers','library','tests','tools']:shutil.copytree(R/directory,d/directory,ignore=shutil.ignore_patterns('__pycache__'))
  for f in R.iterdir():
   if f.is_file() and (f.suffix=='.sov' or f.name in ['sovren','sovren-dbg']):shutil.copy2(f,d/f.name)
  p=d/'compilers/linux/syntax.sov';t=p.read_text();assert 'syntax_mode: 0' in t or 'syntax_mode: 1' in t;p.write_text(t.replace('syntax_mode: 0','syntax_mode: 1',1))
  engine=d/'compilers/linux/compiler';subprocess.run([str(cc),'compilers/linux/compiler.sov','--syntax-tree','-o',str(engine)],cwd=d,check=True,stdout=subprocess.DEVNULL)
  subprocess.run([str(engine),'launcher.sov','-o','sovren'],cwd=d,check=True,stdout=subprocess.DEVNULL)
  pin=hashlib.sha256(engine.read_bytes()).hexdigest();scope={x['name'] for x in json.loads((R/'tools/linux_scope.json').read_text())['excluded_assertions']}
  for name in ['all','fast']:
   out=d/(name+'.suite');subprocess.run([str(engine),'tests/'+name+'.sov','-o',str(out)],cwd=d,check=True,stdout=subprocess.DEVNULL)
   t=time.perf_counter();p=subprocess.run([str(out)],cwd=d,capture_output=True,timeout=180);secs=time.perf_counter()-t
   (R/(a.prefix+'-full-'+name+'.stdout')).write_bytes(p.stdout);(R/(a.prefix+'-full-'+name+'.stderr')).write_bytes(p.stderr)
   text=p.stdout.decode(errors='replace');fail=lambda s:[l[5:] for l in s.splitlines() if l.startswith('FAIL ')]
   previous=(R/('work/p1/'+name+'.stdout')).read_text();unknown=sorted(set(fail(text))-scope);same=fail(text)==fail(previous)
   row={'name':name,'rc':p.returncode,'seconds':secs,'passed':int(re.search(r'(\d+) passed',text).group(1)),'failed':len(fail(text)),'not_run':int(re.search(r'(\d+) not run',text).group(1)) if re.search(r'(\d+) not run',text) else 0,'failed_names':fail(text),'failures_identical_to_P1':same,'unknown_failures':unknown};rows.append(row);print(row['name'],row['passed'],row['failed'],row['not_run'],'same failure names',same,flush=True)
   assert same and not unknown,'new full-suite failure'
 result={'configuration':'isolated AST-default-on source; rebuilt real compiler and launcher; dynamic fixture builds use experimental frontend','compiler_sha256':hashlib.sha256(cc.read_bytes()).hexdigest(),'isolated_compiler_sha256':pin,'source_patch':{'path':'compilers/linux/syntax.sov','old':'syntax_mode: 0','new':'syntax_mode: 1'},'rows':rows}
 (R/(a.prefix+'-full-suite.json')).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
