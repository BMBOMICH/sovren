#!/usr/bin/env python3
"""Conservative source review tripwire, not a semantic proof of no caching.

Flags additions/changes to cache-like definitions and sidecar literals against
an explicit upstream inventory. Removing an inventoried construct is allowed.
Canonical symbol/string interning and in-run memoisation of pure functions are
NOT translation-result caching: they are globals initialised to zero in every
fresh process and never persist across runs or edits. What is forbidden is any
persisted intermediate, artifact/state sidecar, prefix replay, serve/warm path
or cross-run reuse of a translation result.

Two independent checks run:
  1. inventory drift -- every flagged construct's comment-stripped body hash
     must match the reviewed, frozen baseline. A change requires an explicit
     re-review (--freeze-baseline) with written justification; it is never an
     automatic pass.
  2. sidecar scan   -- NO .sov file anywhere in the tree may contain a
     persisted-output sidecar literal in executable (non-comment) text.
"""
import argparse, datetime, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'\b\w*(?:cache|memo(?:iz\w*|(?=_|\b))|replay|prebuilt)\w*\b|\b(?:wid_last_\w+|ik_last_\w+|ml_cut_\w+)\b', re.I)
EXT = re.compile(r'\.(?:ac(?:\.bin)?|lsug|sug|plk|deepoc|state_o|state)\b|\.prebuilt\b')

# Written justification for each inherited construct. Re-freezing after a
# source edit is only legitimate after reading the diff and adding a note here.
REVIEW = {
    'compilers/shared/cx86_p1.sov::scutr s st':
        'word_id() memoises its last (s -> intern kid) pair in wid_last_s/wid_last_r. '
        'Both globals start at 0 in every fresh process. Pure in-run reuse of a pure '
        'function; no file I/O, no sidecar, no cross-run or cross-edit state.',
    'compilers/shared/cx86_p4.sov::try_stmt_inline var rhs':
        'ml_collect_cached(bf) memoises ml_collect() results per body pointer in '
        'process-local lists (mlc_fi/mlc_txt/mlc_m/...), allocated lazily inside the '
        'run. No persistence, no translation-result reuse across runs.',
    'compilers/shared/cx86_p7.sov::try_scaled_mem name argc argl':
        'ik_cached(nm) compares a call-name slice pointer with ik_nm_ptr and returns '
        'ik_nm_kid on a hit; the cut arena is append-only so pointer identity is exact. '
        'Single-run interning shortcut, no file I/O, no sidecar.',
    'compilers/shared/cx86_p1.sov::word_id s':
        'The wid_last_s/wid_last_r last-result pair itself: two globals initialised to 0 '
        'in the data section, written and read only inside word_id() during one compile. '
        'No persistence of any kind.',
    'compilers/shared/cx86_p1.sov::ik_cached nm':
        'Definition site of the in-run interning shortcut described above. Compares '
        'ik_nm_ptr, falls back to intern_kid(); no file I/O, no sidecar literals.',
    'compilers/shared/cx86_p4.sov::ml_collect_cached bf':
        'Definition site of the per-body ml_collect() memo described above. C.4/C.6 '
        'replaced its linear scan over mlc_fi with a direct-indexed O(1) table '
        '(mlc_tab[bf] = ci+1, 0 = absent) plus mlc_tab_ensure() doubling allocator. '
        'It is still the SAME pure in-run memo: one entry per body, appended only on a '
        'miss, hit restores the same mq_* globals. mlc_tab/mlc_tn are globals '
        'initialised to 0 in every fresh process and reset to 0 by build_inl_set(); '
        'the table is a heap array allocated inside the current run. No file I/O, no '
        'sidecar, no persisted intermediate, no prefix replay, no cross-run or '
        'cross-edit reuse of a translation result.',
    'compilers/shared/cx86_p6.sov::try_mem name argc m0 m1 m2 i2 v2':
        'Calls ik_cached(name) for the same single-run interning shortcut; the block '
        'contains no file I/O and no sidecar literals.',
}


