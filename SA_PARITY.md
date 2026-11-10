> **Current inventory (2026-11-09):** 30 native compiler drivers and 10 WebAssembly variants are retained. Ancient evaluator/emitter targets, standalone IR and other transpilers were removed after a verified Desktop backup. Windows compiler binaries are currently missing; translation parity and full self-compilation remain unfinished. See [CURRENT_SCOPE.md](CURRENT_SCOPE.md). Earlier claims below are historical.

> **PASS 8 baseline update (2026-11-09, Asia/Baku).** With the user's explicit
> full permission, the certified **C.2/C.3 `pull_uses` stable-chunk work-queue
> slice** is now INSTALLED. Installed compiler md5 changed
> `be20f64258d4a7a91d5c46e07d64be70` -> `2daa6c7de07dda4661621db44297fc0d`
> (1,856,552 B). `agent/state.json` and
> `work/saparity/baseline_frozen.json` were updated to match. User-program
> output bytes are UNCHANGED: 2,957/2,957 differ (also vs ORIGINAL
> `4162d364...`), 36/36 mode/flag, 12/12 layouts, oracle 24/16/0, fixed point
> `g2==g3==installed`, 22/22 C.31 gates ALL GREEN. **No speed claim**: the
> placebo-controlled R=21 A/B is INSIDE_NOISE (B vs A med +0.01%). Every older
> md5 mention below is dated history for the pre-PASS-8 binary.
>

# PURGE NOTICE (2026-10-25, Track 0.0)

> **Current baseline: schema 9 (2026-11-08).** Installed compiler md5
> `be20f64258d4a7a91d5c46e07d64be70` (1,856,552 B). C.4/C.6 is in-run
> memoisation only. Gate sweep 17/0, C.29 2,957/2,957, C.22 ×1.00 LINEAR
> incl. 8 MB. C.27 1/16 GREEN, C.30 126/155 + 29 pending, every C.20–C.25
> speed cell RED. Global completion **NOT met**. See
> `work/saparity/baseline_frozen.json` (schema 9) and
> `work/saparity/ACCEPTANCE_TABLE.md`.

All cache machinery described below (artifact cache, .prebuilt, .ac/.ac.bin, .plk, .lsug/.sug/runtime.sug, state dumps, deep/.deepoc replay, prefix replay, cache flags) has been **fully removed from this tree** in Track 0.0; every compile is cold and no persisted intermediate can ever be produced again. Sections below are retained as dated history. See `work/attic/purge20261025/PURGE_REPORT.md`.

# Matching `sa` translation speed, everywhere — measured state and the work list

## The pass-count arithmetic (2026-11-03; why Tier-1 items 5+6+7 must land together)

Reference point: `sa` = **4.8 cycles/byte** (740 c/B on the 2026-10-22 box
was pre-bench6; the disciplined figure the tree races against is 4.8 c/B
over its own corpus, one call per 44 source bytes). Sovren self-compile
today: ~481 c/B. Where the cycles go is a **pass-count** problem before it
is a per-pass problem:

- **Nativize-only** (item 5 alone: twin the top-30 untwinned tasks, native
  statement lowering) keeps the pipeline shape: lex/resolve, parse, IR
  build, lower, emit+patch, splice, DCE, ELF — ~12 full-text walks, several
  still re-scanning the same bytes (`expr → expr_body → len_check → cops →
  fop2/fop3` re-walks every expression once per precedence level). At
  native speed each pass costs 1–2 c/B, so 12 passes ≈ **12–25 c/B** —
  3–5× short of 4.8 even with every task twinned.
- **Fuse-only** (items 6+7 alone: one token stream, pre-passes folded into
  the walk) gets the pass count to ≤4 (lex+resolve / lower / emit+patch /
  write) but each pass still runs through interpreted dispatch: ~1.5 µs per
  source line per pass ≈ **~40+ c/B** — the walk shape is right, the
  executor is wrong.
- **Both together**: ≤4 fused passes, each native → **~6 c/B**, and the
  remaining 6−4.8 ≈ 1.2 c/B closes with sa's tail tricks (register-cursor
  emission instead of byte-at-a-time `emit`, zero-copy name interning,
  3-write() ELF, bucketed hash with L1-sized caches).

Neither lever reaches 1.0× alone; the arithmetic requires items 5, 6 and 7
as one program. This is the committed ordering rationale for the Tier-1
increments: twins first (the railway exists and every twin is permanent,
compounding), token-stream wiring second (it changes what the walk reads),
fusion last (it changes the walk itself).



## 2026-11-03 (session 6, third landing): blob emitters emit8-packed (Tier-1 item 5b, emit-chain batching)

All four native blob includes (syntax 7,593 B, statements 4,321 B, emit 2,392 B,
uscan 2,439 B, plus the new cxread 27,833 B) now ship as `emit8:` compact groups
- one emit8() statement per 8 blob bytes instead of one emit() per byte
(44,578 -> ~5,600 lowered statements per self-compile, 8x fewer; the generator
verifies byte-equality against the old emit: rows before writing). Measured
A/B R=15: self 1.001 / x86ins 1.020 / all 0.992 - wall-clock neutral (the
emit-group statement lowering was already cheap), kept for the structural
8x reduction and the smaller includes. Certified `50276097…`: fixed point,
ALL GATES GREEN, 12/12 layouts.

## 2026-11-03 (session 6, second landing): 2-all-spliced join-chain fused (Tier-1 item 7, part)

