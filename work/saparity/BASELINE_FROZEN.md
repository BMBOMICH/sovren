# C.1 — Frozen baseline (2026-11-08, re-frozen five times)

> **CURRENT: schema 9 (2026-11-08).** Installed
> **`be20f64258d4a7a91d5c46e07d64be70`**, 1,856,552 B; `compiler.sov` 413,966 B
> / 13,321 lines. C.4/C.6 in-run memoisation only. Gate sweep **17/0**, C.29
> **2,957/2,957**, fixedpoint g1==g2==g3, oracle **24/16/0**, C.22 **×1.00
> LINEAR incl. 8 MB**. C.27 **1/16 GREEN**, C.30 **126/155 + 29 pending**,
> every C.20–C.25 speed cell **RED**. Global completion **NOT met**. See the
> **Schema 9 freeze** section at the end of this file. The schema-8
> "8 MB deterministic OOM / lines_of_fast RSS root cause" narrative is
> **disproven** by `evidence/C22_scaling_c4.txt` (×1.00 LINEAR, 8 MB rc0).
> See also
> `baseline_frozen.json` (schema 9). Everything below this banner is dated
> history (schemas 4–8) retained for the A/B record.

> **RE-FROZEN AGAIN (schema 7, historical).** C.5 ID/hash twin dispatch landed
> on `compilers/shared/cx86_p3.sov` (44 string compares → 22 interned-pointer
> IDs), plus the C.18/C.19/C.30/C.32 harness gates. Installed md5 is now
> **`d7f19ed4163922d8cb77c8d8d20d2a42`** (1,848,200 B); `compiler.sov` 413,187 B / 13,305 lines.
> **SUPERSEDED by schema 8, then schema 9, at the end of this file** (`727c1e6dab7e947eadec4325bb11f43e`, 1,856,536 B; 22 native twins).
> Three-generation bootstrap converged; 40/40 differential cells
> byte-identical; all standing gates green; C.30 is 155/155 rows with 126
> build, 29 documented lineage-pending, 0 skipped. Placebo-controlled R=21
> A/B remains INSIDE the noise band, so **no speed win is claimed**. Every
> speed cell C.20–C.25 is RED, C.27 is 1/16 GREEN; global completion is NOT
> met. Use `baseline_frozen.json` (schema 7) and `ACCEPTANCE_TABLE.md`.

> **RE-FROZEN AGAIN (schema 6, current).** Three more certified slices landed
> on the real Linux compiler: (1) the `sg_extra_ls` native twin with an
> in-run `sg_tbl` and a sound decision-equivalent precheck, (2) removal of
> `/proc/self/exe` + its 4 KiB probe buffer in favour of `dirname(argv[0])`,
> and (3) the C.27 shape-axis / C.26 flag-surface / C.31 sugar-fixture
> harnesses. Installed md5 is now **`5dff58ce159318c0eb846136d71969ba`** (1,848,016 B);
> `compiler.sov` 413,187 B / 13,305 lines. Every intermediate binary
> converged g2==g3 before install; 40-cell and two-cwd differentials are
> byte-identical; all standing gates green; C.30 fleet is still
> 126/155 + 29 lineage-pending. Placebo-controlled R=21 A/B for every slice
> remains **INSIDE the noise band**, so no speed win is claimed. Every speed
> cell C.20–C.25 is RED and C.27 is 1/16 GREEN. Use
> `baseline_frozen.json` (schema 6) as the machine-readable baseline and
> `ACCEPTANCE_TABLE.md` as the per-cell ledger.

> **RE-FROZEN AGAIN (schema 5).** Step 4 continued: the C.2/C.9/C.11/C.15
> fused front-end scan landed. Installed md5 is now
> **`af588916b35405ba0e12c565c26c4344`** (`compiler.sov` 412,293 B / 13,286
> lines, expanded 1,915,432 B, emitted 1,765,684 B), converged over three
> generations. All gates green; 12/12 layouts; 20/20 minimised fixtures;
> 40-cell differential byte-identity; fleet 126/155 with 29 lineage-pending.
> Placebo-controlled R=21 A/B says the change is **inside the noise band**
> (−0.22 % median, band [−0.75, +0.54]) — recorded as strictly fewer ops,
> **not** a speed win. See `ACCEPTANCE_TABLE.md` for the honest per-cell
> ledger: every speed cell is still RED. Use `baseline_frozen.json` (schema 5)
> as the machine-readable baseline.

