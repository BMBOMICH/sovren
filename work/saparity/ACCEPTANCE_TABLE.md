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

# C.20–C.27 acceptance table — schema 9 (2026-11-08), compiler `be20f642…`

> **Schema 9 (current).** Installed md5
> **`be20f64258d4a7a91d5c46e07d64be70`**, 1,856,552 B; `compiler.sov` 413,966 B
> / 13,321 lines. C.4/C.6 in-run memoisation only. Gate sweep **17/0**,
> C.29 **2,957/2,957**, fixedpoint g1==g2==g3, oracle **24/16/0**.
> **Changed vs schema 8:** C.22 is now **GREEN** — ×1.00 LINEAR with 8 MB OK
> (3,276.38 / 3,482.09 ms). C.27 remains **1/16 GREEN**, C.30 remains
> **126/155 + 29 lineage-pending**, and every C.20–C.25 speed cell remains
> **RED** (fresh min-of-9 cold bench). The detailed tables below were measured
> on schema 8 (`727c1e6d…`) and are retained as **dated history**; they are not
> the current per-cell verdicts. Global completion is **NOT met**: a fresh
> per-cell paired gate (upper 95% latency ratio ≤ 1, lower throughput ratio ≥ 1)
> does not exist yet. Machine-readable current baseline:
> `baseline_frozen.json` (schema 9).

Semantics first. **Nothing here is a parity claim** (C.39). Global completion is
**NOT met**: every speed cell C.20–C.25 is RED and 15/16 C.27 cells are RED.

Host: `e2b.local`, Linux x86_64, 2 CPUs, 1982 MiB RAM / 0 swap, Asia/Baku.
SA reference `sovren-assembler/sa` 83,500 B, self-assembly byte-identical,
positional `argv[2]`. Cold processes only. Expansion/emission accompany the
numbers (C.34); input-byte rates are diagnostic only for cross-language
comparisons.

Installed: md5 `727c1e6dab7e947eadec4325bb11f43e`, 1,856,536 B; `compiler.sov` 413,966 B / 13,321 lines / **22** `*_native.sov` twins. Fixed point
`62c36d16…` → `af588916…` → `647bc0e9…` → `9f1af7c8…` → `5dff58ce…` → `d7f19ed4…` →
`f2672d8b…` (fused `_sov_base_scan`) → `727c1e6d…` (freed growers) — every step converged
g2==g3 before install; the final build converges from gen 1.

## Gates on this binary

| Gate | Result |
|---|---|
| Fixed point / 2-gen self-host | `FIXED POINT OK`, `727c1e6d…` (g1==g2==g3==installed) |
| Oracle | 24 pass / 16 refuse-parity / 0 FAIL |
| Executed semantics / exec gate | PASSED |
| Tier gate | GREEN (3/3 after the C.32 A/A retry fix; 1 transient noise failure before) |
| 12 layouts (`tools/layout_check.py`) | 12/12 byte-identical + semantics-identical |
| C.31 front-fusion fixtures | 20/20 |
| C.31 `sg_extra_ls` sugar fixtures | 12/12 |
| C.31 fused `src_base` fixtures (`tools/basescan_fixture_gate.py`) | **16/16 identical** |
| Gate sweep | **17 PASS / 0 FAIL** |
| C.26 flag surface | 14/14 |
| Anti-cache / no-cache tripwire | 5/5 / OK (0 sidecars) |
| C.30 fleet (`compilers/shared/*` edited, re-run) | **155/155 rows, 126 build, 29 lineage-pending WITH marker, 0 unmarked / 0 skipped — NOT green (29 absent cells fail global completion)** |
| C.22 scaling (re-run) | **×1.41 NONLINEAR (gate ≤1.20), 8 MB OOM rc −9 — NOT green** |
| C.27 shape axis (re-run, N=40,000) | **1/16 GREEN — NOT green** |
| C.18 serial default | GREEN (1 dormant fork behind `pm_ptf`, 0 children, 0 sentinels) |
| C.19 emitter regression | GREEN (155 drivers frozen, 0 behaviour changes) |
| C.29 differ harness (`tools/differ_gate.py`) | **2,957/2,957 identical** vs pre-session `d7f19ed4…` AND vs original `4162d364…` |
| C.33 placebo A/B R=21 (self / x86ins) | B inside band, **no speed win** (self +0.09%/−0.01%; x86ins +0.01%/+0.11%) |
| Syntax / manifest | ALL_OK / 1,419 files, **0 missing, 22 intentional changes** (the `--fmt` mode cell of an early differential briefly stripped the trailing newline from 6 sources; all 6 were restored byte-for-byte from `mf_manifest.json` and the oracle / 2,957 differ / fixed point re-passed) |