The runtime+thread-exit splice was six join() calls, each recopying the whole
accumulated ~44 KB runtime buffer plus one intermediate per line piece.
`rt_splice_all(rt, need, sxe)` now builds it in one allocation with one copy
per piece (byte-identical content; join's 0/empty short-circuits only ever
skipped copies). Certified `e4e40d95…`: fixed point, ALL GATES GREEN, 12/12
layouts, A/B R=15 vs `1e2a6c46`: self 1.027 / all 1.013 / x86ins 1.008.
The phase bucket itself barely moves (-0.05 ms): its residue is the
lines_of_fast + nl_count_lines + sg_extra_ls descriptor scans over rt and
extra (three passes + a descriptor alloc per part) — the next fusion step
there is one combined pass per part.

## 2026-11-03 (session 6): the cx_read C port landed (Tier-1 item 5a, first blob)

`_sov_cx_read` is the twin-planted native port of the compact-form reader
(`tools/native_cxread.c` -> `compilers/linux/cxread_native.sov`, 27,833 B).
The measurement chain that shaped it: a 1:1 table-call port is perf-neutral
(the old compiled cx_read was already machine code); fusing the leaf scanners
is not enough (arrows stayed 0.515 us/line); the real pig was 165,525 indirect
helper calls per self-compile at ~321 cycles each — 87K list_add plus 33.8K
sg_cat5 + 33.8K sg_sp from the `emit:`-group token expansion. The landed fix
gives the blob its own bump arena and builds every fresh string inline
(cat2/4/5, sp, seg, cut, strip, toks content) with inlined list ops; only the
rarely-called alloc/transform helpers (sq2, ph, sub, pad3, digits, lists,
one, cmp, print, fail, lines_of) stay table calls. Certified `1e2a6c46…`:
fixed point, ALL GATES GREEN, 12/12 layouts, A/B R=15 self 1.037 / x86ins
1.014 / all 0.991 (in band); C1 self 26.2 -> 16.3 ms instrumented. Full
account: work/p4/SESSION_2026-11-03_S6_CXREAD_C_PORT_LANDED.md.

## 2026-11-03 (session 5): parallel path retested — fixed functionally, retired as default

The 2026-11-02 parallel forensics predate the ocgrow/emit3 patch fixes, so the
parked "parallel residual" was retested first thing under `fbacd190`:

- The parallel self-build now **completes, deterministically** (3/3 runs
  byte-identical, `a8a4d902…`, same 1,153,832 B size as the serial fixed
  point). The child-oc-collapse / SIGILL-product class is dead — it was the
  same defect family the patch fixes cured.
- The parallel product's **outputs are byte-identical** to the certified
  serial compiler's on hello / all.sov / x86ins, and run serially it
  **rebuilds the serial fixed point exactly** (`fbacd190`). The residual is
  confined to the parallel self-image bytes (layout divergence, not
  semantics).
