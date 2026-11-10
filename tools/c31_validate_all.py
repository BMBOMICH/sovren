#!/usr/bin/env python3
"""C.31 — translation validation for EVERY rewritten core, in one command.

The old state was "fixtures/harnesses exist (20/20 front fusion, 12/12 sugar,
16/16 src_base), but must be extended to every rewritten core". This runner
closes that gap:

  * inventories all 22 `compilers/linux/*native*.sov` twins by SHA-256;
  * maps EVERY twin to the global differential gates that exercise it
    (2,957-case differ, 36-cell mode/flag, 12-layout, oracle, fixed point);
  * maps the three twins that have dedicated counterexample-first minimised
    fixtures to those fixture gates as well;
  * maps the PASS 8 interpreted `pull_uses` work-queue core (NOT a native
    twin) to its own counterexample-first 1-minimal delta-debugging gate;
  * PASS 10: runs an INDEPENDENT literal C.32 harness audit plus C.34
    per-cell input/expanded/emitted byte accounting (24 paired + 16 shape +
    5 tiny-floor R=21 cells);
  * PASS 11: certifies the C.2/C.3 ONE-PASS zero-allocation descriptor lexer
    prototype (counterexample-first, 627-source differential, relocation-free
    twin) and the FOURTH C.30 blocker proof (working-sibling differential);
  * PASS 12: counterexample-first REJECTION certificate for the C.2/C.3
    pad-line full-source-copy slice (9 B minimised fixture; exact stdout,
    --flat and frozen-oracle byte-identity break; R=21 placebo A/B inside
    noise; CERTIFIED_NOT_INSTALLED);
  * PASS 13: rebuilds + certifies the lost C.11 S27/S29 fused-reader build
    tool and 23-field descriptor core (relocation-free twin, 168-case differ,
    nb_disasm 5/5, A/A shim exposed), and runs a LIVE five-item C.32 harness
    audit (no -o to SA, bash layout guard, input+expanded bytes, SA t/ 6/6,
    no nested --prof summing);
  * PASS 14: certifies the C.4/C.5 stable-ID interner prototype
    (counterexample-first 7 B minimised fixture, 500 cases / 1,000 clean-room
    differential comparisons, 15,000 ID/hash dispatch checks, R=21 core A/B
    with placebo band, 633 B relocation-free twin, nb_disasm 6/6), AND the
    C.2-C.8 integrated fused-frontend prototype (SIX broken variants with
    1-minimal fixtures, 500 whole-ELF byte differentials, 50 executed ELFs,
    one read / one pass / one write, two PT_LOAD / zero section headers,
    bounded fixups + short/near relaxation, R=21 cold-process A/B placebo);
  * RUNS every gate cold, records rc + parsed counts + evidence paths;
  * fails if any twin has no gate, any gate is missing, or any gate is RED.

It is semantics-first: a gate that cannot run is a FAIL, never a skip. No
result is cached; each gate is a fresh subprocess. The speed cells (C.20-C.25,
C.27) are deliberately NOT here — they are timing gates, not translation
validation, and they remain RED in `agent/completion_gate.py`.

Usage: python3 tools/c31_validate_all.py [--json OUT] [--quick]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
CAND = str(R / 'compilers/linux/compiler')

# Real, earlier certified binaries present in this workspace. The first one
# that exists is used as the differential control. Never a copy of CAND:
# an A/A control would make every gate vacuously green.
CONTROL_CANDIDATES = [
    '/tmp/cc_control_pre_c4',                 # md5 727c1e6dab7e947eadec4325bb11f43e
    '/tmp/cc_original_4162',                 # original 4162d3641f343449ea2ac5d17eaa7313
    '/home/user/reference/linux/compiler',
]
CONTROL = next((p for p in CONTROL_CANDIDATES if Path(p).is_file()), None)

# Fixture gates that need a control path supplied via env or flag.
FIXTURE_GATES = {'front_native.sov': 'front_fusion_gate.py',
                 'basescan_native.sov': 'basescan_fixture_gate.py',
                 'sgextra_native.sov': 'sgextra_fixture_gate.py'}
# Standalone native cores delivered in the 2026-11-09 pass (C.11, C.15/C.16).
# They are C sources, not .sov twins, so they are inventoried and gated here
# as explicit entries rather than being silently omitted.
EXTRA_CORES = {
    'tools/native_reader_desc.c': ['reader_descriptor_gate.py'],
    'tools/native_reader_fused.c': ['reader_descriptor_gate.py'],
    'tools/native_shapescan.c': ['shape_scan_gate.py'],
    'tools/native_stable_interner.c': ['c4c5_interner_gate.py',
                                       'nb_disasm_verify.py'],
    'tools/native_fused_frontend.c': ['c2c8_fused_frontend_gate.py'],
    'tools/native_fused_frontend_driver.c': ['c2c8_fused_frontend_gate.py'],
}
EXTRA_GATES = ['nb_disasm_verify.py', 'twin_include_gate.py']

# Global gates that exercise every rewritten core, regardless of which twin.
GLOBAL_GATES = ['differ_gate.py', 'mode_flag_gate.py', 'layout_check.py',
                'oracle.sh', 'fixedpoint.sh', 'no_cache_policy.py',
                'flag_surface_gate.py']


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def twins():
    return sorted((R / 'compilers/linux').glob('*native*.sov'))


def run(name, argv, env=None, timeout=900, cwd=R):
    e = dict(os.environ)
    if env:
        e.update(env)
    t0 = time.time()
    try:
        r = subprocess.run(argv, cwd=cwd, env=e, capture_output=True,
                           text=True, timeout=timeout)
        rc, out = r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        rc, out = -1, 'TIMEOUT after %ss' % timeout
    return dict(name=name, argv=' '.join(str(a) for a in argv[1:]),
                rc=rc, duration_s=round(time.time() - t0, 2),
                tail=out.splitlines()[-6:], verdict='PASS' if rc == 0 else 'FAIL')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C31_all_rewrites_c4.json'))
    ap.add_argument('--quick', action='store_true',
                    help='reduce the 2,957-case differ to 400 cases (smoke only)')
    a = ap.parse_args()
    out_path = Path(a.json)
    E.mkdir(parents=True, exist_ok=True)
    # Metadata hygiene only: the workspace snapshot can drop ELF +x bits
    # between sessions, which makes oracle.sh report 0/40 with "Permission
    # denied" even though no byte changed.  restore_exec_bits.py changes MODE
    # only (sha256 unchanged); it is not a cache or a warm path.
    subprocess.run([sys.executable, 'tools/restore_exec_bits.py'], cwd=R,
                   capture_output=True, text=True, timeout=120)

    tfiles = twins()
    inventory = [dict(file=str(t.relative_to(R)), sha256=sha(t), bytes=t.stat().st_size)
                 for t in tfiles]
    for rel in EXTRA_CORES:
        f = R / rel
        inventory.append(dict(file=rel, sha256=sha(f), bytes=f.stat().st_size,
                              kind='standalone_native_core'))
    coverage = {}
    for t in tfiles:
        n = t.name
        gates = list(GLOBAL_GATES)
        if n in FIXTURE_GATES:
            gates.append(FIXTURE_GATES[n])
        coverage[n] = dict(gates=gates, covered=bool(gates))
    for rel, gs in EXTRA_CORES.items():
        coverage[rel] = dict(gates=gs, covered=bool(gs))
    # The installed pull_uses work queue is interpreted, so it is invisible to
    # the *native*.sov glob.  C.31 requires EVERY rewritten core to be gated.
    coverage['compilers/linux/compiler.sov::pull_uses_work_queue'] = dict(
        gates=['c31_pull_uses_counterexample_gate.py'] + list(GLOBAL_GATES),
        covered=True)

    results = []
    # ---- dedicated counterexample-first minimised fixtures (C.31 core) ----
    results.append(run('front_fusion_fixtures',
        [sys.executable, 'tools/front_fusion_gate.py'],
        env={'PREV_COMPILER': CONTROL or '', 'CAND_COMPILER': CAND,
             'OUTPUT': str(E / 'C31_front_fusion_fixtures_c4.json')}, timeout=600))
    results.append(run('basescan_src_base_fixtures',
        [sys.executable, 'tools/basescan_fixture_gate.py',
         '--control', CONTROL or '/tmp/cc_control_c2', '--candidate', CAND,
         '--output', str(E / 'C31_basescan_fixtures_c4.json')], timeout=600))
    results.append(run('sgextra_fixtures',
        [sys.executable, 'tools/sgextra_fixture_gate.py'],
        env={'PREV_COMPILER': CONTROL or '', 'CAND_COMPILER': CAND,
             'OUTPUT': str(E / 'C31_sgextra_fixtures_c4.json')}, timeout=600))
    # ---- PASS 9: counterexample-first MINIMISED fixtures for the installed
    # interpreted C.2/C.3 pull_uses work-queue core (not a native twin) ----
    results.append(run('c31_pull_uses_counterexample',
        [sys.executable, 'tools/c31_pull_uses_counterexample_gate.py',
         '--json', str(E / 'C31_pull_uses_counterexample_2026-11-09.json')],
        timeout=1200))
    # ---- PASS 10: independent C.32 literal audit + C.34 per-cell bytes ----
    results.append(run('c32_c34_per_cell_accounting',
        [sys.executable, 'tools/c32_c34_per_cell_accounting.py',
         '--json', str(E / 'C32_C34_per_cell_accounting_2026-11-09.json'),
         '--md', str(E / 'C32_C34_per_cell_accounting_2026-11-09.md')],
        timeout=900))
    # ---- PASS 11: C.2/C.3 prototype + C.30 fourth proof ----
    results.append(run('c2c3_descriptor_lexer',
        [sys.executable, 'tools/c2c3_descriptor_gate.py',
         '--json', str(E / 'C2_C3_descriptor_lexer_2026-11-09.json')], timeout=900))
    results.append(run('c30_working_sibling_probe',
        [sys.executable, 'tools/c30_working_sibling_probe.py',
         '--json', str(E / 'C30_working_sibling_probe_2026-11-09.json')], timeout=600))
    # ---- PASS 12: C.2/C.3 pad-line slice counterexample + rejection ----
    results.append(run('c2c3_padline_counterexample',
        [sys.executable, 'tools/c2c3_padline_counterexample_gate.py',
         '--json', str(E / 'C2_C3_padline_counterexample_2026-11-09.json')], timeout=900))
    # ---- PASS 13: C.11 reconstruction + live C.32 harness audit ----
    results.append(run('c11_reader_reconstruction',
        [sys.executable, 'tools/c11_reader_reconstruction_gate.py',
         '--json', str(E / 'C11_reader_reconstruction_2026-11-09.json')], timeout=900))
    results.append(run('c32_live_harness_audit',
        [sys.executable, 'tools/c32_live_harness_audit.py',
         '--json', str(E / 'C32_live_harness_audit_2026-11-09.json')], timeout=900))
    # ---- PASS 14: C.4/C.5 stable-ID interner prototype ----
    results.append(run('c4c5_stable_interner',
        [sys.executable, 'tools/c4c5_interner_gate.py',
         '--json', str(E / 'C4_C5_stable_interner_2026-11-09.json')], timeout=900))
    # ---- PASS 14: C.2-C.8 integrated fused-frontend prototype ----
    results.append(run('c2c8_fused_frontend',
        [sys.executable, 'tools/c2c8_fused_frontend_gate.py',
         '--json', str(E / 'C2_C8_fused_frontend_2026-11-09.json')], timeout=900))
    # ---- standalone native cores delivered 2026-11-09 ----
    results.append(run('c11_fused_reader_descriptors',
        [sys.executable, 'tools/reader_descriptor_gate.py', '--cases', '120',
         '--json', str(E / 'C11_fused_descriptor_gate.json')], timeout=900))
    results.append(run('retained_target_variation',
        [sys.executable, 'tools/target_variation.py'], timeout=900))
    results.append(run('c32_harness_check',
        [sys.executable, 'tools/c32_harness_check.py',
         '--json', str(E / 'C32_harness_check_2026-11-09.json')], timeout=900))
    results.append(run('c35_c37_verify',
        [sys.executable, 'tools/c35_c37_verify.py',
         '--json', str(E / 'C35_C37_reverify_2026-11-09.json')], timeout=600))
    results.append(run('c29_nb_disasm_verify',
        [sys.executable, 'tools/nb_disasm_verify.py',
         '--json', str(E / 'C29_nb_disasm_verify.json')], timeout=600))
    results.append(run('c32_twin_include_gate',
        [sys.executable, 'tools/twin_include_gate.py',
         '--json', str(E / 'C32_twin_include_gate.json')], timeout=900))
    results.append(run('c15_c16_shape_scan',
        [sys.executable, 'tools/shape_scan_gate.py',
         '--json', str(E / 'C15_C16_shape_scan_gate.json')], timeout=900))
    # ---- C.30 blocker certificates (PASS 4, 2026-11-09) ----
    # These are read-only censuses, not rewrites, but C.31 requires that every
    # claim about a rewrite/be blocked state is mechanically re-derived. Both
    # tools must exit 0 AND their JSON verdicts must be checked below.
    results.append(run('c30_source_archive_search',
        [sys.executable, 'tools/c30_source_archive_search.py',
         '--json', str(E / 'C30_source_archive_search_2026-11-09.json')], timeout=600))
    results.append(run('c30_fragment_structure',
        [sys.executable, 'tools/c30_fragment_structure.py',
         '--json', str(E / 'C30_fragment_structure_2026-11-09.json')], timeout=900))
    # ---- PASS 6: exact ptrace syscall census + interleaved tiny floor (C.9/C.20/C.34) ----
    # Measurement-only certificate. It must stay RED for C.9/C.20; the gate
    # validates that the measurement was actually taken and is honest.
    results.append(run('c9_c20_floor_census',
        [sys.executable, 'tools/c9_c20_floor_census.py', '--runs', '21',
         '--json', str(E / 'C9_C20_floor_census_2026-11-09.json')], timeout=900))
    # ---- PASS 7: compiler's OWN --flat C.30 proof + literal C.32 audit recheck ----
    results.append(run('c30_official_flat_probe',
        [sys.executable, 'tools/c30_official_flat_probe.py',
         '--json', str(E / 'C30_official_flat_probe_2026-11-09.json')], timeout=900))
    results.append(run('c32_original_audit_recheck',
        [sys.executable, 'tools/c32_original_audit_recheck.py',
         '--json', str(E / 'C32_original_audit_recheck_2026-11-09.json')], timeout=900))
    # ---- global differential gates over every rewritten core ----
    results.append(run('differ_2957',
        [sys.executable, 'tools/differ_gate.py', '--control', CONTROL or '/tmp/cc_control_c5',
         '--candidate', CAND, '--cases', '400' if a.quick else '2957',
         '--output', str(E / ('C29_differ_400_c4.json' if a.quick
                              else 'C29_differ_2957_c4.json'))], timeout=1500))
    results.append(run('mode_flag_36',
        [sys.executable, 'tools/mode_flag_gate.py', '--candidate', CAND,
         '--controls', CONTROL or '/tmp/cc_control_pre_c4',
         '--output', str(E / 'C36_mode_flag_c4.json')], timeout=900))
    results.append(run('layout_12',
        [sys.executable, 'tools/layout_check.py'], timeout=900))
    results.append(run('oracle_24_16_0',
        ['sh', 'work/saparity/oracle.sh'], timeout=900))
    results.append(run('fixed_point',
        ['sh', 'work/saparity/fixedpoint.sh'], timeout=900))
    results.append(run('no_cache_policy',
        [sys.executable, 'tools/no_cache_policy.py'], timeout=300))
    results.append(run('flag_surface_14',
        [sys.executable, 'tools/flag_surface_gate.py'],
        env={'CONTROL_COMPILER': CONTROL or ''}, timeout=900))

    # Verify the C.30 blocker certificates' CONTENTS, not just their exit code.
    # An empty/forged JSON must not be able to make this gate green.
    def jload(path):
        try:
            return json.loads(Path(path).read_text())
        except Exception:
            return {}

    def cert(path, checks):
        try:
            d = json.loads(Path(path).read_text())
            return all(d.get(k) == v for k, v in checks.items())
        except Exception:
            return False
    def c2c3_padline_cert():
        # PASS 12 must be a REJECTION certificate, never an acceptance of the
        # pad-line slice. Content-check the counterexample, both byte-identity
        # breaks, frozen-oracle break, A/B noise, and installed sha unchanged.
        try:
            d = json.loads((E / 'C2_C3_padline_counterexample_2026-11-09.json').read_text())
        except Exception:
            return False
        cur = hashlib.sha256((R / 'compilers/linux/compiler').read_bytes()).hexdigest()
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and d.get('slice_verdict') == 'REJECTED_BYTE_IDENTITY_BREAK_AND_NO_CREDIBLE_WIN'
                and d.get('install_status') == 'CERTIFIED_NOT_INSTALLED'
                and d.get('counterexample', {}).get('found') is True
                and d.get('counterexample', {}).get('bytes', 999) <= 16
                and d.get('broken_detections', {}).get('fixture_detected') is True
                and d.get('byte_identity_break', {}).get('exact_stdout_or_output_mismatches', 0) > 0
                and d.get('byte_identity_break', {}).get('flat_output_sha_mismatches', 0) > 0
                and d.get('oracle_nopad', {}).get('fail', 0) > 0
                and d.get('ab_verdict') == 'NO_CREDIBLE_WIN'
                and d.get('binaries', {}).get('installed') == cur)

    def c11_reader_cert():
        try:
            d = json.loads((E / 'C11_reader_reconstruction_2026-11-09.json').read_text())
        except Exception:
            return False
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and d.get('install_status') == 'CERTIFIED_NOT_INSTALLED'
                and d.get('whole_compile_deletion') == 'NOT_LANDED'
                and d.get('build', {}).get('verdict') == 'PASS'
                and d.get('build', {}).get('checks', {}).get('no_relocations') is True
                and d.get('descriptor', {}).get('cases', 0) >= 120
                and d.get('descriptor', {}).get('mismatches') == 0
                and d.get('nb_disasm', {}).get('ok') == d.get('nb_disasm', {}).get('blobs')
                and d.get('aa_shim', {}).get('byte_identical') is True)

    def c32_live_cert():
        try:
            d = json.loads((E / 'C32_live_harness_audit_2026-11-09.json').read_text())
        except Exception:
            return False
        five = d.get('five_items', {})
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and all(v is True for v in five.values()) and len(five) == 5
                and all(v is True for v in d.get('checks', {}).values())
                and d.get('checks', {}).get('sa_t_gate_6_6') is True
                and d.get('sa_t_gate', {}).get('rc') == 0
                and d.get('sc_live', {}).get('rc') == 0
                and 'layout OK' in d.get('sc_live', {}).get('layout_line', ''))

    def c2c8_fused_cert():
        # Content-verify PASS 14 integrated prototype: SIX
        # counterexample-first fixtures, 500 whole-ELF byte
        # differentials, 50 executed ELFs, one-read/one-pass/
        # one-write, two PT_LOAD / zero section headers, and an
        # R=21 cold-process placebo-controlled A/B. The installed
        # compiler SHA must be unchanged.
        try:
            d = json.loads((E / 'C2_C8_fused_frontend_2026-11-09.json').read_text())
        except Exception:
            return False
        cur = hashlib.sha256((R / 'compilers/linux/compiler').read_bytes()).hexdigest()
        cx = d.get('counterexamples', {})
        diff = d.get('differential', {})
        ab = d.get('core_ab', {})
        ds = ab.get('driver_stats', {}).get('fixed', {})
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and d.get('install_status') == 'CERTIFIED_NOT_INSTALLED'
                and d.get('whole_compile_deletion') == 'NOT_LANDED'
                and d.get('installed_compiler_sha256') == cur
                and len(cx) == 6
                and all(v.get('found') is True and v.get('detected') is True
                        and v.get('bytes', 999) <= 64
                        and v.get('fixed_matches_reference') is True
                        and v.get('fixed_stats_ok') is True
                        and v.get('executed_ok') is True
                        for v in cx.values())
                and diff.get('cases', 0) >= 500
                and diff.get('mismatches') == 0
                and diff.get('executed_cases', 0) >= 50
                and diff.get('executed_mismatches') == 0
                and diff.get('near_branch_cases', 0) > 0
                and diff.get('short_branch_cases', 0) > 0
                and all(v is True for v in d.get('checks', {}).values())
                and ab.get('verdict') == 'CREDIBLE_WIN'
                and ab.get('R') == 21
                and ab.get('cold_process') is True
                and ab.get('warmups') == 0
                and ab.get('timeouts_used') == 0
                and ds.get('read_calls') == 1
                and ds.get('source_scans') == 1
                and ds.get('lexical_passes') == 1
                and ds.get('allocations') == 0
                and ds.get('write_calls') == 1
                and ds.get('lseek_calls') == 0)

    def c4c5_interner_cert():
        # Content-verify PASS 14: counterexample FIRST, >=500 differential
        # cases / >=1,000 comparisons with zero mismatches, exact ID/hash
        # dispatch, R=21 placebo-controlled CREDIBLE_WIN, relocation-free
        # twin, and CERTIFIED_NOT_INSTALLED. An empty/forged JSON cannot pass.
        try:
            d = json.loads((E / 'C4_C5_stable_interner_2026-11-09.json').read_text())
        except Exception:
            return False
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and d.get('counterexample', {}).get('found') is True
                and d.get('counterexample', {}).get('bytes', 999) <= 32
                and d.get('broken_detected_on_counterexample') is True
                and d.get('differential', {}).get('cases', 0) >= 500
                and d.get('differential', {}).get('comparisons', 0) >= 1000
                and d.get('differential', {}).get('mismatches') == 0
                and d.get('differential', {}).get('dispatch_checks', 0) >= 15000
                and d.get('differential', {}).get('dispatch_mismatches') == 0
                and d.get('core_ab', {}).get('runs') == 21
                and d.get('core_ab', {}).get('verdict') == 'CREDIBLE_WIN'
                and d.get('core_ab', {}).get('outside_band') is True
                and d.get('twin', {}).get('verdict') == 'PASS'
                and d.get('twin', {}).get('no_relocations') is True
                and d.get('twin', {}).get('no_undefined') is True
                and d.get('nb_disasm', {}).get('rc') == 0
                and d.get('nb_disasm', {}).get('ok') == d.get('nb_disasm', {}).get('blobs')
                and d.get('nb_disasm', {}).get('sha_match') is True
                and d.get('nb_disasm', {}).get('roundtrip') is True
                and d.get('nb_disasm', {}).get('bad') == []
                and d.get('install_status') == 'CERTIFIED_NOT_INSTALLED'
                and d.get('whole_compile_deletion') == 'NOT_LANDED')

    def c2c3_descriptor_cert():
        # C.2/C.3 prototype: counterexample FIRST, zero differential
        # mismatches over >=500 sources, relocation-free twin, core A/B
        # measured.  Certificate is content-checked, not rc-checked.
        try:
            d = json.loads((E / 'C2_C3_descriptor_lexer_2026-11-09.json').read_text())
        except Exception:
            return False
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and d.get('counterexample', {}).get('found') is True
                and d.get('differential', {}).get('cases', 0) >= 500
                and d.get('differential', {}).get('mismatches') == 0
                and d.get('twin_blob', {}).get('verdict') == 'PASS'
                and d.get('install_status') == 'CERTIFIED_NOT_INSTALLED'
                and d.get('core_ab', {}).get('median_speedup') is not None)

    def c30_sibling_cert():
        try:
            d = json.loads((E / 'C30_working_sibling_probe_2026-11-09.json').read_text())
        except Exception:
            return False
        return (d.get('verdict') == 'NO_FAITHFUL_SIBLING_RESTORATION_PATH'
                and d.get('broken_driver_count') == 29
                and d.get('lead20_hash_overlap') == []
                and d.get('working_drivers_summary', {}).get('total_pinned_includes') == 0
                and d.get('all_pinned_targets_resolved') is True)

    def c32c34_per_cell_cert():
        # Content-verify PASS 10: 24 paired + 16 shape + 5 tiny-floor rows,
        # every literal C.32 item GREEN, and emitted/expanded/input bytes
        # present for every paired cell (C.34, not just a passing exit code).
        try:
            d = json.loads((E / 'C32_C34_per_cell_accounting_2026-11-09.json').read_text())
        except Exception:
            return False
        need = ('input_bytes_sovren', 'expanded_bytes', 'emitted_bytes_sovren')
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and len(d.get('paired_cells', [])) == 24
                and len(d.get('shape_cells', [])) == 16
                and len(d.get('tiny_floor', [])) == 5
                and all(r.get('verdict') == 'GREEN'
                        for r in d.get('literal_audit', []))
                and all(all(r.get(k) is not None for k in need)
                        for r in d.get('paired_cells', []))
                and all(r.get('sovren_median_ms') is not None
                        for r in d.get('tiny_floor', [])))

    def pu_counterexample_cert():
        # Content-verify the PASS 9 gate: three broken variants must each be
        # caught by a fixture that is genuinely MINIMISED (smaller than its
        # seed), the installed fix must match the pre-slice control, and the
        # three older rewritten-core fixture sets must all be present/green.
        try:
            d = json.loads((E / 'C31_pull_uses_counterexample_2026-11-09.json').read_text())
        except Exception:
            return False
        vs = d.get('variants', {})
        return (bool(d) and d.get('verdict') == 'ALL_GREEN'
                and len(vs) == 3
                and all(v.get('verdict') == 'PASS'
                        and v.get('counterexample_detected') is True
                        and v.get('fix_matches_control') is True
                        and v.get('minimised_bytes', 0) < v.get('seed_bytes', 1)
                        and v.get('good', {}).get('emitted_sha256')
                        != v.get('broken', {}).get('emitted_sha256')
                        for v in vs.values())
                and d.get('core_fixtures_verdict') == 'PASS')
    cert_ok = (
        cert(E / 'C30_source_archive_search_2026-11-09.json',
             {'verdict': 'NO_COMPLETE_PER_DRIVER_SOURCES_FOUND',
              'complete_source_candidate_count': 0, 'broken_driver_count': 29}) and
        cert(E / 'C30_fragment_structure_2026-11-09.json',
             {'verdict': 'STRUCTURALLY_INCOMPLETE_FRAGMENTS', 'drivers': 29,
              'all_flattened_compiles_fail': True}) and
        (lambda d: bool(d) and d.get('verdict') == 'C9_C20_RED'
         and d.get('syscall_census', {}).get('sovren_self_compile', {}).get('mprotect', 0) >= 400
         and d.get('tiny_floor', {}).get('sovren_output_deterministic') is True
         and d.get('tiny_floor', {}).get('sa_output_deterministic') is True
         and d.get('tiny_floor', {}).get('sovren_over_sa_median', 0) > 1)(
             jload(E / 'C9_C20_floor_census_2026-11-09.json')) and
        cert(E / 'C30_official_flat_probe_2026-11-09.json',
             {'verdict': 'OFFICIAL_EXPANSION_CONFIRMS_STRUCTURALLY_INCOMPLETE',
              'drivers': 29, 'drivers_whose_official_flat_builds': 0,
              'all_official_flats_fail': True}) and
        cert(E / 'C32_original_audit_recheck_2026-11-09.json',
             {'verdict': 'C32_ORIGINAL_AUDIT_ALL_FIVE_GREEN',
              'items': 5, 'green': 5, 'all_green': True}) and
        pu_counterexample_cert() and c32c34_per_cell_cert()
        and c2c3_descriptor_cert() and c30_sibling_cert()
        and c2c3_padline_cert() and c11_reader_cert() and c32_live_cert()
        and c4c5_interner_cert() and c2c8_fused_cert())

    all_green = (CONTROL is not None
                 and all(t['covered'] for t in coverage.values())
                 and all(r['verdict'] == 'PASS' for r in results)
                 and cert_ok)
    report = dict(schema=1, control=CONTROL, candidate=CAND,
                  quick=a.quick, native_twins=len(tfiles),
                  standalone_native_cores=len(EXTRA_CORES),
                  inventory=inventory, coverage=coverage,
                  gates=results, c30_blocker_certificates_verified=cert_ok,
                  interpreted_core_counterexamples_verified=pu_counterexample_cert(),
                  c32_c34_per_cell_accounting_verified=c32c34_per_cell_cert(),
                  c2c3_descriptor_prototype_verified=c2c3_descriptor_cert(),
                  c30_fourth_proof_verified=c30_sibling_cert(),
                  c2c3_padline_rejection_verified=c2c3_padline_cert(),
                  c11_reader_reconstruction_verified=c11_reader_cert(),
                  c32_live_harness_audit_verified=c32_live_cert(),
                  c4c5_interner_prototype_verified=c4c5_interner_cert(),
                  c2c8_fused_frontend_verified=c2c8_fused_cert(),
                  all_green=all_green,
                  note='Semantic validation only. Speed cells C.20-C.25 and '
                       'shape axis C.27 are timing gates and remain RED. '
                       'C.30 blocker certificates are checked for content; '
                       'they prove the 29 drivers cannot be repaired from '
                       'material in this workspace, NOT that the fleet builds.')
    out_path.write_text(json.dumps(report, indent=2) + '\n')
    print('C.31 validate-all: %d native cores/twins, %d gates, control=%s'
          % (len(inventory), len(results), CONTROL or 'NONE'))
    for t in inventory:
        key = t['file'] if t['file'] in coverage else Path(t['file']).name
        c = coverage.get(key, {'gates': [], 'covered': False})
        print('  %-34s %d gates %s' % (Path(t['file']).name, len(c['gates']),
              'COVERED' if c['covered'] else 'UNCOVERED'))
    for r in results:
        print('  %-30s %-4s rc=%s (%.1fs)' % (r['name'], r['verdict'],
              r['rc'], r['duration_s']))
        for line in r['tail'][-2:]:
            print('      ' + line[:150])
    print('  -> %s' % out_path)
    print('ALL GREEN' if all_green else 'NOT GREEN')
    return 0 if all_green else 1


if __name__ == '__main__':
    sys.exit(main())
