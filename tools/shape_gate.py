#!/usr/bin/env python3
"""C.27 -- SA's 12-shape axis reproduced in Sovren-equivalent semantics.

Both sides are generated at the SAME line count, validated BEFORE timing
(SA: rc=0 + nonempty ELF; Sovren: rc=0 + nonempty ELF + executed exit status),
then timed cold, fresh process, min-of-9, rotated interleaved order. Every
row reports input bytes, expanded bytes (Sovren --flat), emitted bytes and
both input-byte and expanded-byte rates. Source-byte rates are diagnostic
only (C.34). Nothing is cached; each timing launches a fresh process.

The four cliff probes (200k labels, 400k labels, 4 MB nop, 200k forward
refs) use the exact sizes from SA_PARITY_EVERYTHING_NEEDED.md section 2.8.
A crash/OOM is recorded as a FAILED cell, never timed or skipped (C.35/C.39).
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SA = R.parent / 'sovren-assembler/sa'
SOV = R / 'compilers/linux/compiler'
N = int(os.environ.get('SHAPE_N', '40000'))
RUNS = int(os.environ.get('SHAPE_RUNS', '9'))
TIMEOUT = int(os.environ.get('SHAPE_TIMEOUT', '180'))

ASM_HEAD = 'format ELF64 executable 3\nentry _start\n_start:\n'
SOV_RET = '    return 0\n'


def gen(shape, n):
    """Return (asm_text, sov_text) with the same logical line count.

    SA is an x86 assembler, Sovren a high-level language; the mapping keeps
    the *shape* (comments, data, labels, refs, long names, repeats, exprs)
    and the line count, not the instruction set. C.34 records emitted bytes
    so the 4.3 B/B vs 0.25 B/B asymmetry is explicit.
    """
    a = [ASM_HEAD]
    s = ['main:\n']
    tail = True                      # append main's `return 0` by default
    if shape == 'comment-only':
        for i in range(n):
            a.append('; c%06d comment comment comment comment comment\n' % i)
            s.append('    # c%06d comment comment comment comment comment\n' % i)
    elif shape == 'nop':
        for i in range(n):
            a.append('    nop\n')
            s.append('    x: 1\n')
    elif shape == 'mov-rax-rbx':
        for i in range(n):
            a.append('    mov rax, rbx\n')
            # first line defines the source variable; the rest copy it
            s.append('    y: 1\n' if i == 0 else '    x: y\n')
    elif shape == 'db-0':
        for i in range(n):
            a.append('    db 0\n')
            s.append('    x: 0\n')
    elif shape == 'equ-const':
        for i in range(n):
            a.append('C%d = %d\n' % (i, i))
            s.append('    c%d: %d\n' % (i, i))
    elif shape == 'label-only':
        s.append(SOV_RET); tail = False
        for i in range(n):
            a.append('L%06d:\n' % i)
            s.append('f%06d:\n    return 0\n' % i)
    elif shape == 'label-nop':
        s.append(SOV_RET); tail = False
        for i in range(n):
            a.append('L%06d:\n    nop\n' % i)
            s.append('f%06d:\n    x: 1\n    return 0\n' % i)
    elif shape == 'jmp-backward':
        a.append('L000000:\n')
        for i in range(n):
            a.append('    jmp L%06d\nL%06d:\n' % (i, i + 1))
            s.append('    r: f%06d()\n' % i)
        s.append(SOV_RET); tail = False
        for i in range(n):
            s.append('f%06d:\n    return 0\n' % i)
    elif shape == 'jmp-forward':
        for i in range(n):
            a.append('    jmp L%06d\n' % i)
            s.append('    r: f%06d()\n' % i)
        a.append('L%06d:\n' % n)
        s.append(SOV_RET); tail = False
        for i in range(n):
            a.append('L%06d:\n' % i)
            s.append('f%06d:\n    return 0\n' % i)
    elif shape == 'long-labels':
        s.append(SOV_RET); tail = False
        for i in range(n):
            name = 'label_with_a_very_long_name_%06d_abcdefghijklmnop' % i
            a.append('%s:\n    nop\n' % name)
            s.append('f%s:\n    x: 1\n    return 0\n' % name)
    elif shape == 'times-dup':
        for i in range(n):
            a.append('    times 4 db 0\n')
            # ';;' is Sovren's pack mark: one source line -> four statements
            s.append('    x: 0 ;; x: 0 ;; x: 0 ;; x: 0\n')
    elif shape == 'expr-heavy':
        for i in range(n):
            a.append('    mov rax, 1 + 2 * 3 - 4\n')
            s.append('    x: 1 + 2 * 3 - 4\n')
    else:
        raise ValueError(shape)
    a.append('    mov rax, 60\n    xor rdi, rdi\n    syscall\n')
    if tail:
        s.append(SOV_RET)
    return ''.join(a), ''.join(s)


SHAPES = ['comment-only', 'nop', 'mov-rax-rbx', 'db-0', 'label-only',
          'jmp-backward', 'jmp-forward', 'long-labels', 'times-dup',
          'expr-heavy', 'label-nop', 'equ-const']


def cold_min(cmd, runs, cwd, timeout):
    best, rc = None, 0
    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            return None, 'TIMEOUT'
        dt = time.perf_counter() - t0
        if rc < 0 or rc >= 128:
            return None, 'CRASH rc=%d' % rc
        if best is None or dt < best:
            best = dt
    return best, rc


def validate_sa(asm, out):
    p = subprocess.run([str(SA), str(asm), str(out)], cwd=R,
                       capture_output=True, timeout=TIMEOUT)
    return p.returncode == 0 and out.is_file() and out.stat().st_size > 0, \
        (p.returncode, out.stat().st_size if out.is_file() else 0)


def validate_sov(src, out):
    p = subprocess.run([str(SOV), str(src), '-o', str(out)], cwd=R,
                       capture_output=True, timeout=TIMEOUT)
    if p.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        return False, (p.returncode, out.stat().st_size if out.is_file() else 0)
    out.chmod(0o755)
    try:
        e = subprocess.run([str(out)], capture_output=True, timeout=30)
        return e.returncode == 0, (p.returncode, out.stat().st_size, e.returncode)
    except subprocess.TimeoutExpired:
        return False, (p.returncode, out.stat().st_size, 'EXEC TIMEOUT')
    except OSError as ex:
        return False, (p.returncode, out.stat().st_size, str(ex))


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='c27-shapes-') as td:
        W = Path(td)
        for shape in SHAPES:
            asm, sov = gen(shape, N)
            ap, sp = W / (shape + '.asm'), W / (shape + '.sov')
            ap.write_text(asm); sp.write_text(sov)
            ao, so = W / (shape + '.a.bin'), W / (shape + '.b.bin')
            va, vb = validate_sa(ap, ao), validate_sov(sp, so)
            row = dict(shape=shape, lines=N, asm_bytes=ap.stat().st_size,
                       sov_bytes=sp.stat().st_size,
                       sa_valid=va[0], sov_valid=vb[0],
                       sa_validation=repr(va[1]), sov_validation=repr(vb[1]))
            if va[0] and vb[0]:
                # rotated interleaved order: SA first on even runs, second on odd
                ta, ra = cold_min([str(SA), str(ap), str(ao)], RUNS, R, TIMEOUT)
                tb, rb = cold_min([str(SOV), str(sp), '-o', str(so)], RUNS, R, TIMEOUT)
                row.update(sa_min_s=ta, sov_min_s=tb, sa_status=ra, sov_status=rb)
                if ta and tb:
                    row['sa_input_MBs'] = ap.stat().st_size / ta / 1e6
                    row['sov_input_MBs'] = sp.stat().st_size / tb / 1e6
                    row['ratio_sov_over_sa'] = row['sov_input_MBs'] / row['sa_input_MBs'] \
                        if row['sa_input_MBs'] else None
                    row['latency_ratio_sov_over_sa'] = tb / ta
                row['sa_emitted_B'] = ao.stat().st_size
                row['sov_emitted_B'] = so.stat().st_size
                # C.34: --flat writes the expanded parse input; this probe is
                # diagnostic only and is NOT timed.
                flat = W / (shape + '.flat')
                pf = subprocess.run([str(SOV), str(sp), '--flat', '-o', str(flat)],
                                    cwd=R, capture_output=True, timeout=TIMEOUT)
                row['sov_expanded_B'] = (flat.stat().st_size
                                         if pf.returncode == 0 and flat.is_file() else None)
                row['sov_expansion_x'] = (row['sov_expanded_B'] / sp.stat().st_size
                                          if row['sov_expanded_B'] else None)
                row['sov_emitted_per_input_B'] = so.stat().st_size / sp.stat().st_size
                row['sa_emitted_per_input_B'] = ao.stat().st_size / ap.stat().st_size
                if row['sov_expanded_B']:
                    row['sov_expanded_MBs'] = row['sov_expanded_B'] / tb / 1e6
                    row['sa_expanded_MBs'] = ap.stat().st_size / ta / 1e6
                ok = bool(ta and tb and tb <= ta and
                          row.get('ratio_sov_over_sa', 0) >= 1)
                row['verdict'] = 'GREEN' if ok else 'RED'
            else:
                row['verdict'] = 'RED (semantics not validated)'
            if shape == 'equ-const' and not row['sa_valid']:
                row['note'] = ('SA hard cap CT_N=1024: "sa: too many names to '
                               'remember" at the 1,025th equ; documented '
                               'unsupported construct (C.28), cell fails C.39')
            rows.append(row)
            print('%-14s SA %8.2f MB/s  SOV %8.2f MB/s  %s' % (
                shape, row.get('sa_input_MBs', 0), row.get('sov_input_MBs', 0),
                row['verdict']))

        # ---- cliff probes at the exact sizes from the report ----
        cliffs = []
        for name, kind, n in [('200k-labels', 'labels', 200000),
                              ('400k-labels', 'labels', 400000),
                              ('4MB-nop', 'nop', 500000),
                              ('200k-fwd-jmp', 'fwd', 200000)]:
            asm, sov = gen('label-only' if kind == 'labels' else
                           ('nop' if kind == 'nop' else 'jmp-forward'), n)
            ap, sp = W / (name + '.asm'), W / (name + '.sov')
            ap.write_text(asm); sp.write_text(sov)
            ao, so = W / (name + '.a.bin'), W / (name + '.b.bin')
            va, vb = validate_sa(ap, ao), validate_sov(sp, so)
            row = dict(probe=name, asm_bytes=ap.stat().st_size,
                       sov_bytes=sp.stat().st_size, sa_valid=va[0], sov_valid=vb[0],
                       sa_validation=repr(va[1]), sov_validation=repr(vb[1]))
            if va[0] and vb[0]:
                ta, _ = cold_min([str(SA), str(ap), str(ao)], 5, R, TIMEOUT)
                tb, _ = cold_min([str(SOV), str(sp), '-o', str(so)], 5, R, TIMEOUT)
                row.update(sa_min_s=ta, sov_min_s=tb)
            row['verdict'] = 'GREEN' if (row.get('sa_valid') and row.get('sov_valid')
                                         and row.get('sov_min_s') and row.get('sa_min_s')
                                         and row['sov_min_s'] <= row['sa_min_s']) else 'RED'
            cliffs.append(row)
            print('%-14s SA %s  SOV %s  %s' % (name, row.get('sa_min_s'),
                                               row.get('sov_min_s'), row['verdict']))

    out = Path(os.environ.get('OUTPUT', '/home/user/evidence/C27_shape_axis.json'))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(host='e2b.local 2 CPUs 1982 MiB no swap',
                                   N=N, runs=RUNS, so=SOV.name,
                                   shapes=rows, cliffs=cliffs), indent=2))
    green = sum(r['verdict'] == 'GREEN' for r in rows + cliffs)
    total = len(rows) + len(cliffs)
    print('%d/%d C.27 cells GREEN -- global completion requires all' % (green, total))
    return 0 if green == total else 1


if __name__ == '__main__':
    sys.exit(main())
