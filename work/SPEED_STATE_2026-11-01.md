# Speed State — 2026-11-01 (Tier 0 complete)

## Installed compiler

`compilers/linux/compiler` = sha256 `f1c7400fec3421f24ec378ea213962c05c9a9a728e71b23dc0ed6bc18d9f23a6`
(fixed point: gen3 == gen4 == gen5 verified; `track1_gates.sh` ALL GREEN;
`no_cache_policy.py` clean; outputs byte-identical to the previous fixed point
on `tests/all.sov` and `tests/x86ins.sov`; self-compile output differs only in
the embedded seed image, which is expected — the seed is the compiler itself.)

### Lineage archaeology (resolved)

The session note "install compiler-step1 for a free ~8%" was wrong — two
different binaries had been conflated:

| binary | sha256 (16) | md5 (8) | self-compile | verdict |
|---|---|---|---|---|
| prev installed (`compiler.prev-orphan2`) | `8a82e549a7e6a93c` | `8eebfa43` | **141–146 ms** | was the S0 fixed point, fastest |
| `compiler-step1` / `compiler.gen3` / `step1.g1` | `a18134832191588b` | `83c8aedb` | 149–151 ms | NOT a fixed point of S0 (transient 99b8dbf6 → 8a82e549); ~5% slower |
| `work/p3/ref.g1`/`cur2.g1`/`base.g2`/`inc2.g3` | `aed570cab6662e88` | `31f7a5a3` | 154 ms | fixed point of an old p3 source state |
| `work/p3/clean.g1..g3` | `63ede3819b59cab2` | `a26cb51f` | 165 ms | fixed point of the clean line |

The md5 `31f7a5a3` in the old note belongs to the p3 lineage, not to
`compiler-step1`. Nothing was gained by installing step1; it has been renamed
`compiler.gen3-rejected-not-fixedpoint`. The real Tier 0 win came from the
decline fix below.

## Baseline ratios (R15 medians, fresh-process, pre-decline-fix)

| workload | Sovren MB/s | sa MB/s | ratio |
|---|---|---|---|
| self | 9.03 | 619.9 | 68.7x |
| all.sov | 6.05 | 479.7 | 79.3x |
| x86ins | 4.94 | 677.5 | 137x |

## Phase table (self-compile, 355,963 B source, instrumented 172.7 ms)

| phase | ms | share | what |
|---|---|---|---|
| `bw` | 68.10 | 39.4% | per-task statement interpreter, 1,133 calls |
| `W-walk0` | 29.03 | 16.8% | line walk splitting source into task bodies |
| `c0-parsed` | 22.29 | 12.9% | parse |
| `C1` | 15.61 | 9.0% | pu_lines |
| `4-compiled` | 8.08 | 4.7% | |
| `p-stub` | 7.24 | 4.2% | stub pass |
| `pu` | 6.27 | 3.6% | pull_uses (2 calls) |
| `2-all-spliced` | 5.18 | 3.0% | splice pass |
| `3-scanned` | 3.12 | 1.8% | u_scan/u_prep |
| `pre-u` | 2.84 | 1.6% | |
| `5a-flat0` | 2.02 | 1.2% | |
| rest | 2.3 | 1.3% | |

On `tests/all.sov` (68.4 ms instrumented): `bw` 42.0%, `3-scanned` 11.8%,
`W-walk0` 11.5%, `c0-parsed` 7.9%, `pu` 6.9%, `C1` 5.9%.
Parse-to-IR is fully native: statement_native_trees 52,317/52,317 (self),
8,803/8,803 (all).

## Decline fix (landed 2026-11-01)

Root cause of the all.sov regression: `tools/native_syntax.c` deliberately
declined (BAD=11) any string literal containing ` is `, ` or `, ` and `
` so a legacy `cops` compat path could rewrite it, and set the `h[15]`
short-circuit flag for `&&`/`||` *inside string content*. 350 of 1,006
fast-path spans on all.sov declined → double parsing.

String content is data, not syntax. Verified empirically: string args
containing ` is `/` and `/` or ` reach the runtime byte-identical through the
fast path (`file_write_all` probe). The interpreted fallback lexer never had
either behavior, so the native lexer was made to match it: both the BAD=11
scan and the in-string `h[15]` set are removed. Emitter regenerated
(`build_native_syntax.py`, 7,593 bytes, sha256 `d719f9ed…`).

Result (R15 rotating A/B, `work/p0/ab_cops_decline.json`):

| workload | before | after | speedup |
|---|---|---|---|
| all | 57.60 ms | 55.05 ms | **1.046x** |
| self | 145.99 ms | 143.84 ms | **1.015x** |
| x86ins | 23.85 ms | 23.99 ms | 0.994x (noise; only 2 declines there) |

Declines: all.sov 350 → 14, self 84 → 0, x86ins 2 → 0.

The remaining 14 all.sov declines are rc 5 on `str_cat` code-template spans
whose strings contain *doubled inner quotes* (`"... arm_load(a, "/tmp/x.bin") ..."`).
The slow path supports doubled quotes; the native lexer does not, so it
declines and the correct compat path handles them. Implementing doubled-quote
scanning in the native lexer is open; worth ~1% on all.sov, deferred as it
touches string semantics.

## Measurement discipline (in force)

- `tools/speed_gate.py --require-ratio` for gate claims; R>=12, medians.
- `tools/ab_speed.py` rotating interleaved A/B with per-round byte-identity
  (`--allow-layout-diff` only when the seed image legitimately differs).
- `tools/no_cache_policy.py` + `tools/cache_tree_guard.sh` clean.
- Fixed point = two-generation byte identity (`track1_gates.sh`).
- Profiler: `compiler --prof <src>`; decline spans dumped to
  `/tmp/sov_decline_spans.txt` (400-span cap, 300-char cap in this build).