## C.20–C.25 (fresh min-of-9 cold, same-session SA)

| Cell | Workload | Input B | Sovren | SA ref | Verdict |
|---|---|---:|---:|---:|---|
| C.20 | tiny-30B | 31 | 846 µs / 0.04 MB/s | 344 µs (interleaved min-of-21 floor 211 µs) | **RED** |
| C.20 | floor-hello | 191 | 907 µs / 0.21 MB/s | 344 µs | **RED** |
| C.20 | tiny-bare-28B | 28 | 800 µs / 0.04 MB/s | 344 µs | **RED** |
| C.21 | bigint | 5,253 | 0.66 MB/s | ~102.0 MB/s | **RED** |
| C.21 | tls | 78,193 | 3.08 MB/s | ~102.0 MB/s | **RED** |
| C.21 | suite | 199,276 | 4.35 MB/s | ~102.0 MB/s | **RED** |
| C.21 | x86 | 43,446 | 2.54 MB/s | ~102.0 MB/s | **RED** |
| C.22 | vars4m | 3,966,680 | 9.45 MB/s | 102.0 MB/s | **RED** |
| C.22 | loc100k | 1,777,799 | 8.99 MB/s | 102.0 MB/s | **RED** |
| C.22 | fns1m | 950,689 | 5.90 MB/s | 102.0 MB/s | **RED** |
| C.23 | deepfns | 92,073 | 7.38 MB/s | 102.0 MB/s | **RED** |
| C.24 | self-compile | 413,187 | 1.76 MB/s | 102.0 MB/s | **RED** |
| C.25 | `tests/all.sov` / `x86ins.sov` | 51 (385,891 expanded, 318,000 emitted) / 42,322 | `speed_gate.py` old 6.6 / new 6.5 ms, delta −0.4% | 77–91 MB/s expanded | **RED** |

`cold_gate.py --scaling`: **×1.41 NONLINEAR** (gate ≤1.20) over 0.25–4 MB;
8 MB cell **FAIL (OOM-killed rc −9)** on this 1,982 MiB / no-swap host for
both the current and previous certified binaries. `×1.41` is not a win.

## C.26 — identity and refusal parity: GREEN

40 differential cells old-vs-new byte-identical, 12/12 layouts + one-char
edits, 14/14 flag-surface cells. Accepted modes (`default`, `--flat`,
`--bare`, `--prof`, `--unsafe`, `-o`) produce the same bytes as the previous
certified compiler for the same mode. `--mkdsug`, `--uncached`, `--no-ac`,
`--no-learn`, `--serve`, `--warm`, `--cache`, `--state` are **explicit
refusals** (`Error: unknown flag …`, rc=1, zero-byte/no artifact) — never
accepted no-ops. No `.plk/.ac/.ac.bin/.lsug/.sug/.dsug/.state/.deepoc` exists.
Evidence: `evidence/C26_flag_surface.json`, `evidence/C29_layout_check.json`.

## C.27 — SA's 12-shape axis in Sovren-equivalent semantics

`tools/shape_gate.py`, N = 40,000 lines per shape, min-of-5 cold, semantics
validated before timing (SA rc=0 + nonempty ELF; Sovren rc=0 + nonempty ELF
+ executed exit 0). Both sides generated at the same line count. Emitted
bytes show Sovren's dead-code pruning: these are **front-end/parse throughput**
cells, not emitted-code-equivalent cells — recorded as a harness limitation,
not hidden. Verdict requires Sovren latency ≤ SA and throughput ≥ SA.