> **Previous re-freeze (schema 4).** The first certified `compiler.sov` edit (C.36 + the C.2/C.9
> `--bare` slice) changed the installed binary from md5 `4162d364…` to
> **`5daeae4fcfb7de6c379f3a1a1d58aaa1`**, `compiler.sov` to 411,284 B /
> 13,270 lines, expanded text to 1,910,245 B and emitted bytes to 1,762,001.
> All gates were re-run green (fixed point, oracle, tier, exec, anti-cache
> **5/5**, no-cache policy, `tests/gates/speed_gate.py`) and outputs are
> byte-identical to the previous compiler on 8 source/mode pairs. `cold_gate`
> self-compile is unchanged (264.50 → 264.64 ms). The numbers in the rest of
> this file are from the earlier binary and remain valid as the *reference*
> shape; use the machine-readable twin `baseline_frozen.json` (schema 4) for
> current A/B work.


**Machine-readable twin:** `baseline_frozen.json`. **Invalidate and re-freeze after any change to a source, binary, toolchain, harness or host.** Every A/B is measured against this baseline, with a placebo control, and must record host + input/expanded/emitted bytes.

## Host
Linux x86_64, 2 CPUs, `e2b` sandbox, Asia/Baku. **A/A noise here is ±5% at R=8 and within ±3% at R=21** — this is why `tools/tier_gate.sh` step 4 was raised from R=8 to R=21 (C.33). The S28R ±1% layout-lottery band belongs to the original faster host; on this host the measured placebo band is **−0.75% / +0.50%**. Any result inside that band is not a win.

## Under test
| | |
|---|---|
| Installed compiler | `compilers/linux/compiler`, 1,843,888 B, md5 `4162d3641f343449ea2ac5d17eaa7313`, static ELF, no section headers |
| Compiler source | `compilers/linux/compiler.sov`, 411,100 B / 13,268 lines / 500 tasks |
| Expanded `--flat` | 1,910,061 B (**4.65×**) · emitted 1,762,049 B (**4.29 B per input B**) |
| SA | `sa` 83,500 B, `sa.asm` 331,035 B; self-assembly **byte-identical**; output is positional `argv[2]` |

## Gates at freeze (all re-run this session)
- `work/saparity/oracle.sh` → **24 pass + 16 refuse-parity + 0 FAIL**
- `work/saparity/fixedpoint.sh` → **OK** (`g2 == g3 == installed`)
- `tools/tier_gate.sh` → **GREEN 6/6** (no-cache policy, cache tree guard, track1 gates, A/A R=21, paired executed workloads, phase table)
- `tools/exec_gate.py --quick` → **PASSED** (fixed point, 4 executed programs, 0 mismatches)
- `tools/no_cache_policy.py` → **OK** (7 reviewed constructs, 0 sidecar literals)
- `tools/fleet_speed_gate.py 3` → **126/155 build, 29 lineage-pending explicitly recorded** (pre-existing incomplete backends / `.build-failed`; never silently skipped)
- `tools/cold_gate.py --runs 9 --scaling` → **NONLINEAR ×2.06** (gate ≤ ×1.20) — **open blocker** for C.22/C.27

## Official parity ratios (`tools/speed_gate.py`, expanded bytes)
`tests/all.sov` **0.083×** · `compilers/linux/compiler.sov` **0.096×** · `tests/x86ins.sov` **0.071×** → 10–14× short. On raw input bytes self-compile is 1.78 MB/s vs SA 104.5 MB/s (~59×).

## `cold_gate.py` (the sanctioned speed measurement, unique-line corpora, output SHA verified every run)
| Cell | Bytes | Best ms | MB/s |
|---|---|---|---|
| self-compile | 411,100 | 264.50 | 1.55 |
| x86ins | 42,322 | 31.86 | 1.33 |
| hello | 191 | 1.41 | 0.14 |
| gen-1mb-sov | 1,261,722 | 464.82 | 2.71 |
| scale-8mb-sov | 10,067,678 | 7,540.13 | 1.34 |
| **gen-1mb-asm (SA)** | 1,000,053 | **7.60** | **131.63** |

SA is **48.5×** Sovren at 1 MB of unique lines. Per-byte cost grows ×2.06 from 0.25 MB to 8 MB, so the pipeline is still superlinear — this is new, direct evidence for C.2/C.13 and the reason C.22/C.27 cannot be certified yet.

## Lanes (min-of-9)
Tiny floor: SA **0.211 ms**, Sovren **0.648–0.758 ms**, `sc` **1.067 ms**, `/bin/true` **0.992 ms**.
Real libraries: `bigint` 0.64 · `x86` 2.59 · `tls` 3.09 · `suite` 4.43 MB/s (vs SA ~104.5).
4 MB synthetics: `vars4m` 9.80 · `loc100k` 9.50 · `fns1m` 6.06 · `deepfns` 7.53 MB/s.
`sc` prototype: 107.23 / 91.80 / 94.99 / 37.85 MB/s on the same lanes; `sc/bench.sh` with paths fixed reads `vars4m` 108.41 vs SA 100.89 MB/s.

