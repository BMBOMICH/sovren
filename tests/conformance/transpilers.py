#!/usr/bin/env python3
"""Executable, fail-closed semantic matrix, including real downstream toolchains.
Outputs are never compared to known-broken transpiler golden files.
Native comparisons are reported separately from explicit expected results.
"""
import argparse, hashlib, json, os, shutil, subprocess, tempfile, time
from pathlib import Path
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--native',default=str(R/'compilers/linux/compiler'));p.add_argument('--c',default=str(R/'compilers/c-language/compiler'));p.add_argument('--js',default=str(R/'compilers/javascript/compiler'));p.add_argument('--ts',default=str(R/'compilers/typescript/compiler'));p.add_argument('--tsc',default=shutil.which('tsc'));p.add_argument('--output',default=str('/tmp/transpiler-conformance.json'));p.add_argument('--require-ts',action='store_true');p.add_argument('--require-native',action='store_true');a=p.parse_args()
cases=[]
def add(name,source,stdout,rc=0,args=(),flags=()):cases.append(dict(name=name,source=source,stdout=stdout,rc=rc,args=list(args),flags=list(flags)))
add('hello',(R/'tests/hello.sov').read_text(),'Hello from Sovren! Fully self-hosted!\n30\nz is big\nloop\nloop\nloop\n')
add('original-loop-regression','main:\n    x: 0\n    i: 0\n    as long as i < 10\n        x: x + i\n        i: i + 1\n    print x\n','45\n')
add('calls-loop',(R/'tests/gates/fixtures/q1.sov').read_text(),'1999000\n')
add('forward-call','main:\n    print later(21)\nlater x:\n    return x * 2\n','42\n')
add('recursion','fact x:\n    if x < 2 -> return 1\n    return x * fact(x - 1)\nmain:\n    print fact(10)\n','3628800\n')
add('mutual-recursion','even n:\n    if n = 0 -> return 1\n    return odd(n - 1)\nodd n:\n    if n = 0 -> return 0\n    return even(n - 1)\nmain:\n    print even(10)\n    print odd(10)\n','1\n0\n')
add('statement-call','show n:\n    print n\nmain:\n    show(42)\n','42\n')
add('nested-loops','main:\n    x: 0\n    i: 0\n    as long as i < 5\n        j: 0\n        as long as j < 3\n            x: x + i * j\n            j: j + 1\n        i: i + 1\n    print x\n','30\n')
add('nested-else','main:\n    x: 2\n    if x = 1\n        print 1\n    if not\n        if x = 2\n            print 2\n        if not\n            print 3\n    print 4\n','2\n4\n')
add('outer-else-after-loop','main:\n    x: 0\n    if 1\n        as long as x < 3\n            x: x + 1\n    if not\n        x: 9\n    print x\n','3\n')
add('function-scope-locals','main:\n    if 1\n        x: 42\n    print x\n','42\n')
add('leave-loop','main:\n    i: 0\n    as long as 1\n        i: i + 1\n        if i = 7 -> leave\n    print i\n','7\n')
add('zero-loop','main:\n    x: 7\n    as long as 0\n        x: 99\n    print x\n','7\n')
add('dynamic-argc','main argc argv:\n    print argc\n','3\n',args=['one','two'])
add('return-code','main:\n    return 37\n','',37)
add('reserved-identifiers','switch int:\n    class: int + 2\n    return class\nmain:\n    print switch(40)\n','42\n')
add('comparisons','main:\n    print 2 = 2\n    print 2 is 3\n    print 2 is not 3\n    print 2 != 2\n    print 2 <= 3\n    print 3 >= 2\n','1\n0\n1\n0\n1\n1\n')
add('boolean','main:\n    print 0 or 3\n    print 2 and 3\n','1\n1\n')
add('short-circuit','bad:\n    print 999\n    return 1\nmain:\n    print 0 and bad()\n    print 1 or bad()\n','0\n1\n')
for name,expr,expected in [('precedence','2 + 3 * 4',14),('parens','(2 + 3) * 4',20),('negative-division','-17 / 5',-3),('negative-remainder','-17 % 5',-2),('positive-division','17 / 5',3),('i64-max','9223372036854775807',9223372036854775807),('wrap-add','9223372036854775807 + 1',-9223372036854775808),('wrap-sub','-9223372036854775808 - 1',9223372036854775807),('wrap-mul','9223372036854775807 * 2',-2),('intermediate-wrap','(9223372036854775807 + 1) / 2',-4611686018427387904),('u64-wrap','18446744073709551615',-1),('leading-zeros','00017',17)]:
 add(name,'main:\n    print '+expr+'\n',str(expected)+'\n')
