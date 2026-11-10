#!/usr/bin/env python3
"""Compare current retained drivers against the recorded two-input behavior.
This is a regression check, not full-language or speed certification.
The WebAssembly exception retains its existing partial behavior. Missing
baselines fail; explicit --freeze records observations rather than certification.
"""
import glob, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
GATE = R / 'compilers/linux/compiler'
SNAP = R / 'tests/gates/target_variation.json'
# Same line count AND same byte length, different literal. A real translator
# must embed the literal and therefore emit different bytes; a constant
# emitter / evaluator cannot. Using different-shaped inputs would misclassify
# emitters that copy line counts into headers as "translating".
INPUTS = [
    'main:\n    print 111111\n    return 0\n',
    'main:\n    print 222222\n    return 0\n',
]


def main():
    freeze = '--freeze' in sys.argv
    reg=json.loads((R/'compilers/registry.json').read_text(encoding='utf-8'))
    drvs=sorted(str(R/e['source']) for e in reg['entries'])
    rows = []
    with tempfile.TemporaryDirectory(prefix='c19-') as td:
        W = Path(td)
        for i, text in enumerate(INPUTS):
            (W / f'in{i}.sov').write_text(text)
        for d in drvs:
            rel = os.path.relpath(d, R)
            marker = Path(d).parent / '.build-failed'
            out = W / 'out.bin'
            binary = W / 'driver.bin'
            p = subprocess.run([str(GATE), d, '-o', str(binary)], cwd=R,
                               capture_output=True, timeout=300)
            built = binary.is_file() and binary.stat().st_size > 1000
            row = dict(driver=rel, builds=built,
                       marker=(marker.read_text().strip()[:80] if marker.is_file() else None))
            if not built:
                row['class'] = 'lineage-pending'
                rows.append(row)
                continue
            binary.chmod(0o755)
            res = []
            for i in range(len(INPUTS)):
                if out.exists():
                    out.unlink()
                try:
                    q = subprocess.run([str(binary), str(W/f'in{i}.sov'), '-o', str(out)],
                                       cwd=R, capture_output=True, timeout=15)
                    data = out.read_bytes() if out.is_file() else b''
                    res.append(dict(rc=q.returncode, size=len(data),
                                    sha=hashlib.sha256(data).hexdigest()[:16] if data else None))
                except (subprocess.TimeoutExpired, OSError) as e:
                    res.append(dict(rc='TIMEOUT/'+type(e).__name__, size=0, sha=None))
            row['runs'] = res
            if any(r['rc'] != 0 or r['size'] == 0 for r in res):
                row['class'] = 'error'
            elif res[0]['sha'] == res[1]['sha'] and res[0]['size'] == res[1]['size']:
                row['class'] = 'constant'
            else:
                row['class'] = 'translating'
            rows.append(row)
            binary.unlink()

    classes = {}
    for r in rows:
        classes[r['class']] = classes.get(r['class'], 0) + 1
    report = dict(total=len(rows), classes=classes,
                  constant=[r['driver'] for r in rows if r['class'] == 'constant'],
                  error=[r['driver'] for r in rows if r['class'] == 'error'],
                  lineage_pending=[r['driver'] for r in rows if r['class'] == 'lineage-pending'],
                  rows=rows)
    print('drivers', len(rows), 'classes', classes)
    print('constant emitters', len(report['constant']))
    print('error backends', len(report['error']))
    print('lineage-pending (never skipped)', len(report['lineage_pending']))

    if not SNAP.is_file() and not freeze:
        print('Missing target variation baseline; not certified')
        return 1
    if freeze:
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        SNAP.write_text(json.dumps(report, indent=1) + '\n')
        print('FROZEN ->', SNAP.relative_to(R))
        return 0
    old = json.loads(SNAP.read_text())
    diffs = []
    by_old = {r['driver']: r for r in old['rows']}
    for r in rows:
        o = by_old.get(r['driver'])
        if o is None:
            diffs.append((r['driver'], 'ABSENT', 'new'))
        elif o['class'] != r['class'] or o.get('runs') != r.get('runs'):
            diffs.append((r['driver'], o['class'], r['class'] + ' / behaviour'))
    print('classification+byte-behaviour changes vs frozen snapshot:', len(diffs))
    for d in diffs[:20]:
        print('  ', d)
    return 0 if not diffs else 1


if __name__ == '__main__':
    sys.exit(main())