def inventory(root):
    result = {}
    files = [root / 'runtime.sov', root / 'compilers/linux/compiler.sov',
             *sorted((root / 'compilers/shared').glob('*.sov'))]
    for p in files:
        text = p.read_text()
        rel = str(p.relative_to(root))
        lines = text.splitlines(keepends=True)
        starts = [i for i, l in enumerate(lines)
                  if l and not l[0].isspace() and re.match(r'\w+(?:\s+\w+)*:\s*(?:#.*)?$', l.strip())]
        for j, start in enumerate(starts):
            stop = starts[j + 1] if j + 1 < len(starts) else len(lines)
            code = ''.join(l.split('#', 1)[0] for l in lines[start:stop])
            hits = TOKEN.findall(code)
            if hits:
                key = rel + '::' + lines[start].strip().split(':')[0]
                result[key] = {'sha256': hashlib.sha256(code.encode()).hexdigest(),
                               'tokens': sorted(set(hits))}
        # Strings are intentionally included: source spellings of persistent output
        # sidecars should require review even if they occur only in flag diagnostics.
        literals = sorted(set(EXT.findall('\n'.join(l.split('#', 1)[0] for l in lines))))
        if literals:
            result[rel + '::sidecar-literals'] = {'literals': literals}
    return result


def sidecar_scan(root):
    """No .sov file may mention a persisted sidecar in executable text."""
    hits = []
    for p in sorted(root.rglob('*.sov')):
        for i, l in enumerate(p.read_text(errors='replace').splitlines(), 1):
            code = l.split('#', 1)[0]
            if EXT.search(code):
                hits.append(f'{p.relative_to(root)}:{i}: {code.strip()[:120]}')
    return hits


def freeze(root, out):
    constructs = inventory(root)
    unexplained = sorted(k for k in constructs if '::sidecar-literals' not in k and k not in REVIEW)
    payload = {
        'schema': 1,
        'note': 'Existing upstream constructs: inventory, not endorsement of result caching. '
                'Changes require explicit review. In-run memoisation/interning is allowed; '
                'persisted intermediates and cross-run reuse are not.',
        'reviewed_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'review_host': __import__('platform').node(),
        'review': REVIEW,
        'unexplained_constructs': unexplained,
        'constructs': constructs,
    }
    Path(out).write_text(json.dumps(payload, indent=2) + '\n')
    print(f'froze {len(constructs)} constructs -> {out}; unexplained={len(unexplained)}')
    if unexplained:
        for k in unexplained:
            print('  UNREVIEWED:', k)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--inventory-root')
    ap.add_argument('--baseline', default=str(ROOT / 'tools/no_cache_inventory.json'))
    ap.add_argument('--freeze-baseline', metavar='PATH',
                    help='after an explicit written review, re-freeze the inventory')
    a = ap.parse_args()
    target = Path(a.inventory_root) if a.inventory_root else ROOT
    if a.freeze_baseline:
        freeze(target, a.freeze_baseline)
        raise SystemExit()
    current = inventory(target)
    if a.inventory_root:
        print(json.dumps({'schema': 1,
                          'note': 'Existing upstream constructs: inventory, not endorsement of result caching.',
                          'constructs': current}, indent=2))
        raise SystemExit()
    baseline = json.loads(Path(a.baseline).read_text())['constructs']
    bad = [k for k, v in current.items() if baseline.get(k) != v]
    persistent = sidecar_scan(ROOT)
    if bad:
        print('NO-CACHE REVIEW REQUIRED: ' + ', '.join(bad))
    if persistent:
        print('PERSISTED-SIDECAR LITERALS FOUND:')
        for h in persistent:
            print('  ' + h)
    if bad or persistent:
        raise SystemExit(1)
    print(f'no-cache source tripwire OK ({len(current)} reviewed constructs unchanged; '
          f'no persisted sidecar literals in any .sov)')
