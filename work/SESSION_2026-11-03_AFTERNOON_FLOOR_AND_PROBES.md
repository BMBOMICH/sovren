# Sovren parity session — 2026-11-03 (afternoon continuation)

Deliverable: `sovren-tree-2026-11-03-v2.zip` (the full updated tree).
Certified compiler: `2368f3f14ba6ec2a` (ratchet lineage below).
All numbers from the tree's own discipline tools: `tools/ab_speed.py`
(R=12 rotating interleaved medians), `tools/paired_workloads.py`
(exit-code-asserted), CPU-time A/B for the tiny path (interleaved
per-child rusage — immune to this box's scheduler steal), and
`bash tools/tier_gate.sh` (GREEN on the final state, all six stages).

## What was asked

Everything left open from the morning session's report: item 5 phase C
(top-30 twinning + role lowering), item 6 (token stream), item 7 (pass
fusion), item 9 (latency floor), item 10 (decline path), item 11
(exec-without-fork).

## What landed (three verified rounds, all byte-identical outputs)

### Round 1+2 — the latency floor, part 1 (item 9)
Forensics first: a ptrace syscall tracer + a dumpmod sampling profiler
(fnmap via a temporary FNMAP-dump build) found the real tiny-path floor.
- **Dead-bzero removal.** Every `_sov_heap_alloc(n>64KiB)` returns fresh
  mmap memory (kernel-zeroed; large blocks are munmapped on free, never
  recycled) — the `_sov_bzero` calls that followed such allocations were
  dead work. Made conditional (`<= 64KiB` keeps the bzero) at ten sites:
  `kgrow_ht`, `zz_nsync`, `fn_sync` growth, `pd_uk`/`pd_key`, the four
  `fsem_*` tables, `floc_ep/ce`, the ELF `flat` buffer, and the SX buffer.
  Measured on exit7: one 512KiB bzero (zz_nsync's names table) plus ~190KiB
  of medium ones, gone.
- **Kid-table pre-sizing.** Any compile interns ~1.4k compiler keyword
  constants before the first user line parses; the old 256-slot table
  walked the 256→4096 rehash chain every run. Now 8192 slots + 64KiB pool,
  one allocation, zero rehash on guest compiles (first attempt at 65536
  slots was measured SLOWER by CPU-time A/B — page-fault scatter ate the
  win — and was right-sized down; the lesson is in the diff history).
- **Probe reorder.** `par_setup` checked `/proc/cpuinfo` (open + 256KiB
  buffer + read) before checking `/tmp/sov_nopar`; under the discipline
  (nopar always present) that read was pure waste. Nopar is now checked
  first; cpuinfo is only read when parallelism would actually run.
- Measured: exit7/sum/calls CPU-time A/B **+6.9% / +7.2% / +3.9%**
  (median); bulk self/all/x86ins +0.3-0.8%.

### Round 3 — the probe storm (item 9, and a self-build win)
The syscall census found **7,944 open() calls on the self build** (8,718
total syscalls). The write_elf patch loop probed `/tmp/sov_glog2` **per
patch record** (~7,400), plus per-new-global and parse-end probes.
Hoisted into `zz_g2()` — a once-per-run boolean (an in-run gate flag,
not compilation data; no cache-policy exposure — the no-cache gate
confirms). Self-build syscalls: **8,718 → 781**.
Measured: self **+1.5%**, x86ins +1.1%, all +0.4% (R=12 A/B).

### Item 11 — exec-without-fork: verified already working
`--exec` (run_exec) builds the child argv and calls execve directly —
no fork, no clone syscall in the trace, and the program's exit code
becomes the compiler's (verified: exit7 → 7, sum → 92, syscall trace
shows execve and zero clones). Documented here because the morning
report had it as unverified.

### Item 10 — decline path: pre-probe confirmed landed and firing
The 2026-11-03 pre-parse decline probe is in the certified tree
(syntax.sov syntax_try): the doubled-inner-quote spans (rc 5) now
decline up front — same census accounting, no wasted token+tree parse.
all.sov: 14 declines, 649/649 native trees. The remaining half-measure
(widening the admitted grammar to actually parse those spans) stays
deliberately deferred: the legacy whole-quoted-surface rule makes it
semantics-risky for <1%.

## What was measured, tried, and NOT landed (the discipline)

- **div_magic table rewrite** (43-branch chain → direct-indexed table for
  d<41 + 9-entry chain): byte-identical, but A/B **neutral** (0.995-1.001)
  — the sampler's 4.3% attribution for it was adjacent-code bleed.
  Reverted; the tree carries only measured wins.
- **cur/cur_ln list pre-sizing**: bounded win (~1-2ms, most bodies fit
  the initial cap 24 + one doubling), skipped as not worth the churn.
- **sg_plain one-pass rewrite**: all three gate workloads contain ": "
  (compact forms), so sg_plain early-exits for them; the 22-scan toll
  only hits compact-free sources — not a gate metric. Documented for
  whenever a plain-source lane matters.

## The honest state of items 5/6/7 (structural Tier 1)

The session spent its budget on making the floor honest and landing the
verified latency wins; the three structural items remain the next
increments on the now-proven pipeline, with sharper targeting data:
- **Item 5**: the bw callees (bin_k, expr_call, loadv, atom_str_type,
  expr_span, expr_index) are untwinned comparison/emit-chain functions;
  the emit-chain batching (sa's register-cursor tail) is the real lever,
  not per-function twinning — div_magic proved that class of fix neutral.
- **Item 6**: C1's pig is `cx_read` (17.0ms of self, 4.0ms of all.sov) —
  every gate workload takes the compact-form path. The tk_lex oracle is
  intact; wiring body()/stmt()/expr onto token records remains the
  dedicated-session scope.
- **Item 7**: p-stub 8.0ms + pu 6.4ms + 2-all-spliced + 5a-flat0 ≈ 26ms
  of self in fusable passes; untouched this session.

## Measured state (final, this box)

| workload | pre-session | now (2368f3f1) | delta |
|---|---|---|---|
| self | 185-192 ms | **180-186 ms** | ~+2.5-4% |
| all.sov | 62-66 ms | **59.5-61 ms** | ~+3-5% |
| x86ins | 23.2-23.9 ms | 23.2-23.5 ms | ~+1-2% |
| exit7 (CPU-time A/B) | — | **+6.9%** | vs pre-lat9 |
| sum (CPU-time A/B) | — | **+7.2%** | vs pre-lat9 |
| calls (CPU-time A/B) | — | **+3.9%** | vs pre-lat9 |
| self-build syscalls | 8,718 | **781** | -91% |
| tiny-path bzero bytes | 705,600 | ~0 above 64KiB | |

Phase table (self 179.8ms total): bw 69.9/38.9%, W-walk0 30.7/17.1%,
c0-parsed 23.0/12.8%, C1 17.0/9.5% — refreshed by the gate into
`work/PHASE_TABLE.md`.

## Verification (from the tree root)

    touch /tmp/sov_nopar
    bash tools/tier_gate.sh                     # GREEN (all six stages)
    python3 /home/z/my-project/scripts/layout_check.py   # 12/12 layouts
    python3 /home/z/my-project/scripts/cpu_ab.py \
        work/p4/compiler.pre-lat9 compilers/linux/compiler \
        tests/performance/exit7.sov 41          # tiny-path CPU A/B

## Ratchet lineage (this session)

    c52a2003 (lat9 r1+r2: dead bzeros, kid pre-size, probe reorder)
      -> 2368f3f1 (+ zz_g2 probe hoist; installed)
    Each step: 2-generation fixed point, hello/all/x86ins byte-identical,
    tier gate green, 12/12 layout sweep stable on the final state.

A/B JSONs: work/p4/ab_lat9_r1.json, ab_lat9_r2.json, ab_probe_fix.json,
ab_divtab.json (the reverted neutral), ab_final_session.json.
