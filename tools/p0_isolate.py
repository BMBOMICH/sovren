"""Investigation-only controlled source mutations, restored after each build."""
from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1];W=R/'work/p0';seed=R/'compilers/linux/compiler';rows=[]
experiments=[
 ('no_pool_gc','compilers/shared/cx86_p7.sov','    sg_s1: intern_kid("str")','    return\n    sg_s1: intern_kid("str")'),
 ('no_native_intern','compilers/shared/cx86_p3.sov','    if tid is kid_intern_fast -> return emit_nt_intern_fast()','    if tid is kid_intern_fast -> return 0'),
 ('no_native_streq','compilers/shared/cx86_p3.sov','    if tid is kid__sov_str_eq -> return emit_nt_streq()','    if tid is kid__sov_str_eq -> return 0'),
 ('no_native_f64add','compilers/shared/cx86_p3.sov','    if tid is kid_f64_add -> return emit_nt_f64add()','    if tid is kid_f64_add -> return 0')]
for name,rel,old,new in experiments:
 p=R/rel;original=p.read_text();assert old in original
 try:
  p.write_text(original.replace(old,new,1));exe=W/name
  c=subprocess.run([str(seed),'compilers/linux/compiler.sov','-o',str(exe)],cwd=R,capture_output=True,timeout=30)
  record=dict(name=name,build_rc=c.returncode,tests=[])
  if c.returncode==0:
   for src in ['library_str','string_if','float_add']:
    out=W/(name+'-'+src);b=subprocess.run([str(exe),'/home/user/investigation/deeper/'+src+'.sov','-o',str(out)],cwd=R,capture_output=True,timeout=20)
    row=dict(source=src,compile_rc=b.returncode)
    if b.returncode==0:
     try:
      e=subprocess.run([str(out)],capture_output=True,timeout=3);row.update(rc=e.returncode,out=e.stdout.decode(errors='replace'))
     except subprocess.TimeoutExpired:row['timeout']=True
    record['tests'].append(row)
  rows.append(record);print(json.dumps(record),flush=True)
 finally:p.write_text(original)
(W/'isolation.json').write_text(json.dumps(rows,indent=2))
