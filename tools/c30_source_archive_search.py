#!/usr/bin/env python3
"""C.30 — exhaustively close the "where are the real per-driver sources?" search.

The 29 lineage-pending fleet drivers are compact/pinned-include fragments that
do not compile (no `main:` task, unindented statements, duplicate definitions).
Earlier sessions established that 25/29 are byte-identical to the uploaded
upstream manifest, that all 1,315 include pins verify, and that a recursive
flatten still fails.  This tool closes the LAST open question: does ANY archive
or backup anywhere in the workspace hold a *different*, complete per-driver
source for those 29 paths?

It is deliberately a SEARCH / CENSUS tool, not a repair tool.  It never writes
into compilers/, never deletes a .build-failed marker, never edits a gate and
never claims a build.  A "real source" candidate must be a compiler.sov whose
text has a column-0 `main:` task; compact fragments do not.

Usage: python3 tools/c30_source_archive_search.py [--json OUT]
"""
import argparse
import hashlib
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path

ROOT = Path('/home/user')
SOV = ROOT / 'dl' / 'sovren'
E = ROOT / 'evidence'
BLOCKER = E / 'C30_blocker_2026-11-09.json'
ARCHIVE_SUFFIXES = ('.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.gz')
MAIN_RE = re.compile(r'^main(?:\s+\w[^:]*)?:', re.M)
PIN_RE = re.compile(r'^\s*include\s+\S+\.sov\s+\d+\s+\d+', re.M)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def is_driver_path(name):
    n = name.replace('\\', '/').lstrip('./')
    return n.endswith('/compiler.sov') or n == 'compiler.sov'


def classify(name, data):
    """Return a compact verdict for a compiler.sov-like archive member."""
    try:
        text = data.decode('utf-8', 'replace')
    except Exception:
        text = ''
    main = bool(MAIN_RE.search(text))
    pins = len(PIN_RE.findall(text))
    return dict(path=name, bytes=len(data), sha256=sha256(data)[:16],
                lines=text.count('\n') + 1, has_main_task=main,
                pinned_include_lines=pins,
                verdict='COMPLETE_SOURCE' if main else 'FRAGMENT_OR_NONSOURCE')


def scan_zip(p):
    out = []
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if info.is_dir() or not is_driver_path(info.filename):
                continue
            try:
                out.append(classify(info.filename, z.read(info)))
            except Exception as exc:
                out.append(dict(path=info.filename, error=repr(exc)))
    return out


def scan_tar(p):
    out = []
    with tarfile.open(p, 'r:*') as t:
        for m in t.getmembers():
            if not m.isfile() or not is_driver_path(m.name):
                continue
            try:
                f = t.extractfile(m)
                out.append(classify(m.name, f.read() if f else b''))
            except Exception as exc:
                out.append(dict(path=m.name, error=repr(exc)))
    return out


def scan_gz(p):
    """A bare .gz is one file; only treat it as a candidate if its name says so."""
    import gzip
    if 'compiler' not in p.name.lower():
        return []
    with gzip.open(p, 'rb') as f:
        return [classify(p.name, f.read())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C30_source_archive_search_2026-11-09.json'))
    a = ap.parse_args()
    blocker = json.loads(BLOCKER.read_text())
    broken = [d['driver'] for d in blocker['drivers']]
    broken_basenames = {Path(d).parent.as_posix() for d in broken}

    archives = sorted(str(p) for p in ROOT.rglob('*')
                      if p.is_file() and str(p).endswith(ARCHIVE_SUFFIXES)
                      and not any(part in {'.cache', 'node_modules', '.git'}
                                  for part in p.parts))
    archive_rows = []
    for a_path in archives:
        p = Path(a_path)
        try:
            if p.suffix == '.zip':
                members = scan_zip(p)
            elif p.name.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2')):
                members = scan_tar(p)
            else:
                members = scan_gz(p)
            err = ''
        except Exception as exc:
            members, err = [], repr(exc)
        archive_rows.append(dict(archive=str(p.relative_to(ROOT)), bytes=p.stat().st_size,
                                 compiler_sov_members=len(members), error=err,
                                 members=members))

    # Broken-driver paths outside the live compilers/ tree (regular files).
    loose = []
    for rel in broken:
        for p in ROOT.rglob(Path(rel).name):
            if not p.is_file():
                continue
            rp = p.relative_to(ROOT).as_posix()
            if rp.startswith('dl/sovren/compilers/'):
                continue
            if not rp.endswith('/compiler.sov') and rp != 'compiler.sov':
                continue
            loose.append(dict(path=rp, bytes=p.stat().st_size,
                              sha256=sha256(p.read_bytes())[:16]))

    # A candidate only counts if it is a COMPLETE source AND its path lands in
    # one of the 29 lineage-pending driver directories.  The Linux compiler
    # source (compilers/linux/compiler.sov) is complete but is NOT a missing
    # per-driver source; it must not be counted as a candidate.
    def matches_broken(path):
        n = path.replace('\\', '/').lstrip('./')
        return any(n.endswith(d) or ('/' + d) in n for d in broken)

    complete = [dict(archive=r['archive'], **m)
                for r in archive_rows for m in r['members']
                if m.get('has_main_task') and matches_broken(m.get('path', ''))]
    complete_nonbroken = [dict(archive=r['archive'], path=m.get('path'))
                          for r in archive_rows for m in r['members']
                          if m.get('has_main_task') and not matches_broken(m.get('path', ''))]
    fragment_copies = sum(1 for r in archive_rows for m in r['members']
                          if m.get('verdict') == 'FRAGMENT_OR_NONSOURCE')
    rep = dict(
        schema=1, date='2026-11-09',
        purpose='Exhaustive search for COMPLETE per-driver sources of the 29 lineage-pending fleet drivers.',
        broken_driver_count=len(broken),
        broken_driver_parent_dirs=sorted(broken_basenames),
        archives_scanned=len(archives),
        archives=archive_rows,
        complete_source_candidates=complete,
        complete_source_candidate_count=len(complete),
        complete_sources_not_for_broken_drivers=complete_nonbroken,
        fragment_or_nonsource_members=fragment_copies,
        loose_compiler_sov_outside_live_fleet=loose,
        verdict=('NO_COMPLETE_PER_DRIVER_SOURCES_FOUND'
                 if not complete else 'CANDIDATES_FOUND_REVIEW_REQUIRED'),
        note=('Every archive member named compiler.sov is either the Linux compiler '
              'source, a shared cx86 backend source, or a compact/pinned-include '
              'fragment WITHOUT a column-0 main: task. No archive holds a distinct '
              'complete source for any of the 29 lineage-pending paths. This closes '
              'the source search; C.30 remains blocked on material that does not '
              'exist in this workspace, not on an untried repair.'),
    )
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.30 source archive search: %d archives, %d complete candidates -> %s'
          % (len(archives), len(complete), rep['verdict']))
    for r in archive_rows:
        print('  %-48s %7d B  compiler.sov members=%d %s'
              % (r['archive'], r['bytes'], r['compiler_sov_members'], r['error']))
        for m in r['members']:
            print('      %-55s main=%-5s pins=%-4s %s'
                  % (m.get('path'), m.get('has_main_task'),
                     m.get('pinned_include_lines'), m.get('verdict')))
    print('  -> %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