add('quoted-delimiters',"main:\n    print 'a ;; b -> c # d'\n",'a ;; b -> c # d\n')
add('embedded-quotes',"main:\n    print 'say \"hello\"'\n",'say "hello"\n')
add('string-escapes',r'''main:
    print "a\nb\tend\\"
''','a\nb\tend\\\n')
add('unicode',"main:\n    print 'Salam, Azərbaycan — 你好'\n",'Salam, Azərbaycan — 你好\n')
add('CRLF','main:\r\n    print 42\r\n','42\n')
add('no-final-newline','main:\n    print 42','42\n')
add('inline-nested','main:\n    if 1 -> if 2 -> print 42\n','42\n')
add('packed-children','main:\n    x: 0\n    if 1 -> x: x + 2 ;; x: x + 3\n    print x\n','5\n')
add('over-4KB','# padding\n'*600+'main:\n    print 42\n','42\n')
add('over-100KB','# padding\n'*12000+'main:\n    print 42\n','42\n')
add('long-packed-line','main:\n    x: 0\n    '+' ;; '.join(['x: x + 1']*1000)+'\n    print x\n','1000\n')
add('many-functions',''.join(f'f{i} x:\n    return '+(f'f{i+1}(x + 1)' if i<511 else 'x + 1')+'\n' for i in range(512))+'main:\n    print f0(0)\n','512\n')
# --unsafe controls lint in native Sovren; it must not silently change arithmetic.
for case in list(cases):
 if case['name'] in ('wrap-add','wrap-sub','wrap-mul','intermediate-wrap'):
  add(case['name']+'-unsafe',case['source'],'trap\n',rc=1,flags=['--unsafe'])
  case['stdout']='trap\n';case['rc']=1
add('division-zero','main:\n    print 1 / 0\n','trap\n',1)
add('division-overflow','main:\n    print -9223372036854775808 / -1\n','trap\n',1)
import random
rng=random.Random(5614)
def expression(depth):
 if not depth:
  x=rng.randint(-40,40);return str(x),x
 left,x=expression(depth-1);right,y=expression(depth-1);op=rng.choice(['+','-','*'])
 value={'+':lambda:x+y,'-':lambda:x-y,'*':lambda:x*y}[op]()
 return '('+left+' '+op+' '+right+')',value
pairs=[expression(3) for _ in range(128)]
add('generated-expressions','main:\n'+''.join('    print '+e+'\n' for e,v in pairs),''.join(str(v)+'\n' for e,v in pairs))
add('division-register-overflow','divide a b:\n    return a / b\nmain:\n    print divide(-9223372036854775808, -1)\n','trap\n',1)
add('remainder-register-overflow','remainder a b:\n    return a % b\nmain:\n    print remainder(-9223372036854775808, -1)\n','trap\n',1)
add('division-boundary-safe','divide a b:\n    return a / b\nmain:\n    print divide(-9223372036854775808, 1)\n','-9223372036854775808\n')
# Adversarial collision chain: 256 task rows + main/header/init/128 additions/print + 17 = 404 buckets.
def namehash(text):
 h=5381
 for c in text.encode():h=(h*33+c)%2147483647
 return h
names=[];i=0
while len(names)<128:
 name='collision_'+str(i)
 if namehash(name)%404==0:names.append(name)
 i+=1