| Shape | Input B (SA / Sovren) | Expanded B (Sovren `--flat`) | Emitted B (SA / Sovren) | MB/s (SA / Sovren) | Throughput ratio | Latency ratio | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| comment-only | 2,000,092 / 2,160,019 | 2,160,084 | 4,108 / 496 | 2381.50 / 48.77 | 0.0205× | 52.74× | **RED** |
| nop | 320,092 / 360,019 | 360,084 | 44,108 / 496 | 200.01 / 14.90 | 0.0745× | 15.10× | **RED** |
| mov-rax-rbx | 680,092 / 360,019 | 360,084 | 124,108 / 122,896 | 257.54 / 13.11 | 0.0509× | 10.40× | **RED** |
| db-0 | 360,092 / 360,019 | 360,084 | 44,108 / 496 | 312.17 / 15.14 | 0.0485× | 20.62× | **RED** |
| label-only | 360,092 / 880,019 | 880,084 | 4,108 / 496 | 127.23 / 6.42 | 0.0505× | 48.40× | **RED** |
| jmp-backward | 1,000,101 / 1,560,019 | 1,560,084 | 84,108 / 761,872 | 115.26 / 5.55 | 0.0481× | 32.40× | **RED** |
| jmp-forward | 1,000,101 / 1,560,019 | 1,560,084 | 203,916 / 761,872 | 142.44 / 5.56 | 0.0390× | 39.96× | **RED** |
| long-labels | 2,440,092 / 3,040,019 | 3,040,084 | 44,108 / 496 | 0.15 / 10.70 | 70.4865× | 0.02× | **GREEN** |
| times-dup | 680,092 / 1,320,019 | 1,320,084 | 164,108 / 496 | 127.94 / 11.54 | 0.0902× | 21.52× | **RED** |
| expr-heavy | 1,080,092 / 840,019 | 840,084 | 284,108 / 1,482,784 | 103.62 / 10.30 | 0.0994× | 7.82× | **RED** |
| label-nop | 680,092 / 1,240,019 | 1,240,084 | 44,108 / 496 | 149.39 / 6.15 | 0.0411× | 44.32× | **RED** |
| equ-const | 577,872 / 697,799 | n/a | 0 / 0 | n/a | n/a | n/a | **RED (semantics not validated)** |

`equ-const` at N=40,000 hits SA's hard `CT_N=1024` cap
(`sa: too many names to remember` at the 1,025th `equ`, rc=1, no output):
a documented unsupported construct (C.28), so the cell is absent and fails
C.39. `long-labels` is **not** a parity win: SA's fixed 65,536-slot symbol
table degenerates to 15.9 s on 40,000 × 60-byte names while Sovren takes
0.27 s. One green lane is not a parity claim (C.39).

### Cliff probes (exact sizes from §2.8, min-of-5 cold)

| Probe | Input B (SA / Sovren) | SA min | Sovren min | Slowdown | Verdict |
|---|---:|---:|---:|---:|---|
| 200k-labels | 1,800,092 / 4,400,019 | 22.88 ms | 767.24 ms | 33.5× | **RED** |
| 400k-labels | 3,600,092 / 8,800,019 | 56.20 ms | 1552.37 ms | 27.6× | **RED** |
| 4MB-nop | 4,000,092 / 4,500,019 | 13.76 ms | 258.72 ms | 18.8× | **RED** |
| 200k-fwd-jmp | 5,000,101 / 7,800,019 | 54.97 ms | 1541.37 ms | 28.0× | **RED** |

**C.27 total: 1/16 GREEN, 15/16 RED.** Raw data:
`evidence/C27_shape_axis.json` / `.txt`.

## What landed in this implementation pass (all certified, none claimed as a speed win)

1. **C.36 complete** — `--no-ac`/`--no-learn` deleted; anti-cache 4/5 → 5/5.
2. **C.2 / C.9 / C.11 / C.15 slice** — bounded 2-arg SWAR `front_scan`
   replaces six whole-source runtime-need probes; one `length(src)` reused;
   `u_prep` keeps its own `unsafe:` gate. `front_native.sov` 1,215 B,
   SHA `8d009f40…`. Three-generation bootstrap converged.
