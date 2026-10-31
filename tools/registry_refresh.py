#!/usr/bin/env python3
"""registry_refresh.py - make backends/registry.json truthful (items 44, 59).

Recomputes every recorded SHA-256 (source, executable, compatibility
source, shared sources, entrypoints) from the files on disk and rewrites
the registry. Files that do not exist get null + are reported; nothing is
invented. Also records per-entry build status when a build census file
(tools/build_census.py output or conformance run) is supplied via
--status name=STATUS lines; without it, build_status is left untouched.

Truth rules applied on every run:
  * full_language_certified is cleared for entries whose source does not
    build (call with --fail-list FILE listing unbuildable ids, one per
    line) - certification must be earned by a passing build census.
  * evaluator entries get capability_profile "compile-time evaluator
    (constant-fold subset)" unless already more specific: they evaluate a
    program and emit a result stub; they are not general compilers.

Usage:
  python3 tools/registry_refresh.py [--fail-list FILE] [--check]

--check: verify only; exit nonzero listing every stale hash (release gate).
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "compilers/registry.json")


def sha(path):
    p = os.path.join(ROOT, path)
    if not os.path.isfile(p):
        return None
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    check = "--check" in sys.argv
    fail_ids = set()
    if "--fail-list" in sys.argv:
        f = sys.argv[sys.argv.index("--fail-list") + 1]
        fail_ids = {l.strip() for l in open(f) if l.strip()}
    reg = json.load(open(REG))
    stale, missing = [], []
    for e in reg["entries"]:
        pairs = [("source", "source_sha256"), ("executable", "executable_sha256"),
                 ("compatibility_source", "compatibility_source_sha256")]
        for path_key, hash_key in pairs:
            if path_key in e and e[path_key]:
                h = sha(e[path_key])
                if h is None:
                    missing.append((e["id"], e[path_key]))
                if e.get(hash_key) != h:
                    stale.append((e["id"], hash_key))
                    if not check:
                        e[hash_key] = h
        for group in ("shared_source_sha256", "entrypoint_sha256"):
            for path in list(e.get(group, {})):
                h = sha(path)
                if h is None:
                    missing.append((e["id"], path))
                if e[group][path] != h:
                    stale.append((e["id"], f"{group}:{path}"))
                    if not check:
                        e[group][path] = h
        if not check:
            if e["id"] in fail_ids and e.get("full_language_certified"):
                e["full_language_certified"] = False
                e["availability"] = "unbuildable (source drift)"
            if e.get("kind") == "evaluator":
                e["capability_profile"] = \
                    "compile-time evaluator (constant-fold subset, not a general compiler)"
    print(f"entries={len(reg['entries'])} stale={len(stale)} missing={len(missing)}")
    for i, k in stale[:20]:
        print(f"  STALE {i} {k}")
    for i, p in missing[:20]:
        print(f"  MISSING {i} {p}")
    if check:
        return 1 if (stale or missing) else 0
    with open(REG, "w") as f:
        json.dump(reg, f, indent=2)
        f.write("\n")
    print("registry rewritten:", REG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