add('collision-chain',''.join(name+':\n    return '+str(i)+'\n' for i,name in enumerate(names))+'main:\n    total: 0\n'+''.join('    total: total + '+n+'()\n' for n in names)+'    print total\n','8128\n')
add('left-to-right-effects','mark n:\n    print n\n    return n\nadd a b:\n    return a + b\nmain:\n    print mark(1) + mark(2)\n    print add(mark(3),mark(4))\n','1\n2\n3\n3\n4\n7\n')
add('effectful-while-condition','mark n:\n    print n\n    return n\nmain:\n    x: 0\n    as long as mark(x) < 3\n        x: x + 1\n    print x\n','0\n1\n2\n3\n3\n')
add('nested-effects-short-circuit','mark n:\n    print n\n    return n\nmain:\n    print mark(1) + (mark(2) * mark(3))\n    print 0 and mark(9)\n    print 1 or mark(8)\n','1\n2\n3\n7\n0\n1\n')
negative={
 'tab-indentation':'main:\n\tprint 42\n',
 'unary-not':'main:\n    print not 0\n',
 'unknown-statement':'main:\n    teleport 42\n',
 'unknown-call':'main:\n    print missing(42)\n',
 'unknown-local':'main:\n    print missing\n',
 'wrong-arity':'f x:\n    return x\nmain:\n    print f()\n',
 'duplicate-function':'main:\n    print 1\nmain:\n    print 2\n',
 'duplicate-parameter':'f x x:\n    return x\nmain:\n    print 1\n',
 'bad-string':"main:\n    print 'unclosed\n",
 'unsupported-array':'main:\n    x: [1, 2]\n    print x\n',
 'unsupported-import':'use string\nmain:\n    print 1\n',
 'unsupported-global':'x: 2\nmain:\n    print x\n',
 'unsupported-string-variable':"main:\n    x: 'text'\n    print x\n",
 'unsupported-argv':'main argc argv:\n    print argv\n',
 'unmatched-else':'main:\n    if not\n        print 1\n',
 'else-after-loop':'main:\n    as long as 0\n        print 1\n    if not\n        print 2\n',
 'bad-indent':'main:\n    print 1\n        print 2\n',
 'empty-control':'main:\n    if 1\n    print 2\n',
 'misaligned-dedent':'main:\n    if 1\n        print 1\n      print 2\n',
 'bad-expression':'main:\n    print 1 2\n',
 'leave-outside-loop':'main:\n    leave\n',
 'missing-main':'other:\n    print 1\n',
 'integer-too-large':'main:\n    print 18446744073709551616\n',
 'embedded-NUL':'main:\n    print 1\n\x00invalid tail\n',
 'empty-source':'',
}
def run(cmd,timeout=30):
 t=time.perf_counter_ns()
 try:
  q=subprocess.run(list(map(str,cmd)),cwd=R,capture_output=True,timeout=timeout)
  return dict(rc=q.returncode,stdout=q.stdout.decode(errors='replace'),stderr=q.stderr.decode(errors='replace'),ms=(time.perf_counter_ns()-t)/1e6)
 except subprocess.TimeoutExpired:return dict(rc=124,stdout='',stderr='TIMEOUT',ms=timeout*1000)