- On this 2-core box the parallel path is **11% slower** (200.4 vs 180.0 ms
  median self-build; the 50/50 split's fixed cost).

Conclusion: a silently-on, slower, byte-divergent default is a hazard, not a
feature. **Serial is now the default; parallel is opt-in via `/tmp/sov_par`**
(par_setup inverted; the legacy `/tmp/sov_nopar` file is now meaningless and
harmless). The DCE caveat stands: never hard-park with a constant `pn: 0`.

Landed as `8e924765…` (2-generation fixed point in one shot, hello/all/x86ins
byte-identical vs `fbacd190`, tier gate GREEN, 12/12 layouts). Measured:
serial-vs-serial A/B R=21 = 1.003–1.009 (neutral by design); **default-path
A/B R=15 (no sentinel files, what a fresh checkout sees) = self 1.126 / all
1.148 / x86ins 1.253** — the removed parallel tax. Full account:
`work/p4/SESSION_2026-11-03_NIGHT2_SERIAL_DEFAULT.md`.

A fresh `sg_sq2`-twin evaluation closed the last small C1 candidate: only 67
of 12,279 self-source lines carry an apostrophe, so the sq2 path is cold;
the C1 pig is the cx_read state machine itself (dedicated-session C port,
~30 table callees).

## 2026-11-03: the patch bug is dead; both native twins are landed

The "patch/reloc misdirection" that parked the bw and u_scan twins was
root-caused as three stacked planted-twin defects (ocgrow twin's 1 MiB first
size; emit3 twin's grow path clobbering rdx — the third byte; forensic crash
traps + a fn-clobbering trampoline in tools/native_emit.c). All fixed.
Certified compiler `4c0ef593…`: fixed point, ALL GATES GREEN, byte-identical
outputs on every workload, 12/12 layout sweep stable, discipline pinned in
`tools/tier_gate.sh`. u_scan twin live: 3-scanned on all.sov 8.4 -> 0.8 ms.
Full account: work/p4/SESSION_2026-11-03_PATCHBUG_DEAD_TWINS_LANDED.md.
The tables below are retained history; the live table is work/PHASE_TABLE.md.

## Post-audit phase table (2026-11-01, ratcheted compiler 8a82e549…)

Fresh `--prof` runs on this date, one call each, instrumented totals. This supersedes
the 2026-10-22 table in §3 below. Changes since that table: the gen3 ratchet
(a1813483) plus three measured deltas on top — the native expression parser's node
capacity now matches its actual buffer (1.5n vs the artificial n, flipping a handful
of arg-dense spans into the syntax path), the parallel split moved from 60/40 to
50/50 of cumulative body lines, and prof-only decline-reason census instrumentation
(zero cost without `--prof`).

| phase | self (179.8 ms) | all.sov (69.0 ms) | x86ins (24.3 ms) | what it is |
|---|---|---|---|---|
| `bw` | 72.2 ms / 40.2% | 29.2 ms / 42.3% | 10.7 ms / 44.0% | per-task body statement codegen (interpreted lowering) |
| `W-walk0` | 29.2 ms / 16.3% | 7.6 ms / 11.0% | 3.5 ms / 14.4% | the task walk |
| `c0-parsed` | 23.1 ms / 12.8% | 5.4 ms / 7.8% | 4.2 ms / 17.4% | parse |
| `C1` | 15.9 ms / 8.9% | 4.0 ms / 5.8% | 2.2 ms / 8.8% | `pu_lines`, the line reader |
| `4-compiled` | 8.4 ms / 4.6% | 1.2 ms / 1.7% | — | final codegen |
| `p-stub` | 7.5 ms / 4.2% | 2.5 ms / 3.6% | — | `stub_diet` |
| `pu` | 7.0 ms / 3.9% | 4.8 ms / 6.9% | 1.3 ms / 5.2% | `pull_uses`, chunk loading |
| `2-all-spliced` | 5.3 ms / 3.0% | 3.1 ms / 4.5% | 0.5 ms / 2.0% | runtime + chunk + source splice |
| `3-scanned` | 3.2 ms / 1.8% | 8.5 ms / 12.4% | 0.3 ms / 1.2% | `u_scan` + `u_prep` |
| `pre-u` | 3.0 ms / 1.7% | 1.2 ms / 1.7% | 0.5 ms / 2.2% | pre-pass probe |

Decline census (2026-11-01, all.sov): 656 expression-tree attempts, 350 declines,
**100% of them spans whose quoted call arguments contain " is "/" or "/" and "** —
the legacy `cops` text-rewrite guard in the native lexer. Each declining span is
attempted twice (statement role-5 parse, then the expr path). The guard is
semantically load-bearing: the legacy path rewrites those strings and the accepted
artifacts encode that, so widening the grammar over them changes output bytes.
Measured on 2 cores: the wall-clock "all.sov regression" attributed to this
double-parse was actually the 60/40 parallel split; serial (1-core) gen3 was 8.7%
faster than gen2 while 2-core was 5% slower. The 50/50 split removed it: all.sov
56.9–59.7 ms (was 63.7 gen2 / 66.3–67.5 gen3), self 146–152 ms (was 167 gen2).
Known hazard, recorded: a transient parallel-child failure silently falls into the
parent's `rfrom` redo path, which can emit an artifact one page larger
(observed once, 322,096 vs 318,000 B; not reproducible across 10+ runs).

Final recorded A/B of this round (2026-11-01, `tools/ab_speed.py --runs 15
--allow-layout-diff`, medians, 2 cores): self **1.14×** (167.6 → 146.9 ms),
all.sov **1.12×** (62.4 → 55.7 ms), x86ins 0.964× (21.3 → 22.1 ms — the 50/50
split's fixed cost on a workload whose parallelizable share is small; a size-
adaptive split would recover it). Both bulk workloads now beat the installed
release outright.

## Parallel-merge bug: tight reproducer (2026-11-01)

The README "known open item" (parallel-path segfault during `par_merge`) now has a
three-line reproducer: add ANY task with an `emit:` group of ≥ ~232 bytes to
`compilers/linux/compiler.sov` — no native dispatch, no callers needed — and the
parallel self-build segfaults in the parent's merge (`pm` trace: crash right after
`M2`/`PB=0001`, i.e. in the hole/patch walk of `par_merge`, after `pm_init`). With
`--prof` or `/tmp/sov_nopar` (serial) the identical build succeeds. Existing large
`emit:` groups (the 8 KB syntax blobs) survive because their tasks land in the
CHILD's compile range; the same blob twinned into a parent-range task crashes.
This blocks shipping new native-task blobs (emit_nt_*) until fixed. A complete,
builder-verified native `u_scan` core was built for this round
(`tools/native_uscan.c`, `python3 tools/build_native_syntax.py --uscan` →
`compilers/linux/uscan_native.sov`, 2,429 B, no relocations/external symbols,
byte-exact mirror of the interpreted walk incl. the fused u_san equivalence
argument) and is ready to wire (`u_scan` wrapper + `u_scan_core` dispatch + the
include) the moment the merge bug is fixed; expected ≈ −8 ms on all.sov, −2.5 ms
on self. The 2026-11-01 x86ins "broken artifact" scare was a measurement error:
the artifact hash matches the session-start baseline exactly.


Measured 2026-10-22 against the tree as it stands. Every number below came from a
command run in this session; nothing is carried over from the older notes.

## 1. Do we match? No.

Cold, fully uncached, `tools/speed_gate.py` (its own harness, `--no-cache`,
`library/.prebuilt/` made read-only so no cache hit is reachable):

| workload | expanded B | sovren | sa | ratio | gap |
|---|---|---|---|---|---|
| `compilers/linux/compiler.sov` (self-compile) | 699,606 | 4.347 MB/s (161 ms) | 780.3 MB/s | **0.00557×** | 180× |
| `tests/all.sov` | 379,701 | 5.825 MB/s (65 ms) | 761.0 MB/s | **0.00765×** | 131× |

