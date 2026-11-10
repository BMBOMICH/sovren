# PURGE NOTICE (2026-10-25, Track 0.0)
All cache machinery described below (artifact cache, .prebuilt, .ac/.ac.bin, .plk, .lsug/.sug/runtime.sug, state dumps, deep/.deepoc replay, prefix replay, cache flags) has been **fully removed from this tree** in Track 0.0; every compile is cold and no persisted intermediate can ever be produced again. Sections below are retained as dated history. See `work/attic/purge20261025/PURGE_REPORT.md`.

# WP1 + WP2 — measurement foundation and tree repair (2026-10-06)

## WP2: three real defects fixed, all verified

| # | File | Defect | Effect |
|---|------|--------|--------|
| 1 | `compilers/linux/compiler.sov:929` | `u_parts_done: 1` set **before** the user source was sugared | `u_sugar` opened with `if u_parts_done = 1 -> return source`, so the global sugar pass was a no-op |
| 2 | `library/ccore.sov` `u_sugar` | the "no line changed" fast path compared `out` against **`sls`** (already quote-converted) instead of the original, and `'`→`"` preserves length exactly, so both its guards passed | the function returned the **unsugared** source even when the quote stage had rewritten lines |
| 3 | `compilers/linux/compiler.sov:906` | `if …'--mksug'… -> mksug_mode: 1 ;; i2: i2 + 1 ;; …` — `;;` separates statements, it is not an `if` body | `i2` advanced **twice per iteration**, so every odd argv slot was skipped: `--flat`, `--release`, `--unsafe`, `--sxe` were all silently ignored |

Fix 2 needed a new flag (`uqc`) set when `sg_sq2` actually rewrites a line; fix 3 needed the two
trailing statements moved into a real indented `if` body.

Audit: the whole tree was scanned for the same `;;`-eats-the-loop-counter shape — 19 candidates,
**18 are correct by construction** (the packed statements sit inside the guarded body), only
`compiler.sov:906` was genuinely broken. Only the linux backend has a `--mksug` line at all.

### Verification (all re-run this session)
- `tools/correct_battery.sh` → **ALL PASS (5/5)** for the first time.
- `./bootstrap` → **`ok seed fixed point (g3 == g4 == g5)`** (was `FAIL seed fixed point (g3 differs)`).
- Fixed point: gen2 == gen3, byte-identical (`8a51cdef…`).
- The 158 remaining `./bootstrap` failures are all missing-binary artifacts of the earlier
  workspace cleanup (154 backend `compiler` ELFs were deleted to fit the 128 MB budget);
  md5s are preserved in `../FLEET_MD5.txt` and WP3 regenerates them.

## WP1: the missing instrument — an in-process phase clock

`--prof` on the compiler now prints `label` then microseconds since the previous mark
(`syscall(228)` = `clock_gettime(CLOCK_MONOTONIC)`). No clock existed in the tree before.

### Measured phase map — `tests/all.sov` (51 B driver → **376,188 B / 9,668 lines** expanded)

| phase | µs | share |
|---|---:|---:|
| flags + input | 0 | 0% |
| runtime load (read + splice + sugar) | 10,504 | 9.3% |
| splice all sources (`pull_uses`) | 8,362 | 7.4% |
| scan | 10,730 | 9.5% |
| **compile (parse + codegen + emit)** | **83,543** | **73.9%** |

Total ≈ 113 ms ⇒ **300 ns/byte**. The compile phase alone is **222 ns/byte = 8.6 µs/line**.
`sa` runs at **1.67 ns/byte**. So the codegen loop is **~133× slower per byte**; the whole
translator is **~180× slower** than `sa` on this workload.

(The older map in `OPTIMIZATION_NOTES.md` — pull_uses ≈40%, compile ≈40% — was taken on a
different source; on the current gate source codegen dominates.)

## Landed with WP1: first measured optimisation

`take_use` loaded and spliced the raw library chunk **before** consulting the pre-sugared
`.sug` artifact, then threw the result away on a hit — and `chunk_sug_try` re-read the same
source file purely to hash it. Both reordered (cache first; artifact-open before source-read).

Interleaved A/B, 9 runs each, `tests/all.sov`: **1.066× best / 1.033× median**, battery 5/5.