3. **C.10 / C.12** — `sg_extra_ls` native twin (`tools/native_sgextra.c`,
   `tools/build_native_sgextra.py`, `compilers/linux/sgextra_native.sov`,
   `sg_tbl`/`sg_tbl_init`/`_sov_sg_extra_ls` wrapper + `cx86_p3` dispatch).
   Preserves `src_base` (deleting it was a counterexample: 8/40 mismatches).
   v2 adds a **sound** precheck: `sg_extra(t)` can only be nonzero with
   `;;`, `" -> "` or `": "`, so lines without all three skip the table calls
   decision-equivalently. 12 sugar fixtures + 40 differential cells identical.
   The `2-all-spliced` endpoint read 4.95 → 4.16 ms for v1, but the v2
   min-of-9 probe read 4.17 → 5.39 ms (`evidence/C12_sgextra_v2_prof.txt`)
   while the SUM-of-endpoints min read 230.1 → 224.9 ms: the nested-aggregate
   endpoint is too noisy to attribute. Whole-run placebo-controlled R=21
   remains INSIDE the noise band, so **not a speed win**.
4. **C.9** — `/proc/self/exe` readlink + 4 KiB probe buffer deleted;
   `self_dir` now comes from `argv[0]`'s dirname, with the in-sync baked
   runtime payload as last resort. Two-cwd differential (project root and
   `/tmp`) byte-identical.
5. **C.27 harness built** — `tools/shape_gate.py` reproduces all 12 SA shapes
   plus 4 cliff probes with semantics-first validation and C.34 byte fields.
6. **C.26/C.36 harness built** — `tools/flag_surface_gate.py`: 14/14.
7. **C.31** — `tools/sgextra_fixture_gate.py`: 12 counterexample-first sugar
   fixtures (pack marks, arrow, run form, digit assignment, two colons,
   colon-in-string, multiline string, `>` without colon, `unsafe:`+pack).
8. **C.29/C.32** — `tools/layout_check.py` (12/12), `tools/front_fusion_gate.py`
   (20/20), SA positional `argv[2]` fixes retained, `--prof` nested aggregates.
9. **C.30** — fleet re-run after the `compilers/shared/*` edit:
   **126/155 build + 29 lineage-pending**, explicitly NOT green.

### Placebo-controlled evidence (C.33, R=21 rotated interleaved)

| Slice | A | B | B vs A median | Placebo median | Band | Verdict |
|---|---|---|---|---|---|---|
| front fusion, self | `5daeae4f…` | `af588916…` | −0.22% | −0.25% | [−0.75%, +0.54%] | INSIDE |
| front fusion, `--flat` 4 MB | `5daeae4f…` | `af588916…` | −0.11% | −0.09% | [−0.59%, +102.91%] | INSIDE |
| `sg_extra_ls` v1 | `af588916…` | `647bc0e9…` | +0.04% | +0.03% | [−0.54%, +0.53%] | INSIDE |
| `sg_extra_ls` v2 precheck | `647bc0e9…` | `5dff58ce…` | +0.06% | +0.05% | [−0.50%, +0.55%] | INSIDE |

A `--flat` 4 MB run once printed `−50.31%` median; the identical A/A placebo
showed both 15.6 ms and 31.8 ms in the same rotation (host bimodality), and
all three minima were 15.5–15.6 ms. It is **not** a win and is not claimed.

## C.38 additions — dead ends (do not retry)

- `sg_extra_ls` stub/replacement with `0`: 8/40 differential mismatches
  (`tests/all.sov`, `tests/x86ins.sov`), `src_base` is load-bearing.
- Byte-at-a-time / NUL-scanned v1 `front_native.sov` (2× slower on `--flat`).
- Fused `unsafe:` bit1 gate (7.2 ms on 4 MB vs SWAR `find_text` 15.6 ms for
  the whole front end) — reverted.
- **Parked `bw` twin** (`tools/land_bw_twin.py`, `work/p4/tw_block_v2.sov`,
  `tools/native/native_emit.c`): fully implemented but PARKED by the
  certified compiler's patch/reloc misdirection under source perturbation
  (documented in `work/p4/SESSION_2026-11-02_NIGHT_BW_TWIN_AND_PATCH_BUG.md`).
  It is a documented dead twin — C.38 forbids re-landing it.
