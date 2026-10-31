import subprocess, time, os, statistics, glob
TCC='tests/tccinst/bin/tcc'; SOV='compilers/linux/compiler'
def bench(cmd, n=7):
    ts=[]
    for _ in range(n):
        t0=time.perf_counter()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ts.append((time.perf_counter()-t0)*1000)
    return statistics.median(ts)
print(f"{'case':24} {'bytes':>9} {'tcc ms':>9} {'sov ms':>9} {'ratio':>7}")
for name in ('s','m','l'):
    cb=os.path.getsize(f'tests/tccbench/{name}.c'); sb=os.path.getsize(f'tests/tccbench/{name}.sov')
    tm=bench([TCC,'-o',f'/tmp/b_{name}_c',f'tests/tccbench/{name}.c'])
    if os.path.exists('/tmp/sov_nopar'): os.remove('/tmp/sov_nopar')
    sm=bench([SOV,f'tests/tccbench/{name}.sov','-o',f'/tmp/b_{name}_s'])
    print(f"{name+' (c '+str(cb)+'B)':24} {sb:>9} {tm:>9.2f} {sm:>9.2f} {sm/tm:>6.1f}x")
sov_in=sum(os.path.getsize(f) for f in ['compilers/linux/compiler.sov','compilers/shared/cx86.sov','runtime.sov']+glob.glob('compilers/shared/cx86_p*.sov'))
if os.path.exists('/tmp/sov_nopar'): os.remove('/tmp/sov_nopar')
sm=bench([SOV,'compilers/linux/compiler.sov','-o','/tmp/b_self'], n=5)
print(f"{'SOVREN self':24} {sov_in:>9} {'':>9} {sm:>9.2f}  ({sov_in/1024/sm*1000:.0f} KB/s)")
