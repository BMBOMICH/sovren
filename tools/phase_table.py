#!/usr/bin/env python3
"""Phase-table publisher: run `compiler --prof` on the three parity workloads,
parse the phase-endpoint JSON, and emit the post-audit phase table (markdown).

Endpoint semantics: mark() = endpoint-delta buckets; time lands in the bucket
of the NEXT mark. The last mark's tail is folded into 'tail'. Phases whose
bucket is one of the known big ones are labeled. Output: work/PHASE_TABLE.md
plus a JSON sidecar with the raw aggregates.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
COMP = R / 'compilers/linux/compiler'
WORKLOADS = [
    ('self', 'compilers/linux/compiler.sov'),
    ('all', 'tests/all.sov'),
    ('x86ins', 'tests/x86ins.sov'),
]
# canonical phase descriptions (from SA_PARITY.md tables)
WHAT = {
    'bw': 'per-task body statement codegen (interpreted lowering)',
    'W-walk0': 'the task walk',
    'c0-parsed': 'parse',
    'C1': 'pu_lines, the line reader',
    '4-compiled': 'final codegen',
    'p-stub': 'stub_diet',
    'pu': 'pull_uses, chunk loading',
    '2-all-spliced': 'runtime + chunk + source splice',
    '3-scanned': 'u_scan + u_prep',
    'pre-u': 'pre-pass probe',
    '5a-flat0': 'ELF flat emission, relocations',
    'p-dce': 'prune_dead',
    'ZZ': 'the main parse loop',
    'f1-spliced': 'splice_inc',
}

def prof(src):
    out = Path(tempfile.mkdtemp(prefix='phasetab-')) / 'a.out'
    r = subprocess.run([str(COMP), '--prof', str(R / src), '-o', str(out)],
                       capture_output=True, text=True, timeout=300)
    txt = r.stdout + r.stderr
    i = txt.find('{"schema"')
    if i < 0:
        raise RuntimeError('no prof JSON for ' + src)
    # the JSON is pretty-printed with embedded newlines; take to end, strip
    blob = txt[i:]
    # find matching end by parsing leniently: json ends at last '}'
    j = blob.rfind('}')
    return json.loads(blob[:j+1]), out.stat().st_size

def buckets(marks):
    """marks are (endpoint, ns, calls) in ENDPOINT ORDER? No — the JSON lists
    aggregates keyed by endpoint. The compiler prints them in first-mark order.
    Bucket value of a mark = its ns value is the AGGREGATE of the span ENDING
    at that mark (endpoint-delta). So each mark's ns IS its phase time."""
    return {m['endpoint']: (m['ns'], m['calls']) for m in marks}

def main():
    tables = {}
    totals = {}
    for name, src in WORKLOADS:
        data, art = prof(src)
        b = buckets(data['marks'])
        tot = sum(ns for ns, _ in b.values())
        tables[name] = b
        totals[name] = tot
    # union of endpoints, keep canonical ordering by total time
    all_eps = {}
    for b in tables.values():
        for ep, (ns, calls) in b.items():
            all_eps.setdefault(ep, [0, 0])
            all_eps[ep][0] += ns
            all_eps[ep][1] += calls
    order = [ep for ep, _ in sorted(all_eps.items(), key=lambda kv: -kv[1][0])]
    lines = []
    lines.append('# Post-audit phase table (%s, compiler %s)' %
                 (__import__('datetime').date.today().isoformat(),
                  subprocess.run(['sha256sum', str(COMP)], capture_output=True, text=True).stdout.split()[0][:16]))
    lines.append('')
    lines.append('Fresh `--prof` runs, one call each, instrumented endpoint-aggregates '
                 '(mark = endpoint-delta; ns lands in the bucket of the mark).')
    lines.append('')
    hdr = '| phase | self (%.1f ms) | all.sov (%.1f ms) | x86ins (%.1f ms) | what it is |' % (
        totals['self'] / 1e6, totals['all'] / 1e6, totals['x86ins'] / 1e6)
    lines.append('|---|---|---|---|---|')
    lines.append(hdr)
    for ep in order:
        row = ['`%s`' % ep]
        for name in ('self', 'all', 'x86ins'):
            b = tables[name]
            if ep in b:
                ns, calls = b[ep]
                row.append('%.1f ms / %.1f%%' % (ns / 1e6, 100.0 * ns / totals[name]))
            else:
                row.append('—')
        row.append(WHAT.get(ep, ''))
        lines.append('| ' + ' | '.join(row) + ' |')
    txt = '\n'.join(lines) + '\n'
    out_md = R / 'work' / 'PHASE_TABLE.md'
    out_md.write_text(txt)
    (R / 'work' / 'phase_table.json').write_text(json.dumps(
        {'totals_ns': totals, 'marks': {k: {ep: {'ns': ns, 'calls': c} for ep, (ns, c) in v.items()} for k, v in tables.items()}}, indent=2))
    print(txt)
    print('written:', out_md)

if __name__ == '__main__':
    main()