- SA large pages on grown tables, grow×4, half-load growth, source-sized
  tables, parallel-by-default; SWAR strlen, inline `starts_with`,
  native-inline `find_text`, `sg_ind` inline, peephole/copy prop, cops guards,
  line-level memoisation, rt_baked-first, emitter batching, sugar-once,
  inl2 fusion, intern-table shrink.

## Still open — no claim of completion

C.2–C.8 as a whole (the 13,000-line front end still does ~12 whole-text
walks), C.10–C.13 (the 136 ms `bw` / codegen layer), C.16–C.19, C.30
(155-driver fleet green), C.27 (15 red cells), and **every speed cell
C.20–C.25**. Semantics-first, upper 95% paired latency ratio ≤1 and lower
throughput ratio ≥1 per workload × size × mode × flag cell, fresh cold
processes, same-session SA, expanded + input bytes reported; unknown/absent
cells fail.


## Additional slices landed since schema 6 (compiler `d7f19ed4…`)

**10. C.5 — ID/hash twin dispatch.** `compilers/shared/cx86_p3.sov` replaced
44 `_sov_str_eq(tnm, "name")` comparisons (22 in `nt_will_twin`, 22 in
`try_native_body`) with `tid`/`wtid is ntk_<name>` integer comparisons against
a lazily built table of `intern_kid()` canonical pointers. This is exactly
equivalent: `intern_kid(s)` returns the unique pool pointer for `s`, so
`intern_kid(tnm) is intern_kid("X")` iff the strings are equal. It removes
~58k interpreted string-compare calls per self-compile. Compile-time only:
**40/40 differential cells byte-identical**, all standing gates green,
three-generation bootstrap converged. Placebo-controlled R=21 A/B: self
median −0.01% vs placebo +0.02%, band [−0.50%, +0.56%] → **INSIDE**, so no
speed win is claimed. Script: `work/scripts/apply_c5_id_dispatch.py`.

**11. C.30/C.32 fleet harness fixed.** `tools/fleet_speed_gate.py` now records
the `.build-failed` marker text, the first error, and the process return code
for every non-building driver, asserts `len(rows) == len(drivers)` (nothing
skipped), and exits non-zero on an unmarked lineage-pending row. Re-run after
the `compilers/shared/*` edit: **155 discovered / 155 rows / 126 build / 29
lineage-pending / 0 unmarked / 0 skipped**. The 29 are the shipped
`corrupt-era artifact removed; source desynced` / `build failed` sources;
their `.sov` text has broken include indentation and cannot be rebuilt from
the uploaded tree. This is a genuine source-corruption blocker, not a gate
defect. Gate output `rc=0` means the census is honest, **not** that 155/155
build: C.30's build criterion remains NOT green.

**12. C.19 emitter regression gate.** `tools/emitter_regression.py` builds all
155 drivers cold, executes each on two equal-length programs differing only
in a numeric literal, and freezes rc + output size + SHA-256 for both runs.
`tests/gates/emitter_regression.json` is the regression constraint; a re-check
reports **0 classification/byte-behaviour changes**. Note: the historic
"23 constant emitters + 5 error backends" census used a 17-construct
execution-verified corpus; this stricter byte-level snapshot preserves all
155 behaviours and classifies 4 pure-constant, 122 differing, 29 pending.

**13. C.18 serial-by-default gate.** `tools/serial_default_gate.py` walks the
real include graph (24 files), finds exactly one `syscall(57, 0)` fork at
`compiler.sov:11092` behind `pm_ptf`, verifies the opt-in sentinels
(`/tmp/sov_ptime`, `/tmp/sov_tklex`, `/tmp/sov_par`) are absent, and samples
`/proc` during a cold self-compile: **0 child processes → GREEN**. This mirrors
SA's dormant `tc_*` split. No parallel worker was added.

