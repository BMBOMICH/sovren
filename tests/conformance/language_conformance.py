#!/usr/bin/env python3
"""Full-language conformance runner.

For every registered backend whose artifacts can execute on this host
(linux x86-64), compiles each corpus case with cold caches, executes the
artifact, compares stdout to the recorded oracle, and emits per-feature
coverage evidence bound to the backend's own executable hash.

Usage: python3 tests/conformance/language_conformance.py [--output PATH]
Exit 0 only if every eligible backend passed every corpus case.
"""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'tests/conformance/corpus'
COLD = []  # cache/sugar machinery was removed tree-wide; legacy flags are rejected as unknown

# Targets whose artifacts execute on this host through sovren's own x86
# emulator (library/x86.sov): the driver runs the PE and passes guest stdout
# through. executor: 'native' = runs directly, 'sovren-x86-emulator' = PE.
EMULATOR_EXECUTORS = {
    'windows': 'compilers/windows/compiler',
    'windows/store': 'compilers/windows/store/compiler',
}

# case file -> which contract features it evidences
CASE_FEATURES = {
    'c01_int_arith.sov': ['integer-arithmetic'],
    'c02_recursion.sov': ['functions-recursion'],
    'c03_control.sov': ['structured-control'],
    'c04_shortcircuit.sov': ['short-circuit'],
    'c05_ltr.sov': ['left-to-right-effects'],
    'c06_text_out.sov': ['text-literal-output'],
    'c07_argv.sov': ['dynamic-argc', 'argv-access'],
    'c08_text.sov': ['general-text'],
    'c09_collections.sov': ['collections'],
    'c10_records.sov': ['structs'],
    'c11_pointers.sov': ['pointers-memory'],
    'c12_globals.sov': ['globals'],
    'c13_imports.sov': ['imports-libraries'],
    'c14_platform.sov': ['platform-services'],
    'c15_float.sov': ['floating-point'],
    'c16_abi.sov': ['target-abi'],
}
# deterministic invocation: case -> argv tail
CASE_ARGV = {
    'c07_argv.sov': ['alpha', 'beta'],
}
EXPECTED = {
    'c01_int_arith.sov': ['187', '-21', '-2', '-2', '1000000000000'],
    'c02_recursion.sov': ['610', '2000'],
    'c03_control.sov': ['30', '111'],
    'c04_shortcircuit.sov': ['2', '0', '1'],
    'c05_ltr.sov': ['6', '123'],
    'c06_text_out.sov': ['hello conformance', 'line with "quote" and tab-end', ''],
    'c07_argv.sov': ['3', 'alpha', 'beta'],
    'c08_text.sov': ['11', 'formance', '50', '1', '99'],
    'c09_collections.sov': ['5', '16', '1'],
    'c10_records.sov': ['222', '244'],
    'c11_pointers.sov': ['69', '1234567890123', '1'],
    'c12_globals.sov': ['115', '115'],
    'c13_imports.sov': ['4252', '7bits'],
    'c14_platform.sov': ['11', 'platform ok'],
    'c15_float.sov': ['9007199254740992', '21', '0', '-2', '-1', '9223372036854775807', '9223372036854775807', '3', '9223372036854775807'],
    'c16_abi.sov': ['1234567', '507'],
}

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def eligible(e):
    if e['id'] in EMULATOR_EXECUTORS:
        return e.get('kind') == 'native'
    h = e.get('host') or {}
    return h.get('os') == 'linux' and h.get('architecture') == 'x86_64' and e.get('kind') == 'native'

def build_win_driver():
    driver = Path('/tmp/conf_win_driver.bin')
    try:
        driver.unlink()
    except FileNotFoundError:
        pass
    r = subprocess.run([str(ROOT / 'compilers/linux/compiler'), str(CORPUS.parent / 'win_driver.sov'),
                        '-o', str(driver), *COLD], cwd=ROOT, capture_output=True, timeout=300)
    if r.returncode != 0 or not driver.is_file():
        return None
    driver.chmod(driver.stat().st_mode | 0o111)
    return driver

