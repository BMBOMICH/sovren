#!/usr/bin/env python3
"""Fresh-source randomized arithmetic qualification; independent integer oracle."""
import argparse, hashlib, json, random, subprocess, tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def signed(v):return (v+2**63)%2**64-2**63
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--calls',action='store_true');ap.add_argument('--output',default='work/p2/syntax-differential.json');a=ap.parse_args()
 rng=random.Random(125640);env={'va':-7,'vb':3,'vc':0,'vd':1023}
 def expr(depth):
  if not depth or rng.random()<.3:
   s=rng.choice(list(env)+['0','1','2','3','7','13','0007','1023']);return s,env.get(s,int(s) if s[0].isdigit() else 0)
  l,x=expr(depth-1);op=rng.choice('+-*/%')
  if op in '/%':r=str(rng.choice([1,2,3,7,13]));y=int(r)
  else:r,y=expr(depth-1)
  if op=='+':v=x+y
  elif op=='-':v=x-y
  elif op=='*':v=x*y
  else:
   q=abs(x)//abs(y)*(-1 if (x<0)!=(y<0) else 1);v=q if op=='/' else x-q*y
  if not -2**63 <= v < 2**63:raise OverflowError
  text='('+l+' '+op+' '+r+')'
  if a.calls and rng.random()<.35:text='oracle_id('+text+')'
  return text,v
 cases=[]
 while len(cases)<1200:
  try:cases.append(expr(rng.randrange(1,7)))
  except OverflowError:pass
 cases += [('va - vb - vd + 7',signed(-7-3-1023+7)),('va + vb * vd % 13',signed(-7+(3*1023)%13))]
 rows=[]
 with tempfile.TemporaryDirectory(prefix='syntax-gate-') as td:
  td=Path(td);src=td/'fresh.sov'
  # Batches force several independently parsed trees and repeated reuse of the
  # same storage with different source text. No compilation results are reused.
  for start in range(0,len(cases),100):
   batch=cases[start:start+100];src.write_text(('oracle_id vv:\n    if 0\n        return 123\n    return vv\n' if a.calls else '')+'main:\n'+''.join(f'    {k}: {v}\n' for k,v in env.items())+''.join('    print '+s+'\n' for s,v in batch))
   hashes=[]
   for flags in [[],['--syntax-tree'],['--syntax-tree','--plain']]:
    out=td/'program';out.unlink(missing_ok=True)
    p=subprocess.run([str((R/a.compiler).resolve()),str(src),*flags,'-o',str(out)],capture_output=True,timeout=30)
    assert p.returncode==0,(start,flags,p.stdout,p.stderr)
    e=subprocess.run([str(out)],capture_output=True,timeout=10)
    actual=e.stdout.decode().splitlines();expected=[str(v) for s,v in batch]
    assert e.returncode==0 and actual==expected,(start,flags,e.returncode,[(batch[i],v,expected[i]) for i,v in enumerate(actual) if v!=expected[i]][:5])
    hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
   assert hashes[0]==hashes[1],(start,'default/tree code generation differs')
   rows.append({'start':start,'cases':len(batch),'tree_default_byte_identity':True,'ordinary_tree_plain_executions':True})
 result={'compiler_sha256':hashlib.sha256((R/a.compiler).read_bytes()).hexdigest(),'seed':125640,'calls_enabled':a.calls,'cases':len(cases),'integer_oracle':'nonoverflowing signed 64-bit arithmetic and truncating signed quotient/remainder','rows':rows,'all_passed':True}
 (R/a.output).write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(cases),'independent arithmetic oracles, three modes, exact default/tree bytes')
if __name__=='__main__':main()
