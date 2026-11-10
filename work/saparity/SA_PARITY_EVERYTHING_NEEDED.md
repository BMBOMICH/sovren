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

# SA parity — everything still needed (2026-11-08, honest RED)

**Answer: NO, parity is not achieved.** `python3 agent/completion_gate.py`
returns **10/14 PASS -> NOT DONE**. Four semantic gates fail. Nothing below
may be words-only: each item names the artifact that a future run must produce.

## GREEN now (10/14, machine-checked)
- no rollback: installed compiler matches `agent/state.json`
- `evidence/C4_gate_sweep_19.txt`: **19 PASS / 0 FAIL**
- `evidence/C29_differ_2957_c4.json`: 2,957/2,957, 0 mismatches
- `agent/results/gate_selfcheck.log`: FIXED POINT OK, oracle 24/16/0
- `evidence/C22_scaling_c4.txt`: LINEAR incl. 8 MB
- schema-9 docs frozen to installed `be20f64258d4a7a91d5c46e07d64be70`
- `work/saparity/semantics_frozen.json`: all six semantics written down (F2)
- `evidence/C29_differ_original_c4_full.json`: 2,957/2,957 vs **original
  `4162d364…`** binary, found at `reference/linux/compiler` (F4)
- `evidence/C36_mode_flag_c4.json`: **36/36 GREEN**, 6 sources x 6
  mode/flag combos, absent cells fail, refusal parity explicit (F5)
- `evidence/C33_placebo_{self,x86ins}_be20.txt` + this repo's
  `NO_CACHE_REVIEW.md`: fresh R=21 placebo on the new hash, INSIDE the band
  → **no credible win** (F3/F6, honest result, not a failure)

## RED — the four semantic gates

### 1. C.30 155/155 build, 0 lineage-pending
`evidence/C30_fleet_c4_refresh.txt`: **126 build / 29 lineage-pending / 0
UNMARKED**. The 29 drivers are *raw module fragments*, not complete programs
(`compilers/android/compiler.sov` is 6,567 B, interleaved top-level tasks and
`include inc/incNN.sov` lines, no `main:`). A mechanical indentation wrap was
tried and rejected: it only replaced "must be indented" with `undeclared name
sl / gfoff / src_base / had_err`. See `agent/NEXT_ACTIONS.md`.
**Needed:** the real per-driver sources or a module→driver wrapper that
declares the missing names, then a fresh `fleet_speed_gate.py 3` census showing
155 build / 0 lineage-pending, and a fresh `C30_error_classes_c4.json`.

### 2. C.30 all four error classes zero
`evidence/C30_error_classes_c4.json`: 29 drivers, 0 SOURCE_MISSING, but
duplicate_name 29, unindented_statement 29, duplicate_top_level 17,
cannot_read_library 2. **Needed:** all four counts zero with a fresh census.
(Do not edit the JSON by hand.)

### 3. C.27 all 16 shape cells GREEN
`evidence/C27_shape_axis_c4.json`: **1/16 GREEN**. **Needed:** a fresh
`SHAPE_N=40000 python3 tools/shape_gate.py` with 16/16 GREEN. Speed RED cells
also exist (`work/saparity/bench.sh` is RED); C.27 is the semantic shape axis.

### 4. C.20–C.25 every paired speed cell GREEN
`evidence/C20_C25_paired_cells_c4.json` (F7, built 2026-11-08):
**0/24 GREEN**. Each cell uses fresh cold processes, output SHA-256 on every
run, `sa` with positional `argv[2]`, interleaved A/B, bootstrap 95% CI on
**paired** latency and **paired** throughput ratios, input AND expanded bytes
reported. GREEN = upper95(latency) ≤ 1.0 and lower95(throughput) ≥ 1.0.
**Needed:** 24/24 GREEN. Current small-cell latency CIs straddle 1.0 and the
large default cells are RED. Higher run counts alone will not fix a real
latency gap; the compiler must actually get faster.

## Current no-cache status (2026-11-09)
C.35 / C.36 / C.37 are DONE. `python3 tools/no_cache_policy.py` exits **0**
(`no-cache source tripwire OK (7 reviewed constructs unchanged; no persisted
sidecar literals in any .sov)`). `--no-ac` / `--no-learn` deleted; inventory
re-frozen with written justification; `sidecar_scan()` added. Extension v3.1.6
is DONE by user report; it is not part of compiler parity.

## Standing policy
- **Semantics before speed.** No parity claim from a placebo-band "win".
- No absolute "fastest / everywhere" claims; every number is scoped to the
  measured host, build, workload and definition.
- Absent, timed-out, nondeterministic or refused cells are FAIL, never skipped.
- `agent/completion_gate.py` must reach 14/14 and global completion before
  any parity or completion claim.

## Honest dead ends (do not retry)
`apply_c13_line_capacity.py`, `/tmp/c13g/g2`, `/tmp/c13fg/g2`, `sc` detour,
`sgextra` stubs, `--run` on self, cross-run cache/memoisation, C.17
THP/MAP_POPULATE (breaks byte-identical outputs), stripping/kit_expand for
C.30 drivers, mechanical indentation of C.30 fragments, `--prof` nested
aggregate summing, `reference/gates/*.sh` (use `work/saparity/*.sh`).

## 2026-11-09 engineering pass (honest partial)

`agent/completion_gate.py` is still **10/14 PASS -> NOT DONE**. Full per-item
ledger: `/home/user/COMPILER_WORK_2026-11-09.md`.

DONE this pass: **C.31** (`tools/c31_validate_all.py`, all 22 native twins
covered, 10 gates ALL GREEN), **C.32** (all five harness items, including the
rebuilt SA `t/gate.py` at 6/6 with 245/245 mnemonics and 20/20 diagnostics),
and re-verification of C.14/C.18/C.19/C.26/C.28/C.29/C.33/C.34/C.35/C.36/C.37.

NEW blocker evidence: **C.30** 25/29 broken drivers are byte-identical to the
uploaded upstream manifest, all 1,315 include pins verify, and flattening
still fails — the real per-driver sources are absent (`C30_lineage_hashes_c4.json`).
**C.11** build tool restored, but `shim_reader.so` is an A/A placeholder with
text identical to `old_reader.so`; the fused C source is still gone
(`C11_reader_reconstruction.json`).

Fresh RED re-measurements: paired gate **0/24**, shape gate **1/16**. C.2-C.8
pass inventory measured with `--prof` (`C2_C8_pass_inventory.json`); no rewrite
landed. No emitted byte changed, no green cell faked, no parity claim.