`sa` runs a 4,196,595 B assembly file in 5.4 ms. These are the only two
workloads where Sovren does real work, and both are ~2 orders of magnitude off.

## 2. The bigger problem: "everywhere" is mostly not translating at all

The speed question is undefined on most backends, because they do not compile.
Differential test — compile two deliberately different programs with each
backend and compare the artifacts:

```
program A: main: print 'ALPHA PROGRAM ONE'; q: 99; print q*3; print 'loop' 4 times
program B: zzz:  print 'BETA PROGRAM TWO'; w: 7;  print w + 100
```

| result | count | backends |
|---|---|---|
| **identical output for both programs** | **19** | 6502, 8051, aix, c166, dex, evm, ebpf, ez80, fuchsia, harmonyos, hexagon, hpux, jvm, pic16, pic18, plan9, qbe-ir, uefi, z80 |
| output tracks the source | 8 | arm64-mte, arm64-sve, arm64-sve2, cil, csharp, linux, llvm-ir, riscv64-be |
| errors out on ordinary programs | 5 | android, c-language, javascript, typescript, windows |

The 19 are placeholder writers. `ez80` and `z80` both emit the same 17 bytes for
any input:

```
21 10 00 7e b7 28 06 32 00 f0 23 18 f6 3e 00 76 00
```

That is a hardcoded Z80 demo loop — `ld hl,0x10; ld a,(hl); or a; jr z; ld (0xf000),a; inc hl; jr; ld a,0; halt` — with no relationship to the source. `evm` emits 3 bytes (`60 00 00` = `PUSH1 0`) for every program ever given to it. `plan9` emits 48, `pic16` 24, `6502` 22.

They report success (`rc=0`, "wrote") and they are fast (0.2–1.5 ms) **because
they emit a constant**. Their translation speed is not a speed; it is zero work.

A 7-line `tests/hello.sov` (two strings, arithmetic, `if`/`else`, a loop)
compiles to 968 B of real ELF on `linux` and to 17 B on `ez80`.

Separately: `arm64-sve`, `arm64-sve2`, `arm64-mte` and `riscv64-be` all print the
banner `linux-riscv64-v: wrote`. The artifacts differ (AArch64 vs RISC-V ELF
machine IDs are correct), so these are feature variants of one code generator,
but the banner is wrong on all four.

## 3. Where the time actually goes (x86-64 linux, fresh `--prof`)

177 ms instrumented of ~215 ms wall:

| phase | ms | share | what it is |
|---|---|---|---|
| `bw` | 88.8 | **50.1%** | per-task body statement codegen, 745 marks |
| `ZZ` | 21.7 | 12.2% | the main parse loop |
| `C1` | 14.3 | 8.1% | `pu_lines`, the line reader |
| `5a-flat0` | 9.8 | 5.5% | ELF emission, relocations |
| `3-scanned` | 8.7 | 4.9% | `u_scan` + `u_prep`, the unsafe pre-pass |
| `p-dce` | 7.7 | 4.3% | `prune_dead` |
| `c0-parsed` | 7.3 | 4.1% | parse bookkeeping |
| `pu` | 5.7 | 3.2% | `pull_uses`, chunk loading |
| `4-compiled` | 5.7 | 3.2% | final codegen |
| `2-all-spliced` | 3.4 | 1.9% | runtime + chunk + source splice |
| `f1-spliced` | 1.8 | 1.0% | `splice_inc` |

Half the compile is one interpreted loop emitting one task body at a time.

## 4. The arithmetic that sets the target

```
sa      4,196,595 B in 5.4 ms  =  7.40 cycles per byte
sovren    699,606 B in 161 ms  = ~481 cycles per source byte
554,657 dynamic calls / 376,188 source bytes = 1.47 calls per source byte
181.1M cycles / 554,657 calls                  = 326 cycles per call
```

`sa`'s entire budget is **one function call per 44 source bytes**. This compiler
makes **one call per 0.68 source bytes**. Matching `sa` is not "make each call
faster" — it is a **~65× reduction in call count**. That number has not moved
materially and is the whole problem.

## 5. What is needed

### Tier 0 — make "everywhere" measurable at all (blocking, and the largest single item)

1. **Turn the 19 stub backends into real compilers.** Until each one implements
   the language, its speed is undefined. This is not a performance task; it is
   the completion task, and it is bigger than everything in Tier 1 combined.
2. **Fix the 5 backends that error on ordinary programs** (android, c-language,
   javascript, typescript, windows).
3. **Fix the target banner** so `arm64-sve`/`sve2`/`mte` and `riscv64-be` stop
   announcing themselves as `linux-riscv64-v`.
4. **A versioned language contract plus a conformance corpus**, so "matches sa"
   can be checked per cell instead of asserted. `PLAN.md` already scopes this:
   one contract, one corpus, reused by every backend, with unsupported features
   reported as red rather than skipped-to-green.

### Tier 1 — close the gap on the one backend that works (x86-64 linux, 131–180×)

Ordered by measured share of the remaining time:

5. **Parse once into a token stream and walk it.** This is the structural lever.
   Today the same expression text is re-scanned once per precedence level
   (`expr → expr_body → len_check → cops → fop2/fop3`), each doing its own
   `_sov_find_text` scan, and every token is materialised as a fresh substring
   via `cut` (84,690 calls). One token stream removes both the re-scanning and
   the substring allocation.
