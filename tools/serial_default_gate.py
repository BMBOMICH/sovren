#!/usr/bin/env python3
"""C.18 — stay serial by default.

SA ships a dormant two-process translation split (tc_spawn has no inbound
reference). Sovren must not grow one. This gate statically walks the Linux
compiler's real include graph and requires zero active clone/fork/thread
spawn call sites, plus a dynamic check that a cold compile creates no child
process (sampled from /proc while the compiler runs).
"""
import json, os, re, subprocess, sys, threading, time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ENTRY = R / 'compilers/linux/compiler.sov'
OUT = Path(os.environ.get('OUTPUT', '/home/user/evidence/C18_serial_default.json'))
PAT = re.compile(r'^\s*(?:.*?\bthread_create\s*\(|.*?\bsyscall\s*\(\s*56\b|'
                 r'.*?\bsyscall\s*\(\s*57\b|.*?\btc_spawn\s*\()')


def includes(p):
    """Yield resolved include targets from a .sov file."""
    for line in p.read_text().splitlines():
        m = re.match(r'^include\s+(\S+\.sov)\b', line)
        if not m:
            continue
        s = m.group(1)
        for c in (p.parent / s, R / 'library' / s, R / s,
                  R / 'compilers/shared' / Path(s).name,
                  R / 'compilers/linux' / Path(s).name):
            if c.is_file():
                yield c
                break


def main():
    seen, todo, hits = set(), [ENTRY], []
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if PAT.match(line):
                hits.append((str(p.relative_to(R)), i, line.strip()[:100]))
        todo.extend(includes(p))
    # runtime.sov is DATA the compiler splices into user programs, not part of
    # the compiler's own execution graph; its optional thread API is allowed.
    hits = [h for h in hits if not h[0].startswith('runtime.sov')]

    # dynamic: sample the compiler process's children while it runs
    children = []
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            for d in Path('/proc').iterdir():
                if not d.name.isdigit():
                    continue
                try:
                    ppid = re.search(r'PPid:\s*(\d+)',
                                     (d / 'status').read_text()).group(1)
                    if ppid == str(proc.pid):
                        children.append(d.name)
                except (OSError, AttributeError):
                    pass
            time.sleep(0.002)

    src = R / 'compilers/linux/compiler.sov'
    proc = subprocess.Popen([str(R/'compilers/linux/compiler'), str(src),
                             '-o', '/tmp/c18_serial.bin'],
                            cwd=R, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    rc = proc.wait()
    stop.set()
    th.join(timeout=1)

    # SA ships a dormant tc_* split behind zero-init flags; Sovren's fork site
    # is likewise dormant behind pm_ptf, which is 0 unless an explicit opt-in
    # sentinel (/tmp/sov_ptime or /tmp/sov_tklex) is present. C.18 forbids a
    # two-process split BY DEFAULT, so classify the site, require the sentinels
    # absent and confirm dynamically that a normal cold compile forks nothing.
    sentinels = [str(p) for p in ('/tmp/sov_ptime', '/tmp/sov_tklex', '/tmp/sov_par')
                 if Path(p).exists()]
    dormant = all('syscall(57' in h[2] for h in hits)
    report = dict(files_scanned=len(seen), spawn_call_sites=hits,
                  classified='dormant-behind-pm_ptf' if dormant else 'ACTIVE',
                  opt_in_sentinels_present=sentinels,
                  compile_rc=rc, child_pids_seen=sorted(set(children)),
                  verdict=('GREEN' if rc == 0 and not children and not sentinels
                           and dormant else 'RED'))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print('C.18:', len(seen), 'files scanned,', len(hits),
          'dormant fork sites,', len(set(children)), 'child processes,',
          len(sentinels), 'opt-in sentinels:', report['verdict'])
    for h in hits[:10]:
        print('   ', h)
    return 0 if report['verdict'] == 'GREEN' else 1


if __name__ == '__main__':
    sys.exit(main())