**14. C.17 status.** `runtime.sov` already applies `madvise(MADV_HUGEPAGE)`
(`syscall(28, …, 14)`) on maps ≥2 MiB and uses `MAP_NORESERVE` geometric
reserves; `emit*` are already native twins. The two remaining C.17 deltas —
lowering the THP threshold to 512 KiB and adding `MAP_POPULATE` on ≥1 MiB
maps — would change `runtime.sov`, which is spliced into every
runtime-needing compiled program and therefore break C.29's byte-identical
`hello`/`all.sov`/`x86ins.sov` requirement. They are documented, not applied.

**15. Workspace declutter.** The one-off root-level `apply_*.py`,
`update_docs_*.py` and probe scripts were moved into `work/scripts/`; the
workspace root now holds only the four top-level documents, the two `dl/`
trees (both still visible), `evidence/`, `originals/`, `reference/`, the
manifest/enumerator/downloader, and the symlinks.

## Why C files exist, and where the .sov files are

The `.sov` files are the deliverables. `dl/sovren/compilers/linux/` contains
22 `*_native.sov` twins (`front_native.sov`, `sgextra_native.sov`,
`basescan_native.sov`, `syntax_native.sov`, `statements_native.sov`, …), and
`compilers/linux/compiler.sov` (413 KB / 13,300+ lines) ends with an
`include` chain that pulls all of them in. A `.sov` source can only plant raw
bytes through `emit8`/`emit4`/`emit` statements with numeric constants — it
cannot express x86 machine code directly. So each `tools/native_*.c` is a
**build source**: gcc compiles it freestanding, `objcopy -j .text` extracts
the raw bytes, and `tools/build_native_*.py` emits them as `emit8` rows in the
corresponding `.sov` twin. The builder asserts zero undefined symbols and
zero relocations. The C file and the `.sov` twin are one unit (source →
generated artifact), not two competing implementations. The extra harnesses
(`shape_gate.py`, `flag_surface_gate.py`, `sgextra_fixture_gate.py`,
`emitter_regression.py`, `serial_default_gate.py`) are the gates that C.18,
C.19, C.26, C.27, C.29 and C.31 require; each writes evidence to
`/home/user/evidence/`.


**16. C.29 differ harness generalised.** `tools/differ_gate.py` generates
2,957 deterministic Sovren programs across 12 shape families (arithmetic,
nested `if`, `as long as`, pack-mark sugar, arrow one-liners, forward calls,
strings/quotes, comments, long identifiers, `times` forms, expression-heavy
and one-char/tiny edits), compiles every case **cold twice** (control +
candidate), compares rc + output SHA-256, then executes both binaries and
compares exit status / stdout / stderr. Refusal parity requires both sides to
refuse with the same rc and no artifact. Seed `20261108`, so any counterexample
is reproducible from its case index alone. Results: **2,957/2,957 identical
against the immediate control `5dff58ce…`** and **2,957/2,957 identical
against the original uploaded binary `4162d364…`**. Evidence:
`evidence/C29_differ_2957.json`, `C29_differ_2957_vs_original.json`.


**17. C.32 tier-gate noise fix.** An identical-binary A/A sanity check at
R=21 failed once in three runs on this 2-CPU host (`A/A noise out of band
twice`). `tools/tier_gate.sh` now takes up to 4 fresh A/A samples instead of
2, **without** relaxing R=21 or the 3% band. Re-run: 3/3 `TIER GATE GREEN`.
The one transient failure is recorded, not hidden.

**18. Schema 8 — fused front-end scan (2026-11-08).** Three source changes landed
and were bootstrapped to the converged fixed point `727c1e6d…`:

1. **C.2/C.3/C.12/C.13 — one fused native pass.** `compilers/linux/basescan_native.sov`
   (built from `tools/native_basescan.c` by `tools/build_native_basescan.py`, 1,019 B
   `.text` blob) replaces `_sov_lines_of_fast` ×2 + `_sov_list_len` ×2 +
   `_sov_sg_extra_ls` ×2 with two `_sov_base_scan(text, sg_tbl)` calls. Each returns
   `(sugar_extra << 32) | line_count` from **ONE** pass over **ONE** flat copy — no
   line-pointer list is built. `src_base` remains bit-exact (16/16 minimised
   fixtures, 2,957/2,957 differ, 12/12 layouts, oracle 24/16/0). The new entry is
   ID-dispatched in `cx86_p3.sov` (`ntk__sov_base_scan`) and `sg_tbl` gained a
   third slot (`_sov_heap_alloc`).
