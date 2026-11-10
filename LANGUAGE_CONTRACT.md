# Sovren Language Contract — version 58.0

This is the versioned behavioral contract the conformance corpus enforces
(Track 0.2). Bump the version only with a corpus change; CI fails closed on
any cell that drops coverage. Any backend cell that cannot execute or
disagrees with a case is RED — never skipped-to-green.

## Binding
- Runner: `tests/conformance/language_conformance.py` (exit 0 ⇔ every
  eligible registry cell passes every corpus case on this host; every
  ineligible/missing-lineage cell is recorded line-by-line as red).
- Corpus: `tests/conformance/corpus/c01..c16` (+ p2 extras). Each case is
  pinned to contract features in `CASE_FEATURES`.
- Registry: `backends/registry.json` enumerates every backend cell; the
  runner attests each binary by sha256 and snapshots every implementation
  source by sha256, so the evidence binds to exact bytes.

## Contract features (c01..c16)
c01 integer-arithmetic · c02 functions-recursion · c03 structured-control ·
c04 short-circuit · c05 left-to-right-effects · c06 text-literal-output ·
c07 dynamic-argc + argv-access · c08 general-text · c09 collections ·
c10 structs · c11 pointers-memory · c12 globals · c13 imports-libraries ·
c14 platform-services · c15 floating-point · c16 target-abi.

Semantics sources of truth: the Linux x86-64 lineage compiler
(`backends/native/linux/compiler.sov` via `compilers/linux/compiler`) and
`runtime.sov`. Divergences are bugs in the diverging cell, not tests to skip.

## Modes (per backend cell, from backends/required-matrix.json)
fresh-application · fully-uncached · identical · edited-function ·
end-to-end — with the listed edit categories and workload families.
95% CI latency ≤ sa ×1.0 and throughput ≥ sa ×1.0 are the parity gates.

## Version history
- 58.0 (2026-10-26): first pinned version; corpus c01..c16, features as
  above. Cache lineage purge complete (legacy `--usepfx/--cache/--uncached`
  flags are rejected as unknown; only `compilers/*` lineage is measurable).
