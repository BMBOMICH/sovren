#!/usr/bin/env python3
"""Explicit source-only versus end-to-end transpiler pipeline; no shell evaluation."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,time
from backend_support import select
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('-o','--output',required=True,type=Path);p.add_argument('--target',choices=['c','js','ts'],default='c');p.add_argument('--emit-only',action='store_true');p.add_argument('--cc',default='cc');p.add_argument('--tsc',default='tsc');p.add_argument('--unsafe',action='store_true');p.add_argument('--evidence',type=Path);a=p.parse_args()
src=a.source.resolve();out=a.output.absolute();record={'target':a.target,'mode':'source-only' if a.emit_only else 'end-to-end','success':False};start=time.perf_counter_ns()
def run(cmd,stage):
 t=time.perf_counter_ns();r=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=120,cwd=R)
 record[stage]={'command':list(map(str,cmd)),'ms':(time.perf_counter_ns()-t)/1e6,'rc':r.returncode,'stdout':r.stdout.decode(errors='replace')[-4000:],'stderr':r.stderr.decode(errors='replace')[-4000:]}
 if r.returncode:raise RuntimeError(stage+' failed: '+record[stage]['stderr']+record[stage]['stdout'])
try:
 if src==out.resolve() or (out.exists() and os.path.samefile(src,out)):raise ValueError('refusing to overwrite source')
 out.unlink(missing_ok=True)
 with tempfile.TemporaryDirectory(prefix='sovren-pipeline-') as td:
  w=Path(td);translated=w/f'program.{a.target}';entry=select(dict(c='c-language',js='javascript',ts='typescript')[a.target]);driver=R/entry['executable']
  record['compiler_sha256']=hashlib.sha256(driver.read_bytes()).hexdigest();record['source_sha256']=hashlib.sha256(src.read_bytes()).hexdigest()
  run([driver,src,'-o',translated,*(['--unsafe'] if a.unsafe else [])],'translation')
  if not translated.is_file() or not translated.stat().st_size:raise RuntimeError('translator returned no fresh output')
  artifact=translated
  if not a.emit_only:
   if a.target=='c':
    artifact=w/'program';run([a.cc,'-std=c11','-O2',translated,'-o',artifact],'downstream')
   elif a.target=='ts':
    run([a.tsc,'--target','ES2020','--module','commonjs','--strict','--skipLibCheck','--outDir',w/'js',translated],'downstream');artifact=w/'js/program.js'
   else:run(['node','--check',translated],'validation')
  if not artifact.is_file() or not artifact.stat().st_size:raise RuntimeError('downstream returned no fresh output')
  # Stage beside the requested destination so final rename is on one filesystem.
  fd,tmp=tempfile.mkstemp(prefix='.'+out.name+'.',dir=out.parent);os.close(fd)
  try:shutil.copy2(artifact,tmp);os.replace(tmp,out)
  finally:Path(tmp).unlink(missing_ok=True)
  record.update(success=True,artifact_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),artifact_bytes=out.stat().st_size,launch=([str(out)] if a.target=='c' and not a.emit_only else ['node',str(out)] if not a.emit_only else None))
except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:record['error']=str(e)
record['total_ms']=(time.perf_counter_ns()-start)/1e6
if a.evidence:a.evidence.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2));raise SystemExit(0 if record['success'] else 1)
