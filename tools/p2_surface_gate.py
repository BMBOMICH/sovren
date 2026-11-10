#!/usr/bin/env python3
"""Exact observable differential gate for migrated syntax and legacy declines."""
from pathlib import Path
import argparse,subprocess,tempfile,json,hashlib
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--output',default='work/p2/surface-gate.json');a=ap.parse_args();cc=str((R/a.compiler).resolve())
 expressions=['nestedloops()','two_loops()','compound_probe()','xs[0]','xs[id(1)]','mutate(xs)','runspawn()','seven(loud(1),loud(2),loud(3),loud(4),loud(5),loud(6),loud(7))','add(loud(1),loud(2))','id(7)','id(id(7)+3)*5','add(id(2),id(3)*5)','seven(1,2,3,4,5,6,id(7))','id(-7)+3','(id(7))','zero()','const(1+2)*7','id(const(7*3))','id(const(va))','wrap_add(id(9223372036854775807),1)','wrap_mul(id(7),id(3))','band(id(7),id(3))','bor(id(7),id(8))','bxor(id(7),id(3))','bshl(id(7),id(2))','bshr(id(-7),id(2))','bsar(id(-7),id(2))','id(7) & 3 | 8 ^ 3','id(7) << 2','id(-7) >> 2','id(-7) >>> 2','id(7) == 7','id(7) != 3','id(7) >= 7','id(7) <= 7','id(-7) < 2','id(7) > 2','id(7) == 7 != 3','id(7) < 2 > 3','id(7) & 3 == 1','0 && loud(7)','1 || loud(7)','1 && loud(7)','0 || loud(7)','1 || (0 && loud(9))','0 && (1 || loud(9))','text("a,b(c)")','text("a is b")','text("a is not b")','text("a and b or c")','text("a \\" b")','text(("hello"))','text("a" + "b")','add(id(1),id(2),id(3))','add(id(1),)','add(,id(1))','id(0x7) + 2','id(0b101) + 2','id(1.25)','id(length of "abcd")','text(id(as ptr "abc"))','text(id("abc" as ptr))','id(not_valid_word)','id(7) / 0','9223372036854775807 + id(1)','id(-9223372036854775808) / -1']
 pre='nestedloops:\n    ii: 0\n    ss: 0\n    as long as ii < 3\n        jj: 0\n        as long as jj < 2\n            ss: ss + id(ii + jj)\n            jj: jj + 1\n        ii: ii + 1\n    return ss\ntwo_loops:\n    nn: 7\n    ss: 0\n    as long as nn > 0\n        ss: ss + id(nn)\n        nn: nn - 1\n    as long as ss > 10\n        ss: ss - id(3)\n    return ss\ncompound_probe:\n    vv: 10\n    vv += 7\n    vv *= 3\n    vv -= 1\n    return vv\nworker vv:\n    return vv\nrunspawn:\n    hh: spawn worker(7)\n    join hh\n    return 77\nmutate qq:\n    qq[0]: 33\n    aa: qq[0]\n    bb: qq[1]\n    return aa + bb\nid vv:\n    return vv\nadd xx yy:\n    return xx + yy\nseven aa bb cc dd ee ff gg:\n    return aa+bb+cc+dd+ee+ff+gg\nzero:\n    return 0\nloud vv:\n    print vv\n    return vv\ntext vv:\n    return as text vv\n'
 rows=[]
 with tempfile.TemporaryDirectory(prefix='syntax-surface-') as td:
  td=Path(td);src=td/'input.sov';out=td/'program'
  for i,expr in enumerate(expressions):
   # Both ordinary expression and return-expression entry points matter.
   for entry in ['print','return']:
    source=pre+'main:\n    va: 7\n    xs: _sov_list_new()\n    xs: _sov_list_add(xs, 11)\n    xs: _sov_list_add(xs, 22)\n'
    if entry=='print':source+='    print '+expr+'\n'
    else:source+='    print result(va, xs)\nresult va xs:\n    return '+expr+'\n'
    src.write_text(source);observations=[];hashes=[]
    for flags in [['--legacy-syntax'],[],['--syntax-tree'],['--syntax-reference']]:
     out.unlink(missing_ok=True);p=subprocess.run([cc,str(src),*flags,'-o',str(out)],cwd=R,capture_output=True,timeout=30)
     obs={'compile_rc':p.returncode,'compile_stdout':p.stdout.decode(errors='replace'),'compile_stderr':p.stderr.decode(errors='replace')}
     if p.returncode==0:
      e=subprocess.run([str(out)],capture_output=True,timeout=5);obs.update(run_rc=e.returncode,stdout=e.stdout.decode(errors='replace'),stderr=e.stderr.decode(errors='replace'));hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
     observations.append(obs)
    known={'nestedloops()':'9\n','two_loops()':'10\n','compound_probe()':'50\n','xs[0]':'11\n','mutate(xs)':'55\n','runspawn()':'77\n','id(7)':'7\n','0 && loud(7)':'0\n','1 || loud(7)':'1\n'}
    if expr in known:
     assert all(o.get('run_rc')==0 and o.get('stdout')==known[expr] for o in observations),(expr,entry,observations)
    same=len({json.dumps(o,sort_keys=True) for o in observations})==1;rows.append({'expression':expr,'entry':entry,'same_observables':same,'byte_identity':len(set(hashes))<=1,'observations':observations if not same else observations[:1]})
    if not same:print('FAIL',entry,expr,observations,flush=True)
 assert sum('run_rc' in row['observations'][0] for row in rows)>=80, 'gate fixtures failed before execution'
 result={'compiler_sha256':hashlib.sha256(Path(cc).read_bytes()).hexdigest(),'cases':len(rows),'all_pass':all(x['same_observables'] for x in rows),'rows':rows}
 (R/a.output).write_text(json.dumps(result,indent=2)+'\n');print('PASS' if result['all_pass'] else 'FAIL',sum(x['same_observables'] for x in rows),'/',len(rows));raise SystemExit(0 if result['all_pass'] else 1)
if __name__=='__main__':main()
