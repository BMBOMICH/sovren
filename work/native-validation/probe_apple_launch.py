from pathlib import Path
import hashlib,json,struct,subprocess
def probe(root):
    c=root/'reference.c';c.write_text('int main(void) {return 7;}\n')
    subprocess.run(['clang',c,'-o',root/'reference'],check=True)
    ref=(root/'reference').read_bytes();pos=32
    for i in range(struct.unpack_from('<I',ref,16)[0]):
        cmd,size=struct.unpack_from('<II',ref,pos)
        if cmd==29:
            so,sz=struct.unpack_from('<II',ref,pos+8)
            print('REFERENCE SIGNATURE '+ref[so:so+160].hex(),flush=True)
        pos+=size
    q=subprocess.run([root/'reference'],capture_output=True);print('REFERENCE EXIT '+str(q.returncode),flush=True)
    original=(root/'tiny.macho').read_bytes()
    def signature(b):
        at=32
        for i in range(struct.unpack_from('<I',b,16)[0]):
            cmd,size=struct.unpack_from('<II',b,at)
            if cmd==29:
                off=struct.unpack_from('<I',b,at+8)[0]; cd=off+20
                ho=struct.unpack_from('>I',b,cd+16)[0]
                slots=struct.unpack_from('>I',b,cd+28)[0]
                for pg in range(slots):b[cd+ho+pg*32:cd+ho+(pg+1)*32]=hashlib.sha256(b[pg*4096:min((pg+1)*4096,off)]).digest()
                return
            at+=size
    cases=[]
    for flags in (0,1,0x200001,0x200005):
        b=bytearray(original);struct.pack_into('<I',b,24,flags);cases.append(('flags-'+hex(flags),b))
    b=bytearray(original)
    off=struct.unpack_from('<I',b,568)[0]+20
    struct.pack_into('>I',b,off+12,0x20002)
    cases.append(('linker-signature',b))
    for flags in (0,0x200000):
        b=bytearray(original);struct.pack_into('<I',b,24,flags)
        # A native exit syscall isolates launch from all Sovren startup code.
        struct.pack_into('<III',b,16384,0xd28000e0,0xd2800030,0xd4001001)
        cases.append(('direct-exit-'+hex(flags),b))
    for subtype in (1,2):
        b=bytearray(original);struct.pack_into('<I',b,8,subtype);cases.append(('cpu-'+str(subtype),b))
    b=bytearray(original);struct.pack_into('>I',b,off+12,0x20002)
    # Linker's ad-hoc signature uses an empty CMS blob as a second slot.
    start=struct.unpack_from('<I',b,568)[0]; cd=bytes(b[start+20:])
    sig=struct.pack('>5I',0xfade0cc0,28+len(cd)+8,2,0,28)+struct.pack('>2I',0x10000,28+len(cd))+cd+struct.pack('>2I',0xfade0b01,8)
    b[start:]=sig;struct.pack_into('<I',b,572,len(sig));struct.pack_into('<Q',b,624,len(sig))
    cases.append(('cms-slot',b))
    rows=[]
    for name,b in cases:
        signature(b);p=root/(name+'.macho');p.write_bytes(b);p.chmod(0o755)
        q=subprocess.run([p],capture_output=True,timeout=30)
        row={'name':name,'rc':q.returncode,'stdout':q.stdout.decode(errors='replace'),'stderr':q.stderr.decode(errors='replace')};rows.append(row);print(json.dumps(row),flush=True)
    (root/'launch-probes.json').write_text(json.dumps(rows,indent=2))
    q=subprocess.run(['sudo','log','show','--last','1m','--style','compact','--predicate','process == "kernel" AND eventMessage CONTAINS[c] "sovren-arm64-repair"'],capture_output=True,timeout=40)
    print('LAUNCH LOG '+q.stdout.decode(errors='replace'),flush=True)