import sys
sys.path.insert(0,str(R/'tools'))
from backend_support import source_snapshot
implementation_snapshot=source_snapshot()
rows=[];native=[];skips=[];ts_jobs=[]
with tempfile.TemporaryDirectory(prefix='sovren-transpile-conformance-') as td:
 W=Path(td)
 for case in cases:
  src=W/'input.sov';src.write_text(case['source']);out=W/'native';out.unlink(missing_ok=True)
  b=run([a.native,src,'-o',out,'--uncached',*case['flags']])
  result=run([out,*case['args']]) if b['rc']==0 and out.is_file() else b
  native.append(dict(name=case['name'],result=result,oracle_agrees=(result['rc'],result['stdout'],result['stderr'])==(case['rc'],case['stdout'],'')))
  for target in ('c','js','ts'):
   exe=Path(getattr(a,target));dest=W/f'{case["name"]}.{target}';dest.unlink(missing_ok=True)
   b=run([exe,src,'-o',dest,*case['flags']]);row=dict(case=case['name'],target=target,translate=b,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),fresh=dest.is_file() and dest.stat().st_size>0)
   result=None
   if b['rc']==0 and row['fresh']:
    if target=='c':
     binary=W/'c-program';binary.unlink(missing_ok=True);d=run(['cc','-std=c11','-O2',dest,'-o',binary]);row['downstream']=d
     if d['rc']==0 and binary.is_file():result=run([binary,*case['args']])
    elif target=='ts':
     if not a.tsc:skips.append(dict(case=case['name'],target='ts',reason='TypeScript compiler unavailable'))
     else:ts_jobs.append((row,case,dest))
    else:result=run(['node',dest,*case['args']])
   row['runtime']=result;row['pass']=result is not None and (result['rc'],result['stdout'],result['stderr'])==(case['rc'],case['stdout'],'');rows.append(row)
   print(case['name'],target,'PASS' if row['pass'] else 'FAIL',flush=True)
 if ts_jobs:
  jsdir=W/'ts-js'
  batch=run([a.tsc,'--target','ES2020','--module','commonjs','--strict','--skipLibCheck','--outDir',jsdir,*[x[2] for x in ts_jobs]],timeout=60)
  for row,case,dest in ts_jobs:
   row['downstream']=batch
   row['downstream_note']='Batched correctness-only typecheck; not an individual latency measurement.'
   result=None
   if batch['rc']==0 and (jsdir/(dest.stem+'.js')).is_file():result=run(['node',jsdir/(dest.stem+'.js'),*case['args']])
   row['runtime']=result;row['pass']=result is not None and (result['rc'],result['stdout'],result['stderr'])==(case['rc'],case['stdout'],'')
   print(case['name'],'ts-final','PASS' if row['pass'] else 'FAIL',flush=True)
 for name,text in negative.items():
  src=W/'input.sov';src.write_text(text)
  for target in ('c','js','ts'):
   out=W/f'bad.{target}';out.write_text('stale output sentinel')
   q=run([getattr(a,target),src,'-o',out]);ok=q['rc'] not in (0,124) and not out.exists()
   rows.append(dict(case=name,target=target,negative=True,result=q,pass_test=ok));print(name,target,'PASS' if ok else 'FAIL',flush=True)
 for target in ('c','js','ts'):
  src=W/'input.sov';src.write_text('main:\n    print 42\n');out=W/'missing-directory'/'out'
  q=run([getattr(a,target),src,'-o',out]);rows.append(dict(case='writer-failure',target=target,negative=True,result=q,pass_test=q['rc'] not in (0,124) and not out.exists()))
report=dict(schema=2,implementation_sources_sha256=implementation_snapshot,compiler_sha256={t:hashlib.sha256(Path(getattr(a,t)).read_bytes()).hexdigest() for t in ['c','js','ts','native']},shared_source_sha256=hashlib.sha256((R/'library/transpile.sov').read_bytes()).hexdigest(),declared_scope='structured integer / literal-text subset, not full language',tools={t:str(getattr(a,t)) for t in ['c','js','ts','tsc']},native_oracle_comparisons=native,results=rows,skipped=skips,pass_all=all(x.get('pass',x.get('pass_test',False)) for x in rows) and not skips and (not a.require_native or all(x['oracle_agrees'] for x in native)))
Path(a.output).write_text(json.dumps(report,indent=2));print('SUMMARY',sum(x.get('pass',x.get('pass_test',False)) for x in rows),'/',len(rows),'native agreement',sum(x['oracle_agrees'] for x in native),'/',len(native),'skipped',len(skips),flush=True)
raise SystemExit(0 if report['pass_all'] else 1)
