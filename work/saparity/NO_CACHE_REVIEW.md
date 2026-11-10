# C.35 / C.36 / C.37 — no-cache review, reconciliation and purge confirmation

> **Current baseline: schema 9 (2026-11-08).** Installed compiler md5
> `be20f64258d4a7a91d5c46e07d64be70` (1,856,552 B). C.4/C.6 is in-run
> memoisation only. Gate sweep 17/0, C.29 2,957/2,957, C.22 ×1.00 LINEAR
> incl. 8 MB. C.27 1/16 GREEN, C.30 126/155 + 29 pending, every C.20–C.25
> speed cell RED. Global completion **NOT met**. See
> `work/saparity/baseline_frozen.json` (schema 9) and
> `work/saparity/ACCEPTANCE_TABLE.md`.


**Date:** 2026-11-08 · **Rule:** no caching was introduced, implemented or recommended in this work. Single-run hash tables, interners, arenas, memo slots and fixup vectors are required data structures, not caching. The prohibition is on persisted intermediates, artifact/state sidecars, prefix replay, serve/warm paths and any reuse of a translation result across runs or edits.

## 1. The tripwire before and after

`tools/no_cache_policy.py` previously exited **1** with:

```
NO-CACHE REVIEW REQUIRED:
  compilers/shared/cx86_p1.sov::scutr s st,
  compilers/shared/cx86_p4.sov::try_stmt_inline var rhs,
  compilers/shared/cx86_p7.sov::try_scaled_mem name argc argl
```

Cause: **not** new caching. Three upstream source bodies had been edited after `tools/no_cache_inventory.json` was frozen, so their comment-stripped body hashes no longer matched. Token sets were identical (`wid_last_r/wid_last_s`, `ml_collect_cached`, `ik_cached`). The policy explicitly says changes require an explicit review — so a review was performed (below), documented, and the inventory re-frozen with written per-construct justification. **The check was not removed, weakened or bypassed.**

After the review: `python3 tools/no_cache_policy.py` →
`no-cache source tripwire OK (7 reviewed constructs unchanged; no persisted sidecar literals in any .sov)`, exit 0.

The tripwire was also **strengthened**, not weakened:
- a second, independent `sidecar_scan()` walks **every** `.sov` in the tree and fails on any persisted-output sidecar literal in executable (non-comment) text;
- `EXT` now also matches `.state`;
- the baseline carries `reviewed_at`, `review_host`, a `review` map and `unexplained_constructs` (currently **0**);
- `--freeze-baseline` refuses to be silent about unreviewed constructs.

## 2. Review findings (all 7 inherited constructs)

| Construct | What it actually is | Verdict |
|---|---|---|
| `cx86_p1.sov::scutr s st` | `word_id()` memoises the last `(s → intern kid)` pair in `wid_last_s/wid_last_r` | in-run only |
| `cx86_p1.sov::word_id s` | the two `wid_last_*` globals, both initialised to 0 in the data section | in-run only |
| `cx86_p1.sov::ik_cached nm` | compares a call-name slice pointer with `ik_nm_ptr`, else `intern_kid()` | in-run only |
| `cx86_p4.sov::ml_collect_cached bf` | per-body `ml_collect()` memo in lazily allocated `mlc_*` lists | in-run only |
| `cx86_p4.sov::try_stmt_inline var rhs` | statement-level inliner using that memo | in-run only |
| `cx86_p6.sov::try_mem …` | calls `ik_cached(name)` | in-run only |
| `cx86_p7.sov::try_scaled_mem …` | calls `ik_cached(name)` | in-run only |

Common evidence: all state lives in globals that start at 0 (or lists allocated lazily) inside **one** compiler process; a repo-wide grep for `tr_shell`, file read/write and `_sov_f*` in these files returns nothing; no sidecar literal; no key validation; no branch that can load a previous run's result. SA itself uses the same kind of in-run reuse (`speed_gate.py`: "shipped SA is the target (it uses in-run reuse)"), and `sc/sc.c` reaches 107 MB/s with zero caching. These are memo slots for pure functions, not translation-result caches.

## 3. Sidecar cleanup (C.36)

The only remaining sidecar literal in the whole tree was `bootstrap.sov:6`:

```
bo_wipe src:
    dummy: tr_shell(str_cat('rm -f ', ... '.plk .ac .ac.bin .lsug .state ...))
```

It is now an **explicit no-op** with a purge comment, so the four `bo_wipe(src)` callers stay unchanged. `sidecar_scan` over all `.sov` files now reports **0** hits. `bash tools/cache_tree_guard.sh` and `python3 tools/rt_baked_sync.py` both pass (tier gate step 2).

`bootstrap.sov` does not compile standalone either before or after this edit (pre-existing `undeclared name cp/g4/m2` errors at line 287+ in `main`, identical in the backed-up original) — the edit introduced no new failure. The compiler fixed point is unaffected because `compiler.sov` was not touched.

## 4. Documentation purge (C.36 / C.37)