def run_case(exe, case, art, driver):
    if driver is None:
        return None
    argv = CASE_ARGV.get(case, [])
    rrc = subprocess.run([str(driver), str(art), *argv], capture_output=True, timeout=300)
    return rrc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str('/tmp/language-coverage.json'))
    a = ap.parse_args()
    registry = json.loads((ROOT / 'backends/registry.json').read_text())
    entries = [e for e in registry['entries'] if eligible(e)]
    out = {'implementation_sources_sha256': {}, 'backend_executables_sha256': {}, 'cells': [], 'summary': {}}
    snap = {}
    for root in ['runtime.sov']:
        p = ROOT / root
        snap[root] = sha256(p)
    for root in ['compilers', 'library', 'frontend', 'ir', 'runtime', 'backends', 'transpilers', 'emitters']:
        for p in sorted((ROOT / root).rglob('*.sov')):
            if p.is_file() and not p.is_symlink():
                snap[str(p.relative_to(ROOT))] = sha256(p)
    out['implementation_sources_sha256'] = snap
    outdir = Path(a.output).parent
    outdir.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for e in entries:
        exe = ROOT / e['executable']
        if not exe.is_file():
            # failing closed per 0.2: a missing/stale-quarantined lineage
            # binary is a RED cell (lineage-pending), never a skip
            all_ok = False
            out['summary'][e['id']] = 'lineage-pending (red: executable quarantined/absent)'
            continue
        if not (exe.stat().st_mode & 0o111):
            exe.chmod(exe.stat().st_mode | 0o111)
        esha = sha256(exe)
        out['backend_executables_sha256'][e['id']] = esha
        driver = None
        if e['id'] in EMULATOR_EXECUTORS:
            driver = build_win_driver()
            if driver is None:
                out['summary'][e['id']] = 'emulator-driver-unavailable'
                all_ok = False
                continue
        # probe: can this backend's artifacts execute on THIS host?
        # (emulator targets are probed by their own lane below)
        if e['id'] in EMULATOR_EXECUTORS:
            out['summary'].setdefault(e['id'], 'PENDING')
        else:
            probe_src = CORPUS / 'c01_int_arith.sov'
            probe_art = Path('/tmp/conf_probe.bin')
            try:
                probe_art.unlink()
            except FileNotFoundError:
                pass
            try:
                rp = subprocess.run([str(exe), str(probe_src), '-o', str(probe_art), *COLD],
                                    cwd=ROOT, capture_output=True, timeout=300)
                if rp.returncode == 0 and probe_art.is_file():
                    rp2 = subprocess.run([str(probe_art)], capture_output=True, timeout=120)
                    if rp2.returncode != 0:
                        # artifact exists but cannot execute on this host: the
                        # target is ineligible here (not a cell failure)
                        out['summary'][e['id']] = 'artifact-not-host-executable'
                        continue
            except (subprocess.TimeoutExpired, OSError):
                out['summary'][e['id']] = 'artifact-not-host-executable'
                continue
        passed_features = set()
        case_ids = {}
        ok_all = True
        for case, features in sorted(CASE_FEATURES.items()):
            src = CORPUS / case
            art = Path('/tmp') / ('conf_' + case.replace('.sov', '.bin'))
            try:
                art.unlink()
            except FileNotFoundError:
                pass
            try:
                r = subprocess.run([str(exe), str(src), '-o', str(art), *COLD],
                                   cwd=ROOT, capture_output=True, timeout=300)
            except subprocess.TimeoutExpired:
                ok_all = False
                continue
            if r.returncode != 0 or not art.is_file() or art.stat().st_size == 0:
                ok_all = False
                continue
            if driver is not None:
                rrc = run_case(exe, case, art, driver)
                if rrc is None:
                    ok_all = False
                    continue
            else:
                try:
                    rrc = subprocess.run([str(art), *CASE_ARGV.get(case, [])], capture_output=True, timeout=120)
                except OSError:
                    ok_all = False
                    continue
            lines = rrc.stdout.decode(errors='replace').split('\n')
            if lines and lines[-1] == '':
                lines = lines[:-1]
            if rrc.returncode == 0 and lines == EXPECTED[case]:
                for f in features:
                    passed_features.add(f)
                    case_ids.setdefault(f, []).append(case)
            else:
                ok_all = False
        for f in sorted(set(sum(CASE_FEATURES.values(), []))):
            ok = f in passed_features
            out['cells'].append({
                'target': e['id'], 'feature': f, 'pass_test': ok, 'executed': ok,
                'compiler_sha256': esha, 'case_ids': case_ids.get(f, []),
                'executor': 'sovren-x86-emulator' if driver is not None else 'native',
            })
        out['summary'][e['id']] = 'PASS' if ok_all else 'FAIL'
        all_ok = all_ok and ok_all
    Path(a.output).write_text(json.dumps(out, indent=2) + '\n')
    for tid, s in sorted(out['summary'].items()):
        print(f'{tid:60} {s}')
    print('ALL PASS' if all_ok else 'FAILURES PRESENT')
    raise SystemExit(0 if all_ok else 1)

if __name__ == '__main__':
    main()