6. **Replace the codegen interpreter with generated native code.** `bw` is 50%
   of the compile and it is interpreted dispatch per statement. Nothing else
   reaches 65×.
7. **Fold the pre-pipeline passes into the single parse.** `3-scanned` (8.7 ms),
   `p-dce` (7.7 ms) and `pu` (5.7 ms) are three more full-text walks over the
   same source, plus `2-all-spliced` and `f1-spliced`. One pass that produces
   the token stream can serve all of them.

### Tier 2 — already tried, measured, and closed. Do not re-attempt.

| attempt | measured result |
|---|---|
| SWAR `_sov_strlen` | 1.003× — noise, reverted |
| `_sov_starts_with` codegen inline | crashed at scale, reverted |
| `_sov_find_text` native inline (481 B) | crashed nondeterministically, shelved |
| `sg_ind` inline | **0.832× — 17% slower**, reverted |
| peephole / copy propagation | 27,906 static copies × 0.095 ns each (x86 rename eliminates them) = low single digits, not the 8% the static count implies |
| `cops` guards | 0.946× regression |
| line-level memoisation | dead — identical lines cost the same as unique lines |
| `ih_slow` small-list fix | 1.008× best / 1.031× median — the one that landed |

Hard-won constraints for any future inline work: a sequence may touch **`rax`
and the argument registers only** — `rcx`/`rdx` are not safe and clobbering them
corrupts argv parsing; a bare `ret` inside an inline pops a garbage return
address (inlines have no call frame); and hand-assembled jump offsets must come
from `as` and be diff-compared, because a probe can pass while the self-compile
SIGILLs.

## 6. The honest framing

`sa` is a single-pass assembler with a flat symbol table. Sovren parses a
high-level language and performs scope and name resolution, control-flow
analysis, dead-code elimination, relocation and ELF writing. Bytes/second across
two different languages is diagnostic, not proof of equivalent frontend work —
`PLAN.md` says exactly this. "Match `sa`" is a self-imposed target, and reaching
it means making Sovren's front end cost as much per byte as a single-pass
assembler's.

So the answer to "what is needed to match `sa` everywhere" is: **finish 19
backends that currently emit a constant, and replace the front end with a
single-pass token-stream design.** The first is a completeness project. The
second is a rewrite, not an optimisation pass — no tuning of the current
interpreter gets within 65×.

---

## Fleet-wide conformance (added after the audit)

Two things the original audit could not see, both found by rebuilding every
backend from its own source:

**1. 26 of 32 installed backend binaries were stale.** They had been built from
older sources. `compilers/csharp/compiler`, for example, emitted
`; Sovren LLVM IR subset` while its own source is a C# emitter. All 29 buildable
backends were rebuilt and reinstalled; `android` and `windows` do not build
from source at all.

**2. The `main:` removal silently broke 27 of 32 backends.** Every backend
source defines its driver as a task named `main`, but only 5 of 32 define it
*first*. Under the new positional entry rule the entry became a helper task
(`at8 o v`, `emit s`, `w64 o v`) instead of the driver, so the backends ran the
wrong code and produced nothing. The driver was moved to the top of the 22
sources that needed it; the other 5 already had it first.

Neither of these was a translation-speed problem. They are the reason "every
backend" could not be measured honestly before.

**Measured state now, with fresh binaries and a corrected corpus:**

| category | backends |
|---|---|
| fully working (17/17 constructs, execution verified) | `linux` (x86-64) |
| real translators, some constructs missing | `common-intermediate-language`, `csharp`, `llvm-intermediate-representation` |
| emit a constant, ignore the input | 23 backends |
| error out | `android`, `c-language`, `javascript`, `typescript`, `windows` |

The 23 constant emitters are the real blocker for parity. `ez80` and `z80`
emit a hardcoded 17-byte Z80 demo loop for any input; `evm` emits `PUSH1 0`;
`arm64-mte`/`arm64-sve`/`arm64-sve2`/`riscv64-be` are compile-time *evaluators*
that run a task named `main` at compile time and emit only its value as the ELF
exit code.

Translation speed is therefore **defined on one target only**. Every parity
number in this document is an x86-64 number.

---

## Dead-flag purge (completed)

The "silently swallowed flag" was `library/driver_compat.sov`'s `sd_recompile`
task. It forked the compiler and re-exec'd it with a rebuilt argv that stripped
`--usestate/--mkstate/--usepfx/--pfxlearn/--learn/-o` and then **injected**
`--no-replay`, `--no-pfx`, `--no-learn`. The real parser never saw them, which
is why they appeared to be accepted. It is deleted, along with every other
cache/state/learn/sugar path it served.

Verified: **zero** occurrences of any of
`--no-cache --no-learn --uncached --no-lsug --no-pfx --no-replay --serial-sugar
--parallel-sugar --emit-ir --mkstate --usestate --pfxlearn --usepfx --mksug
--mksuguser --mksugrt --slice --timing --reproducible --audit-privacy --cache
--learn` in any `.sov` source. Unknown flags are rejected; the real flags
(`--flat --prof --bare --plain --release --unsafe --kernel --sxe --sxe-compact
--run --fmt -o`) still work. The linux backend lost 16.6 KB of dead code and
the self-compile fixed point moved 585520 -> 568904.

## Where the translation-speed gap actually is

Measured on self-compile of `backends/native/linux/compiler.sov`
(680,585 B expanded, 25,343 lines, 741 tasks):

