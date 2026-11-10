#!/usr/bin/env python3
"""Fail-closed Linux P0 correctness gate. Never installs the candidate.
Legacy all/fast execution is a separate required integration result, not hidden here.
"""
import argparse,hashlib,importlib.util,json,subprocess,tempfile,os,signal,re,struct,random,math
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--flag',action='append',default=[]);ap.add_argument('--output',default='work/p0/gate.json');a=ap.parse_args();compiler=(R/a.compiler).resolve()
 spec=importlib.util.spec_from_file_location('conf',R/'tests/conformance/language_conformance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 rows=[]
 def run(cmd,timeout=60,cwd=R):
  proc=subprocess.Popen(list(map(str,cmd)),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  try:out,err=proc.communicate(timeout=timeout);rc=proc.returncode
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate();rc=124
  return subprocess.CompletedProcess(cmd,rc,out,err)
 def record(name,ok,**kwargs):rows.append(dict(name=name,ok=bool(ok),**kwargs));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 def sidecars():return sorted(str(p.relative_to(R)) for p in R.rglob('*') if p.is_file() and (p.name.endswith(('.ac','.ac.bin','.sug','.lsug','.plk','.deepoc','.state_o')) or '.prebuilt' in p.parts))
 before=sidecars()
 with tempfile.TemporaryDirectory(prefix='sovren-p0-') as td:
  d=Path(td)
  def build(src,out,flags=()):
   out.unlink(missing_ok=True);b=run([compiler,src,*a.flag,*flags,'-o',out]);return b,b.returncode==0 and out.is_file() and out.stat().st_size>0
  for case,expected in m.EXPECTED.items():
   o=d/'case';b,ok=build(R/'tests/conformance/corpus'/case,o)
   e=run([o,*m.CASE_ARGV.get(case,[])],10) if ok else None
   record(case,ok and e.returncode==0 and e.stdout.decode(errors='replace').splitlines()==expected,compile_rc=b.returncode,run_rc=e.returncode if e else None,stdout=e.stdout.decode(errors='replace') if e else '')
  for name,text,expected in [
   ('parallel-literals','use suite\nmain:\n    print "CHECK"\n    print 123\n','CHECK\n123\n'),
   ('parallel-text-condition','use string\nmain:\n    s: str_cat("con", "formance")\n    if str_eq(s, "conformance") = 1\n        print 1\n    print 99\n','1\n99\n'),
   ('float-boundary','use f64\nmain:\n    print f64_to_i64(f64_add(f64_from_i64(9007199254740992), f64_from_i64(1)))\n    print f64_to_i64(f64_from_i64(-9007199254740992))\n','9007199254740992\n-9007199254740992\n')]:
   p=d/(name+'.sov');p.write_text(text)
   for fl in [[],['--plain'],['--no-dce']]:
    o=d/'probe';b,ok=build(p,o,fl);e=run([o],10) if ok else None
    record(name+str(fl),ok and e.returncode==0 and e.stdout.decode(errors='replace')==expected,run_rc=e.returncode if e else None,stdout=e.stdout.decode(errors='replace') if e else '')
  # --prof deliberately forces the existing serial path. Compare decoded
  # payload bytes against automatic-parallel builds, not only console text.
  esc=d/'escaped.sov';esc.write_text('use suite\nmain:\n    print "A' + chr(92)*4 + 'nB"\n    print "C' + chr(92)*4 + 'tD"\n    print "E' + chr(92)*2 + 'nF"\n')
  expected=b'A'+bytes([92,92])+b'nB\nC'+bytes([92,92])+b'tD\nE'+bytes([92])+b'nF\n'
  payloads=[]
  for flags in [[],['--prof'],['--no-dce'],['--prof','--no-dce']]:
   o=d/'escaped';b,ok=build(esc,o,flags);e=run([o],10) if ok else None
   payloads.append(e.stdout.hex() if e else None)
   record('decoded-backslashes'+str(flags),ok and e.returncode==0 and e.stdout==expected,actual=e.stdout.hex() if e else None,expected=expected.hex())
  regression_cases=[
   ('forward-return', 'main:\n    print greeting()\ngreeting:\n    return "hello"\n', 'hello\n'),
   ('forward-chain', 'main:\n    print first()\nfirst:\n    return second()\nsecond:\n    return third()\nthird:\n    return "chained"\n', 'chained\n'),
   ('frac-text', 'use frac\nmain:\n    print frac_text(frac_add(frac_make(1, 2), frac_make(1, 3)))\n', '5/6\n'),
   ('immutable', 'main:\n    immutable n: 5\n    print n\n    print n\n', '5\n5\n'),
   ('effectful-spawn', 'wk n:\n    print n\n    return n\nmain:\n    h: spawn wk(7)\n    join h\n    print 9\n', '7\n9\n'),
   ('not-text-after-reassign', 'main:\n    print number()\nnumber:\n    s: "text"\n    s: 7\n    return s\n', '7\n'),
  ]
  for name,src,expected in regression_cases:
   p=d/(name+'.sov');p.write_text(src)
   for flags in [[],['--plain'],['--no-dce']]:
    o=d/'regression';b,ok=build(p,o,flags);e=run([o],10) if ok else None
    record(name+str(flags),ok and e.returncode==0 and e.stdout.decode(errors='replace')==expected,compile_rc=b.returncode,run_rc=e.returncode if e else None,actual=e.stdout.decode(errors='replace') if e else b.stdout.decode(errors='replace')[-400:])
  thread_names={'thread slot round trip','thread join waits for the job','thread six value spawn','thread eight way sum','mutex serialises two threads','thread allocates from its private context','thread free list recycles the block','context exhaustion falls back to the global heap','eight threads churn private contexts'}
  for name,src,expected in re.findall(r'tr_thread_expect\("([^"\n]+)", ("(?:[^"\\]|\\.)*"), ("(?:[^"\\]|\\.)*")\)',(R/'library/suite.sov').read_text()):
   if name not in thread_names:continue
   p=d/'thread.sov';p.write_text(json.loads(src))
   for flags in [[],['--no-dce']]:
    o=d/'thread';b,ok=build(p,o,flags);e=run([o],10) if ok else None
    record(name+str(flags),ok and e.returncode==0 and e.stdout.decode().strip()==json.loads(expected),compile_rc=b.returncode,run_rc=e.returncode if e else None,actual=e.stdout.decode(errors='replace') if e else '')
  def signed(x):return x if x<2**63 else x-2**64
  def number(x):return struct.unpack('>d',x.to_bytes(8,'big'))[0]
  def bits(x):return int.from_bytes(struct.pack('>d',x),'big')
  pairs=[(bits(2.0**53),bits(1.0)),(bits(2.0**53+2),bits(1.0)),(bits(-2.0**53),bits(-1.0)),(1,1),(2**52-1,1),(bits(1.0),1),(0,2**63),(2**63,2**63),(bits(float('inf')),bits(float('-inf'))),(0x7ff0000000000042,bits(1.0)),(bits(1.0),0xfff8000000000043)]
  rng=random.Random(8675309)
  pairs += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(96)]
  lines=['use f64','main:'];oracle=[]
  for x,y in pairs:
   if math.isnan(number(x)):z=x
   elif math.isnan(number(y)):z=y
   else:
    n=number(x)+number(y);z=0x7ff0000000000001 if math.isnan(n) else bits(n)
   lines += [f'    a: {signed(x)}',f'    b: {signed(y)}','    print f64_add(a, b)'];oracle.append(str(signed(z)))
  p=d/'f64-bits.sov';p.write_text('\n'.join(lines)+'\n')
  for flags in [[],['--plain'],['--no-dce']]:
   o=d/'f64-bits';b,ok=build(p,o,flags);e=run([o],10) if ok else None
   record('f64-add-107-bit-oracles'+str(flags),ok and e.returncode==0 and e.stdout.decode().splitlines()==oracle,compile_rc=b.returncode,run_rc=e.returncode if e else None)
  for name,src in [('undeclared-read','main:\n    print missing\n'),('call-arity','add a b:\n    return a + b\nmain:\n    print add(1)\n')]:
   p=d/(name+'.sov');p.write_text(src);b,ok=build(p,d/'invalid')
   record(name,not ok and b.returncode!=0 and b'Error' in b.stdout+b.stderr)
  # Exercise the production native atom predicate on every byte value,
  # including empty strings and a valid-character suffix.
  atom_src=(R/'compilers/shared/cx86_p4.sov').read_text();atom_src=atom_src[atom_src.index('expr_atom e:'):atom_src.index('\nexpr_atom_word e:')]
  p=d/'native-atom.sov';p.write_text('use string\nlength s:\n    return _sov_strlen(s)\nemit value:\n    return 0\nemit3 a b c:\n    return 0\nocgrow:\n    return 0\n'+atom_src+'\nmain:\n    s: _sov_alloc(4)\n    i: 0\n    as long as i < 256\n        poke_byte(s, 0, i)\n        poke_byte(s, 1, 0)\n        print expr_atom(s)\n        poke_byte(s, 1, 65)\n        poke_byte(s, 2, 0)\n        print expr_atom(s)\n        i: i + 1\n')
  o=d/'native-atom';b,ok=build(p,o);e=run([o],10) if ok else None
  expected=''.join((str(int(i==95 or 48<=i<=57 or 65<=i<=90 or 97<=i<=122))+'\n')*2 for i in range(256))
  record('native-atom-all-256-bytes',ok and e.returncode==0 and e.stdout.decode()==expected,compile_rc=b.returncode,run_rc=e.returncode if e else None)
  # Native allocation and an emulated exit: verify the canary disappears
  # from heap memory only for a private program, with a positive control.
  for private,want in [(True,'0'),(False,'1')]:
   p=d/'wipe.sov';p.write_text('use string\nmain:\n'+('    private\n' if private else '')+'    s: str_copy("HEAPCANARY0123456789")\n    print s\n    _sov_print_int(s)\n')
   guest=d/'wipe-guest';b,ok=build(p,guest)
   wrapper=d/'wipe-check.sov';wrapper.write_text('use x86\nuse string\nuse num\nmain:\n    m: x86_new()\n    if x86_load(m, "'+str(guest)+'") is 0\n        sys_exit(2)\n    x86_run(m)\n    if x86_why(m) is not 1\n        print x86_reason(m)\n        sys_exit(3)\n    o: x86_out(m)\n    nl: str_find(o, "\\n")\n    address: str_num(str_trim(str_cut(o, nl + 1, str_len(o))))\n    found: 0\n    i: 0\n    as long as i < 65536\n        if x86_peek_q(m, address + i) is 4705770418013816136\n            found: 1\n        i: i + 1\n    print found\n')
   o=d/'wipe-check';wb,wok=build(wrapper,o);e=run([o],10) if wok and ok else None
   record('heap-wipe-'+('private' if private else 'positive-control'),ok and wok and e.returncode==0 and e.stdout.decode().strip()==want,actual=e.stdout.decode(errors='replace') if e else '')
  for src in ['x: 41\nmain argc argv:\n    y: x\n    print y\n','use suite\nmain:\n    print "DEBUG"\n']:
   p=d/'debug.sov';p.write_text(src);normal=d/'normal';debug=d/'debug';nb,nok=build(p,normal);db,dok=build(p,debug,['--debug']);mp=Path(str(debug)+'.map')
   record('debug-code-identical-'+str(len(src)),nok and dok and digest(normal)==digest(debug) and mp.is_file() and mp.read_text().startswith('# src_base '))
  repl=d/'repl';rb,rok=build(R/'repl.sov',repl)
  envdir=d/'repl-environment';(envdir/'compilers/linux').mkdir(parents=True)
  (envdir/'compilers/linux/compiler').symlink_to(compiler)
  (envdir/'library').symlink_to(R/'library',target_is_directory=True)
  (envdir/'runtime.sov').symlink_to(R/'runtime.sov')
  script=d/'repl.script';script.write_text('1+2\n2*21\nuse string\nstr_cat("a","b")\n')
  e=run([repl,script],20,cwd=envdir) if rok else None
  record('repl-fresh-script',rok and e.returncode==0 and e.stdout.decode().strip()=='3\n42\nok\nab',actual=e.stdout.decode(errors='replace') if e else rb.stdout.decode(errors='replace')[-300:])
  arm=d/'arm-library.sov';arm.write_text('use arm\nmain:\n    m: arm_new()\n    print arm_pc(m)\n')
  ab,aok=build(arm,d/'arm-library');ae=run([d/'arm-library'],10) if aok else None
  record('native-twins-no-false-frame-warning',aok and b'Warning' not in ab.stdout+ab.stderr and ae.returncode==0 and ae.stdout==b'0\n')
  launcher=envdir/'sovren';lb,lok=build(R/'launcher.sov',launcher)
  second=d/'launcher-second';sb,sok=build(R/'launcher.sov',second)
  record('linux-launcher-repeatable-build',lok and sok and digest(launcher)==digest(second))
  record('linux-launcher-installed-fresh',lok and digest(launcher)==digest(R/'sovren'))
  sample=d/'launcher-input.sov';sample.write_text('main:\n    print 42\n');out=d/'launcher-output'
  le=run([launcher,sample,'-o',out],10,cwd=envdir) if lok else None
  oe=run([out],10) if le and le.returncode==0 and out.is_file() else None
  record('linux-launcher-dispatch',oe is not None and oe.returncode==0 and oe.stdout==b'42\n')
  jobs=d/'batch.jobs';jobs.write_text(str(sample)+' '+str(out)+'\n')
  be=run([launcher,'--batch',jobs],10,cwd=envdir) if lok else None
  record('linux-launcher-batch-success',be is not None and be.returncode==0 and b'batch: 1 ok, 0 failed' in be.stdout)
  jobs.write_text(str(sample)+' '+str(out)+'\n'+str(d/'missing.sov')+' '+str(d/'missing-output')+'\n')
  be=run([launcher,'--batch',jobs],10,cwd=envdir) if lok else None
  record('linux-launcher-batch-failure-is-failure',be is not None and be.returncode==1 and b'batch: 1 ok, 1 failed' in be.stdout)
  # Keep the compiler-only source exceptions fail-closed under mutation.
  policy_cases=[('named-monotonic','now_ns:\n    syscall(228, 1, 0)\n',-1),('wrong-clock','now_ns:\n    syscall(228, 0, 0)\n',228),('unrelated-clock','evil:\n    syscall(228, 1, 0)\n',228),('network','now_ns:\n    syscall(41, 0, 0)\n',41),('exec','par_setup:\n    syscall(59, 0, 0)\n',59),('worker-fork','par_setup:\n    syscall(57, 0)\n',-1),('other-fork','evil:\n    syscall(57, 0)\n',57)]
  for pname,content,want in policy_cases:
   fixture=d/'policy-input.txt';fixture.write_text(content)
   source=d/'policy-check.sov';source.write_text('use suite\nmain:\n    print pv_source_clean("'+str(fixture)+'", 3)\n')
   pb,pok=build(source,d/'policy-check');pe=run([d/'policy-check'],10) if pok else None
   record('privacy-source-'+pname,pok and pe.returncode==0 and pe.stdout.decode().strip()==str(want),actual=pe.stdout.decode(errors='replace') if pe else pb.stdout.decode(errors='replace')[-400:])
  for name,text in [('overflow','g: 9223372036854775807\nmain:\n    print g + 1\n    print "BAD"\n'),('divide-zero','g: 0\nmain:\n    print 1 / g\n    print "BAD"\n')]:
   p=d/(name+'.sov');p.write_text(text);o=d/'trap';b,ok=build(p,o);e=run([o],10) if ok else None
   record(name,ok and e.returncode!=0 and e.returncode not in [-11,-4] and b'BAD' not in e.stdout,compile_rc=b.returncode,run_rc=e.returncode if e else None,stdout=e.stdout.decode(errors='replace') if e else '')
  p=d/'bad.sov';p.write_text('main:\n    missing_task(1)\n');b,ok=build(p,d/'bad');record('undefined-call-diagnostic',not ok and b.returncode!=0 and b'Error' in b.stdout+b.stderr)
  for flag in ['--cache','--usepfx','--uncached','--no-cache']:
   b,ok=build(R/'tests/hello.sov',d/'flag',[flag]);record('reject '+flag,not ok and b.returncode!=0)
  p=d/'mutation.sov';results=[]
  for value in [101,202,101]:
   p.write_text(f'main:\n    print {value}\n');o=d/'mutation';b,ok=build(p,o);e=run([o],10) if ok else None
   results.append((e.returncode,e.stdout.decode(errors='replace'),digest(o)) if e else None)
  record('fresh-source-mutation',all(r and r[0]==0 and r[1]==f'{v}\n' for r,v in zip(results,[101,202,101])) and results[0][2]==results[2][2],results=results)
  src=R/'compilers/linux/compiler.sov';gens=[];exe=compiler
  for i in range(3):
   out=d/f'g{i}';b=run([exe,src,*a.flag,'-o',out]);
   if b.returncode or not out.is_file():break
   gens.append(digest(out));exe=out
  record('ordinary-g2-equals-g3',len(gens)==3 and gens[1]==gens[2],generations=gens)
  for name in ['all','fast']:
   b,ok=build(R/'tests'/(name+'.sov'),d/name);record(name+'-compile',ok,compile_rc=b.returncode,execution_required_separately=True)
  o=d/'profile';b,ok=build(R/'tests/hello.sov',o,['--prof'])
  try:profile=json.loads(b.stderr);valid=profile['schema']==1 and bool(profile['marks'])
  except (ValueError,KeyError):valid=False
  record('single-profile-report',ok and valid,stderr=b.stderr.decode(errors='replace')[-300:])
 policy=run(['python3',R/'tools/no_cache_policy.py']);record('no-cache-source-tripwire',policy.returncode==0,stdout=policy.stdout.decode())
 record('no-new-sidecars',before==sidecars())
 output=R/a.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(dict(compiler=str(compiler),flags=a.flag,sha256=digest(compiler),cells=rows,all_pass=all(r['ok'] for r in rows),focused_gate_only=True),indent=2)+'\n')
 raise SystemExit(0 if all(r['ok'] for r in rows) else 1)
if __name__=='__main__':main()
