#!/usr/bin/env python3
"""Retained native semantic corpus. No transpiler or downstream C/JS/TS dependency."""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tools'))
from backend_support import source_snapshot
p=argparse.ArgumentParser()
p.add_argument('--native',default=str(R/'compilers/linux/compiler'))
p.add_argument('--output',type=Path,default=Path('/tmp/native-conformance.json'))
a=p.parse_args()
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

def run(cmd):
    try:
        q=subprocess.run(list(map(str,cmd)),cwd=R,capture_output=True,timeout=60)
        return dict(rc=q.returncode,stdout=q.stdout.decode(errors='replace'),stderr=q.stderr.decode(errors='replace'))
    except (OSError,subprocess.TimeoutExpired) as e:
        return dict(rc=125,stdout='',stderr=str(e),unavailable=True)
rows=[]
snapshot=source_snapshot()
with tempfile.TemporaryDirectory(prefix='sovren-native-conformance-') as td:
    w=Path(td)
    for c in cases:
        src=w/'input.sov';src.write_text(c['source'],encoding='utf-8')
        out=w/'program';out.unlink(missing_ok=True)
        build=run([a.native,src,'-o',out,*c['flags']])
        result=run([out,*c['args']]) if build['rc']==0 and out.is_file() else build
        rows.append(dict(name=c['name'],build=build,result=result,oracle_agrees=(result['rc'],result['stdout'],result['stderr'])==(c['rc'],c['stdout'],'')))
binary=Path(a.native)
report=dict(schema=3,declared_scope='preserved native positive corpus; not full-language certification',implementation_sources_sha256=snapshot,compiler_sha256={'native':hashlib.sha256(binary.read_bytes()).hexdigest() if binary.is_file() else None},native_oracle_comparisons=rows,results=rows,skipped=[],pass_all=bool(rows) and all(x['oracle_agrees'] for x in rows))
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Native conformance',sum(x['oracle_agrees'] for x in rows),'/',len(rows))
raise SystemExit(0 if report['pass_all'] else 1)