| phase | share | what it is |
|---|---|---|
| `bw` | 45.0% | the per-task statement interpreter (`body`), 738 calls |
| `ZZ` | 13.5% | line walk that splits the source into task bodies |
| `C1` | 8.5% | `pu_lines` |
| `3-scanned` | 5.9% | `u_scan` / `u_prep` |
| `5a-flat0` | 5.0% | post-pass |
| `c0-parsed` | 4.8% | parse |
| `pu` | 4.4% | `pull_uses` |
| `p-dce` | 3.9% | `prune_dead` |

Two structural facts, both measured rather than guessed:

**1. 640 of 741 tasks are interpreted; only 104 get a native fast path.**
`try_native_body` can emit hand-written x86 for a task instead of interpreting
it, and it does so for 104 tasks (1,350 code lines). The other 640 tasks
(23,077 code lines) go through the interpreter. The 25 largest interpreted
tasks hold 41% of all interpreted lines.

**2. `call_args` is a 107-entry linear `_sov_str_eq` chain and it runs
16,335 times per self-compile.** That is ~1.75 million string comparisons in
one phase. Replacing the chain with an integer hash test (`nh: nhash(name)`
once, then `if nh is <constant>`) measured **1.20x / 16.9% faster** — but the
resulting compiler could not compile itself, because `nhash`'s body is not
compilable in this build (it is reached only through the `emit_nt_nhash`
native path, never as interpreted source). That change was reverted; the
verified state is the 568904 fixed point.

So the gap is not a few slow functions. It is that 86% of the compiler is
interpreted at roughly 2.8 us per source line, and `sa` is a hand-written
assembler. Closing the remaining ~190x means giving the other 640 tasks native
paths — i.e. replacing the codegen interpreter with generated native code.
That is a rewrite of the code generator, not a tuning pass, and no amount of
tuning the current interpreter reaches it.

## 2026-11-04 (session 8): dce family + kgrow_ht are native

Certified `df77a7e0…` (installed). The dead-code elimination family —
`dce` (reachability + compaction + string-pool GC), `dce_stores`,
`dce_litter` — and the kid-intern rehash `kgrow_ht` now run as planted C
twins (tools/native_dce.c, native_dstores.c, native_dlitter.c,
native_kgrow.c -> dce/dstores/dlitter/kgrow_native.sov). A/B R=21 vs the
session-7 certified `cdf6f98e`: self 1.021-1.028x, all.sov 1.025-1.028x,
x86ins 0.999-1.008x. Phase table: p-dce 0.8 ms, p-post 0.0 ms (the dce
buckets collapsed). Fresh census: 115 twinned tasks. The remaining
structural mass is unchanged: the walk core (body/stmt/compile, the bw +
W-walk0 buckets = 60% of self), the token-stream parse-once (item 6),
and the cx_read blob residue (6.2%). Full account:
work/p4/SESSION_2026-11-04_S8_DCE_FAMILY_KGROW_TWINS.md.

## 2026-11-03 (session 4, night): Tier-2 sweep — what closed, what measured dead, what remains

Certified compiler after this session: `fbacd190…` (ratchet lineage below).
Fixed point verified, TIER GATE GREEN (all six stages, now including the
new `tools/rt_baked_sync.py` stage-2 check), 12/12 layout sweep, pairs
qualified (exit7 2.55 / sum 2.68 / calls 6.07 ms vs sa 0.64/1.16/1.00).

### Closed with measurement (no code needed)

- **Item 10 (decline path / grammar gap): CLOSED.** Fresh census on the
  certified compiler: self-compile declines **0** (824/824 expression trees
  native, 57,075/57,075 statement trees native); all.sov declines **14**
  (missing-paren, 2.2% of attempts — genuinely legacy-path spans). The
  2026-11-01 census (350 declines, 100% cops-guard) describes a state that
  the grammar-widening rounds since then eliminated. "Half of all.sov pays
  twice" no longer holds; the double-parse residue is ~14 spans.
- **Item 11 (launcher exec-without-fork): ALREADY DONE.** `launcher.sov`'s
  `lc_exec` chmods then calls `syscall(59, …)` (execve) directly — the
  launcher replaces itself, no fork. Verified working from the tree root.
- **Item 9 "direct 3-write() ELF": effectively done.** write_elf flushes
  through wbuf in 64 KiB chunks: 8 writes for the 518 KB self artifact,
  1 write for tiny artifacts. Coalescing to exactly 3 saves ≤7 syscalls
  (~10 µs) — not worth any output-layout risk.

### Measured and deliberately NOT landed (the bake-in lesson)

- **rt_baked as primary runtime source: NET-NEGATIVE, reverted.** The
  baked payload was REGENERATED from the current runtime.sov (it was stale:
  40,184 B vs 43,642 B — a latent correctness bug in the fallback), and the
  load order was flipped baked-first. A/B (R=12): x86ins 0.961, all 0.980,
  self 0.987 — the base64 decode (~160 c/B interpreted, ~2 ms) costs an
  order of magnitude more than the open+read it eliminates (~0.15 ms), and
  the latency pairs never load the runtime at all (`need is 0` on
  exit7/sum/calls). An emit-group blob instead of base64 would sugar into
  43,642 `emit(N)` statements in the self-compile parse — strictly worse.
  Landed instead: the fallback is now exactly in sync (rt_baked_sync gate
  in tier-gate stage 2), and the measurement is recorded in-source at the
  load site. `scripts/regen_rt_baked.py` regenerates it.

