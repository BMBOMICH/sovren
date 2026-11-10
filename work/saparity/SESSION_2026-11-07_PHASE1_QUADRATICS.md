# sa-parity work — session 2026-11-07 (phase 1: the two quadratics + walk-path cuts)

Deliverable: `sovren-tree-2026-11-07-v9.zip` — certified compiler
`7d930fd5` (md5), oracle 24 pass + 16 refuse-parity + 0 FAIL, fixed point
g2 == g3 == installed, every synthetic output byte-identical to the
session-start binary on loc/vars/fns shapes.

## What was asked

The remaining sa-parity plan: phase 1 (kill the 97k self-compile
allocations), phase 2 (pass fusion), the recorded walls (the 100k-locals
O(n^2), the lsh twins, the floor), then the everywhere-audit with every
lane >= sa, oracle and fixed point green at every step.

## What landed

1. **The c0-parsed quadratic is dead (st_var memo).** `st_var`/`st_expr`
   answered `list_idx(st_vars, ...)` — a linear scan over every distinct
   local — once per assignment line and once per RHS atom. The fix is an
   open-addressed content-keyed memo over the append-only st_vars/st_ids
   pair (stv_find/stv_put/stv_kill): hits verify against the live list,
   misses go straight to the append (the memo is complete — every append
   goes through stv_put, both reset sites kill it). The first version
   kept a list_idx fallback on miss, which re-paid the full scan for
   every NEW local — the second half of the quadratic. Removed.
2. **The walk quadratic is dead (lord sort).** lord_build's register-home
   seeding tail built the frequency-ordered name list with a per-item
   position scan + middle insert: O(n^2) shifts for n distinct targets
   (~1.4 s of loc100k alone). Replaced by collect-in-arrival-order plus a
   bottom-up merge sort keyed (score desc, arrival asc) — the exact total
   order the insertion produced (verified: outputs byte-identical on all
   shapes). Landing it needed the phase-3 migration rename
   `_sov_lord_build` -> `_sov_lord_build2` (the old binary's baked
   whitelist would have planted the OLD blob into g2; bootstrap converged
   at g3). A < 32-target threshold keeps tiny bodies on the classic
   insertion (the merge scaffolding cost deepfns 24% before it).
3. **st_expr strip fast path.** The RHS spans the c0 blob hands carry at
   most trimmable leading bytes; a clean tail now means a pure pointer
   skip instead of the strip call. (The hoped-for 100k-alloc kill was
   misattributed — those allocs are st_node's per-node adjacency lists,
   see "recorded next walls".)
4. **lines_of_fast SWAR native twin.** The existing hand-written twin was
   a byte-at-a-time loop; it is replaced by a C port
   (tools/native_linesfast.c -> linesfast_native.sov, 978 bytes, no
   relocs) with the same qword SWAR split as the interpreted body,
   table-calling _sov_list_new/_sov_heap_alloc. Dispatch plants on the
   new wrapper `_sov_lines_of_fast(src, lf_tbl)`; the old kid-table
   dispatch and byte-loop twin were deleted. Interleaved A/B measured it
   roughly neutral-to-small-positive — the sampler's "12%" for
   lines_of_fast was ptrace-interrupt bias toward tight loops.
5. **stv first table is 16 slots.** The original 256-slot (4 KiB) first
   table per function regressed deepfns 24% (1500 small functions x one
   4 KiB bzero each); 16 slots + doubling restores it.

## Measured effect (same-session, interleaved, min-of-9)

| shape | old (ea609674) | new (7d930fd5) | speedup |
|---|---|---|---|
| loc12k | 239.0 ms | 21.5 ms | 11.1x |
| loc100k | 15.16 s | 173.4 ms | **87.4x** |
| vars4m | 15.27 s | 339.4 ms | **45.0x** |
| fns1m | 261.2 ms | 259.9 ms | 1.0x |
| self-compile | 203.7 ms | 202.8 ms | 1.0x |
| deepfns | 11.1 ms | 11.4 ms | 1.0x |

