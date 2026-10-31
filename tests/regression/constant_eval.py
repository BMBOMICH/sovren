#!/usr/bin/env python3
"""Check real native constant evaluation, including errors, never stub output."""
import argparse,hashlib,json,random,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2];p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,default=R/'compilers/linux/compiler');p.add_argument('--output',type=Path,default='/tmp/constant-evaluation.json');a=p.parse_args();a.compiler=a.compiler.resolve()
cases=[('-1 + 2',1),('8 - 3 - 2',3),('48 / 4 / 3',4),('1 < 2',1),('2 > 1',1),('2 <= 2',1),('2 >= 2',1),('2 == 2',1),('2 != 2',0),('2 = 2',1),('1 - -2',3),('2 * -3',-6),('-(2 + 3) * 4',-20),('2 * 3 + 4 * 5',26),('20 % 6 * 2',4),('const(1 + 2)',3),('1 / 0',None),('1 % 0',None),('1 +',None),('1 <',None),('(1 + 2',None),('missing',None),('9223372036854775807 + 1',None),('-9223372036854775808 - 1',None),('-9223372036854775808 / -1',None),('-9223372036854775808 % -1',None),('-9223372036854775808 * -1',None),('9223372036854775807 * 2',None),('-(-9223372036854775808)',None),('-9223372036854775808 / 1',-9223372036854775808)]
rng=random.Random(5801)
for i in range(250):
 x,y,z=(rng.randrange(-50,51) for _ in range(3));cases.extend([(f'{x} - {y} - {z}',x-y-z),(f'{x} + {y} * {z}',x+y*z),(f'{x} <= {y}',int(x<=y))])
header='''use string
use num
use arg
cval: 0
num_cache: 0
num_value s:
    return _sov_atoi(s)
num_of s:
    return _sov_atoi(s)
length s:
    return str_len(s)
strip s:
    return str_trim(s)
cut s a b:
    return str_cut(s,a,b)
digitb c:
    if c >= 48 and c <= 57 -> return 1
    return 0
'''
rows=[]
with tempfile.TemporaryDirectory(prefix='sovren-const-') as td:
 w=Path(td);src=w/'probe.sov';binary=w/'probe'
 src.write_text(header+(R/'library/constant_eval.sov').read_text()+'''\nmain:
    if ceval(as text arg_at(1)) = 0
        print 'reject'
        return 0
    print cval
''')
 q=subprocess.run([str(a.compiler),str(src),'-o',str(binary)],cwd=R,capture_output=True,timeout=60);assert q.returncode==0,(q.stdout,q.stderr)
 for expr,value in cases:
  q=subprocess.run([str(binary),expr],capture_output=True,text=True,timeout=10);expected='reject\n' if value is None else str(value)+'\n';ok=q.returncode==0 and q.stdout==expected and not q.stderr;rows.append(dict(expression=expr,expected=expected,result=q.stdout,rc=q.returncode,pass_test=ok))
 # The production compiler must use the module, not merely a passing unit copy.
 production=[(e,v) for e,v in cases if v is not None]
 src.write_text('main:\n'+''.join('    print const('+e+')\n' for e,v in production));q=subprocess.run([str(a.compiler),str(src),'-o',str(binary)],cwd=R,capture_output=True,text=True,timeout=60)
 expected=''.join(str(v)+'\n' for e,v in production)
 run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10) if q.returncode==0 else q
 rows.append(dict(expression='production const() lowering',expression_count=len(production),expected=expected,result=run.stdout,rc=run.returncode,pass_test=run.returncode==0 and run.stdout==expected))
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(dict(compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest(),module_sha256=hashlib.sha256((R/'library/constant_eval.sov').read_bytes()).hexdigest(),pass_all=all(x['pass_test'] for x in rows),results=rows),indent=2)+'\n')
print('Constant evaluation',sum(x['pass_test'] for x in rows),'/',len(rows))
for x in rows:
 if not x['pass_test']:print(x)
raise SystemExit(not all(x['pass_test'] for x in rows))