### Fresh targeting data for the remaining Tier-1 work (items 5/6/7)

Corrected fnmap sampling (the earlier session-4 map was one generation
stale — attribute via `work/p4/compiler.fnmapg1` only):

- **Self-compile, integrated (top of a smeared distribution — no single
  pig):** `_sov_list_add` 4.5%, `_sov_strlen` 4.4%, `_sov_str_eq` 4.1%,
  `collect_body` 3.2%, `syntax_build` 2.8% (inside the native blob),
  `_sov_strcat` 2.8%, `cfind1` 2.8%, `_sov_find_text` 2.2%, `dce` 2.1%,
  `cx_info` 2.1%, `_sov_med_try` 2.0%, `syntax_statement_build` 2.0%,
  `cut_full` 1.8%, `st_build` 1.8%, `lines_of_fast` 1.8%, `lb_words` 1.7%,
  `cx_read` 1.6%, `fl_span_tally` 1.6%, `strip_span` 1.6%.
- **C1's true cost is the cx_read family (~6–7% ≈ 12 ms), not
  lines_of_fast:** `sg_plain(compiler.sov)` returns 0 (the source mentions
  compact forms), so the descriptor reader runs: `cx_read` + `cfind1` +
  `cx_info` + the per-line bypass. A cx_read C-blob twin is the single
  biggest tractable win in the C1 bucket and sits in the proven
  u_scan idiom, but its output IS the parser's input line list —
  semantics-critical, dedicated-session scope.
- **Tiny-path floor (2.4 ms, tiny0 19 B):** `_sov_bzero` 13%, kernel
  12.8%, `_sov_strcat` 8.9%, `_sov_list_add` 8.6%, `rt_heap` 5.9%,
  `main` 5.3%, `_sov_list_new` 4.9%, `gn_sync` 4.8%, `pull_uses` 4.7%,
  `compile` 4.4%, `sx_tbl_init` 4.2%, `st_build` 4.0%, `sx_arg_str` 4.0%,
  `_sov_med_try` 3.5%. The floor is ~10 phases × interpreted fixed setup
  — the same twins/walk work as the bulk lanes (there is no separate
  lazy-init shortcut that stays decision-identical: the machinery calls
  ARE the floor). The allocator paths (rt_heap/med_try/bzero churn:
  150 mmap + 425 mprotect on self) live in runtime.sov and are frozen by
  the byte-identical gate.
- Phase table (self, instrumented): bw 72.0 ms/39.4%, W-walk0 31.7/17.3%,
  c0-parsed 22.6/12.4%, C1 17.4/9.5%, p-stub bucket (really dce) 7.8,
  4-compiled 7.3, pu 7.0, 2-all-spliced 5.5, pre-u 3.8, 3-scanned 2.5,
  5a-flat0 2.2.

### Ratchet lineage

    d96aaf91 (session 3 certified)
      -> fbacd190 (rt_baked regenerated+synced, stray "-o" artifact removed;
                   bake-in-first measured and reverted with data recorded)
    Each step: 2-generation fixed point, hello/all/x86ins byte-identical
    vs the pre-session certified compiler, tier gate green on the final
    state (A/A needed one retry, within band), 12/12 layout sweep stable,
    pairs qualified, final A/B R=21: x86ins 1.009 / all 1.000 / self 1.003
    (the landed round is behavior-neutral by construction when the disk
    runtime exists; the win is the corrected fallback + the gate).

## Session 7 (2026-11-04): the walk-twin triplet + the allocation lesson

Three walk-side C twins landed through the full discipline:
**collect_body** (per-loop body collector, blob 1,349 B), **st_build**
(statement-table graph builder, 3,222 B), **lord_build** (register-home
seeding line pass, 3,723 B). Certified `cdf6f98e…` installed; per-landing
A/Bs: collect 1.042×/1.053×/1.000× (self/x86ins/all, R=15), st_build
increment 1.011×/1.017×/1.010× (R=15), lord increment 1.014×/1.002×/1.002×
(R=21). Session combined ≈ 1.069× self / 1.074× x86ins / 1.012× all vs
`50276097`. Census now 112 twinned / 961 untwinned (95.7%).

**The measured lesson that unlocked it:** the first collect_body twin was
neutral because its per-call exact-size output-list `_sov_heap_alloc` (and
a per-call arena chunk in the first cut) WAS the cost — one RIP held
2,265/2,291 in-blob samples. A persistent interpreter-side `[arp][are]`
arena block (fetched once per call through the table, the cx_read v4
allocation-invisibility proof covering the content question) took
_sov_collect_body from 2.99% to 0.07% of samples. st_build and lord_build
were built on that model from the start. Two correctness notes for every
future twin: (1) Sovren integer comparisons are SIGNED — a C blob must
compare block_end-style answers as long long (-1 answers exist);
(2) fixed-point chains must be rebuilt from the certified compiler when a
blob changes mid-chain (a v1→v2 chain showed a divergent intermediate;
the clean chain reproduced the same terminal fixed point).

**Measured and skipped with data (do not re-walk):** the 5b wrapper twins
(syntax_fast_assignment 0.12% + syntax_fuse_tree 0.26%; their emitters are
already native — cset 0.01%, rax_imm 0.03%, storev 0.02%, emit-chain total
1.53%); the cx_read blob tail (sg_sq2+sg_lists+sg_one+sg_cmp+sg_ph+sg_sub+
sg_digits table calls = 0.55% — the C1 residue is inside the blob's own
state machine). Also recorded: the fnmap sampler's PTRACE_INTERRUPT stops
cluster at kernel boundaries, inflating "self" shares of table-calling
blobs (st_build reads 2.75% in the fresh profile; the A/B medians are the
claim-grade truth).

