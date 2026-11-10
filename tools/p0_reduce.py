#!/usr/bin/env python3
"""Run literal-source legacy test reductions without the legacy harness."""
import re,json,subprocess,sys,os,signal
from pathlib import Path
R=Path(__file__).resolve().parents[1];exe=(R/sys.argv[1]).resolve();dest=R/'work/p0/reduced';dest.mkdir(exist_ok=True)
wanted=set(sys.argv[2:])
pat=r'(?:tr_expect|tr_thread_expect)\("([^"\n]+)", ("(?:[^"\\]|\\.)*"), ("(?:[^"\\]|\\.)*")\)'
results=[]
for name,src,expected in re.findall(pat,(R/'library/suite.sov').read_text()):
 if wanted and name not in wanted:continue
 src=json.loads(src);expected=json.loads(expected);slug=re.sub('[^a-z0-9]+','-',name.lower());p=dest/(slug+'.sov');p.write_text(src);out=dest/(slug+'.bin');out.unlink(missing_ok=True)
 b=subprocess.run([str(exe),str(p),'-o',str(out)],cwd=R,capture_output=True,timeout=30)
 (dest/(slug+'.build.log')).write_bytes(b.stdout+b.stderr)
 e=None
 if b.returncode==0 and out.exists():
  proc=subprocess.Popen([str(out)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=R,start_new_session=True)
  try:stdout,stderr=proc.communicate(timeout=5);rc=proc.returncode
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate();rc=124
  e=subprocess.CompletedProcess([str(out)],rc,stdout,stderr)
 got=e.stdout.decode(errors='replace').strip() if e else None
 row=dict(name=name,build_rc=b.returncode,run_rc=e.returncode if e else None,expected=expected,actual=got,ok=e is not None and e.returncode==0 and got==expected,source=str(p.relative_to(R)))
 print(('PASS ' if row['ok'] else 'FAIL ')+name+(' '+repr(got) if not row['ok'] else ''),flush=True);results.append(row)
(dest/'results.json').write_text(json.dumps(results,indent=2)+'\n')
