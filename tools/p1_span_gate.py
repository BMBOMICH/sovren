#!/usr/bin/env python3
"""Differential boundary/annotation test for the safety scanner's cut->cutn change.
Compare the exact frozen P0 function against the changed function; fresh builds,
no translated-output reuse. Input files are data read by each test executable.
"""
import argparse,hashlib,json,random,subprocess,tempfile,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('compiler');ap.add_argument('--output',default='work/p1/span-differential.json');a=ap.parse_args();cc=(R/a.compiler).resolve();current=(R/'compilers/linux/compiler.sov').read_text()
 with zipfile.ZipFile(R/'work/p0/p0-source-snapshot.zip') as z:old=z.read('compilers/linux/compiler.sov').decode()
 def function(text):return text[text.index('u_scan source:\n'):text.index('\nnhash s:',text.index('u_scan source:\n'))]
 baseline=current.replace(function(current),function(old),1)
 rng=random.Random(4815162342);cases=[b'',b'peek_byte(p, 0)',b'poke_byte(p, 0, 1)\n',b'# unsafe-module\nmain:\n    peek_byte(p, 0)',b'# unsafe\npeek_byte(p, 0)',b'unsafe:\n    peek_raw(p, 0)\npeek_byte(p, 0)',b'print "peek_byte(p, 0)"',b'print "a\\\"poke_raw(p)"',b'\r\n\tport_out(1, 2)\r\n']
 atoms=[b'peek_byte(p, 0)',b'poke_byte(p, 0, 1)',b'peek_raw(p, 0)',b'poke_raw(p, 0, 1)',b'port_in(1)',b'port_out(1, 2)',b'print "peek_byte(p, 0)"',b'# unsafe-module',b'# unsafe',b'unsafe:',b'# peek_byte(p, 0)',b'plain: 3',b'print "\\\\\\\"poke_raw"',b'']
 for _ in range(512):
  lines=[rng.choice([b'',b' ',b'    ',b'\t',b'        '])+rng.choice(atoms)+rng.choice([b'',b' ',b'\r']) for _ in range(rng.randrange(1,15))]
  cases.append(b'\n'.join(lines)+rng.choice([b'',b'\n']))
 harness='''\nmain argc argv:
    if argc is 0
        emit3(0, 0, 0)
        emit(0)
        ocgrow()
    i: 1
    as long as i < argc
        text: file_read_all(peek_ptr(argv, i))
        if text is 0
            sys_exit(2)
        u_listing: 0
        u_bare_total: 0
        print u_scan(text)
        print u_bare_total
        i: i + 1
'''
 with tempfile.TemporaryDirectory(prefix='sovren-span-diff-') as td:
  d=Path(td);fixtures=[]
  for i,data in enumerate(cases):p=d/(str(i)+'.txt');p.write_bytes(data);fixtures.append(str(p))
  outputs=[]
  for label,source in [('baseline',baseline),('candidate',current)]:
   p=d/(label+'.sov');p.write_text(source.replace('main argc argv:\n','original_main argc argv:\n',1)+harness);out=d/label
   b=subprocess.run([str(cc),str(p),'-o',str(out)],cwd=R,capture_output=True,timeout=30)
   if b.returncode:raise RuntimeError((b.stdout+b.stderr).decode()[-4000:])
   e=subprocess.run([str(out),*fixtures],cwd=R,capture_output=True,timeout=15)
   if e.returncode or len(e.stdout.splitlines())!=len(cases)*2:raise RuntimeError('scanner harness failed '+label+repr(e.stdout[-500:]))
   outputs.append(e.stdout)
  if outputs[0]!=outputs[1]:raise RuntimeError('safety scanner results changed')
 result={'schema':1,'cases':len(cases),'seed':4815162342,'all_pass':True,'comparison':'exact P0 u_scan body vs bounded-span change; result and unmarked-bare-access count compared','compiler_sha256':hashlib.sha256(cc.read_bytes()).hexdigest(),'results_sha256':hashlib.sha256(outputs[0]).hexdigest()}
 (R/a.output).write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(cases),'scanner boundary/annotation differential cases')
if __name__=='__main__':main()