2. **C.2/C.3 — delete two whole-text walks.** `length(all_after) - length(src)` after
   `all: join(all, src)` is exactly `snap_a`; the two post-join `length()` calls are
   replaced by `snap_m: snap_a`.
3. **C.13 — free superseded geometric arenas.** `tk_grow` (`cx86_p1.sov`) and
   `ocgrow` (`cx86_p4.sov`) now `_sov_free()` the old buffer after the copy; every
   consumer addresses these arenas by offset through the global.

**No speed win is claimed.** R=21 placebo A/B on self: B min +0.09% / med −0.01%,
placebo +0.03% / −0.07%, band [−0.57%, +0.53%] → INSIDE. x86ins: B +0.01% / +0.11%,
placebo min −39.10% (one 19.31 ms host outlier) / med +0.01%, band
[−39.60%, +0.51%] → INSIDE. Fresh min-of-7 `--prof`: `bw` 112–124 ms of ~265 ms
self-compile, `2-all-spliced` ~5.7 ms (`evidence/PROFILE_final_c2.txt`).

**Dead end (reverted, do not retry).** Sizing the `lines_of_fast` pointer array by
line count instead of source byte count (`nl_count_lines+1`) exposed a latent
out-of-bounds writer: `work/p4/tw_block_v2.sov --bare` changed from a clean refusal
(rc1) to a segfault (rc139). It also did **not** fix the 8 MB OOM or improve any lane.
Reverted; `linesfast_native.sov` rebuilt from the original C source (978 B blob,
`--check` green).

**C.22 8 MB root cause found.** An instrumented build plus `/proc/<pid>/maps`
sampling shows the OOM is **~1 GB RSS of never-freed `lines_of_fast` flat copies
and allocator meta arenas** (318 × 64 MiB large reserves, 20 × 16 MiB arenas), not
the 16× VA headroom. Freeing `tk_buf`/`oc` alone is insufficient. The fix is the
C.2–C.4 single-pass / zero-copy rewrite, which is not landed.

**C.30 explicit verdict.** All 155 drivers produce a row; 126 build and 29 are
lineage-pending with a `.build-failed` marker and are never skipped. Direct
inspection (`compilers/apple/macos`, `compilers/windows`,
`compilers/operating-systems/freebsd`) shows pinned `inc/*.sov` slices that contain
mixtures of indented and unindented statements; compiling yields "a statement inside
a task must be indented" and duplicate `g_meta`/`g_meta_bump`. `--bare` does not
help. Five flatten strategies (A–E) all returned rc141. **29 absent cells ⇒ C.30
FAIL**, not an honest census passing.

**C.17 explicit verdict.** `madvise(MADV_HUGEPAGE)` threshold and `MAP_POPULATE`
in `runtime.sov` are deliberately NOT applied: `runtime.sov` is spliced into every
runtime-needing program, so changing it breaks the byte-identical oracle/hello/
all.sov/x86ins.sov cells and `rt_baked_sync`; the hints cannot close a 33× label-lane
gap. C.18 (serial default) stays GREEN — no `clone()` worker was added.

**`bw` correction.** The `bw` native twin is already landed and dispatched
(`statements.sov:167`, `cx86_p3.sov:14/39/80/162`, `emit_native.sov:3`); the earlier
"parked `bw` twin" note is stale. `tools/land_bw_twin.py` remains a C.38 dead end and
must not be re-landed. The remaining `bw` cost is inside the twin and the codegen
walk, which is the C.2–C.8 rewrite.

Evidence: `evidence/PROFILE_final_c2.txt`, `C31_basescan_fixtures.json`,
`C29_differ_2957.json`, `C29_differ_2957_vs_original.json`,
`C30_fleet_final_c2.txt`, `C20_C25_final_c2.txt`, `C22_scaling_final_c2.txt`,
`C27_shape_axis_final_c2.json/.txt`.

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