Fresh left-list (census + fnmap ordered, certified cdf6f98e):
- The walk core: body (1.3%) / stmt (1.0%) / compile (0.7%) / try_*
  cascade — the 535-611-line interpreters, dedicated sessions.
- dce (1.9%) + dce_stores (1.1%): 266-line port over the patch records.
- inl2_one (1.2%): output-global surgery.
- Item 6 (token-stream parse-once; tk_lex oracle cx86_p1.sov:3515):
  still THE structural lever — c0-parsed 19.8 ms + the string-rebuild
  pigs collapse together.
- Item 7 remainders: pull_uses spans (pu 6.8 ms), 5a-flat0 (1.9 ms),
  2-all-spliced residue.
- Tier 2 pairs: unchanged (tiny sources never reach the walk twins; the
  floor is the same twins/walk work).

### Ratchet lineage (appended)

    50276097 (session 6)
      -> 58c804e4 (+ collect_body twin)
      -> ae7a437e (+ st_build twin)
      -> cdf6f98e (+ lord_build twin)  <- installed

## 2026-11-04 (session 9): the flor_range decomposition — where W-walk0 actually goes

Two landings (intern insert paths, +1%; scanner wrapper twins, neutral — the
wrappers were already thin, re-confirming the emit_nt_look lesson). Certified
`1666c43d`. The session's real finding: probe marks inside flor_range split
the 28.7 ms W-walk0 bucket exactly — **inl2_scan 11.9 ms + licm_scan 4.0 ms
(interpreted, ~600 lines in cx86_p6.sov, the next big C-blob port) +
_sov_lord_build 10.8 ms (native, real work) + 2.5 ms preamble**. Full account:
work/p4/SESSION_2026-11-04_S9_INTERN_SCANNERS.md. Four planted-twin byte bugs
caught by the ratchet before landing; scripts/verify_twins.py now
disassembles every new emit-byte run from the source before any build.
Measured path from ~163 ms to 100: inl2/licm ports (−10..13), c0-parsed
twin/item 6 (−12), item 7 fusion (−5), bw grind (−8), C1 residue (−3),
item 6 token stream for the rest — each dedicated-session scope.

> **C.19 re-census (schema 8, 2026-11-08).** The tier-0 counts above
> ("23 constant emitters / 5 error backends") came from the original backend
> directory listing, not from an equal-shape differential. `tools/emitter_regression.py`
> re-froze 155 driver behaviours on **equal-length** inputs (`print 111111` /
> `print 222222`) and classifies **122 translating, 4 constant, 0 error, 29
> lineage-pending**. `z80`/`ez80`/`evm` embed the input literal; JS/TS translate;
> `arm64-mte`/`sve`/`sve2`/`riscv64-be` are compile-time evaluators that emit the
> value of `main` as the ELF exit code. `android`/`windows` are among the 29
> unbuildable lineage drivers, not error backends. The gate reports **0
> classification + byte-behaviour changes** against its frozen snapshot
> (`tests/gates/emitter_regression.json`). Both counts are preserved: the historical
> census is the directory-level view, the re-census is the measured, shape-controlled
> view. Translation speed is still defined on the x86-64 `linux` target only.

---

## 2026-11-08 refresh (v3.0.0 + schema-9 re-verification)

This document's older numbers are **dated history**, not the current state.
Re-derived from files this run:

- Installed compiler md5 `be20f64258d4a7a91d5c46e07d64be70`, 1,856,552 B;
  fixed point OK; oracle 24 pass / 16 refuse-parity / 0 FAIL.
- **19 PASS / 0 FAIL** gate sweep (`evidence/C4_gate_sweep_19.txt`).
- C.29 **2,957/2,957** vs control AND vs the **original `4162d364…`** binary
  (`evidence/C29_differ_original_c4_full.json`).
- **36/36 GREEN** mode/flag differential (`evidence/C36_mode_flag_c4.json`).
- C.26 flag-surface overclaim fixed: per-flag candidate-vs-control comparison
  with one shared `-o` path; modes are NOT byte-identical to each other.
- Fresh R=21 placebo on the new hash: **INSIDE the band → no credible win**
  (`evidence/C33_placebo_self_be20.txt`, `C33_placebo_x86ins_be20.txt`).
- Full per-cell paired gate built (`tools/paired_cell_gate.py`): **0/24 GREEN**,
  execution checked after every translation, `--flat` cells FAIL as
  `NOT_MATCHED_WORK`. A previous 4/24 figure is withdrawn.
- C.30 fleet still **126/155 build, 29 lineage-pending**; C.27 **1/16 GREEN**.
- `agent/completion_gate.py` = **10/14 PASS -> NOT DONE**. Four RED semantic
  gates remain. **No parity or completion claim.**
- Extension v3.0.0: `bash arena-auto-continuation/verify.sh` = ALL CHECKS
  PASSED, ZIP 6,470 B / 6 files, not installed in any browser.

Full current ledger: `arena-auto-continuation/REMAINING.md` and
`dl/sovren/work/saparity/SA_PARITY_EVERYTHING_NEEDED.md`.