## No caching
Every compile is fully cold. No artifact cache, persisted intermediate, prefix replay, state sidecar, serve/warm path, cache-key validation or cross-run reuse of a translation result. Single-run symbol tables, interners, arenas and fixup vectors are required data structures, **not** caching. `t/srcs.py` generates its corpus fresh into a new temp dir on every call.

## Schema 8 freeze (2026-11-08)

Supersedes schema 7 (`d7f19ed4…`). Installed
`727c1e6dab7e947eadec4325bb11f43e`, 1,856,536 B; `compiler.sov` 413,966 B /
13,321 lines / 22 native twins; g1==g2==g3==installed. Host unchanged
(`e2b.local`, 2 CPUs, 1982 MiB / 0 swap, Asia/Baku); SA `sa` 83,500 B,
positional `argv[2]`, self-assembly byte-identical. Cold processes only.

Re-measured on this binary: self-compile 264.23 ms / 1.57 MB/s;
x86ins 32.10 ms / 1.32 MB/s; hello 1.34 ms / 0.14 MB/s; `gen-1mb-sov`
464.74 ms / 2.71 MB/s; `scale-4mb` 2572.44 ms / 1.96 MB/s; `scale-8mb` **FAIL**
(OOM rc −9); `gen-1mb-asm` (SA) 7.65 ms / 130.72 MB/s. Per-byte cost growth
**×1.41** (gate ≤1.20) → NONLINEAR. C.27 **1/16** GREEN, C.30 **126/155**
build, every C.20–C.25 cell RED (`evidence/C20_C25_final_c2.txt`,
`C22_scaling_final_c2.txt`, `C27_shape_axis_final_c2.json`,
`C30_fleet_final_c2.txt`).

The schema-8 changes are structural, **not** a speed win: R=21 placebo A/B self
B +0.09%/−0.01% (band [−0.57%, +0.53%] INSIDE), x86ins B +0.01%/+0.11%
(band [−39.60%, +0.51%] INSIDE). All further A/B claims are against this
baseline with a byte-identical placebo control. `baseline_frozen.json` schema 8
carries the machine-readable form, including the reverted line-cap dead end,
the `bw` correction, the C.17/C.30 verdicts and the 8 MB OOM root cause.

## Schema 9 freeze (2026-11-08, CURRENT)

Supersedes schema 8 (`727c1e6dab7e947eadec4325bb11f43e`, 1,856,536 B), which is
retained at `/tmp/cc_control_pre_c4` as the pre-C.4 control. Installed compiler
is now **`be20f64258d4a7a91d5c46e07d64be70`**, **1,856,552 B**;
`compiler.sov` 413,966 B / 13,321 lines; `cx86_p4.sov` 169,920 B, SHA-256
`225d1c0aff5b5eb5…`. Fixed point converges g1==g2==g3==installed.

**C.4/C.6** memoises `ml_collect_cached` inside a single compile
(`mlc_tab[bf] = ci + 1`). The sampler found 2,057 samples / **38.97%** in that
function. It is discarded on process exit, writes no sidecar, and is not a
cache under the no-cache policy (re-reviewed). `bw` lane timings improved
69.85→62.46 / 349.78→269.45 / 2,627.16→1,236.00 ms at 250 / 1,000 / 4,000 KB.

Fresh evidence on this binary: `evidence/C4_gate_sweep.txt` **17 PASS / 0 FAIL**;
`evidence/C29_differ_c4.json` **2,957/2,957, 0 mismatches** plus a 12-case
differential with 0 mismatches; `evidence/C22_scaling_c4.txt` **×1.00 LINEAR**,
8 MB OK (10,067,678 B, 3,276.38 best / 3,482.09 med ms);
`evidence/C27_shape_axis_c4.json` **1/16 GREEN** (12 shapes + 4 cliffs);
`evidence/C30_fleet_c4.txt` 155 rows / 126 build / 29 lineage-pending;
manifest **1,419 / 0 missing / 22 intentional changes**. The C.30 classifier's
off-by-one was fixed: the census summary line no longer counts as a 30th
driver, so `evidence/C30_error_classes_c4.json` now records **29** real drivers
(duplicate_name 29, duplicate_top_level 17, unindented_statement 29,
cannot_read_library 2) and **0** SOURCE_MISSING rows.

**Still RED / open:** every C.20–C.25 paired speed cell; 15/16 C.27 cells;
29 C.30 drivers; C.29 differential vs original `4162d364…` on this binary;
36-cell mode/flag differential; C.33 placebo R=21 on `be20…`; the full per-cell
paired latency/throughput gate; C.9 startup reads; C.2–C.8 / C.10 / C.11 /
C.15 / C.16; C.28–C.39 hygiene. **Global completion is NOT met** and no parity
claim is made. Schema-8 A/B numbers below are retained as dated history, not as
the current baseline. `baseline_frozen.json` is schema 9.

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
