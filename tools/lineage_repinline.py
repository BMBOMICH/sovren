#!/usr/bin/env python3
"""Error-driven lineage include re-pinner: compile, harvest 9901001 stale-pin
reports (spec / found-frm / count / found-hash), rewrite the pinned include
line in the driver source (bare-hash and #-hash forms), repeat until clean."""
import re, subprocess, sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
GATE=str(R/'compilers/linux/compiler')
def repin(src):
    log=[]
    for it in range(400):
        r=subprocess.run([GATE,str(src),'-o','/tmp/repinned.bin'],
                         cwd=R,capture_output=True,text=True)
        err=r.stderr+r.stdout
        if 'Wrote' in err and r.returncode==0:
            log.append(f"OK after {it} repins"); return True,log
        lines=err.splitlines()
        # find pattern: number\nspec\nfrm\ncnt\nhash
        m=None
        for i,ln in enumerate(lines):
            if re.fullmatch(r'9901001', ln.strip()) and i+4<len(lines):
                m=(lines[i+1].strip(),lines[i+2].strip(),lines[i+3].strip(),lines[i+4].strip()); break
        if not m:
            log.append('NON-PIN-ERROR: '+' | '.join(lines[:6])); return False,log
        spec,frm,cnt,hsh=m
        t=Path(src).read_text()
        # match: include spec ... (parens)? trailing hash (bare or #)
        pat=re.compile(r'^(?P<i>[ ]*)include '+re.escape(spec)+r'(?P<mid>(?: +\d+ +\d+)?(?: +\([^)]*\))?)(?: +#?-?\d+)?[ ]*$', re.M)
        mm=pat.search(t)
        if not mm:
            log.append(f'include line not found for {spec}'); return False,log
        nl=mm.group('i')+'include '+spec+' '+frm+' '+cnt+( ' '+hsh if hsh else '')
        # preserve parens group from mid if present
        par=re.search(r'(\([^)]*\))', mm.group('mid'))
        if par: nl=mm.group('i')+'include '+spec+' '+frm+' '+cnt+' '+par.group(1)+' '+hsh
        t=t[:mm.start()]+nl+t[mm.end():]
        Path(src).write_text(t)
    log.append('MAX-ITER'); return False,log
if __name__=='__main__':
    for s in sys.argv[1:]:
        ok,log=repin(s)
        print(('PASS ' if ok else 'FAIL ')+s+' : '+' ; '.join(log[-2:]))
