#!/usr/bin/env python3
# Autonomous lineage repair loop: compile driver -> read error line (splice-flat
# numbering) -> locate offending context in kit_expand'd flat -> apply rule -> recompile.
# Rules apply to the inc/driver SOURCES by exact-text reverse-map whenever possible.
import subprocess, sys, re, os
sys.path.insert(0, 'tools'); from kit_expand import expand
GATE='./compilers/linux/compiler'
INC=['library/inc/inc00.sov','library/inc/inc01.sov','library/inc/inc02.sov','library/inc/inc03.sov','library/inc/inc04.sov','library/inc/inc05.sov','library/inc/inc06.sov','compilers/shared/carm.sov','compilers/shared/ccore.sov']

def flat_of(driver):
    cur=open(driver).read().split('\n')
    for _ in range(8):
        open('/tmp/lfx.sov','w').write('\n'.join(cur))
        nxt=expand('/tmp/lfx.sov').split('\n')
        if nxt==cur: break
        cur=nxt
    return cur

def compile_err(driver):
    r=subprocess.run([GATE,driver,'-o','/tmp/lfx.sov.bin'],capture_output=True,text=True)
    if os.path.exists('/tmp/lfx.sov.bin'):
        os.unlink('/tmp/lfx.sov.bin'); return None
    out=r.stderr+r.stdout
    ms=re.findall(r'(?:^|\n)(\d+)\r?\n(Error: [^\n]+)', out)
    return (int(ms[-1][0]), ms[-1][1]) if ms else None

def fix_solo_group(lines, ln):
    """Rule 1: `<num>:`/`<word>:` header with a SINGLE bare-word member ->
    `member: num` (numeric) or delete-blank label semantics unchanged; or if group
    header has 0 members before a dedent, delete header line."""
    L=lines[ln-1]
    hm=re.match(r'^( *)(blank|-?\d+|[A-Za-z_]\w*):\s*$', L)
    if not hm: return None
    ind=hm.group(1); hdr=hm.group(2)
    # collect member lines directly under header
    j=ln; mem=[]
    while j<len(lines):
        s=lines[j]
        if s.strip()=='':
            j+=1; continue
        i2=len(s)-len(s.lstrip(' '))
        if i2<=len(ind): break
        if re.match(r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*$', s): mem.append(j)
        else: break
        j+=1
    if len(mem)==1:
        mword=lines[mem[0]].strip()
        if re.match(r'^-?\d+$', hdr):
            lines[mem[0]]=ind+mword+': '+hdr
            lines[ln-1]=''
            return f'collapse {hdr}: + {mword} -> {mword}: {hdr}'
        if hdr=='blank':
            # blank: grp with one name == name marker; current grammar solo blank: w/ 1 member is legal; shouldn't be here
            return None
    if len(mem)==0:
        nx=None
        for k in range(ln, min(ln+3,len(lines))):
            if lines[k].strip(): nx=lines[k]; break
        return None
    return None

def main(driver):
    fixes=0
    for it in range(40):
        res=compile_err(driver)
        if res is None:
            ln=err=None
        else:
            ln,err=res
        if ln is None:
            print(f'{driver}: CLEAN (build or non-line error) after {fixes} fixes')
            r=subprocess.run([GATE,driver,'-o','/tmp/lfx.sov.bin'],capture_output=True,text=True)
            print('  final:', ('BUILD '+str(os.path.getsize('/tmp/lfx.sov.bin'))) if os.path.exists('/tmp/lfx.sov.bin') else [l for l in (r.stderr+r.stdout).splitlines() if 'Error' in l][:1] or r.returncode)
            return
        flat=flat_of(driver) if it%5==4 or True else flat
        if ln>len(flat): print(f'{driver}: err line {ln} > flat {len(flat)}'); return
        if 'value group' in err:
            r_=fix_solo_group_init(flat, ln)
        else:
            print(f'{driver}: line {ln}: {err}  target={flat[ln-1][:70]!r}')
            r_=None
        if r_:
            tgt=r_[1]
            hit=None
            for f in [driver]+INC:
                t=open(f).read()
                if tgt in t and tgt.strip()!='':
                    open(f,'w').write(t); hit=f; break
            print(f'  FIX@{ln} {r_[0]} -> {hit}')
            fixes+=1
        else:
            print(f'{driver}: unhandled at line {ln}: {err}')
            for k in range(max(0,ln-4), min(len(flat), ln+2)):
                print(f'   {k+1:6} {flat[k][:88]}')
            return
def fix_solo_group_init(lines, ln):
    r=fix_solo_group(lines, ln)
    return (r, '\n'.join(lines)+'\n') if r else None
if __name__=='__main__':
    main(sys.argv[1])
