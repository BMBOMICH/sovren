# Sovren parity session — 2026-11-03 (evening continuation)

Deliverable: `sovren-tree-2026-11-03-v3.zip` (the full updated tree).
Certified compiler: `d96aaf91` (md5 d96aaf91eeae5a33599eb905dc922c9e,
ratchet lineage below). Verified: 2-generation fixed point (the installed
compiler reproduces itself byte-for-byte), `bash tools/tier_gate.sh` GREEN
on the final state (all six stages), 12/12 layout sweep stable, hello /
all / x86ins byte-identical vs the pre-session certified compiler at
every step.

## What was asked

"Keep continuing until everything's done": the three structural Tier 1
items left open by the afternoon report — item 5 (role lowering /
emit-chain batching), item 6 (token stream), item 7 (pass fusion) — plus
whatever the discipline could verify along the way.

## The forensics investment (before touching code)

The afternoon's targeting data came from the single-shot `--prof` phase
table. This session built an integrated, noise-resistant profiler to
re-derive it natively:

- `scripts/fnmap_build.py` — builds a variant compiler that dumps its own
  function map (917 entries: fn_names/fn_offs, oc offsets) when
  `/tmp/sov_fnmap` exists; the variant is its own 2-generation fixed
  point, so the dumped map describes the binary being sampled.
- `scripts/sampler_fnmap.py` — ptrace sampling profiler that maps RIP
  directly onto the fnmap ranges. The earlier endbr64-based mapping was
  unreliable (generated functions do not start with endbr64); the direct
  fnmap bisect is exact. Two rbp-chain frames give caller-of-caller
  attribution. Interrupts are interval-throttled (on this box a full-rate
  ptrace loop starves the tracee >100x) and the child respawns until the
  budget expires, so short compiles accumulate samples.
- Integrated profiles: 77 complete self-compiles and ~160 all.sov
  compiles per run.

Two findings that changed the plan:

1. **The `--prof` phase table mislabels and inflates.** `mark()` lands
   elapsed time in the closing mark's bucket, so the "p-stub" bucket
   actually contains `dce()`, "p-dce" contains `pk_sync`+`wbuf_flush`,
   and `stub_diet` itself is ~0 ms on self (want_args=1, sd_live=1,
   early return). And single-shot instrumentation over-weights several
   buckets vs the integrated native profile: C1 17.2 ms claimed vs
   ~11 ms sampled, 2-all-spliced 5.1 vs ~2.5, 5a-flat0 3.9 vs <1.5.
2. **The bulk lanes' true pigs (integrated sampling).** Self: the
   walk/lowering twins plus `collect_body` (3.1%), `syntax_build`
   (2.1%), `syntax_statement_build` (1.9%), medium allocator (1.8%),
   `dce`+`dce_stores` (~3%), `dce_litter`'s per-record `bsearch_le`
   (1.3%), `st_build` (1.6%). all.sov: the parse's string work —
   `stmt`'s compound/repl strcats (4.2%), `par_intern`→`unesc` (4.0%),
   `syntax_call_operand` interning (3.0%), chunk file reads (3.3%).

## What landed (three rounds, each ratcheted + A/B'd)

### Round A1 — dce: one pass, no re-interning (the real "p-stub" pig)
`dce()` walked all ~48k patch records twice: once to materialize a
48k-entry `downer` side list, then again calling `intern_kid(kind)` per
record — re-interning exactly the table `pk_sync` had built one call
earlier. Now the owner walk and the call-edge walk are ONE pass; the
interned kind is read straight from `patch_kid` (with the standard
length guard and `intern_kid` fallback); the rebuild tail recomputes
owners with its own advancing window instead of reading `downer`.
(cx86_p7.sov, `dce`.)

### Round A5 — the private/wipe probe folded into the parse
The standalone pre-parse probe `strip_span`'d every line (12k on self,
~2.5% sampled) to test `private` / `wipe `. The single-pass parse loop
now does it inline, decision-identically: top-level lines compare the
`s = strip(raw)` it already computed; indented lines gate on the first
non-space byte at the offset `nind` already walked (only p/w/tab can
ever match; a tab still goes through `strip_span`'s strip path exactly
as before). The standalone sweep is gone. (compiler.sov, compile.)

### Round R2 — dce_litter: advancing owner window
`dce_litter` ran `bsearch_le(fn_offs, ...)` per patch record (~48k x
log2(2.7k) on self). Replaced with one shared advancing cursor over the
ascending `patch_at` (the same invariant dce's ff window already relies
on), with a bsearch fallback for any record that sorts before the
cursor — correctness never depends on the monotonicity guess.
(cx86_p3.sov, `dce_litter`.)

