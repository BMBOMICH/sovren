#!/usr/bin/env python3
import argparse,copy,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from validate_sir import validate
p=argparse.ArgumentParser();p.add_argument('--staged',action='store_true');p.add_argument('--output',type=Path,default='/tmp/shared-ir.json');a=p.parse_args();rows=[]
sources={f:(R/f).read_text() for f in ['tests/hello.sov','tests/gates/fixtures/q1.sov']}
sources.update(recursion='f n:\n    if n < 2 -> return 1\n    return n * f(n - 1)\nmain:\n    print f(5)\n',escaping='main:\n    print \'Salam — "hi" \\t \\\\ ;; ->\'\n',locals='f x:\n    if x\n        y: x + 1\n    if not\n        y: 8\n    return y\nmain:\n    print f(2)\n',argc='main argc argv:\n    print argc\n')
with tempfile.TemporaryDirectory(prefix='sovren-sir-') as td:
 w=Path(td)
 for label,source in sources.items():
  src=w/'input.sov';src.write_text(source);outputs=[]
  for target,name in [('c','c-language'),('js','javascript'),('ts','typescript')]:
   driver=Path('/tmp/sovren-repair')/(target+'-new') if a.staged else R/'compilers'/name/'compiler';dest=w/'module.json'
   for flags in [[],[],['--unsafe']]:
    dest.unlink(missing_ok=True);q=subprocess.run([str(driver),str(src),'--emit-ir','-o',str(dest),*flags],capture_output=True,cwd=R,timeout=30)
    assert q.returncode==0,(label,target,q.stdout,q.stderr)
    data=dest.read_bytes();m=json.loads(data);summary=validate(m);outputs.append(data)
   rows.append(dict(case=label,target=target,sha256=hashlib.sha256(data).hexdigest(),**summary,pass_test=True))
  assert len(set(outputs))==1,(label,'target-dependent or non-deterministic IR')
  for fault in ['version','node-type','call','block']:
   bad=copy.deepcopy(m)
   if fault=='version':bad['version']=999
   elif fault=='node-type':
    if not bad['nodes']:continue
    bad['nodes'][0]['type']='f64'
   elif fault=='call':bad['nodes'].append(dict(id=len(bad['nodes']),type='i64',kind='call',function=0,line=1,text='not_a_function',symbol=99999,left=-1,right=-1,arguments=[]))
   else:bad['statements'].insert(0,dict(function=0,line=1,kind='end',expression=-1,text='',auxiliary=-1))
   try:validate(bad)
   except (ValueError,KeyError,TypeError,IndexError):rows.append(dict(case=label+'-reject-'+fault,pass_test=True))
   else:raise AssertionError('accepted malformed '+fault)
a.output.write_text(json.dumps(dict(pass_all=True,results=rows),indent=2)+'\n');print('Shared IR:',len(rows),'checks PASS')
