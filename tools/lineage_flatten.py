#!/usr/bin/env python3
"""Flatten lineage drivers: recursively inline `include spec frm cnt (pars)? hash`
into literal current-file content (paren %k substitution, indent prefixing);
strip pin args from includes that remain (reported). Output: driver .flat.sov"""
import re, sys
from pathlib import Path
R=Path(".").resolve()
inc_re=re.compile(r'^(?P<ind>[ \t]*)include (?P<spec>\S+?\.sov)(?: +(?P<frm>\d+) +(?P<cnt>\d+))?(?: +\((?P<par>[^)]*)\))?(?: +#?-?\d+)?[ \t]*$')
cache_mark=re.compile(r'\b(ac_store|ac_try|ac_key|ac_mix|lsug_|dp_oc_|deepoc|prebuilt|sugar_cache|sdp_)')
def resolve(spec, base):
    for c in (base/spec, R/"library"/spec, R/spec, R/"compilers/shared"/Path(spec).name, R/"backends"/spec):
        if c.exists(): return c
    return None
expanded_cache={}
def expand_file(p, depth=0):
    lines=p.read_text().splitlines(); out=[]
    for L in lines:
        m=inc_re.match(L)
        if not m or not m.group('frm'):
            out.append(L); continue
        sp=resolve(Path(m.group('spec')), p.parent)
        if not sp: out.append(L); continue
        if depth>28: out.append(L); print(f"DEPTH-CAP {p} {m.group('spec')}"); continue
        key=(str(sp),int(m.group('frm')),int(m.group('cnt')),m.group('par'),m.group('ind'),depth<=0)
        src=sp.read_text().splitlines()
        frm,cnt=int(m.group('frm')),int(m.group('cnt'))
        sl=src[frm-1:frm-1+cnt]
        par=(m.group('par') or '').split()
        ind=m.group('ind')
        body=[]
        for s in sl:
            for k,pv in enumerate(par): s=s.replace('%'+str(k+1), pv)
            body.append(ind+s)
        out.extend(body)
    return out
def flatten(src, dst):
    p=Path(src); cur=p.read_text().splitlines()
    for it in range(30):
        txt="\n".join(cur); p2=p
        new=[]; any_inc=False
        for L in cur:
            m=inc_re.match(L)
            if m and m.group('frm'):
                any_inc=True
                sp=resolve(Path(m.group('spec')), p2.parent)
                if sp:
                    sl=sp.read_text().splitlines()[int(m.group('frm'))-1:int(m.group('frm'))-1+int(m.group('cnt'))]
                    par=(m.group('par') or '').split(); ind=m.group('ind')
                    for s in sl:
                        for k,pv in enumerate(par): s=s.replace('%'+str(k+1), pv)
                        new.append(ind+s)
                else:
                    print("UNRESOLVED", m.group('spec'), "in", p); new.append(L)
            else:
                new.append(L)
        cur=new
        if not any_inc: break
    Path(dst).write_text("\n".join(cur)+"\n")
    print(f"{dst}: {len(cur)} lines after flatten")
if __name__=='__main__':
    a=sys.argv[1:]; flatten(a[0], a[1])