## Measured (discipline tools, final state)

| comparison | x86ins | all.sov | self |
|---|---|---|---|
| A1 vs certified (R=12) | +1.0% | +1.5% | +0.9% |
| A5 vs certified (R=12) | +1.8% | +0.8% | +0.4% |
| R2 vs certified (R=12) | +0.6% | +0.7% | +2.1% |
| final: pre-session vs installed (R=12) | +1.0% | +0.2% | +0.1% |
| final: pre-session vs installed (R=21) | +1.0% | -0.5% | +1.5% |

Honest reading: every round was positive on all three bulk lanes, and
the changes strictly remove work (48k interns + a 48k-entry list, a
12k-line strip sweep, 48k binary searches) — but the cumulative bulk
effect sits at/near this box's noise band (its own A/A gate tolerance
is 3%; two finals gave self +0.1% and +1.5%). Tiny-path CPU-time A/B
(interleaved per-child rusage, immune to scheduler steal): exit7
+2.7%, sum +1.4% (median). Self-build syscalls 781 -> 743 (no probe
regression). A/B JSONs: work/p4/ab_a1_dce_kid.json, ab_a5_privprobe2.json,
ab_r2_dlitter.json, ab_final_session3.json, ab_final_session4.json.

## Analyzed with the new data and deliberately NOT landed

- **rel_n counter fusion into the filter passes** (write_elf's counting
  sweep): the 5a-flat0 bucket's 3.9 ms is single-shot `--prof`
  inflation; integrated sampling bounds the sweep under ~1.3 ms — the
  drop-path risk (a missed decrement mis-sizes the flat buffer) is not
  worth it.
- **2-all-splice pass fusion** (rt/extra line+extras counting): same
  story — real cost ~2-2.5 ms, not 5.1; fusing means duplicating
  sg_extra_ls's decline probe on raw bytes. Skipped.
- **sg_marks single-pass rewrite**: 3 native SWAR scans vs 1 interpreted
  byte loop — the div_magic lesson (that rewrite class measured neutral)
  applies. Skipped.
- **unesc/intern_fast decode fusion** (4.0% of all.sov): the hot path
  executes inside the native twin blob, so the fix means regenerating
  the blob (C pipeline, sha-pinned) — dedicated-session scope with the
  blob pipeline, same as the bw emit-chain work.
- **collect_body**: already on the IR fast path (syntax_mode=1 default);
  the remaining 3.1% is the block-end scan + copy. Fusing needs its own
  semantics-careful pass.

## The honest state of items 5/6/7

- **Item 5 (bw/role lowering)**: not attempted this session. Integrated
  sampling confirms bw+walk ~40-50% of self but smeared across the
  planted twins (emit_nt_syntax_statements, _sov_emit_tw); the
  emit-chain batching lever requires the blob pipeline.
- **Item 6 (token stream)**: the decline-path costs are now pinned with
  exact call-site data — stmt's compound/repl strcats (4.2% all),
  par_intern's unesc (4.0% all), syntax_call_operand interning (3.0%
  all). Those are precisely the string-rebuild work the token records
  would eliminate; wiring remains dedicated-session scope.
- **Item 7 (pass fusion)**: the real fusion targets under integrated
  sampling were the dce family — landed (A1 + R2). The other named
  targets (p-stub/stub_diet, splice, flat0) were phase-table artifacts;
  stub_diet is already ~free on self.

## Verification (from the tree root)

    touch /tmp/sov_nopar
    bash tools/tier_gate.sh                     # GREEN (all six stages)
    python3 /home/z/my-project/scripts/layout_check.py   # 12/12 layouts
    python3 tools/ab_speed.py work/p4/compiler.pre-session \
        compilers/linux/compiler --runs 21 --output work/p4/ab_final_session4.json
    python3 /home/z/my-project/scripts/cpu_ab.py \
        work/p4/compiler.pre-session compilers/linux/compiler \
        tests/performance/exit7.sov 41

## Ratchet lineage (this session)

    2368f3f1 (afternoon certified, pre-session)
      -> d96aaf91 (A1 dce one-pass/kid reads + A5 probe-in-parse
                   + R2 dce_litter owner window; installed)
    Each step: 2-generation fixed point, hello/all/x86ins byte-identical
    vs the pre-session certified compiler, tier gate green on the final
    state, 12/12 layout sweep stable.
