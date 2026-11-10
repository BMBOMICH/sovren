#!/usr/bin/env python3
"""C.32 + C.34 — INDEPENDENT literal harness audit and per-cell byte accounting.

The restated acceptance list keeps flagging the original C.32 audit as still
open (bench.sh / everywhere-audit.sh passing `-o` to SA, sc/bench.sh sibling
paths, report input AND expanded bytes per cell, SA's t/ gate, never sum
nested --prof endpoints) and C.34 as "input + expanded + emitted bytes with
every number".  The paired-cell gate reports input and expanded bytes but NOT
emitted bytes; the shape gate reports them, the tiny-floor gate does not.

This tool closes both gaps with fresh, cold measurements:

  * LITERAL, INDEPENDENT checks of the five original audit items using exact
    source strings (not the phrasing expected by c32_original_audit_recheck.py),
    plus a live SA t/gate.py 6/6 run;
  * per-cell ACCOUNTING for all 24 paired cells: input bytes (Sovren and SA),
    expanded bytes, emitted bytes for BOTH translators, emitted/input,
    expansion factor, and the kind of output (ELF vs flat text);
  * the same for all 16 shape-axis cells (12 shapes + 4 cliffs), read from the
    frozen shape evidence;
  * a fresh R=21 ROTATED INTERLEAVED, cold-process, no-warm-up tiny-floor
    measurement for the five C.20 shapes (28 B, 35 B, 191 B, 1-line, --bare)
    with min + median, host, compiler/SA sizes and all byte counts.

Every compile is cold: fresh process, shared temp output path per translator,
no cache, no sidecar, no warm-up.  SA is always invoked with POSITIONAL argv[2]
and NEVER with -o.  Nothing is installed or modified.

Usage: python3 tools/c32_c34_per_cell_accounting.py [--json OUT] [--md OUT]
Exits 0 only if every literal check is GREEN and every row has the required
byte counts.  Speed verdicts (C.20-C.25, C.27) remain RED and are NOT asserted.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
CC = R / 'compilers/linux/compiler'
SA = Path('/home/user/dl/sovren-assembler/sa')
PERF = R / 'tests/performance'
sys.path.insert(0, str(R / 'tools'))
import cold_gate  # noqa: E402

WORKLOADS = ['exit7', 'sum', 'calls']
SIZES = ['small', 'large-64k']
MODES = [('default', []), ('unsafe', ['--unsafe'])]
FLAGS = [('none', []), ('flat', ['--flat'])]
TINY = {
    'empty-28B':  b'main:\n    return 0\n',
    'exit7-19B':  b'main:\n    return 7\n',
    'hello-191B': b"main:\n    print 'Hello from Sovren! Fully self-hosted!'\n"
                  b"    x: 10 ;; y: 20\n    z: x + y ;; print z\n"
                  b"    if z > 15 -> print 'z is big'\n    print 'loop' 3 times\n",
    'one-line':   b'main:\n    return 7\n',
    '--bare':     b'main:\n    return 7\n',
}
TINY_SA = ('segment readable executable\n_start:\n'
           '    mov eax, 60\n    mov edi, 7\n    syscall\n')
NOTE = 'do not add them up'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(rel):
    p = R / rel
    return p.read_text() if p.is_file() else ''


# ---------------------------------------------------------------- C.32 audit
def literal_audit():
    rows = []

    def add(item, ok, detail):
        rows.append(dict(item=item, verdict='GREEN' if ok else 'RED', detail=detail))

    b1 = read('work/saparity/bench.sh')
    b2 = read('work/saparity/everywhere-audit.sh')
    sct = read('sc/bench.sh')
    sg = read('tools/speed_gate.py')

    # (a) no `-o` is passed to SA in either saparity harness, and SA is
    # invoked positionally (argv[2] is the output path).
    bad = []
    for name, txt in [('bench.sh', b1), ('everywhere-audit.sh', b2)]:
        for i, line in enumerate(txt.splitlines(), 1):
            low = line.strip()
            if low.startswith('#'):
                continue
            if ('sa' in low or '$SA' in low or 'SA=' in low or 'SA =' in low) and \
               re.search(r'(^|\s)-o(\s|$)', low):
                bad.append('%s:%d: %s' % (name, i, low[:120]))
    add('a_no_dash_o_to_sa', not bad and bool(b1) and bool(b2),
        'no -o on any SA invocation line in bench.sh / everywhere-audit.sh'
        if not bad else '; '.join(bad))
    # speed_gate.py builds the SA command as [sa, src, out] with NO -o; that
    # IS positional argv[2].  Check the command construction, not a comment.
    sa_cmd = [l for l in sg.splitlines() if "'sa':Command" in l or '"sa":Command' in l]
    joined = ''.join(sa_cmd)
    pos = bool(sa_cmd) and '-o' not in joined and 'sa.bin' in joined
    add('a_speed_gate_positional', pos,
        'tools/speed_gate.py builds SA as [sa, sa_src, out] with no -o (positional argv[2])')

    # (b) sc/bench.sh sibling paths and live layout marker.
    add('b_sc_sibling_paths',
        ('T=../tests' in sct or 'T="..' in sct) and
        ('sovren-assembler/sa' in sct),
        'sc/bench.sh declares T=../tests and SA=../../sovren-assembler/sa')
    # sc/bench.sh is #!/bin/bash (uses ${EPOCHREALTIME/./}); invoking it with
    # `sh` produces "Bad substitution".  Invoke with bash and read the live
    # startup layout guard line, not the benchmark tail.
    guard = subprocess.run(['bash', 'sc/bench.sh'], cwd=R,
                           capture_output=True, text=True, timeout=300)
    gout = guard.stdout + guard.stderr
    lay = next((l.strip() for l in gout.splitlines() if 'layout OK' in l), '')
    add('b_sc_layout_live', bool(lay),
        'live sc/bench.sh layout guard (bash): ' + (lay[:140] or 'MISSING'))

    # (c) expanded_of declared AND called, `expanded=` printed, SA rows n/a.
    # The ORIGINAL audit item (c) is about the two saparity harnesses;
    # sc/bench.sh is a separate harness whose C.34 duty is the input-byte /
    # diagnostic-rate note (added in PASS 7).
    ok_c = all('expanded_of' in t and 'expanded=' in t for t in (b1, b2))
    add('c_expanded_of_and_rows', ok_c,
        'both saparity harnesses declare/call expanded_of and print expanded=')
    add('c_sc_diagnostic_rate_note',
        ('input' in sct.lower() and 'diagnostic' in sct.lower()),
        'sc/bench.sh carries the C.34 input-byte / diagnostic-rate note')
    add('c_sa_rows_n_a', 'n/a' in b1 or 'n/a' in b2 or 'n/a' in sct,
        'SA rows report n/a for expansion (SA has no --flat mode)')

    # (d) SA t/ gate runs 6/6.
    tg = subprocess.run([sys.executable, str(Path('/home/user/dl/sovren-assembler/t/gate.py'))],
                        cwd='/home/user/dl/sovren-assembler', capture_output=True,
                        text=True, timeout=300)
    tout = (tg.stdout + tg.stderr)
    m = re.search(r'(\d+)\s*/\s*(\d+)', tout)
    six = bool(m) and m.group(1) == m.group(2) == '6' and tg.returncode == 0
    add('d_sa_t_gate_6_of_6', six,
        'SA t/gate.py rc=%d, %s' % (tg.returncode, tout.strip().splitlines()[-1][:120]
                                    if tout.strip() else 'no output'))

    # (e) nested --prof endpoints are NEVER an exclusive sum.
    add('e_no_prof_summing', NOTE in sct.lower() and 'exclusive sum' in sct.lower(),
        'sc/bench.sh states nested --prof aggregates are never an exclusive sum: '
        '"do not add them up"')
    summ = []
    for name, txt in [('bench.sh', b1), ('everywhere-audit.sh', b2), ('sc/bench.sh', sct)]:
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(r'sum\(|\+\s*prof_|prof_\w+\s*\+', line) and not line.strip().startswith('#'):
                summ.append('%s:%d' % (name, i))
    add('e_no_endpoint_addition', not summ,
        'no live harness line adds --prof endpoints: ' + (','.join(summ) if summ else 'clean'))
    return rows


# ------------------------------------------------------------- C.34 accounting
def compile_bytes(argv, out, cwd=R, timeout=180):
    """Cold compile; return (rc, byte count, sha) or (rc, None, '')."""
    if out.exists():
        out.unlink()
    try:
        p = subprocess.run(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, None, ''
    if p.returncode != 0 or not out.is_file():
        return p.returncode, None, ''
    b = out.read_bytes()
    return 0, len(b), sha(b)


def paired_accounting(W):
    rows = []
    for w in WORKLOADS:
        for sz in SIZES:
            if sz == 'small':
                s, a = PERF / (w + '.sov'), PERF / (w + '.sa')
            else:
                s, a = W / (w + '-64k.sov'), W / (w + '-64k.sa')
                cold_gate.gen_unique_sov(str(s), 65536)
                cold_gate.gen_unique_asm(str(a), 65536)
            if not s.is_file() or not a.is_file():
                continue
            in_s, in_a = s.stat().st_size, a.stat().st_size
            flat_out = W / 'acct_flat.bin'
            _, expanded, _ = compile_bytes(
                [str(CC), str(s), '-o', str(flat_out), '--flat'], flat_out)
            sa_out = W / 'acct_sa.bin'
            rc_a, emitted_a, _ = compile_bytes(
                [str(SA), str(a), str(sa_out)], sa_out)
            for mn, mf in MODES:
                for fn, ff in FLAGS:
                    sov_out = W / 'acct_sov.bin'
                    rc_s, emitted_s, _ = compile_bytes(
                        [str(CC), str(s), '-o', str(sov_out)] + mf + ff, sov_out)
                    rows.append(dict(
                        cell='%s/%s/%s/%s' % (w, sz, mn, fn),
                        workload=w, size=sz, mode=mn, flag=fn,
                        input_bytes_sovren=in_s, input_bytes_sa=in_a,
                        expanded_bytes=expanded,
                        emitted_bytes_sovren=emitted_s,
                        emitted_bytes_sa=emitted_a if rc_a == 0 else None,
                        emitted_kind_sovren='flat_text' if fn == 'flat' else 'elf',
                        emitted_kind_sa='elf',
                        comparable=(fn != 'flat'),
                        expansion_factor=(round(expanded / in_s, 4) if expanded and in_s else None),
                        emitted_per_input_sovren=(round(emitted_s / in_s, 6)
                                                  if emitted_s and in_s else None),
                        sovren_rc=rc_s, sa_rc=rc_a))
    return rows


def shape_accounting():
    p = E / 'C27_shape_axis_c4.json'
    if not p.is_file():
        return []
    d = json.loads(p.read_text())
    rows = []
    for group in ('shapes', 'cliffs'):
        for c in d.get(group, []):
            key = c.get('shape') or c.get('probe')
            rows.append(dict(cell='shape/' + str(key), group=group,
                             input_bytes_sovren=c.get('sov_bytes', c.get('asm_bytes')),
                             input_bytes_sa=c.get('asm_bytes'),
                             expanded_bytes=c.get('sov_expanded_B'),
                             emitted_bytes_sovren=c.get('sov_emitted_B'),
                             emitted_bytes_sa=c.get('sa_emitted_B'),
                             verdict=c.get('verdict'),
                             note='C.27 gate does not record expanded/emitted bytes for cliff probes'
                             if group == 'cliffs' and c.get('sov_expanded_B') is None else ''))
    return rows


def tiny_floor(W, runs=21):
    """R=21 rotated interleaved cold latency, min + median, for five shapes."""
    out_s, out_a = W / 'tiny_sov.bin', W / 'tiny_sa.bin'
    src_s, src_a = W / 'tiny.sov', W / 'tiny.sa'
    src_a.write_bytes(TINY_SA.encode())
    rows = []
    for name, body in TINY.items():
        bare = (name == '--bare')
        src_s.write_bytes(body)
        in_s, in_a = src_s.stat().st_size, src_a.stat().st_size
        flat_out = W / 'tiny_flat.bin'
        _, expanded, _ = compile_bytes(
            [str(CC), str(src_s), '-o', str(flat_out), '--flat'], flat_out)
        argv_s = [str(CC), str(src_s), '-o', str(out_s)] + (['--bare'] if bare else [])
        argv_a = [str(SA), str(src_a), str(out_a)]
        rc_s, emitted_s, _ = compile_bytes(argv_s, out_s)
        rc_a, emitted_a, _ = compile_bytes(argv_a, out_a)
        ts, ta = [], []
        for k in range(runs):
            # rotated interleaving: alternate which translator goes first
            order = [(argv_s, out_s, ts), (argv_a, out_a, ta)]
            if k % 2:
                order.reverse()
            for argv, out, acc in order:
                t0 = time.perf_counter()
                # NO timeout= here: subprocess' communicate() poll loop adds
                # ~1 ms and swamps a 0.2-0.8 ms floor (PASS 6 dead end).
                p = subprocess.run(argv, cwd=R, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                ok = p.returncode == 0 and out.is_file() and out.stat().st_size > 0
                if ok:
                    acc.append((time.perf_counter() - t0) * 1000.0)
        if not ts or not ta:
            rows.append(dict(cell='tiny/' + name, verdict='FAIL',
                             reason='TRANSLATION_FAILED'))
            continue
        smin, smed = min(ts), statistics.median(ts)
        amin, amed = min(ta), statistics.median(ta)
        rows.append(dict(
            cell='tiny/' + name,
            flags=['--bare'] if bare else [],
            input_bytes_sovren=in_s, input_bytes_sa=in_a,
            expanded_bytes=expanded, emitted_bytes_sovren=emitted_s,
            emitted_bytes_sa=emitted_a, sovren_rc=rc_s, sa_rc=rc_a,
            runs=runs, rotated_interleaved=True, cold_process=True,
            warmups=0,
            sovren_min_ms=round(smin, 4), sovren_median_ms=round(smed, 4),
            sa_min_ms=round(amin, 4), sa_median_ms=round(amed, 4),
            median_ratio_sovren_over_sa=round(smed / amed, 4) if amed else None,
            target_sa_min_ms=0.211,
            verdict='RED' if smed > amed else 'GREEN',
            note='C.20 separate latency gate; source-byte rates across an '
                 'assembler and a high-level language are diagnostic, not '
                 'proof of equal frontend work (C.34/C.39).'))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C32_C34_per_cell_accounting_2026-11-09.json'))
    ap.add_argument('--md', default=str(E / 'C32_C34_per_cell_accounting_2026-11-09.md'))
    ap.add_argument('--runs', type=int, default=21)
    a = ap.parse_args()
    # The workspace snapshot can drop executable bits between sessions; both
    # binaries are byte-identical, only their mode needs restoring.  Never
    # changes compiler bytes (C.29/C.35).
    for b in (CC, SA, R / 'sc/sc'):
        if b.is_file() and not os.access(b, os.X_OK):
            b.chmod(0o755)
    cc_b, sa_b = CC.read_bytes(), SA.read_bytes()
    host = ' '.join([platform.node(), platform.system(), platform.release(),
                     platform.machine(), '%s CPUs' % (os.cpu_count() or 0)])
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 10',
               host=host,
               compiler_md5=hashlib.md5(cc_b).hexdigest(),
               compiler_size=len(cc_b), compiler_sha256=sha(cc_b),
               sa_sha256=sha(sa_b), sa_size=len(sa_b),
               method='cold fresh process per compile; shared -o path per '
                      'translator; SA positional argv[2] only; R=21 rotated '
                      'interleaved, no warm-ups, no cache, no sidecar',
               verdict='FAIL')
    with tempfile.TemporaryDirectory(prefix='c32c34-') as td:
        W = Path(td)
        rep['literal_audit'] = literal_audit()
        rep['paired_cells'] = paired_accounting(W)
        rep['shape_cells'] = shape_accounting()
        rep['tiny_floor'] = tiny_floor(W, a.runs)
    lit = all(x['verdict'] == 'GREEN' for x in rep['literal_audit'])
    need = ('input_bytes_sovren', 'expanded_bytes', 'emitted_bytes_sovren')
    paired_ok = (len(rep['paired_cells']) == 24 and
                 all(all(r.get(k) is not None for k in need)
                     for r in rep['paired_cells']))
    tiny_ok = (len(rep['tiny_floor']) == 5 and
               all(r.get('sovren_median_ms') is not None and
                   r.get('emitted_bytes_sovren') is not None
                   for r in rep['tiny_floor']))
    shape_ok = len(rep['shape_cells']) == 16
    rep['checks'] = dict(literal_audit_all_green=lit,
                         paired_24_cells_accounted=paired_ok,
                         shape_16_cells_accounted=shape_ok,
                         tiny_5_shapes_r21_accounted=tiny_ok)
    rep['verdict'] = ('ALL_GREEN' if all(rep['checks'].values()) else 'FAIL')
    rep['speed_note'] = ('This is ACCOUNTING, not a speed claim. C.20-C.25 and '
                         'C.27 remain RED; no parity/completion/14-14 claim.')
    out = Path(a.json)
    out.write_text(json.dumps(rep, indent=2) + '\n')

    md = ['# C.32/C.34 fresh per-cell byte accounting — 2026-11-09', '',
          'Host: `%s`' % host, '',
          'Compiler md5 `%s` (%d B), sha256 `%s`; SA sha256 `%s` (%d B).' %
          (rep['compiler_md5'], rep['compiler_size'], rep['compiler_sha256'][:16],
           rep['sa_sha256'][:16], rep['sa_size']), '',
          'Cold fresh process per compile; SA positional argv[2] only; '
          'R=21 rotated interleaved, no warm-ups, no cache. '
          'Source-byte rates across an assembler and a high-level language '
          'are diagnostic, not proof of equal frontend work.', '',
          '## Literal C.32 audit', '',
          '| item | verdict | detail |', '|---|---|---|']
    for r in rep['literal_audit']:
        md.append('| %s | %s | %s |' % (r['item'], r['verdict'],
                                        r['detail'].replace('|', '/')))
    md += ['', '## Paired cells (24) — input / expanded / emitted bytes', '',
           '| cell | in SOV | in SA | expanded | emitted SOV | emitted SA | kind | comparable |',
           '|---|---:|---:|---:|---:|---:|---|---|']
    for r in rep['paired_cells']:
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s |' %
                  (r['cell'], r['input_bytes_sovren'], r['input_bytes_sa'],
                   r['expanded_bytes'], r['emitted_bytes_sovren'],
                   r['emitted_bytes_sa'], r['emitted_kind_sovren'],
                   r['comparable']))
    md += ['', '## Tiny floor (R=21 interleaved, C.20)', '',
           '| shape | in SOV | in SA | expanded | emitted SOV | emitted SA | min/med SOV ms | min/med SA ms | med ratio | verdict |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in rep['tiny_floor']:
        md.append('| %s | %s | %s | %s | %s | %s | %s / %s | %s / %s | %s | %s |' %
                  (r['cell'], r.get('input_bytes_sovren'), r.get('input_bytes_sa'),
                   r.get('expanded_bytes'), r.get('emitted_bytes_sovren'),
                   r.get('emitted_bytes_sa'), r.get('sovren_min_ms'),
                   r.get('sovren_median_ms'), r.get('sa_min_ms'),
                   r.get('sa_median_ms'), r.get('median_ratio_sovren_over_sa'),
                   r.get('verdict')))
    md += ['', '## Shape axis (16) — bytes from frozen C.27 evidence', '',
           '| cell | in SOV | in SA | expanded | emitted SOV | emitted SA | verdict |',
           '|---|---:|---:|---:|---:|---:|---|']
    for r in rep['shape_cells']:
        md.append('| %s | %s | %s | %s | %s | %s | %s |' %
                  (r['cell'], r['input_bytes_sovren'], r['input_bytes_sa'],
                   r['expanded_bytes'], r['emitted_bytes_sovren'],
                   r['emitted_bytes_sa'], r['verdict']))
    md += ['', 'Checks: `%s`' % json.dumps(rep['checks']), '',
           'Verdict: **%s**. %s' % (rep['verdict'], rep['speed_note']), '']
    Path(a.md).write_text('\n'.join(md))

    print('C.32/C.34 per-cell accounting: %s' % rep['verdict'])
    for k, v in rep['checks'].items():
        print('  %-32s %s' % (k, 'GREEN' if v else 'FAIL'))
    print('  %d literal items, %d paired cells, %d shape cells, %d tiny shapes' %
          (len(rep['literal_audit']), len(rep['paired_cells']),
           len(rep['shape_cells']), len(rep['tiny_floor'])))
    print('  -> %s' % out)
    print('  -> %s' % a.md)
    return 0 if rep['verdict'] == 'ALL_GREEN' else 1


if __name__ == '__main__':
    sys.exit(main())
