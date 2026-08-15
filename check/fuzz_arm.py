#!/usr/bin/env python3
"""Differential fuzz: compile the same random program for x86-64 and AArch64,
   run both, and require identical output."""
import random, subprocess, sys, os
sys.path.insert(0, 'check')
from fuzz import gen_expr, gen_cond, eval_cond, pyeval

def run(seed, n=60):
    rng = random.Random(seed)
    bad = 0
    for it in range(n):
        nv = rng.randint(0,4)
        vars=[]; env={}; lines=["main:"]
        for k in range(nv):
            nm=f"v{k}"; val=rng.randint(0,40)
            lines.append(f"    {nm}: {val}"); vars.append(nm); env[nm]=val
        if rng.random() < 0.6:
            e = gen_expr(rng, rng.randint(1,3), vars)
            if pyeval(e, env) is None: continue
            lines.append(f"    print {e}")
        else:
            ctext,_ = gen_cond(rng, vars)
            lines += [f"    if {ctext}", "        print 1", "    if not", "        print 0"]
        src="\n".join(lines)+"\n"
        open('/tmp/fz.sov','w').write(src)
        r1=subprocess.run(['./sovren','/tmp/fz.sov','-o','/tmp/fz.x86'],capture_output=True,text=True)
        r2=subprocess.run(['./sovren','/tmp/fz.sov','--android','-o','/tmp/fz.arm'],capture_output=True,text=True)
        if r1.returncode or r2.returncode: continue
        os.chmod('/tmp/fz.x86',0o755)
        a=subprocess.run(['/tmp/fz.x86'],capture_output=True,text=True,timeout=30).stdout.strip()
        b=subprocess.run(['python3','arm64/run_arm64.py','/tmp/fz.arm'],
                         capture_output=True,text=True,timeout=180).stdout.strip()
        if a!=b:
            print(f"DIVERGE seed={seed} it={it}"); print(src)
            print("  x86 :",a); print("  arm :",b); bad+=1
            if bad>3: return bad
    return bad

if __name__=='__main__':
    seed=int(sys.argv[1]) if len(sys.argv)>1 else 1
    n=int(sys.argv[2]) if len(sys.argv)>2 else 60
    b=run(seed,n)
    print(f"arm-diff fuzz: {n} programs, {b} divergences")
    sys.exit(1 if b else 0)
