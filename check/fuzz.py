#!/usr/bin/env python3
"""Generate random Sovren programs, compile them, and compare the answer
   against Python computing the same thing. Finds compiler bugs nobody
   thought to test for."""
import random, subprocess, sys, os

SOV = "./sovren"

def gen_expr(rng, depth, vars):
    if depth <= 0 or rng.random() < 0.3:
        if vars and rng.random() < 0.5:
            return rng.choice(vars)
        return str(rng.randint(0, 50))
    op = rng.choice(['+', '-', '*', '/', '%'])
    a = gen_expr(rng, depth-1, vars)
    b = gen_expr(rng, depth-1, vars)
    if op in '/%':
        b = str(rng.randint(1, 20))
    e = f"{a} {op} {b}"
    if rng.random() < 0.4:
        e = f"({e})"
    return e

def pyeval(expr, env):
    # Sovren integer division truncates toward zero like C
    import re
    def idiv(a, b): 
        q = abs(a)//abs(b)
        return q if (a<0)==(b<0) else -q
    def imod(a, b):
        return a - idiv(a,b)*b
    e = expr
    try:
        # replace / and % with helper calls via a tiny recursive parse
        return eval_c(e, env)
    except Exception:
        return None

def eval_c(s, env):
    toks = tokenize(s)
    val, i = parse_add(toks, 0, env)
    return val

def tokenize(s):
    out=[]; i=0
    while i < len(s):
        c=s[i]
        if c.isspace(): i+=1; continue
        if c.isdigit():
            j=i
            while j<len(s) and s[j].isdigit(): j+=1
            out.append(('n', int(s[i:j]))); i=j; continue
        if c.isalpha() or c=='_':
            j=i
            while j<len(s) and (s[j].isalnum() or s[j]=='_'): j+=1
            out.append(('v', s[i:j])); i=j; continue
        out.append(('o', c)); i+=1
    return out

def parse_add(t,i,env):
    v,i = parse_mul(t,i,env)
    while i<len(t) and t[i][0]=='o' and t[i][1] in '+-':
        op=t[i][1]; i+=1
        r,i = parse_mul(t,i,env)
        v = v+r if op=='+' else v-r
    return v,i

def parse_mul(t,i,env):
    v,i = parse_atom(t,i,env)
    while i<len(t) and t[i][0]=='o' and t[i][1] in '*/%':
        op=t[i][1]; i+=1
        r,i = parse_atom(t,i,env)
        if op=='*': v=v*r
        elif op=='/':
            q=abs(v)//abs(r); v = q if (v<0)==(r<0) else -q
        else:
            q=abs(v)//abs(r); q = q if (v<0)==(r<0) else -q
            v = v - q*r
    return v,i

def parse_atom(t,i,env):
    if t[i][0]=='o' and t[i][1]=='(':
        v,i = parse_add(t,i+1,env)
        return v,i+1
    if t[i][0]=='n': return t[i][1], i+1
    if t[i][0]=='v': return env[t[i][1]], i+1
    raise ValueError

def gen_cond(rng, vars):
    a = gen_expr(rng, 1, vars)
    b = gen_expr(rng, 1, vars)
    op = rng.choice(['<','>','<=','>=','is','is not'])
    return f"{a} {op} {b}", (a,op,b)

def eval_cond(c, env):
    a,op,b = c
    va = eval_c(a, env); vb = eval_c(b, env)
    if op=='<': return 1 if va<vb else 0
    if op=='>': return 1 if va>vb else 0
    if op=='<=': return 1 if va<=vb else 0
    if op=='>=': return 1 if va>=vb else 0
    if op=='is': return 1 if va==vb else 0
    return 1 if va!=vb else 0

def run(seed, n=300):
    rng = random.Random(seed)
    bad = 0
    for it in range(n):
        nv = rng.randint(0,4)
        vars=[]; env={}; lines=["main:"]
        for k in range(nv):
            nm = f"v{k}"
            val = rng.randint(0,40)
            lines.append(f"    {nm}: {val}")
            vars.append(nm); env[nm]=val
        mode = rng.random()
        if mode < 0.55:
            e = gen_expr(rng, rng.randint(1,4), vars)
            want = pyeval(e, env)
            if want is None or abs(want) > 2**62: continue
            lines.append(f"    print {e}")
        elif mode < 0.8:
            ctext, ctup = gen_cond(rng, vars)
            want = eval_cond(ctup, env)
            lines.append(f"    if {ctext}")
            lines.append(f"        print 1")
            lines.append(f"    if not")
            lines.append(f"        print 0")
        else:
            lim = rng.randint(0, 12)
            step = rng.randint(1, 4)
            lines.append(f"    acc: 0")
            lines.append(f"    idx: 0")
            lines.append(f"    as long as idx < {lim}")
            lines.append(f"        acc: acc + idx")
            lines.append(f"        idx: idx + {step}")
            lines.append(f"    print acc")
            acc=0; idx=0
            while idx < lim:
                acc += idx; idx += step
            want = acc
        src="\n".join(lines)+"\n"
        open('/tmp/fuzz.sov','w').write(src)
        r=subprocess.run([SOV,'/tmp/fuzz.sov','-o','/tmp/fuzz.bin'],
                         capture_output=True, text=True)
        if r.returncode!=0 or b'Error' in r.stdout.encode():
            print("COMPILE FAIL:\n"+src+r.stdout); bad+=1; continue
        os.chmod('/tmp/fuzz.bin',0o755)
        g=subprocess.run(['/tmp/fuzz.bin'],capture_output=True,text=True,timeout=20)
        got=g.stdout.strip()
        if got != str(want):
            print(f"MISMATCH seed={seed} it={it}")
            print(src)
            print(f"  got  {got}")
            print(f"  want {want}")
            bad+=1
            if bad>4: return bad
    return bad

if __name__=='__main__':
    seed=int(sys.argv[1]) if len(sys.argv)>1 else 1
    n=int(sys.argv[2]) if len(sys.argv)>2 else 300
    b=run(seed,n)
    print(f"fuzz: {n} programs, {b} problems")
    sys.exit(1 if b else 0)