Scaling is now linear in locals: 12k -> 48k -> 100k costs 21.5 -> ~86 ->
173 ms (was quadratic: 4x lines cost 13-16x). The everywhere-audit ran
with zero crashes on every lane. Same-session sa reference: 115.3 MB/s
on its own source, 751 us tiny floor (machine ~15% slower than the
morning session; the ledger above is old-vs-new on the same machine
state, which is the only honest comparison).

## The everywhere-audit (phase 4 lanes, honestly NOT at sa)

| lane | sovren | vs sa same-session |
|---|---|---|
| tiny floor (28-191 B) | 2572-2848 us | 3.4-3.8x off (sa 751 us) |
| real library files | 0.53-4.21 MB/s | not matched |
| vars4m / loc100k / fns1m | 11.5 / 10.2 / 3.7 MB/s | not matched; **linear now** |
| deepfns | 7.61 MB/s | not matched |
| self-compile (410 KB) | 204.6 ms = 2.01 MB/s | ~57x off (sa 115.3) |

## How the quadratics were found (the method, for the next session)

`--instrument-compiler` builds a counting compiler; `--prof` dumps
phase-endpoint aggregates to stderr. Marks bisect phases without touching
the certified source (probe builds are thrown away). For leaf-level
attribution the fn map comes from the glog gate (`touch /tmp/sov_glog`,
compile the compiler, `awk '$1=="fn"' /tmp/sov_globs.txt` — offsets are
exact, validated 1028/1031 endbr-aligned; the 3 misses are frameless
twins) and tools/sampler.py (ptrace) samples it. Caution: interrupt
sampling overstates tight loops — lines_of_fast read "12%" but replacing
its byte-loop twin measured ~0; trust interleaved min-of-9 A/B for
verdicts.

## Recorded next walls (honest, in measured order)

1. **Phase 2 — pass fusion** is the structural lever for the ~57x
   self-compile gap: the reader still splits rt + extra + src into lines,
   joins them back as text, and C1 re-splits; u_scan_wide, sp_has_include
   and splice_inc each walk the whole source; cx_read + c0_parse + the
   walk are three passes. sa's shape is one read, one parse-emit walk,
   end-of-run patches.
2. **st_node's adjacency lists** are the real 1-alloc-per-line in
   c0-parsed (100k on loc100k): every graph node news a fresh empty list.
   A flat edge arena (head-pointer array + bump-allocated cells) would
   kill them; touches st_node/st_edge/the BFS in both the interpreted
   body and tools/native_stbuild.c.
3. **Per-function fixed overhead** (fns1m's wall): ~12 allocs + ~5 us per
   function across the body() call path, the walk epilogue and the line
   loop entry (probe marks y-pre/y-body/z-e1 measured 5/4/3 allocs per
   function respectively; the 3 in the call path are still unidentified).
4. **The lsh twin re-landing** (unchanged from the phase-3 note: ~13 ms /
   7% self-compile cost rides on it).
5. **The floor** (2572-2848 us vs sa's 751): runtime load + seeding +
   process start; untouched this session.

## How to verify (from the tree root)

    bash work/saparity/oracle.sh                     # 24+16+0
    bash work/saparity/fixedpoint.sh                 # g2==g3==installed
    bash work/saparity/bench.sh                      # speed ledger + cliff
    bash work/saparity/everywhere-audit.sh           # the phase-4 lanes
    md5sum compilers/linux/compiler                  # 7d930fd5...

## Files touched

- compilers/linux/compiler.sov — stv memo (+kills at both reset sites),
  lord merge-sort tail with <32 threshold and the _sov_lord_build2
  rename, st_expr trim-exact fast path, lf_tbl/_sov_lines_of_fast
  wrapper + call sites, include linesfast_native.sov
- compilers/shared/cx86_p2.sov — deleted the byte-loop
  emit_nt_lines_of_fast twin
- compilers/shared/cx86_p3.sov — twin dispatch for _sov_lord_build2 and
  _sov_lines_of_fast (nt_will_twin + try_native_body), kid_lines_of_fast
  line removed
- tools/native_lord.c — merge-sort tail with threshold (blob regenerated:
  SHA256 08660ad0...)
- tools/native_linesfast.c — NEW: the SWAR splitter C port
- tools/build_native_syntax.py — 'linesfast' mode
- compilers/linux/lord_native.sov, linesfast_native.sov — regenerated
