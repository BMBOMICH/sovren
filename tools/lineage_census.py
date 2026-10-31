#!/usr/bin/env python3
# Lineage fleet census: compile every shipped native/emitter lineage driver
# from SOURCE with the current linux gate; classify errors; exit!=0 if mass changes.
import subprocess, os, glob, sys, json, collections
drvs = sorted(set(glob.glob('backends/native/*/compiler.sov') + glob.glob('backends/native/*/*/compiler.sov') + glob.glob('emitters/*/compiler.sov') + glob.glob('backends/native/store/*/compiler.sov')))
rows={}
for d in drvs:
    out='/tmp/census_'+d.replace('/','_').replace('.sov','')
    try:
        r=subprocess.run(['./compilers/linux/compiler', d, '-o', out], capture_output=True, text=True, timeout=150)
        o=r.stderr+r.stdout
        if os.path.exists(out): rows[d]='ok'
        else:
            errs=[l for l in o.splitlines() if 'Error:' in l]
            rows[d]=errs[0][:80] if errs else ('oom-kill' if r.returncode not in (0,1) else 'rc'+str(r.returncode))
    except subprocess.TimeoutExpired: rows[d]='timeout-150s'
    finally:
        if os.path.exists(out): os.unlink(out)
cls=collections.Counter(v if v=='ok' else (v.split(':')[1].strip() if ':' in v else v) for k,v in rows.items())
json.dump(rows, open('/tmp/census.json','w'), indent=1, sort_keys=True)
ok=[k for k,v in rows.items() if v=='ok']
print(f"census: {len(rows)} drivers, {len(ok)} build: {sorted(set(os.path.dirname(k) for k in ok))}")
print("fail classes:", dict(cls))