- Root `PLAN.md` lane **"Cache and edits"** replaced with **"Cold edits (no cache)"**: every edit rebuilds from a fully cold process; no dependency graph, per-function summaries, relocation/address invalidation or persisted state; byte-identical output and executed behaviour for one-character/whitespace/body/size/signature/global/import/compiler/flag edits, consecutive edits, interrupted writes and failure injection; cold-vs-warm is never a speed claim.
- `--no-ac` / `--no-learn` are **DELETED** from `compiler.sov` (C.36 complete). This was not cosmetic: `tests/regression/cache.py` requires every retired cache flag to be *rejected*, and the shipped compiler still accepted these two as no-ops, so the anti-cache regression gate was **4/5**. After deletion it is **5/5 green**. `tests/gates/speed_gate.py` was updated to stop passing the two flags. The compiler was rebuilt (2-generation fixed point `5daeae4f…`), re-certified and the baseline re-frozen.
- **PURGED HISTORY (must never return):** artifact cache, `.plk`/`.ac`/`.ac.bin`/`.lsug`/`.sug`/`.dsug`/`.state`/`.deepoc` sidecars, prefix replay, sugar caches, persisted intermediates, cache-key validation, serve/uncached/warm paths, `./sovren` launcher double-exec cache hits, "cold versus warm" speed claims, and all speedups attributed to them in older `SA_PARITY.md`, `SPEED_ARCHITECTURE.md`, `PATH_TO_LIGHEST.md` and `PATH_TO_LIGHTEST.md` sections. Those documents are historical evidence only.
- `tools/cold_gate.py` removes `/tmp/sov_nopar`, `/tmp/sov_tklex`, `/tmp/sov_ptime` before every run; `tools/exec_gate.py` does the same; `tools/tier_gate.sh` step 2 runs the cache-tree guard. Nothing persists between processes.

## 5. Commands that prove it

```bash
python3 tools/no_cache_policy.py                 # exit 0
python3 tools/no_cache_policy.py --freeze-baseline tools/no_cache_inventory.json  # review protocol
bash tools/cache_tree_guard.sh                  # cache guard OK
python3 tools/rt_baked_sync.py                  # baked payload == runtime.sov
bash tools/tier_gate.sh                         # TIER GATE GREEN (6/6)
python3 tools/exec_gate.py compilers/linux/compiler --quick   # GATE PASSED
python3 tests/regression/cache.py                # 5/5 anti-cache gates green
```

## 6. The first structural slice (C.2 / C.9)

`compiler.sov` now skips the six whole-source `look(src, …)` runtime-need
probes when `--bare` is in effect (a negative `need` sentinel, restored to 0
at `rt: blank`). Previously all six scans ran and their result was discarded.
`--prof` on a 4 MB `--bare` source confirms the deletion: `1-rt-loaded`
**1,590,698 ns → 359 ns** (1.59 ms of real work removed). The interleaved
R=21 A/B on the same 465 ms workload reads **−0.02 % median**, i.e. inside the
±5 % host noise band, so this is recorded as *strictly fewer ops*, **not** as a
speed win — exactly the C.12/S28R discipline (a slice must delete >~2 ms).
Outputs are byte-identical on all tested sources and modes.

## F3/F6 — placebo policy, freshly re-measured 2026-11-08

A **layout-only placebo** is a byte-for-byte copy of the control compiler
(`/tmp/cc_placebo_be20`, R=21, same source, same interleaved rotation). Its
median delta defines the measurement noise band. **A candidate result INSIDE
that band is NOT a credible win**; `ab_gate.py --require-outside-placebo` exits
2 in that case. Fresh evidence on the installed `be20f642…` binary:

| workload | A med | B med | placebo med | B vs A | verdict |
|---|---|---|---|---|---|
| `compilers/linux/compiler.sov` (self) | 264.99 ms | 265.08 ms | 265.24 ms | +0.04% | INSIDE band `[-0.50%, +0.60%]` → no credible win |
| `tests/x86ins.sov` | 31.81 ms | 31.82 ms | 31.84 ms | +0.02% | INSIDE band `[-0.50%, +0.60%]` → no credible win |

Files: `evidence/C33_placebo_self_be20.txt`, `evidence/C33_placebo_x86ins_be20.txt`.
This is an honest **no credible win** result, not a failure of the build; the
C.4 gain is claimed only on the large streaming workloads where fresh cold
timings are materially better (`C22_scaling_c4.txt`, `fleet_speed_gate`).
Do not claim a general speed win from these two placebo cells.

---

## 2026-11-08 refresh (v3.0.0 + schema-9 re-verification)

Older numbers here are **dated history**. Re-derived from files this run:
installed `be20f64258d4a7a91d5c46e07d64be70`; fixed point OK; oracle 24/16/0;
**19/19 gates**; C.29 **2,957/2,957** vs control and vs the original
`4162d364…`; **36/36** mode/flag cells; fresh R=21 placebo **INSIDE the band →
no credible win**; full paired gate **0/24 GREEN** (execution checked after
every translation, `--flat` FAIL as `NOT_MATCHED_WORK`); C.30 **126/155**;
C.27 **1/16**. `agent/completion_gate.py` = **10/14 PASS -> NOT DONE**, four
RED semantic gates remain. **No parity or completion claim.** Extension v3.0.0:
`bash arena-auto-continuation/verify.sh` = ALL CHECKS PASSED, ZIP 6,470 B /
6 files, not installed in any browser. Full ledger:
`arena-auto-continuation/REMAINING.md` and
`dl/sovren/work/saparity/SA_PARITY_EVERYTHING_NEEDED.md`.