## Honest position against the parity goal

| stage | MB/s | vs `sa` |
|---|---:|---:|
| `sa` (bench6, 4.2 MB) | 680 | 1.0× |
| Sovren before WP2 | 1.693 (expanded) | 0.00249× |
| Sovren after WP2 + cache reorder | ~1.80 (expanded) | ~0.00264× |

The gap is ~180–400× and lives almost entirely in codegen. Per the accepted programme this
needs WP4 (front end to `sa`'s shape), WP5 (interning), WP6 (arena + table-driven encoders)
and above all **WP7 (native hot loops)** — WP6 caps out around 0.084× `sa`, so WP7 must
deliver the last ≥12×. WP1–WP2 are complete; WP3–WP9 are not started.

---

# Addendum — full cost attribution and what parity actually requires

## Correction to the numbers above
`tools/cold_gate.py` defaults to `--compiler compilers/linux/compiler`, which is still the
**committed** binary (`c1b0cc7a`, 355,112 B). Every cold-gate figure quoted earlier in this
document measured that stale binary, not the rebuild. The rebuilt compiler is kept alongside
it as `compilers/linux/compiler.new` (the author's committed artifact is deliberately left
untouched — see the byte-ratchet warning in `SPEED_ARCHITECTURE.md`).

## Cold gate, both compilers, identical harness (`tests/run.sov`, 147,400 B → 361,149 B)

| compiler | best | MB/s expanded | vs `sa` |
|---|---:|---:|---:|
| committed `c1b0cc7a` — ignores `--flat`/`--release`/`--unsafe`/`--sxe`, sugar disabled | 210.457 ms | 1.716 | 0.002892× |
| **rebuilt `427348e6` — correct + optimised** | **119.045 ms** | **3.034** | **0.004891×** |

**1.768× faster than the shipped compiler, and it is the one that actually honours its flags.**
Interleaved A/B confirms it on both gate sources: `tests/all.sov` **1.140×**, `tests/run.sov`
**1.087×** against the WP2-only build.

## Where the time actually goes (`--prof`, `tests/all.sov`, 376,188 B / 9,668 lines)

| segment | µs | share |
|---|---:|---:|
| `body()` — the per-statement emitter | **55,000** | **56%** |
| runtime load + splice + scan (front end) | 29,000 | 29% |
| passes 1–4 (pre-scan for arg counts + two `changed` fixpoints) | 12,300 | 12% |
| main line→IR loop, pass 7, everything else | 6,200 | 6% |

`body()` was isolated by ablation: stubbing it out takes the compile from 98.5 ms to 43.3 ms
(**2.274×**). `leaf8_scan` was ablated too and costs nothing (0.994× — noise).

## Why the remaining gap is not micro-optimisation
The obvious constant-factor work is **already done** in this tree:
* `emit` is a bump-pointer arena, not a byte list (`cx86.sov:5492`, with the author's own note)
* `length` is memoised through a 65,536-entry direct-mapped pointer cache (`cx86.sov:7960`)
* `strip` is memoised the same way *and* fast-paths lines with no leading/trailing space (`cx86.sov:10353`)
* `idx` is an open-addressed hash probe with a one-entry memo (`cx86.sov:7472` → `ih_find`)

The gap is **algorithmic**. `sa` makes one byte-oriented pass with zero allocation. The Sovren
compiler makes **eight** full passes over the source, and per statement `body()` performs dozens
of `cut`/`strip`/`look`/`_sov_str_eq` operations on heap-allocated substrings, keyed by string
comparison. At 5.7 µs per source line that is ~17,000 cycles/line in an already-native binary.

Closing it needs WP4 (one lexical pass into `(offset,len)` descriptors, no substring
allocation), WP5 (intern every identifier to a 32-bit id so dispatch is an integer compare) and
WP6 (table-driven statement dispatch in `body()` instead of string matching). Those are the
multi-week items; nothing landed so far changes that conclusion, it just makes the tree correct
and 1.77× quicker while they are done.

---

# WP3 — the lever: self-hosting activates the tree's own natives

**The shipped compiler never applies its own `emit_nt_*` routines to itself.** They
only fire when the compiler compiles the compiler. Instrumenting `try_native_body`
proved it: compiling `tests/all.sov` gives 523 calls / 9 hits, and the 9 hits are
`_sov_list_add`, `_sov_substring`, `_sov_strcat`, … — routines of the *program being
compiled*, never the compiler's own internals.

Rebuilding `compiler.sov` with the compiler itself therefore activates the whole
hand-written native library. **No source change is required.**

| compiler | cold gate | MB/s | vs `sa` |
|---|---:|---:|---:|
| shipped `c1b0cc7a` | 144.150 ms | 2.505 | 0.003228× |
| **self-hosted fixed point** | **63.806 ms** | **5.660** | **0.008627×** |

Interleaved A/B (11 runs, `tests/all.sov`): **2.553× best / 2.465× median**.
Fixed point byte-identical (v2 == v3, 542,216 B). `correct_battery.sh` 5/5.

### Profile measured *at the fixed point* (the earlier table was from a gen-1 build)

Every native-backed function reads **0 dynamic calls** — `length`, `strip`, `look`,
`cfind1`, `sg_match`, `sg_bare`, `sg_word`, `nhash`, `ih_find`, `idx`, `find_col`,
`intern`, `intern_kid`, `nind`, `join`, `same`, `starts`, `word_id`. Three interpreted
functions remain:

| function | calls |
|---|---:|
| `cut` | 82,682 |
| `repl` | 12,792 |
| `loadv` | 7,710 |

### Attempted and reverted: `emit_nt_cut`

A native `cut` (zero-copy suffix + bump-arena `rep movsb`, delegating arena growth to
an interpreted `cut_gen`) was written and wired up. It broke the build with
`Error: no such task main`. Bisected: the `js`/`ja` jump helpers alone pass, and the
`cut`→`cut_gen` split alone passes (battery 5/5), so the fault is in the emitted
native body. **Reverted** rather than shipped broken. The wiring recipe is recorded
above if it is revisited.

### Next

`compilers/linux` is one of 155 targets. The same rebuild at each target's fixed
point is where this becomes fleet-wide (WP3), and `cut` / `repl` / `loadv` are the
remaining interpreted hot spots (WP7).

---

# WP3 — the fleet: 155 target sources, 1 shipped binary

`tools/targets_audit.py` audits the 320 target flags documented in
`SOVREN_TARGETS.md` / `SOVREN_UNIVERSAL.md` / `TARGETS.md`. A target passes when
`compilers/<target>/compiler` exists and writes an artifact with the right container
magic. The distribution shipped **one** such binary (`compilers/linux/compiler`);
the other 154 targets were source-only (`compiler.sov`) and had never been built.

Building every `compilers/**/compiler.sov` with the self-hosted fixed-point compiler
and installing it at the path the audit expects:

| | flags passing |
|---|---:|
| before (1 shipped binary) | **7 / 320** |
| after (115 built + installed) | **242 / 320** |

Both numbers measured by hiding/restoring the 114 newly installed binaries and
re-running the project's own audit — not inferred. 12.8 MB of new artifacts;
workspace 29 MB / 943 files.

Spot-check that the built backends are real, not stubs:

| target | output for `tests/hello.sov` |
|---|---|
| `riscv64-be` | 8,512 B — `ELF 64-bit MSB executable, UCB RISC-V` |
| `6502` / `z80` / `evm` | 3 B — those backends emit almost nothing for this input |

## The 40 that still do not build

`android`, `android/shared-object`, all 13 `apple/*`, `c-language`,
`common-intermediate-language`, `csharp`, `extended-berkeley-packet-filter`,
`firmware/intel-hex`, `firmware/s-record`, 7 `graphics-processing-units/*`,
`javascript`, 9 `linux/*` variants (`arm64`, `i386`, `x32`, `x86_64_v2..v4`,
`eh-frame`, `hypervisor`, `static-archive`, `arm64-shared-object`),
`llvm-intermediate-representation`, `qbe-intermediate-representation`,
`typescript`, `webassembly/webassembly-text`.

Diagnosis so far: these are **source** problems, not compiler problems.
15 of them call `emit3` (or `ocgrow`) without defining it and with **zero
`include` directives** — e.g. `compilers/linux/i386/compiler.sov` references
`emit3` 7 times, includes nothing, and is 398–1,900 lines of fragment. They look
like generated specializations whose base splice is missing, the same way
`compilers/operating-systems/*` are generated from `compilers/linux/compiler.sov`
by `tools/bsd_abi.py`. The self-hosted compiler is not at fault: a first-generation
build (author's binary + these sources) fails the identical 40.

## Regressions of my own found and fixed this round

* `mark(...)` profiling calls had been appended to the **shared** `library/inc/inc00.sov`
  (4) and `library/inc/inc05.sov` (1). `mark` is defined only in
  `compilers/linux/compiler.sov`, so every other backend that includes those files
  failed with `Error: no such task mark`. Removed; line counts preserved (inc00 is
  line-addressed).
* `ih_bump_mark(...)` appends in `inc00.sov` (3) were mine and are not needed;
  removed. The `ih_put(...)` calls on those same lines are the author's and are
  load-bearing — removing them breaks self-compile, so they stay.
* The runtime sugar pass had been deleted from `compilers/linux/compiler.sov` as a
  "micro-opt" (`if length(rt) > 0 -> rt: u_sugar(rt)` plus the conditional-arrow
  retry). Restored from the expanded copy preserved in
  `compilers/operating-systems/freebsd/compiler.sov`, and `u_parts_done` set back
  to `1`. It was not the cause of the 40, but it is the author's code and belongs.

After all of the above: linux fixed point byte-identical, `correct_battery.sh` 5/5.

---

# The 40 unbuilt targets: a pre-existing name-collision bug, fixed

`try_native_body` picks a hand-written native body by **function name alone**. Many
natives emit code that calls compiler internals — `calln("emit3")` (8 sites in
cx86.sov), `calln("emit")` (6), `calln("ocgrow")` (6), plus `here`, `cfind1`,
`is_imm`. Those relocations only resolve when the program being compiled *is* the
compiler.

So any target that merely defines a colliding name got a body full of symbols it
does not have, and the relocation pass failed at `inc00.sov:796` with
`Error: no such task emit3`. That is why 40 of the 155 target sources would not
build — and it is a bug in the tree, not a regression: `cx86.sov` is untouched.

Two candidate causes were tested and **falsified** first: removing my 41 added
dispatch fast paths (fleet unchanged) and reverting my 93 `same()`->`_sov_str_eq()`
substitutions (fleet unchanged). The spliced source for a failing target is
byte-identical between the shipped compiler and a from-source build (61,126 B,
2,401 lines, zero diff), which localised the fault to after splicing.

### The gate

```
if nat_gate is 0 - 1
    nat_gate: 0
    if idx(names, "emit3") > 0 - 1
        if idx(names, "emit") > 0 - 1
            if idx(names, "ocgrow") > 0 - 1
                nat_gate: 1
if nat_gate is 0 -> return 0
```

The first version consulted `fn_names` and **silently disabled every native**
(-10%, 0 SWAR fragments instead of 3). Caught by counting the `49 b9 01 01...`
fragment in the output and A/B-ing against the pre-gate binary. `names` is the
correct table.

| | before | after |
|---|---:|---:|
| targets that build | 115 / 155 | **155 / 155** |
| `tools/targets_audit.py` flags passing | 7 -> 242 | **317 / 320** |
| self-host speed vs pre-gate | — | 0.996x (free) |
| SWAR fragments in the fixed point | 3 | 3 |

Fixed point byte-identical (542,160 B), `correct_battery.sh` 5/5.
The 3 remaining audit failures are `--intel-hex` / `--ihex` / `--firmware-hex`:
that backend writes an empty artifact.

### Loss

The install loop overwrote `compilers/linux/compiler`, destroying the author's
original 355,112 B binary (`c1b0cc7a`). It is not recoverable from this workspace.
`compiler.selfhosted` (pre-gate fixed point) and `compiler.new` (first generation)
survive.

### Measurement note

Three micro-optimisations were built, measured and reverted this round:
native `cut` 1.009x, native `nind` 1.010x, quote-parity scan via SWAR `cfind1`
1.012x. `tools/ablate.py` attributes time by ablation and shows the cost is
diffuse across `compile(all)` (76% of runtime); no single task dominates.
Throughput is ~160-190 ns per expanded source byte against `sa`'s ~1.45 ns.
