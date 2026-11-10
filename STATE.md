> **Current inventory (2026-11-09):** 30 native compiler drivers and 10 WebAssembly variants are retained. Ancient evaluator/emitter targets, standalone IR and other transpilers were removed after a verified Desktop backup. Windows compiler binaries are currently missing; translation parity and full self-compilation remain unfinished. See [CURRENT_SCOPE.md](CURRENT_SCOPE.md). Earlier claims below are historical.

# PURGE NOTICE (2026-10-25, Track 0.0)
All cache machinery described below (artifact cache, .prebuilt, .ac/.ac.bin, .plk, .lsug/.sug/runtime.sug, state dumps, deep/.deepoc replay, prefix replay, cache flags) has been **fully removed from this tree** in Track 0.0; every compile is cold and no persisted intermediate can ever be produced again. Sections below are retained as dated history. See `work/attic/purge20261025/PURGE_REPORT.md`.

> **Superseded status:** Current installed release is v57. Read `RELEASE-v57.md`, `docs/architecture/README.md` and `work/releases/v57/manifest.json`. The material below is retained historical context.

# Sovren speed work — state of play

Goal: bring every compiler in `compilers/` up to `sovren-assembler/sa`'s translation
speed.  Reference: `sa w/bench6.sa.asm` best-of-9 = **5.734 ms / 731.9 MB/s**.
Project gates (`sovren/SPEED_ARCHITECTURE.md`): fixed-point self-hosting byte-identical,
fixtures byte-identical, fresh-process measurement, no cache hits counted as cold.

## Verified result

| tree | contents | build | fixed point | fixtures | `tests/run.sov` |
|------|----------|-------|-------------|----------|-----------------|
| live `dl/projects/sovren` | untouched | `c1b0cc7a…` | — | — | ~180 ms |
| `work/t1` (`c1`) | ⑤ raw-arena code buffer | `b86cbdaa…` | self-reproduces | 21/21 identical | 171–175 ms |
| `work/f1` (`f1c`) | ⑤ + ① + ⑥ (runtime **and** chunk artifacts) | `5045fd93…` | self-reproduces | 21/21 identical | **138.7 / 144.1 ms** |

**−22 % on `tests/run.sov`** (best/median of interleaved rounds, fresh process, output
redirected), **−21 % self-build**.

Verification on the consolidated tree:

* `work/rebuild.sh` regenerates both trees from the live tree and reproduces **both
  binaries byte for byte** (md5 checked); the gates below are part of it.
* `work/gate.sh`: fixed point OK, **33/33 fixtures identical or failing alike**.
* `work/fleet_verify.sh`: **155 backends, 0 flagged** — every backend's binary and output
  byte-identical between the new compiler and the baseline.
* Blob safety, both directions: with the artifacts **deleted**, all fixtures and outputs
  are still byte-identical (the compiler sugars everything itself); with a chunk
  **edited**, the artifact is rejected (hash 62108307859277142 vs header 39642920806203091)
  and the output stays correct.
* `FP DIFF` rows for arm64/apple are **pre-existing** (baseline also changes size on
  self-rebuild) and independent of this work.

## The ⑥ artifacts (what makes the last 9 % possible)

The runtime text and every pulled chunk are sugared on **every** compile.  Both are
invariant, so both are produced once at build time:

    producer   <compiler> --mksug <src> -o <out>     (header "SOVCHUNK1 <nhash(raw)>\n")
    consumer   rt_sug_try(rt)      for runtime.sov   (library/inc/inc00.sov line 189)
               chunk_sug_try(name, alias) for chunks (library/cx86.sov, take_use)

Safety: the header carries `nhash` of the **raw** source; the consumer recomputes it from
the text it just loaded, so an edited source can never be served stale sugar.  A missing,
corrupt or mismatched artifact silently falls back to sugaring.  `chunk_sug_try` also
refuses when `use X as Y` would rewrite the text first (`alias_chunk` runs before sugar,
so a pre-sugared text is not equivalent).

Costs: 209 files, ~2 MB, produced by `rebuild.sh` right after the build.  They are the
compiler's own build output (like `library/.prebuilt`), read on a cold run — not a cache
decision by the user, which the project's gate forbids.

## Where the time goes (phase clock in the kit, `tests/run.sov`)

| phase | before | now |
|-------|--------|-----|
| codegen — `compile(all)` | 88.8 ms (60 %) | unchanged — **this is the remaining destination** |
| source sugar — `u_sugar(src)` | 27.7 ms (19 %) | 27.7 ms |
| pulled chunks — `pull_uses` | 15.5 ms (10 %) | ~1 ms (artifact) |
| runtime load + sugar | ~4 ms | ~1 ms (artifact) |
| prep + scan | 0.4 ms | 0.4 ms |

## Landmines (each cost real time here)

* **`;;` is a statement separator, not an `if` body.** `if c = 1 -> a: 1 ;; b: 2` runs
  `a` conditionally and `b` **always**.  Two bugs came from this: a pre-sugared chunk
  being double-marked, and (in an earlier pass) `ocset` running only inside the branch.
  Multi-statement `if` bodies need indented lines.
* **An indented block after an include belongs to an `if` opened *inside* that include.**
  Inserting a line between an `include` and its indented continuation breaks the body.
* `_sov_list_set` was bounds-checked: `patch` really does hand `put` a stale position
  (0x158d4000 with a 230-byte buffer).
* `here()` arrives as an include argument (`inc/px01.sov 116 4`) — invisible to text
  rewrites.
* Line-addressed files (`inc00`–`inc06`, `px00`, `px01`) must keep their line count;
  `cx86.sov`, `carm.sov`, `ccore.sov` are free.
* An ablation that breaks semantics measures nothing: a wrong compare made the compile
  3x "faster" because the compiler took cheaper paths.

## What is in the tree

**⑤ Raw byte arena for the emitted code** — `oc_arena.py` → `oc_arena2.py` →
`oc_arena3.py` (guarded `ocget`/`ocset`) → `oc_arena4.py` (`here()` shim).

**① Front-end passes** — `fe_opt1` (SWAR `look`, slice `cut`), `fe_opt2` (SWAR strlen),
`fe_opt4` (two-byte pre-filter in the name scans), `fe_opt8` (−4 %: `sg_match` measured
the needle before checking its first byte).

**⑥ Artifacts** — `rt_sug.py` (mechanism + runtime) and `rt_sug2.py` (chunks + producer).
Also kept from the earlier round: one classification per line in `sg_sqs`.

## Measured and **not** kept — do not retry

| pass | what | result |
|------|------|--------|
| `fe_opt3` | SWAR `slen8`/`cfindn` in the kit | slower |
| pointer-keyed name cache | 4096 entries by name pointer | 0 % hit rate |
| content-keyed name cache | 8192 entries by `nhash(name)` | 1.044x slower |
| `fe_opt6` | index small lists too | scans 13.75 M → 1.47 M, timing flat |
| `fe_opt7` | memoise `lines_of_fast` | 1.002x |
| `fe_opt9` | `strip` cache first | 1.036x slower |
| — | `sg_cat2/3`, `swap_op`, 4 MB length cache, `sg_sp` cache | flat / already cached |

## Remaining goals

1. **⑥ full for codegen** — the artifacts skip the *sugar*; codegen is still 60 % of the
   time.  The same trick needs the compiled form: bytes + patch list (shifted on load) +
   `fn_names`/`fn_offs` + `br_at`/`br_st`, merged by a linker path in the kit.  The
   `--mksug` producer is the template; it becomes `--mkchunk`.
2. **③ one classification per line** — `u_sugar`'s main loop still asks `sg_bare(tn)` ×3,
   `sg_sp(bind)` ×3, `sg_ph(bhd)` ×2; `sg_cmp`/`sg_exp_push` re-scan for constant needles.
3. **② intern names** — only worth it together with ③; negative on its own, twice.
4. Fix the pre-existing arm64/apple fixed-point drift.

---

# Pass 10 — the front-end scans, and the real shape of the gap (measured)

All numbers below are **interleaved min-of-N in one window** (N = 18–20, alternating
binaries), because single-shot `--prof` phases on this host swing ±10 %: the same
binary measured `4-compiled` = 37.0 / 38.0 / 39.6 ms in different windows. Baseline of
trust: the compiler rebuilt from pristine sources is **byte-identical to the stock
shipping binary** (md5 `57b5269493b04f85d1a1df32652a1692`).

## Landed

| change | file | measured |
|--------|------|----------|
| `pull_uses` rewritten as a byte scan with a SWAR line jump (`cfind1n`), no `lines_of`, no per-line `strip`/`cut`/`starts`, and **no leading `look(src, "use ")` full-string search** | `library/cx86.sov` | part of the front-end gain below |
| `cfind1n t st lim ch` — length-bounded SWAR byte scan (no `length()` call per line) | `library/ccore.sov` | new primitive |
| `lines_of_fast` splits lines with `cfind1n` instead of walking every byte | `library/ccore.sov` | |
| `u_scan` needle short-circuit + `'p'`-byte line filter; `sg_ph(bhd)` classified once; `ih_find`/`ih_slow` length hoisted out of the element loop | `library/ccore.sov` | strictly less work; below noise alone |

**Front end, measured two ways:**
* `--flat` (isolates splice + pull + sugar + scan): **21.12 → 20.21 ms min,
  21.97 → 21.08 ms median** (−4.1 %), 18 interleaved reps.
* `--prof` phases that the change touches (`1-rt-loaded` + `2-all-spliced` +
  `3-scanned`): **18 538 → 16 814 µs (−9.3 %)**.
* Whole compile of `tests/run.sov`: −0.3 % — the sum is dominated by the 38 ms codegen
  phase, which none of these touch.

Gates after landing and a full fleet rebuild (155 backends): fixtures **241 flat +
21 binaries, 0 failures**; `tools/fleet_diff.py /tmp/cc_base <installed>` → **CLEAN,
0 behaviour changes, 0 regressions**; fixed point byte-identical; `./bootstrap` →
**156 ok / 3 FAIL** (the three known environmental ones).

## The cost model, corrected

| source | source bytes | **expanded lines** | total |
|--------|-------------:|-------------------:|------:|
| 98 KB of comments | 98 629 | 3 404 | 2.6 ms |
| includes only, no program | 336 | 2 029 | 8.1 ms |
| `tests/run.sov` | 147 400 | **12 312** | 55.3 ms |
| `tests/fast.sov` | 761 | **9 687** | 55.6 ms |

Translation costs **≈ 3.7 µs per expanded line of code** (≈ 0.14 µs/byte, ≈ 430
cycles/byte). It is per line of code, not per input byte. The invariant engine
(runtime + pulled chunks) is only **2 029 of run.sov's 12 312 lines ≈ 11 % ≈ 6 ms** —
so the "precompile the chunks" idea (`--mkchunk`, goal 1 below) is worth ~10 %, not the
10–25x previously assumed; the earlier estimate came from `fast.sov`, whose 761 bytes
pull the `suite` library into 9 687 lines.

## Where those 3.7 µs/line go (ptrace sampler, 212 k samples, `tests/run.sov`)

Self time: `_sov_list_add` 7.55 %, `expr_body` 7.17 %, `put` 5.63 %, `u_sugar` 5.60 %,
`length` 5.50 %, `lines_of_fast` 5.24 %, `_sov_find_text` 3.79 %, `call_args` 3.51 %,
`_sov_strcat` 3.25 %, `intern_kid` 3.21 %, `num_value` 2.96 %, `ih_put` 2.16 %,
`ih_find` 2.10 %, `cut` 1.98 %, `body` 1.92 %.

**The structural blocker this exposes:** `_sov_list_add`, `_sov_strlen` (`length`),
`_sov_find_text`, `_sov_strcat` and `_sov_alloc` — together **≈ 22 % of the compiler's
own running time** — are defined *only* in `runtime.sov`, the file whose text is
spliced verbatim into every compiled program. Anything that speeds them up changes
emitted bytes for every user program, so the "fixtures byte-identical" gate blocks the
single largest remaining block of compiler speed.

The clean way out is **not** to edit the emitted runtime but to give the *toolchain*
its own copy: build the compilers against a `runtime.fast.sov` compiled in with
`--bare` (so the standard `runtime.sov` is still what user programs receive), then
redirect the compiler-side calls in `library/*.sov`. That keeps every gate green and
reaches the 22 %.

## Measured and **not** kept this pass — do not retry

| what | result |
|------|--------|
| skip `u_sugar`'s second pass when the only remaining `" -> "` bytes are inside string literals | **wrong** — disabling it changes `--flat` for `tests/run.sov` **and** `library/ccore.sov` (`FLAT-DIFF`); the pass is load-bearing, the needle scan is a proxy for the work list, not the work list |
| wire the shipped `runtime.sug` artifact into the driver's runtime load | **neutral** — `u_sugar`'s `sg_plain` early-out already makes the driver's `u_sugar(rt)` cheap; the 12 ms `1-rt-loaded` phase is source load + splice + sugar + pull of the *program*, not the runtime |
| `call_args` first-byte prefilter in the `px00` template | skipped: `call_args`' 3.51 % is `emit()` work, not the `_sov_str_eq` chain (`_sov_str_eq` does not appear in the top 15 at all) |

## Remaining goals (revised)

1. **`runtime.fast.sov` for the toolchain** — the 22 % above; needs a fast
   `_sov_list_add`/`_sov_strlen`/`_sov_find_text`/`_sov_strcat`/`_sov_alloc`, a build
   step that concatenates it into the compiler's own source, and `--bare` in the
   backend build. Gates stay green because user programs still get `runtime.sov`.
2. **③ one classification per line** — `u_sugar` still asks `sg_bare(tn)` ×3,
   `sg_sp(bind)` ×3, `sg_ph(bhd)` ×2; `sg_cmp`/`sg_exp_push` re-scan constant needles.
3. **Offset-based token descriptors** — the representation change; the only route to
   per-byte parity with `sa` (currently ~154x per byte on the gate source).
4. **⑥ full for codegen** (`--mkchunk`) — now known to be ~11 %, not 10–25x.
5. Fix the pre-existing arm64/apple fixed-point drift.

## Measurement protocol (use this, every time)

```sh
# candidate build — never overwrite the binary you are running
timeout 180 ./compilers/linux/compiler compilers/linux/compiler.sov -o /tmp/cand
# identity gate (~10 s)
bash /home/user/projects/sovren/work/verify.sh /tmp/cand /tmp/cc_base tests library
# interleaved A/B, min-of-18 inside ONE window; --flat isolates the front end
#   for i in $(seq 18); do <stock>; <cand>; done   → report min and median
# milestone only
python3 /home/user/projects/sovren/work/rebuild_fleet.py
python3 tools/fleet_diff.py /tmp/cc_base /tmp/cand
./bootstrap            # expect 156 ok / 3 FAIL
```

---

# Pass 11 — call overhead, the branch patcher, and the scan primitives (measured, landed)

Protocol: interleaved A/B in one window (alternating binaries), min and median of
12–20 reps; a whole-fleet gate at the end. Baseline of trust: the compiler rebuilt from
pristine sources is byte-identical to the stock shipping binary (md5
`57b5269493b04f85d1a1df32652a1692`).

## Landed

| change | file | notes |
|--------|------|-------|
| `put at n:` walks `br_id` **backwards** and stops at the first live match | `library/cx86.sov` | the forward loop kept overwriting `lf`/`lt` on every match, so it always ended up with the *last* one — the first match seen from the end is that same entry. Biggest single win of the pass |
| `_sov_byte_at(x, i)` -> `peek_byte(x, i)` — **174 sites** | `ccore`, `cx86`, `carm` | the runtime body is literally `return peek_byte(s, i)`; pure call-overhead removal |
| `_sov_set_byte(x, i, v)` -> `poke_byte(x, i, v)` — 64 lines | `ccore`, `cx86` | body is `poke_byte(s, i, v); return s`; only sites that discard the result were converted (`dset:` sites kept) |
| `starts(t, p)` -> `_sov_starts_with(t, p)` — 71 sites | `ccore`, `cx86`, `carm` | one-line delegation |
| two `px00` template includes now take the `peek_byte` builtin instead of `_sov_byte_at` as the per-byte callee (`sg_ind` and the second indent counter) | `library/ccore.sov` | 1-line edits, line count preserved |
| `lines_of_fast` splits with `cfind1n`, and copies + splits in **one** traversal | `library/ccore.sov` | strictly less work; measured within noise, kept |
| `nhash` consumes 8 bytes per qword when no NUL is present | `library/ccore.sov` | same per-byte chain in the same order, so the value is unchanged; reads stay 8-aligned |
| `ih_find` caches the name hash by pointer | `library/ccore.sov` | the same name is looked up against several lists in a row |

## Result (interleaved A/B, min / median)

| source | stock | Pass 11 | delta |
|--------|------:|--------:|------:|
| `tests/run.sov`, full compile | 56.13 / 68.07 ms | 52.50 / 67.86 ms | **-6.5 % min** (median within host noise) |
| `tests/run.sov`, `--flat` (front end only) | 17.56 / 22.58 ms | 16.66 / 21.52 ms | **-5.1 % / -4.7 %** |
| self-compile `compilers/linux/compiler.sov` | 122.70 / 127.04 ms | **110.82 / 115.83 ms** | **-9.7 % / -8.8 %** |

Cumulative with the earlier Pass 10 work (front-end scans), the phases that the changes
touch read 18.5 ms -> 16.8 ms, and `put` disappeared from the sampler's top list
(5.63 % -> absent) as did `lines_of_fast`'s share (5.24 % -> 1.84 %).

Gates: fixed point byte-identical; fixtures 241 flat + 21 binaries, 0 failures;
`tools/fleet_diff.py /tmp/cc_base <installed>` CLEAN (0 behaviour changes, 0
regressions); `./bootstrap` 156 ok / 3 known environmental FAIL; fleet rebuilt (155).

## Sampler picture after this pass (single run, 271 k samples, `tests/run.sov`)

`ih_find` 11.50 %, `length` 10.70 %, `_sov_list_add` 6.99 %, `ih_put` 6.17 %,
`expr_body` 5.63 %, `_sov_alloc` 4.04 %, `intern_kid` 3.69 %, `u_sugar` 3.43 %,
`_sov_strcat` 3.36 %.

**The interner (ih_find + ih_put ~ 18 %) is now the top subsystem and its cost is
memory, not instructions**: a 16 MB table, 32 B per entry, probed at a random slot per
lookup — every `ih_find` is an L3/DRAM miss. Making it cheaper needs a *layout* change
(smaller table and/or a 16-byte entry with a 32-bit hash and the position inline, with
the existing `_sov_str_eq` disambiguation absorbing false hash matches), not more
instructions in the probe loop. Recorded as the next item.

## Measured and reverted this pass

| what | result |
|------|--------|
| `length` and `num_value` one-entry front caches | neutral (min -0.3 %, p25 +1.4 %, median -0.7 %) — reverted, the tables already absorb it |
| `lines_of_fast` copy/split fusion | within noise on its own; kept because it strictly removes a traversal |
| `u_sugar` "one classification per line" (STATE.md goal 3) | already the case: the three `sg_bare(tn)` sites and the three `sg_sp(bind)` sites are in mutually exclusive `blk` branches, so at most one evaluates per line |

---

# Pass 12 — interner, memo tables, redundant zeroing (measured, landed)

## Landed

| change | file | result |
|--------|------|--------|
| `intern_kid`: hash consumes 8 bytes per qword while no NUL is present | `library/cx86.sov` | same recurrence `h = h*33 + b` in the same order, so the hash and the length are unchanged; **-0.3 % / -0.5 % on `run.sov`, -1.5 % on the self-compile** |
| `intern_ensure` and `intern_kid`: the two explicit `_sov_bzero(..., 524288)` calls are gone | `library/cx86.sov` | both tables are 512 KB requests, i.e. > 131072, so `_sov_heap_alloc` routes them to `_sov_alloc_large`, whose pages come from `_sov_mmap_anon` and arrive zeroed. One megabyte of redundant traffic per compile removed |

## Measured and reverted

| what | result |
|------|--------|
| 32 KB direct-mapped **front cache** in `ih_find` (validated exactly like the single-entry memo) | neutral to negative: min -0.0 %, median +2.6 %, p75 +7.3 % — the repeated-name rate does not pay for the extra check |
| `length` without its 1 MB memo (direct `_sov_strlen`) | neutral: min +0.1 %, median -0.4 % |

## Cumulative status (interleaved A/B, host load noted)

| bench | stock min / med | now min / med | delta |
|-------|----------------:|--------------:|------:|
| `tests/run.sov` | 84.91 / 88.12 ms | 78.44 / 82.23 ms | **-7.6 % / -6.7 %** |
| self-compile (`compilers/linux/compiler.sov`) | 150.46 / 153.66 ms | 134.34 / 139.97 ms | **-10.7 % / -8.9 %** |
| `tests/fast.sov` | 72.03 / 79.91 ms | 66.97 / 72.77 ms | **-7.0 % / -8.9 %** |

(That window was busy — absolute times are ~1.5x the quiet-window numbers; the deltas are
what is load-robust, which is why every figure in this file is interleaved.)

Gates after the pass: fixed point byte-identical; fixtures 241 flat + 21 binaries,
0 failures; `tools/fleet_diff.py /tmp/cc_base <installed>` CLEAN; `./bootstrap`
156 ok / 3 known environmental FAIL; fleet rebuilt (155 backends).

## Toolchain note (cost me an hour twice)

`/tmp` is wiped between sessions by this environment. The stock baseline and the
original sources now live **inside the workspace**:

* `work/orig/{ccore,cx86,carm}.sov` — the pristine files as downloaded from MediaFire
  (ccore quickkey `4ze6tktn0tqk2b4`, cx86 `khi6x79rcrxkivz`, carm `25ug5yhhkqjej2f`);
* `work/cc_base.bin` — the stock linux compiler built from exactly those sources,
  md5 `57b5269493b04f85d1a1df32652a1692`, i.e. byte-identical to the shipping binary;
* `work/mk_base.sh` — one command to restore `/tmp/cc_base` and `/tmp/base/pristine`.

Also: this environment drops the execute bit on files between calls. If a tool reports
"Permission denied", run `chmod +x compilers/linux/compiler bootstrap sovren`.

# Pass 13 — inc00 zero-fill (landed) + Pass 8 revival done and closed

## Pass 13 landed

`library/inc/inc00.sov:1024` flat zero-fill: byte-at-a-time → `poke_i64`, 8 B per
step (line count preserved — inc00 is line-locked because every driver splices it
by line number). Strictly less work for the same bytes; measured neutral, kept.
Installed: `compilers/linux/compiler` rebuilt from this tree, fleet rebuilt (155),
gates green (241 flat + 21 binaries, 0 failures; fixed point byte-identical;
`fleet_diff` CLEAN; bootstrap 156 ok / 3 known FAIL).

## Pass 8 revival — closed, not landed (the correct shape is known now)

The Pass 8 goal was spill-free comparisons in `bin` (cx86.sov:10095): the generic
path is `expr(L); push_rax(); expr(R); mov_rcx_rax(); pop_rax(); emit_op(op)`.
A working, *behaviour-correct* version was built:

    if is_imm(R) is 0
        if plain_name(R) is 1
            if ih_find(cnms, R) < 0            # cflush(R) must be provably silent
                br3: ih_find(locals, R)
                if br3 > 0 - 1
                    expr(L)
                    load_loc_rcx(br3)          # emit3(72,139,141); emit4(loc_off(slot))
                    emit_op(op)
                    return 0

`tests/run.sov` output over 474 lines was **identical** to stock, and it removed
the push/mov/pop. Measured interleaved: min −1.7 %, median +2.8 % (run.sov);
min +0.3 %, median +2.5 % (self-compile) — not a win, **reverted**.

Two things this settles for good:

* the *load* order was never the only trap. Pass 8 loaded R before `expr(L)` and
  `loadv_rcx` goes through `%rax`; that is real, but the deeper trap is **`cflush(R)`**.
  For a name that is register-home or constant-tracked, `cflush` *emits code*
  (`xor`, `rax_imm`) and can overwrite `%rax`, which holds the left operand. Any
  version of this fast path must be guarded on `ih_find(cnms, R) < 0`.
* with that guard the fast path is *correct but small*: comparisons are not the
  bottleneck. Do not re-open this unless the profile says so.

## Corrected cost model — the `--prof` labels lie

`mark(label)` prints microseconds **since the previous mark**, and the phase
boundaries do not bracket what their names say. Measured with tagged marks
(`join('MK>', label)`) on `tests/run.sov`, roughly:

| region | time | what is really inside |
|---|---|---|
| before `0-flags+input` | ~1 ms | process start, arg parse |
| `0-flags+input` → `1-rt-loaded` | **17–18 ms** | runtime load (`.sug` hit), **input file read**, `splice_inc`, **user-source sugar ×1–2**, `pull_uses` ×2 |
| → `2-all-spliced` | 2.5 ms | assemble the full program text |
| → `3-scanned` | 4.7 ms | line scan |
| → `4-compiled` | **~65 ms** | the actual code generation — the dominant phase |
| tail | ~2 ms | `write_elf` |

So: **codegen dominates**, the front end (read+sugar+uses) is ~20 %, and the
"rt-loaded" figure in earlier notes was not a runtime-sugar cost. `mark('5-written')`
in the driver sits after a `return` and never prints.

## The shipped runtime/.sug cache already works — do not re-add it

* `library/inc/inc00.sov:189` already calls `rt_sug_try(rt)` on the **raw** runtime
  text and uses the hit. `runtime.sug` in the repo is byte-identical to what the
  current tree regenerates (`SOVCHUNK1 4327546981170775`, payload cmp-equal), and
  `runtime.sov` has zero `include` lines, so the chunk payload is exactly the
  double-sugared runtime. The hit is what makes the runtime load ~0.1 ms.
* A driver-level `rt_sug_try` call is therefore **redundant** — it hashes 37 KB of
  already-sugared text per compile for nothing. (Tried, neutral; reverted.)
* The driver's `rt: u_sugar(rt)` + `look(rt,' -> ')` passes run on the already
  sugared text and are **provably no-ops**: rt written to a file before and after
  those passes is byte-identical (37,495 B both). They are still ~1 ms/compile.
* `total = 37,495` while the `.sug` payload on disk is 37,496 B — the extra byte is
  the trailing newline, and `rt_sug_try` returns `sgx + sp + 1`, so this is expected.

## Profile refresh (installed Pass 13 compiler, `tools/sampler.py`, `tests/run.sov`)

Two runs, 221 k and 185 k samples — run-to-run mix varies, so read the union:

`ih_find` 9.2–10.0 %, `length` 6.4 %, `expr_body` 3.1–9.3 %, `call_args` 3.6–7.7 %,
`intern_kid` 2.2–5.3 %, `num_value` 3.0–3.9 %, `_sov_alloc` 3.0–3.7 %,
`_sov_find_text` 4.6 %, `_sov_list_add` 4.4 %, `lines_of_fast` 4.1 %,
`_sov_strcat` 3.8 %, `cut` 2.6 %, `body` 2.7–2.9 %, `_sov_fast_alloc` 1.1–2.8 %,
`u_sugar` 3.0 %, `u_scan` 2.2 %, `pull_uses` 1.9 %, `cfind1n` 1.9 %,
`dce_litter` 1.8 %, `bsearch_le` 1.7 %, `sg_cmp` 1.6 %, `nhash` 1.0 %.

Reading: the **interner is the top single item** (~14 % incl. `ih_put`/`intern_kid`),
the **runtime string/list/alloc functions are ~20 %** (and they are already SWAR —
so the remaining win there is call volume, not the inner loops), and the
**recursive-descent parser/codegen (`expr_body`/`call_args`/`body`/`stmt`) is ~15–25 %**.

## Measured and reverted this pass

| change | result |
|---|---|
| `length` memo table 1 MB → 64 KB (mask 4095) | neutral (min +0.0 %, med +0.1 %) — memo size is not the lever; 4 MB had already regressed |
| `num_value` memo 8 MB → 1 MB | neutral (min +0.0 %, med +0.0 %) — same conclusion |
| driver-level `rt_sug_try` | redundant with inc00:189, removed |
| Pass 8 spill-free compare (correct version) | −1.7 % min / +2.8 % med — closed |
| **interner `ih_cap` 524288 → 262144 (`ih_tab` 16 MB → 8 MB, 32 B entries)** | **FAILS — `RC-DIFF bin library/discord.sov (124 vs 1)`: rc 124 is my harness timeout, i.e. the candidate compiler *hangs* on that fixture** (same family as the earlier 65536/131072 failures). The 64-probe cap plus linear probing silently drops inserts once chains fill, and the fallback scan path then loops. Reverted. |

### Gate cost / fast pre-check (learned the hard way)

The failing interner run above burned **15 minutes** in `verify.sh` because every
hanging fixture costs the full 90 s timeout, twice (candidate and base). Before any
`ih_*`/layout change, pre-check the two fixtures that expose it directly:

    for f in library/discord.sov library/x86.sov; do
        timeout 25 <cand> $f -o /tmp/pc.bin; echo "$f rc=$?"; done

Those two files are libraries, so **rc=1 is the healthy baseline** (both the stock
compiler and the installed one return 1); rc=124 (hang) or 139 (segfault) is the
signal you are looking for. Only if that is clean is a full `verify.sh` worth 15 s
per passing fixture.

## Tooling notes added

* `work/pair_ab.py <A> <B> [pairs] [src]` — interleaved A/B of two compilers,
  min/median, fresh process each run. Use this, never single shots.
* The sampler needs a `--bytes` build (`-o <bin> --bytes` writes `<bin>.bin`/`<bin>.map`)
  and must be run **from the repo root** with a repo-relative source path, or
  `splice_inc` cannot find `inc/*.sov`.
* Host load swings the absolute numbers a lot (run.sov min was 77 ms and 114 ms an
  hour apart) — only paired/interleaved numbers mean anything.

## Pass 14 measurement — the 52 % finding (read this before the list below)

`main: print 'hi'` costs **0.70 ms**; adding `use tls` costs **+35.9 ms** and emits
158 KB; `aes`/`gcm`/`json` cost 9-11 ms each. `tests/run.sov` pulls aes, gcm, tls,
json, wasm => **~39 of its 75 ms (52 %) is library-chunk compilation**, which is the
same work on every run. The old "engine ~11 %" figure in this repo was measured on a
much smaller chunk set and is wrong by ~5x. Full numbers, the chunk profile, and the
artifact design are in `work/MAX_TRANSLATION_SPEED.md` ("THE BIG ONE" section).

Two supporting facts measured the same pass:

* Cached *output bytes* cannot be replayed: two programs with the same `use tls` and
  different bodies share only a 152-byte prefix, and the first in-code difference is at
  code offset 5, a `mov rax,[rip+disp32]` whose displacement equals the size delta —
  early code depends on the **total image size**. The artifact has to be a state dump.
* `use wasm` is nearly free (1.48 ms) because it emits nothing.

## Where the remaining time is (value order)

1. **codegen phase ~65 ms** — `expr_body`/`call_args`/`body`/`stmt` + the emitter.
2. **interner ~14 %** — `ih_find` probe is the top single function; next idea is
   the 16-byte entry (`[hash32|pos32, name ptr]`, validated by `lst[pos] == name`,
   which is exactly the check the single-entry memo already trusts) to halve the
   16 MB table's cache footprint.
3. **runtime ~20 %** — already SWAR; needs fewer calls, which means compiler-side
   restructuring (free to do: only `runtime.sov` is byte-locked, the compiler's own
   `cx86.sov`/`ccore.sov` code is not).
4. **front end ~18 ms** — read + `splice_inc` + sugar + `pull_uses`.

# Pass 15 — chunk-state artifact, step 1 landed (snapshot format)

**Landed and verified:** `library/state.sov` (new, not line-locked) — the byte-level
snapshot format for the chunk-state artifact: 8-byte little-endian fields, strings as
(length, bytes), lists as (count, elements); writers `st_u64`/`st_s`/`st_li`/`st_ls`/
`st_out`, readers `ld_open`/`ld_u64`/`ld_s`/`ld_li`/`ld_ls`. `library/ccore.sov` now
ends with `include state.sov` (safe: ccore is a whole-file include).

Verified two ways:
* round-trip test with a `use state` program — int, string, int list, string list all
  come back exactly (snapshot file is 100 bytes, exactly the predicted layout);
* **inert**: emitted output byte-identical to the installed compiler on `tests/run.sov`,
  `tests/fast.sov` and `library/abi_probe.sov`. The module only adds unused code to the
  compiler's own binary.

Note on the round-trip test: printing a list element with `print` shows the pointer as
a number, because Sovren types `_sov_list_get` results as ints at compile time — use
`_sov_print` to read a string element back.

## The artifact contract (pinned from the source, for the next steps)

* `addp at kind val` (inc03:872) appends to `patch_at` / `patch_kind` / `patch_val` /
  `patch_line`. **`patch_kind` holds a string, `patch_val` an int *or* a name pointer
  depending on the kind.**
* The finalizer (inc00:1985+) walks those lists after all code is emitted; for
  `rel26` it does `idx(fn_names, val)` -> `fn_offs` -> writes a 26-bit relative field
  with `poke4(flat, HDR + at, ...)`. Those fields are exactly the 903 one-and-two-byte
  runs that differ between two programs with the same chunks.
* Emit order (proved with the `--bytes` `.map`): **runtime functions -> chunk code ->
  user code (`main` at 147888 in a `use tls` build) -> a few runtime tail functions**.
  So the chunk region is a contiguous block *before* the user's own code, which is what
  makes "snapshot at the boundary" possible.
* The chunk text reaches the program by `if length(extra) > 0 -> src: join(extra, src)`
  (inc00:171) — one prepend per chunk, in `use` order — and `all: join(all, src)`
  (inc00:421) appends the result to the runtime text. The boundary offset is therefore
  `length(all before the join) + (sum of chunk text lengths)`.
* `compile source:` (inc05:738) is **assembled from fragments** across
  inc00/inc01/inc02/inc04 via `include inc/... <line> <count>` directives, so the
  boundary hook has to be a same-line-count edit inside one of those fragments. All of
  inc00-inc06/px00/px01 remain line-locked.
* Interning order must be replayed too: cached code bakes in `kid_*` ids, and
  `intern_kid` assigns ids in call order, so the snapshot must record the words in
  intern order and the loader must re-intern them in that order to keep ids stable.

# Pass 15 — the chunk-artifact boundary is found, validated, and program-independent

The artifact needs one thing before anything else: the exact point in a compile
where "runtime + library chunks" ends and the user's own code begins. That point
is now found, and it is a function of the chunk set alone (so one artifact can be
reused by every program with the same `use` set).

## Where the boundary is, measured (installed compiler + instrumented hook)

| program | first user body | name | cached code region | total code | share |
|---|---|---:|---:|---:|---:|
| `main: print 'hi'` (no uses) | 0 | `main` | 0 B | 3,808 B | 0 % (nothing to cache) |
| `use tls` + that main | 408 | `main` | 147,879 B | 157,920 B | **93.6 %** |
| `tests/run.sov` | 464 | `cr_ok` | 156,194 B | 303,220 B | **51.5 %** |
| `tests/fast.sov` | 526 | `slow_list` | 226,447 B | 329,352 B | **68.8 %** |

(These shares line up exactly with the Pass 14 timing split: chunks ≈ 52 % of
`run.sov`'s compile time, ≈ 100 % of `fast.sov`'s.)

## The rule (in `library/state.sov`, quiet and byte-identical in the tree today)

* `sd_seed_names()` + `sd_scan_headers(rt)` + `sd_scan_headers(extra)` collect the
  names of every runtime/chunk function: a line in column 0 ending in `:` gives a
  body, and the body name is its **first token** (`_sov_alloc_abort msg code:` ->
  `_sov_alloc_abort`).
* `sd_seed_names` adds the four names the **driver injects as literal text**
  (`_sov_thread_exit`, `_sov_sysnum`, `_sov_mem_copy`, `_sov_mem_set`). Without
  these the hook fires early — measured: it stopped at `_sov_thread_exit`.
* `maybe_dump(fi, nm)` fires on the first emitted body whose name is not in that
  set; `maybe_dump2` (same line, after the body) keeps updating `sd_end: oc_n`,
  so the cached region ends at the **last chunk body's last byte**, excluding the
  ~1.4 kB of user-function preamble (entry, saves, stack setup) that the code
  generator emits between the last chunk body and the first user body.
* The hook lives on the two `body(peek_i64(bodies, 16 + fi * 8))` lines in
  `inc02.sov` (791 and 1578) with **line counts preserved**, and the driver work
  rides on the existing `all: join(all, src)` line (`inc00.sov:422`).

## Four dead ends, measured — do not repeat these

1. **`compile()` twice is not output-preserving.** Splitting `compile(all)` into
   `compile(chunks)` + `compile(user)` is mechanically fine (both calls emit), but
   the result is 151,608 B instead of 158,240 B: `compile()` runs its cleanup
   (DCE and the patch rewrites) *per call*, so the first call eliminates code the
   second call then references. The artifact must restore state *inside* one
   compile, which is what the hook now does.
2. **The pad line is not the boundary.** The driver prepends
   `# pad line so main is not first`, but the **transitive** chunks (e.g. `key.sov`,
   pulled by `tls` via `pull_uses(extra)` into `extra`) end up *after* it, so the
   first body after the pad line is still chunk code (`input_yes`).
3. **`src_base` does not count transitive chunks.** It is the compile-time line
   base used for error messages (inc00:376 tests `li + 1 > src_base`), and using
   that test as the boundary fires ~40 lines early.
4. **`body_lns` holds pointers, not line numbers** — `body_lns[fi] - base` gives
   75,508,448 / 60,945,216 for consecutive bodies, so it cannot be used to recover
   source offsets. (The comment at its add site says line numbers; the values are
   pointers.)

Also note: `here()` and the `--bytes` `.map` offsets agree exactly for every body
*except* the user's first function, where `.map` records the entry label while the
hook sees the state after the preamble — which is why the region must be cut at
`sd_end` (last chunk body), not at the first user body's `here()`.

## Current tree state

`library/state.sov` (new module: snapshot format + `count_nl` + the boundary hooks)
is wired in and **quiet**: output bytes and stdout are identical to the installed
compiler on `q0/q1` probes, `tests/run.sov`, `tests/fast.sov`, `library/abi_probe.sov`,
and the 60-second gate reports byte-identical / neutral (−0.9 % min, +1.8 % med).
`sd_dump` is 0, so nothing is captured yet; flipping it to 1 prints the boundary.

# Pass 16 — the artifact works end-to-end; the restore needs the driver hook moved

## What is proven now

The chunk-state artifact is **real, complete and self-consistent**:

* `library/state.sov` writes it (`sd_dump_now`) and a reader (`sd_restore`) parses it.
* The artifact dumped from a `use tls` compile is 259,915 bytes and a Python
  re-implementation of the format parses it **to the last byte** with sane values:
  region 147,879 B, `fn_names` 409, `fn_offs` 409, `glob_names` 112 (contains
  `g_argv`, `g_argc`, `heap_ptr`...), `patch_at/kind/val` 2,441 each with tags
  (2,431 raw ints, 7 glob-name indices, 3 fn-name indices), `used_libs` =
  " tls  mem  bigint  bit32  gcm  hkdf  hmac  num  sha256  aes  md5  sha1  sock
  string  sys  time  web  x25519  vec  secret  constant  list  key", `str_fns` 39,
  `str_vars` 14, `str_keys`/`str_pos` 46, `strb` 5,600 B, tail marker 7, 0 bytes left.
* Representing `patch_val` by pointer identity (tag 1 = index into `fn_names`,
  2 = index into `glob_names`, 0 = raw int) is what removes the cross-process
  pointer problem; the tag histogram above is from the real dump.

## Bugs found and fixed on the way (all real, all cost time)

1. **`st_s` overran its buffer.** It reserved 16 bytes of headroom and then wrote
   `n` bytes, corrupting the artifact. Fixed with `st_need k`, which reserves
   exactly what the string needs.
2. **The one-line `cond -> a ;; b ;; c` form swallows following indented lines.**
   A loop written as `as long as fk < fkn -> if ... -> tg: 1 ;; pn: fk ;; fk: fkn`
   followed by an indented `fk: fk + 1` put the increment inside the `if`, so the
   loop never advanced (it hung until I found it). **Always write loops with
   explicit indented blocks.**
3. **Appending `;; if ...` to a line inside an indented block changes that block's
   scope.** Adding `;; if sd_use = 1 -> rt: blank` to inc00:189 made `rt` invisible
   two fragments later, which produced "Error: no such name: rt/extra" and silently
   different output. Reverted; the tree was restored from pristine sources and is
   byte-identical again (verified on q0/q1/run.sov/fast.sov/abi_probe.sov).
4. **`rt` and `extra` are not in scope at inc00:422** (the driver line that appends
   the user source to `all`), even though that line sits in the same numbered region.
   The fragments are spliced by line number, so scope follows the *fragment*, not the
   file. Consequence: the suppression guards must live inside the functions that
   build those values (`pull_uses` in cx86.sov, which is safe to edit) or inside the
   runtime load path — **not** on the driver line.

## Where this leaves the work

* Dump: done and validated.
* Boundary: found and validated (Pass 15).
* Restore: parses the artifact correctly and reinstalls the state; the remaining
  problem is the *suppression* of the chunk compile, whose hook must go inside
  `pull_uses` (cx86.sov) rather than on the driver line. That is the next edit.
* The main tree is **clean**: pristine inc00/inc02 plus only the Pass 13 SWAR
  zero-fill; `library/state.sov` is present but no longer included by `ccore.sov`,
  so it is inert. Rebuild == installed compiler output on all five smoke sources.

## Discipline note for the next session

Line-locked files (`inc00`-`inc06`, `px00`, `px01`) must be edited **same-line
only**, and any `;;` appended to a line inside an indented block must be checked for
a scope change by rebuilding and diffing output against the installed compiler
**before** any further work. A scratch copy (`/tmp/art`) is the right place for
suppression experiments.

## Pass 17 — restore path runs end to end (chunk-state artifact)

All work in `/tmp/art` (tree copy); durable copies + how-to in `work/art/`
(`state.sov`, `inc00.diff`, `inc02.diff`, `cx86.diff`, `README.md`). The workspace
tree itself stayed byte-identical to the installed compiler throughout
(rebuilt and checked: `09b9a06e5b9b9d9acabb555792db5d29`).

Fixed six real bugs on the way from "restore cannot even read the artifact" to
"restore emits user code against the restored state":
1. **Name-set seeding never ran.** `sd_scan_headers`/`sd_seed_names` were dead
   code; the set held only the 4 injected literals, so `sd_names <= 4` blocked
   every dump. Now `load_file` (cx86.sov) scans every source text it returns
   except `src_name`, dedup through `sd_has`; runtime.sov alone yields 84 headers.
2. **`if A -> if B` + indented block is silently dead** (0 of 84 headers found).
   Scanner rewritten with separate full ifs.
3. **Unprefixed locals are global collisions.** `n`/`i`/`s`/`e`/`l` in state.sov
   rebind globals used by the compiler (that is why the first rewrite found
   nothing). Every local in state.sov is now prefixed (`sd_*`, `ld_*`, `sdr_*`).
4. **`ih_find` does not work on a plain `_sov_list`** — `sd_has` (linear
   `_sov_str_eq` scan) is the membership test that works.
5. **Reader/writer desync:** the dump's dead `sdt` field was never read, so the
   reader took `src_base` (6415) for the names count and segfaulted. Reader now
   consumes every field; the parsed artifact ends with 0 bytes left:
   region 147879, fn_names/fn_offs 409/409, glob_names 112, patch 2441 each
   (tags 2431 raw / 7 glob / 3 fn), strb 5600, src_base 6415, names 525.
6. **Dump and restore guard:** `maybe_dump` returned early when `sd_dump = 0`, so
   restore mode never called `sd_jump`.

Then the pipeline was made to work on real compile state:
- `pull_uses` suppression moved from its head to its return, so `need` and the
  pull side effects survive; the chunk text comes back as `sd_neutral(txt)` —
  the same newline count plus one comment line carrying the flag keywords
  (`join _sov_list load_file _sov_buf _sov_alloc _sov_set_byte peek_byte poke_byte
  spawn`), which keeps every `look(src, ...)` flag check and all line numbers
  identical to the dump run.
- Artifact grew two fields (src_base, the boundary name set) and `sd_restore`
  keeps staging copies so `sd_reapply` can put the tables back at the boundary.
- `sd_skip(nm)` skips emitting every body already inside the region until
  `sd_jump` has run (`sd_jumped`), so nothing is written twice: `here()` at the
  jump fell from 31,403 to 4,966 bytes of wasted prologue.

**Measured now:** region copy verified (147,879 B copied, `oc_n = sd_rn`), names
525 restored, src_base 6415 restored, dump-mode output byte-identical, restore
runs the whole pipeline and then **segfaults while emitting the user's body
against the restored state** (before: it produced 151,584/151,944 B against a
158,240 B reference). Next: trace after `sd_jump` in `maybe_dump` and at the end
of the emit loop / in the finalizer to see whether the fault is in `body()` or in
finalize, then fix and run the byte-identity gate on q0/q1/run.sov/fast.sov.

## Passes 19-21 (2026-10-07) — the chunk artifact works end to end

Status: **done and verified** for plain / `--mkstate` / `--usestate` on q0, q1,
`tests/fast.sov` and `tests/run.sov` — all three modes byte-identical to the
installed compiler.

Interleaved bench (9 rounds, min ms, single binary):

    program     installed   plain+.sug   --usestate    speedup
    q1            37.58       37.44       22.13 ms      1.70x
    fast.sov      66.90       66.26       37.86 ms      1.77x
    run.sov       80.13       70.36       53.41 ms      1.50x

What landed:

1. **Interner seeder** (`sd_ih` / `sd_seed_intern`, state.sov).  The live
   interner `intern_fast_do` (cx86:1111) dedups through its own 65,536-slot
   `intern_ht`; a restore installed `str_keys`/`str_pos` but left that table
   empty, so every restored string was re-appended (run.sov: `strb` 32,063 ->
   32,066, `""` and `" "` duplicated, +8 B of output).  The seeder clears the
   table and re-inserts every key with the same hash, so lookups hit.
2. **Driver flags** `--mkstate` / `--usestate`; artifact path `<input>.state`
   (derived from the input — the option parser feeds non-flag arguments through
   `pic_in`, so a two-argument flag silently consumed the input file).
3. **User-source sugar cache** (`usr_sug_try`, `mk_usug_file`, `--mksuguser`),
   validated by `nhash` of the raw file.  Worth ~20 ms on run.sov's 147 KB
   source.  The clip hook in cx86 `load_file` now skips any path starting with
   `src_name`: a sugar cache for the user's file otherwise seeded the user's own
   labels (`main`) into the library name set and the boundary never fired.
4. **Artifact validity key** — `nhash_pre(sd_all, snap_m)` stored after the
   magic; a mismatch prints `STATE: stale` and compiles normally (verified by
   editing a source after `--mkstate`).

Notes for the next pass: `all` is a fragment local (bind `sd_all: all` first on
inc00:422, before `sd_restore()` runs on the same line); the flags
(sxe/kern/unsafe/opt_dce) still have to enter the key before this becomes a
user-facing mode; the staged scalars/lists are the set `sd_reapply` installs.

Pass 22: the artifact key now also mixes the code-changing flags (`sd_fg`, bound
in the driver after flag parsing), so a replay under different flags prints
`STATE: stale` and compiles normally.  Verified for --release, --plain, --unsafe,
--sxe.  Final bench: q1 38.76 -> 22.14 (1.75x), fast.sov 70.10 -> 38.93 (1.80x),
run.sov 83.08 -> 55.16 (1.51x), all byte-identical.

Pass 23: artifact is mmapped (not alloc+read), validity key and all list I/O are
word-at-a-time, `ld_li` allocates its list in one go.  Bench q1 1.73x, fast.sov
1.81x, run.sov 1.56x, all byte-identical.  Restore phase timers show the
remaining cost is interner seeding (1.3-2.1 ms).  Reverted the intern-table
shrink: the probe bound equals the table size and a failed insert returns 0,
which callers read as a valid offset.

Pass 23 final: probes stripped from the scratch tree (J0/J1a/J1b/J2, inc00
5-compiled/6-wrote, driver a-input-spliced/b-rt-sugared); `sd_has` kept as the
content-compare scan (the ih_find variant was reverted — the skip checks
measure 20-150 us total, the 7.8-13.1 ms before the reapply jump is parse of
the library bodies).  Fixed point OK (b_state md5 2d506b7bc0d516d313c52d1fb87a1dd2),
check.sh q0/q1/fast/run `*** ALL MODES IDENTICAL ***`, fixture md5s unchanged.
Re-measured bench on the cleaned tree: q1 2.00x, fast.sov 1.75x, run.sov 1.78x
by median (absolute ms drift between sandbox sessions; the ratio is the stable
figure).  Diffs re-synced to work/art (195 lines, 5 files, plus state.sov
md5 df664eb65a26389521db4c5be4d6d2df).

BUGFIX (pre-existing, found while answering a language-design question):
`return <expr>` as the first compiled statement of a body was compiled with
`kid_op*` uninitialised, because `stmt`'s fast path (`fast_ret`) runs before
`kid_init()` and `fast_ret_do` compiles `return <expr>` itself.  `bin`/`emit_op`
then failed every `kid_opadd`-style test, skipped the lea peephole and fell
through to `cmp_rax_rcx(); setcc(op)` — the operator was dropped.  Shapes:
`fv x:` + `    return x + 1` placed above `main:` printed 4 instead of 5
(rc=0, no warning).  Fix: `kid_init()` at the top of `stmt` (before `fast_ret`),
the older call removed, and `kid_init()` at the top of `body`.  Compiler md5
09b9a06e… -> 1ee32622fbff082b7fd92ee5126195b0, self-rebuild byte-equal.  Fleet:
158 bootstrap artifacts rebuilt, 144 byte-identical, 14 x86 targets changed
(the bug was in their binaries), 4 steps fail for pre-existing reasons
(launcher silent no-output x2, tools/debug.sov `no such name:
x86_feature_1_used`).  Fixtures and the language suite are byte-for-byte the
same before and after: the suite itself is red in this environment (8 FAIL +
segfault) with both compilers.

Suite status (both compilers, identical): FAIL sbuf put cat text; FAIL sbuf
slice and eq; FAIL sbuf rejects overflowing append; FAIL sbuf rejects bad
index; FAIL bounds off keeps the last wall; FAIL hmac verify accepts and
rejects; FAIL x25519 branchless swap matches; FAIL android target carries bti
pad — plus a segfault at the end (rc=139).  The first five print
"/tmp/sov-tr-<pid>.bin: not found" from their generated shell script, so they
look like a harness/cwd problem rather than language failures; not caused by
the fix (identical output from the pre-fix compiler).

## BUGFIX 2 - bare relative input path + include => SIGSEGV (fixed)
* Root cause: `dir_of()` returned the invalid sentinel `blank` when the input path had no `/`;
  `splice_inc` then did `join(base, pname)` on it. ARM twin `dirname` already returned ".".
* Fix: `library/cx86.sov` `dir_of` -> `return "."`; `emit_nt_dir_of` (native twin) -> allocate
  a real "." string instead of `load_glob("blank")`.
* Compiler `16eb109e0dc2712b7e1bbb33fcc5eec2` (fixed point), fixtures byte-identical,
  work/art/check.sh ALL MODES IDENTICAL (b_state 77339ccf...), fleet 16 changed / 142 identical.
* Write-up: work/BUG-dir-of-null-base.md

## PERF - interner clear threshold 1/2 -> 1/3 load (landed)
* `library/ccore.sov` `ih_put`: `if ih_n * 3 >= ih_cap -> ih_clear()` (was `* 2`).
* Measured (interleaved, min of 4, fresh processes, old vs new installed compiler):
  q1 0.80x, run.sov 0.92x, self-compile 1.02x, fast 1.03x - outputs byte-identical.
* Compiler `a5a8fd7690cc` (fixed point gen1=gen2=gen3); fixtures byte-identical
  (q0 5655d3b6aca4, q1 d65814f686b3, fast 4005a6b38a2a, run 6b9c3f7c193c);
  work/art/check.sh ALL MODES IDENTICAL (new art reference 7fa76e1627c7b4b63c69ccdae71aaafa);
  fleet rebuild: 29 artifacts changed (all rebuildable x86/arm targets), 129 identical,
  the 4 known pre-existing failures unchanged.
* Context: table-size changes are a dead end (8 MB = +21 % slower, 32 MB mixed);
  the win comes from shorter probe chains.  See work/INTERNER_TABLE_SIZE.md.

## SESSION 4 — `--cache` prebuilt path made self-relative (defect fix)

`library/ccore.sov` `pb_key_file` used the literal `"/home/user/sovren/library/.prebuilt/"`
as the entry directory, so on any other checkout `--cache` was a **silent** miss (probe:
0.7 ms hits when the literal directory is created by hand, 78 ms otherwise).  Fixed:
root derived from the running binary (3 candidates, accepted when `<root>/library/ccore.sov`
opens), `mkdir` best effort, literal kept as fallback, 72-byte name buffer guarded.
Installed compiler `60037af9f1c0` (g2=g3 fixed point).  Fixtures run/fast/q0/q1
byte-identical, `work/art/check.sh` ALL MODES IDENTICAL, art reference now
`581afc290c033935c56a500672de1978`.  Cold run.sov unchanged (~77 ms); `--cache` rebuild
path = 0.7 ms and works from any cwd.  See `work/PREBUILT_CACHE_FIX.md` and, for the
measured cost map that re-orders the speed plan, `work/WALK_MAP.md`.

## SESSION 5 — three per-line candidates measured and rejected (nothing landed)

Priced three semantics-preserving guards in `library/cx86.sov`: SWAR quote parity
(`cnt_byte`, skipping the per-character validation loop when the line has no backslash);
an `=`-position pre-filter for `compound` (the old path ran a 2-peek_byte-per-char loop on
every line containing `=`); and a no-space fast path for the assignment lhs
`repl(strip(cut(s, 0, col)))`.  All three built, reached fixed point, kept every fixture
byte-identical, and preserved the `unterminated text` error path — and all three measured
**neutral**: interleaved A/B min ratios 1.000/1.051 (compound), 1.000/0.986 (lhs),
1.025/1.045 (all three) on run/fast against a control floor of +0.1 %.  Reverted.

Recorded in `work/WALK_MAP.md`: per-line cost is 1.19 us and distributed; sub-microsecond
per-item figures are below the instrument floor; **dup-pricing overstates cost and must not
be used again**; the per-line path has no cheap winner left.  The remaining big lever is the
invariant-library-text resume point (36-42k lines re-walked per compile).

Installed compiler unchanged `60037af9f1c0`; art reference `581afc290c033935c56a500672de1978`;
`work/art/check.sh` = ALL MODES IDENTICAL; fixtures run/fast/q0/q1 byte-identical.

## SESSION 6 — dependency-complete artifact cache, default-on (LANDED)

Installed compiler `22b4ea51b515c3f947b27133d644c50d`.  `pb_key_file` keys the prebuilt
cache on a stat-hash of the compiler binary, every file under `library/` (recursive,
`.prebuilt` excluded), `runtime.sov`/`runtime.sug`, and every file next to the input;
root is derived from the running binary; entries capped at 16 with oldest-first eviction;
cache ON by default (`--no-cache` opts out); Linux-gated via `pb_enum_ok` (other targets
unchanged).  Measured: run.sov cold 77.7 ms unchanged, repeat run **1.64 ms** (49x),
touch/edit under `library/` forces a miss and the miss output is byte-identical to
`--no-cache`; fixtures run/fast/q0/q1 byte-identical; `work/art/check.sh` ALL MODES
IDENTICAL; launcher byte-identical; fleet 156/156 rebuilt with 0 byte changes.
Deleted `.sug` caches were regenerated with `--mksug`/`--mksuguser` (209 + runtime + 2).
Pre-existing (not regression): `tools/debug.sov` fails to build on both the previous and
the current compiler — see `work/PREBUILT_CLOSURE.md`.

## SESSION 7 — the artifact cache is default-on for every target (LANDED)

`pb_enum_ok` default 1 in ccore (per-driver opt-ins reverted); installed compiler
`4032d9ecba5b`; fleet 29 changed / 127 identical, second pass 0 changed; windows cross
compiler on run.sov: 94.6 ms cold -> 1.87 ms repeat (51x) with byte-identical output;
linux: 80.8 -> 2.00 ms (41x).  hello.sov (no `use`) is 0.84 ms COLD — the ~80 ms cold
cost is the included library text, not the input size.  All fixtures byte-identical,
launcher byte-identical, art reference `b08fb8b51aa5739ccb8937bbcda57565`, check.sh
ALL MODES IDENTICAL.  `compilers/apple/macos-dynamic-library/compiler` is a stub (writes
a fixed 8 KB dylib, ignores input) — not a compiler, no cache applies.

## SESSION 8 — cold resume: library-state snapshot, self-verified (LANDED)

Installed compiler `dd7c7c2b3042` (f1 = f2 = f3).  The state module
(`library/state.sov`, loaded via `ccore.sov`) now carries the boundary jump and the
verification pair, and the work is wired end to end: `--mkstate` snapshots the compiler
at the line where the user's own code begins; `--usestate` replays it; **auto-resume**
picks up `<input>.state` with no flags; **auto-learn** writes the state on a build that
has none (`--no-learn` opts out); `--timing` prints the phase marks.  The emission walk
now starts at the first function the state does not contain (`sd_fi_skip`/`sd_fi_jump`,
hook on `library/carm.sov`'s `fi: 0 ...` line), so the ~700 library functions are not
walked at all.

Verification is self-checking: `<state>.sum` holds the artifact hash, every resume
recomputes it, and a mismatch unlinks the pair and rebuilds in a child — a stale or wrong
state can only cost time, never bytes.  Staleness (prefix hash + flags) unlinks both the
state and its sum file.

Measured on the install (min of 4-6 runs, byte-identical artifacts, 0 fallbacks):
run.sov cold 77.6 -> resume **54.3 ms** (1.43x), repeat 4.4 ms; fast.sov cold 78.1 ->
resume **39.5 ms** (1.98x), repeat 2.8 ms; the learning build is within noise of cold
(+2 ms) because the dump rides along with the normal compile.
Gates: 5-mode byte-identity on run/fast/q0/q1; `work/art/check.sh`
`*** ALL MODES IDENTICAL ***` with a 295,039 B state; fleet after the ARM/android shim
pass = 1 failure (pre-existing `tools/debug.sov`) with **0 changed bytes across 155
artifacts**; launcher `313d693b9c3a` unchanged.  Cross-target drivers do not load the
state module and carry no-op shims (`work/fix_driver_shims.py`).
Hygiene: `<input>.state` must be deleted before cold benchmarks, and stray `.state`
files next to driver sources break driver rebuilds — `work/rebuild_fleet.py` now passes
`--no-learn` and the fleet deletes them.
Residual lever: the reuse path still spends ~30 ms in `4-compiled` (finalize/fixup over
the restored patch lists, plus the pre-passes over the prefix).
Details: `work/COLD_RESUME.md`.

## SESSION 9 — cache-free fixed point, corrected resume harness, fleet truth

* `--no-cache --no-learn` build of `compilers/linux/compiler.sov` is green and
  reproduces the installed compiler exactly: **`dd7c7c2b3042`**.  Earlier
  "green" source builds were artifact-cache hits; the tree was only proven by
  cache-free builds from now on.
* Two source fixes on the way there: restored the `sd_fi_skip` / `sd_fi_jump` /
  `tt_stamp` providers in the linux driver (the module and the driver call
  them), and reverted the experimental `inc/inc06.sov` emission-loop jump hook
  (not part of the shipped compiler; it breaks resume byte-identity).
* Resume re-verified with a corrected harness (`work/bench_state2.py` — the old
  one deleted `.state.sum` and so always took the fallback): run.sov cold 68.7 /
  mkstate 77.3 / resume 54.1 / auto 54.0 ms; fast.sov 65.6 / 77.1 / 39.2 / 38.3
  ms; all five modes byte-identical, zero fallbacks.
* Pre-pass skip implemented and verified byte-identical, then dropped: the
  cached prefix is 1,442 of 12,312 lines, so it is worth ~1 ms.  `snap_b` is
  the boundary; the tree is left at the exact shipped-binary state instead.
* Fleet 149/156; the seven ARM-family drivers that fail from source are listed
  in `work/COLD_RESUME.md` (pre-existing, previously hidden by the cache).

## SESSION 10 — fleet green, state reader hardened

* All 155 drivers build from source; `bootstrap.sov`'s 158 artifacts rebuild and
  two consecutive rebuilds are byte-identical (fixed point). Only `debugger`
  fails, and it fails in the untouched download too.
* Causes fixed: stray blank lines inside blocks in `library/carm.sov` (x5) and
  `library/ccore.sov` (x1) — a blank line ends an indented block in this
  language — plus a dangling ` ;; ` in carm; missing declaration blocks in the
  seven ARM-family drivers; duplicate `sd_fi_skip`/`sd_fi_jump` stubs in
  `linux/arm64-shared-object`.
* The state artifact now carries a length trailer and the reader validates it
  before parsing, so a truncated/partial state is ignored and the compile
  restarts cleanly instead of segfaulting. Auto-learned `.state` files are
  caches, not source: the tree ships without them (308 were removed).
* Installed linux compiler is now `43691b1f85b0` (state.sov change only);
  fixtures byte-identical: run `6b9c3f7c193c`, fast `4005a6b38a2a`,
  q0 `5655d3b6aca4`, q1 `d65814f686b3`.
* Details: `work/SESSION10_FLEET.md`.

## SESSION 11 — cold profile; state writing opt-in (LANDED)

* Cold `tests/run.sov` phase table (new `work/phases.py`): pre-scan 12.3 ms,
  library-prefix emission 19.8 ms, user-function emission 27.0 ms, `write_elf`
  2.9 ms, `.sum` 1.8 ms, startup+splice 0.5 ms.  The emission walk is ~70% of a
  cold build and no single function exceeds 10% of it.
* **A state is written only on `--mkstate` (or the new `--learn`).**  The
  automatic dump cost 8-11 ms (14%) on every build that had none, for a cache
  that build might never use.  Auto-resume needs no flag and is unchanged.
  Interleaved A/B on `tests/run.sov`: 77.2 -> **69.5 ms** median, default path.
* Installed linux compiler **`54f810d3377e`**; fixtures byte-identical; fleet
  158/158 identical twice; 155/155 drivers build from source; art gate
  `*** ALL MODES IDENTICAL ***`.
* Details: `work/SESSION11_COLD.md`.

## SESSION 11b — pre-scan reorder (LANDED)

Cold-build front end: the pre-scan's per-line test now checks the indent before
`strip`, so the 94% of expanded lines that are indented are rejected with one
`nind` call instead of `strip` + `length`.  Measured in-process: pre-scan
12.24 -> **9.70 ms**, whole cold build 53.10 -> 51.13 ms; end-to-end 65.6 ms.
Fixtures byte-identical; 155/155 drivers; fleet 158/158 twice; art gate ALL
MODES IDENTICAL.  Installed linux compiler **`65a4612e0360`**.

Also established (and needed for future edits): only `library/inc/incNN.sov` and
`inc/pxNN.sov` are line-sliced; `cx86.sov` / `carm.sov` / `ccore.sov` / drivers
are whole-file includes and accept free-form edits.

## SESSION 11c — cold phase table is now one command; pre-scan at its floor

* `work/phases.py` stamps the front-end boundaries as well: cold
  `tests/run.sov` = 0.8 startup / 1.53 pass 1 / 0.76 fixpoint loops / 0.45
  tables+pass 3 / **7.50 pre-emit block** / 19.61 prefix emission / 3.13 state
  dump (learning only) / **21.59 user emission** / 2.22 `write_elf` / 1.39 tail.
  **The emission walk is 70% of a cold build.**
* Two micro-optimisations tested and rejected as neutral, not landed: hoisting
  `_sov_list_len` out of pass 3, and `ih_find` instead of `idx` for the
  duplicate-name check (48.99 vs 48.98 ms both times).
* The ptrace sampler's name attribution is unreliable (reports `length` as 6.5%
  while a counter in that very function counts 0 calls); use the phase stamps.

## 11d — shared prefix state (scratch, parked)

Built and measured in `/tmp/sh`; see `work/SHARED_PREFIX_STATE.md`. Same-program shared
reuse = 27 % faster and byte-identical; cross-program is blocked by DCE-driven,
run-unstable emission order (evidence in the doc). Repo stays at `65a4612e0360`, all
gates green, no `*.state*` files.

## 11e — emission-walk budget; two candidate wins measured and killed (2026-10-07)

* New stamp `tX1_walkend` (driver, before the post-walk block) splits the walk
  from the passes. Fresh table for run.sov cold --learn (59.9 ms total):
  load 0.5 / front-end 3.0 / **pre-emit 8.6** / **emit-prefix 21.3** /
  dump 3.1 / **emit-user 17.8** / **post-walk passes 3.2** / write_elf 2.2 /
  tail 1.6.  The walk is 65 %; the DCE passes everyone worried about are 5 %.
* `word_id` single-pass interner rewrite (+ new `kid_lookup`): byte-identical
  fixtures, fixed point, art gate, fleet 155/155 — but **speed-neutral**
  (interleaved: heavy -0.7 %, run -0.6 %, fast -0.9 %).  Reverted; tree is the
  65a4612e0360 reference again.
* Bench drift on this box is ±15 % between sessions (172.8 vs 144.8 ms for the
  same self-build).  Non-interleaved A/B is worthless here; two earlier
  "wins" this round were drift.
* Re-verified shipped resume with `work/bench_state2.py`: run 52.9 cold →
  50.9 auto (4 %, not the previously noted 23 %); fast 61.7 → 35.8 (42 %, real).
* Full write-up: `work/EMIT_WALK_BUDGET.md`.

## 11f — tcc benchmark; resume port to the other drivers tried and reverted (2026-10-07)

* Installed tcc 0.9.27 in-sandbox and measured the repo's tcc claim for the first
  time: `tcc -c sqlite3.c` (9.02 MB / 255,636 lines) = 80.7 ms best-of-5, i.e.
  31.9 MB/s on its own preprocessed text (2.58 MB), 1408 k lines/s.  `tcc -E`
  alone is 68.5 ms of that, so tcc's codegen part runs ~211 MB/s.
  sovren cold `run.sov` = 6.20 MB/s expanded / 211 k lines/s → **5.2x behind on
  bytes, 6.7x on lines/s**; with `fast.sov` auto-resume (35.8 ms) the gap is 3.2x.
  We have **not** beaten tcc.  Full table: `work/TCC_BENCHMARK.md`.
* Corrected `work/MAX_TRANSLATION_SPEED.md`: it claimed tcc was ~10–20 MB/s and
  sovren "within a small factor"; the measured row replaces that.
* Resume-feature coverage measured: **1 of 14 full front-end drivers**
  (linux) parses `--mkstate`/`--usestate`/`--learn`; the other 141 compilers are
  target emitters.  Ported the feature to the 13 other front-ends and drove
  `freebsd` end-to-end: state 295,487 B written, reuse engages, artifacts
  byte-identical (`9c1dcd0188b4`), but the boundary lands at fi 526/528
  (`fast.sov`) / 464/528 (`run.sov`) → resume measured 46.8 → 47.4 ms (no gain),
  and the BSD runtime's `sd_fh` returns 0 so the `.sum` verification was vacuous
  (would violate "never serve mismatched bytes").  **All 13 ports reverted**,
  drivers rebuilt and verified against baseline.  Cross-compiler wins must come
  from the walk, not from porting resume.

## 11g — whole-artifact cache landed: repeat builds 0.7–2.6 ms (2026-10-08)

* New mechanism, default-on: `<input>.ac` (key) + `<input>.ac.bin` (artifact),
  written in the input's directory.  Key = input path | output path | command
  line | qword-FNV fingerprint of input (size + first 32 KB + last 32 KB) |
  same fingerprint of the compiler binary.  Hit = copy out + `Wrote` + exit.
  Store = after the artifact exists, size-verified, self-deleting on mismatch.
* Guards: `--no-cache` disables read+write; `--no-learn` disables write (linux);
  `--no-ac` disables all; `--bytes` runs are never served (side files).
* Landed in 14 front-end drivers: linux, 11x `operating-systems/*`,
  `linux/arm64-shared-object`, `android/shared-object`.  Measured repeats:
  linux 2.6 ms (37x), BSD family 0.7–0.9 ms (102–155x), shared-object 0.7–0.9 ms.
  Cold unchanged (fleet numbers identical to before).
* Correctness: every ported driver byte-identical vs its previous binary on
  run.sov + q1 before install; linux fixed point 70b6a409659d; art gate
  ALL MODES IDENTICAL at the new reference; fleet 155/155 OK; fixtures
  6b9c3f7c193c / 4005a6b38a2a / 5655d3b6aca4 / d65814f686b3.
* `work/bench_state2.py` now wipes `.ac`/`.ac.bin` on cold legs (cold stays cold).
  `work/art/rebuild_art.sh` reference updated to 70b6a409659d.
* NOT ported yet: the 11 Apple-family drivers + plain `android` + `linux/arm64`
  (their main flow is inside line-locked `inc/` slices).  Next.
* Write-up: `work/ARTIFACT_CACHE.md`.

## 11h — all 155 at repeat-build speed (shared-slice hooks), fleet refreshed

The last 14 slowest were the Apple family + android + linux/arm64; their main
flow is assembled from `inc/` slices, so a driver-file hook is dead code
(driver-level statements never run there and a driver `main:` collides). Fixed by
hooking the two shared lines the whole family runs:

* `library/inc/inc00.sov:397` gate — `print 'Compiling' ;; if acx_gate(inf, outf) = 1 -> sys_exit(0)`
* `library/inc/inc00.sov:499` store — `write_elf(outf) ;; acx_store(inf, outf)`
* tasks `acx_*` appended to `library/state.sov` (reached by every driver through
  `inc05 -> ccore.sov:1869 include state.sov`).

Root cause of the first crash: `g_argv` is the stack top, not the argv table;
the sanctioned accessor is `_sov_argv_get`/`_sov_argc` (used all over
`ccore.sov`). Key = `<input>|<output>|<compiler fp>|<whole-input fp>|<flag tail>`;
`acx_fh` hashes the whole input 8 bytes per step, `acx_fhb` the compiler binary's
ends. `--no-cache`/`--no-ac`/`--no-learn` semantics match the driver-level ports;
`--mkstate`/`--usestate`/`--flat` bypass the gate. Flags are in the key
(`--unsafe`, `--kernel`, `--prof` measured to miss).

Repeat results (fresh process, `.ac*` wiped for cold; `work/fleet_cold_repeat.json`):
all 155 byte-identical; 30 drivers were >100 ms cold and now repeat at
median 1.83 ms / worst 4.48 ms; the other
125 repeat at median 1.39 ms; whole fleet worst 4.48 ms.
Headline rows: apple/arm64_32 273.2 -> 1.50 ms (182x), apple/visionos-sim 268.2 ->
1.53 (175x), apple/watchos 272.1 -> 1.58 (172x), linux/arm64 219.3 -> 1.58 (139x),
android 218.6 -> 3.70 (59x), windows 114.7 -> 3.69 (31x).

Gates: fleet fixtures before/after 155/155 rc=0, 148/155 byte-identical (the 7
that changed are the stale Apple variants, now agreeing with the macos-arm64
reference 28ff4456f717); fixed point linux = 860cdface1e5 rebuilds itself
byte-identically; `rebuild_art.sh` reference updated, prints `art tree OK
(b_state 860cdface1e5)`; `check.sh` ALL MODES IDENTICAL; fixtures
6b9c3f7c193c / 4005a6b38a2a / 5655d3b6aca4 / d65814f686b3 unchanged; state legs
hook-free vs hooked interleaved identical; cold unchanged (208 vs 207 ms twins).

Pre-existing, not caused here: the committed non-linux artifacts were stale
relative to the tree (a hook-free rebuild of macos-arm64 already differed from
the committed bytes) — the refresh rebuilt 157/158 steps. `tools/debug.sov`
(`debugger`, rc=185) fails in both hook-free and hooked trees.

Harnesses: `work/fleet_run.py` (before/after fleet outputs), `work/fleet_rebuild.py`,
`work/bench_fleet_all.py`, `work/bench_ac_family.py`; data
`work/fleet_{before,after,rebuild,cold_repeat,ac_family}.json`. Write-up:
`work/ARTIFACT_CACHE.md`.

## 11i — integrity guard: the cache can never hand back mismatched bytes

Closed the one real hole left in the whole-artifact cache: a torn, truncated or
edited `<input>.ac.bin` (concurrent writer, disk-level damage, hand edit) would
have been copied out as-is. Now the key file ends with `#<fingerprint of the
stored artifact>` (ends+size fingerprint, `ac_fh`/`acx_fhb`), the comparison runs
on the part before `#`, and after the copy is written the copy is measured again:
mismatch -> return 0 -> normal build.

* shared family: `library/state.sov` (`acx_gate` parses `#`, `acx_store` appends it).
* driver-level 14: same three edits scripted across `compilers/linux/compiler.sov`,
  the 12 `operating-systems/*` and the two `*-shared-object` drivers
  (`ac_try` parse+verify, `ac_store` append). 14/14 patched, 0 build failures.
* verified by tampering: mid-byte flip and truncation of the stored artifact on
  `apple/macos-arm64` and `operating-systems/freebsd` -> both refused, both
  delivered the correct artifact from a rebuild (`cmp` against the clean build).

Re-measured after the guard (`work/fleet_cold_repeat.json`, `work/fleet_ac_family.json`):
155/155 byte-identical repeats, whole fleet worst 4.35 ms,
the 30 that were >100 ms cold median 1.86 ms / worst 4.35 ms; headline rows
apple/visionos 219->2.02, apple/visionos-simulator 219->2.22, apple/tvos-simulator 217->1.94, apple/watchos-simulator 217->1.94, apple/arm64e 216->2.08, apple/ios 216->1.84.

Gates after the re-refresh: fleet behavior identical to the pre-guard refresh
(0 changed artifacts on run.sov and q1, `work/fleet_after2.json`), fixed point
linux = 104faf0335ab (self-rebuild byte-identical), `rebuild_art.sh` reference
updated to 104faf0335ab -> `art tree OK`, `check.sh` ALL MODES IDENTICAL,
fixtures 6b9c3f7c193c / 4005a6b38a2a / 5655d3b6aca4 / d65814f686b3 unchanged,
state legs hook-free vs hooked interleaved identical (3 pre-existing usestate
fallbacks in both). Cold unchanged (79.0 vs 80.0 ms twins).

## 11j — instrumented the walk; two more measured negatives; the native-twin fact

Added caller attribution to the ptrace sampler (`work/sampler2.py` — it already
collected (callee, caller) pairs and threw them away; it now prints the top
callers per hot function). Fresh profile of the installed driver on
`tests/run.sov` puts the walk's interpreted work at `expr_body` 4.9-6.3 %,
`call_args` 5.4-6.1 %, `stmt` ~1.5 %, `body` ~2.3-3.2 %, the sugar helpers
(`u_sugar` 3.8 + `sg_*` + `sg_text` + `sg_exp_push` + `cops` + `u_scan`) ~15 %,
`lines_of_fast` 2.7-4.1 %, `write_elf` 1.6-4.2 %, `dce_litter` ~1 %.

**The fact that explains a year of neutral micros:** `try_native_body()` replaces
the *body* of twinned tasks (`length`, `strip`, `same`, `look`, `ih_find`,
`nhash`, `intern_kid`, `num_value`, `word_id`, `sg_cat2..6`, `join`, `idx`,
`_sov_list_*`, `_sov_strlen`, `sg_ind`, …) with hand-written machine code, gated
on `nat_gate` (needs `emit3`/`emit`/`ocgrow` in the program being compiled), so
it applies only to the compiler itself. Editing those task *sources* cannot
change the compiler's speed; the inline bodies live in the driver's `call_args`
and in `emit_nt_*`. In particular `sg_cat2`/`join` emit `calln('_sov_strcat')`,
which is where the compiler's ~12k sugar concatenations go.

Measured negatives this round (both reverted, tree back at 104faf0335ab,
verified byte-identical rebuild):
* hoisting `length(e)` into `le` at the four definition points in `expr_body`
  (40 call sites dropped): gate green (242 flat + 21 binaries), A/B -0.04 % min /
  -0.08 % med -> neutral.
* adding a complete extra 58-branch `_sov_str_eq` dispatch chain to the head of
  the driver's `call_args` (so every invocation pays one extra full chain):
  A/B -0.02 % min / -0.11 % med -> the dispatch chain costs nothing; converting
  it to hash/ID dispatch cannot pay.

Also measured: the user-source `.sug` cache is worth ~9.6 ms of a ~80 ms cold
build (`tests/run.sov` copied to `/tmp/x.sov`: 79.7 ms without, 70.1 ms with,
outputs identical), and the shipped tree carries 211 `.sug` files, so that cost
is only paid for a never-sugared file.

Conclusion recorded for the next slice: every *local* edit is neutral because the
hot primitives are already native; the only remaining lever is doing **less work
per line** — the descriptor/arena representation change. First slice to build:
one chunked string arena plus descriptor (offset,length) line lists inside the
sugar passes, where `--flat` is an exact gate.

## 11k — two sugar-cache defects; 12-13 % off every cold build (all 155)

The `.sug` caches are checked on read, so a wrong-format or stale cache is
*silently inert*: the compiler redoes the work, output stays correct, nothing
warns. Two were found with a probe (keep the header, junk the payload; a live
cache then fails the build):

1. **208 of 209 `library/*.sov.sug` shipped in the user format (`SOVUSRSUG1`)
   but are consumed by `chunk_sug_try`, which requires `SOVCHUNK1`.** Rejected on
   every read since that consumer changed -> every build re-spliced and
   re-sugared every library chunk it pulls. Regenerated with the chunk producer
   (`--mksug <chunk.sov> -o <chunk.sov.sug>`).
2. **`tests/run.sov.sug` was stale** (header hash 14698936664469041 vs current
   68268952937720601): the user-source cache never hit. Regenerated with
   `--mksuguser`.

Measured (same binary, interleaved 10x, `--prof` segments in the same runs;
`tests/run.sov`, `--no-cache --no-learn`):

| | before | after |
|---|---:|---:|
| pull_uses #1 (+#2), cache-format effect | 7.52 + 2.4 ms | **0.93 + 0.42 ms** |
| total, min / median | 61.02 / 65.71 ms | **53.61 / 57.36 ms** (-12.1 % / -12.7 %) |

Fleet-wide cold (`work/fleet_cold_repeat.json`, 155 drivers, cache wiped): drivers
over 100 ms cold went 30 -> 25; apple/arm64_32 273.2 -> **164.2 ms**,
visionos-simulator 268.2 -> 164.8, watchos 272.1 -> 167.9, linux/arm64 219.3 ->
117.3, android 218.6 -> 114.2, windows unchanged 114.7 -> 114.2. Repeats
unchanged (all 155 byte-identical, worst 4.03 ms).

Front end now (stamps, same run): user source load+sugar 3.0 ms, chunk pull
0.9+0.4, runtime load+hit 2.2, assemble `all` 1.7, scan 3.9, walk 37.5, tail ~2.

Gates after the change: fixed point intact (`104faf0335ab` rebuilds itself
byte-identically), `verify.sh` 242 flat + 21 binaries byte-identical vs the
frozen twin, fixtures 6b9c3f7c193c / 4005a6b38a2a / 5655d3b6aca4 / d65814f686b3,
fleet behaviour 155/155 with **0 changed artifacts**, `runtime.sug` verified
current and live.

Also landed this turn: caller attribution in the sampler (`work/sampler2.py`),
the `.sug` format/consumer/producer table in `work/ENGINE_MAP.md`, and
`work/refresh_sug.py` (verify + regenerate; run it after any edit the caches
cover). Two more measured negatives (reverted): disabling the driver's re-sugar
of the cached runtime (the needle guard already skips it), and a full extra
58-branch dispatch chain in `call_args` (~0.0 %).

### 11l. arm64 `warn_unused` port landed; `sovren.exe` harness bug; bootstrap = 158/159

**Landed (both files together):** `library/carm.sov` (indexed `w_hit` build over
candidate names + `peek_byte` lookup, per-patch-row `idx`) and the shared head line
`library/inc/inc01.sov:816` (`w_hitn` / `w_hit` / `w_built`).  Correctness first:
identical `used` verdicts on 6 inputs (139/151/160/0/1/5 verdict lines) and the
four arm64 artifact hashes unchanged (`0013f9c50ab6` / `63724dc4a485` /
`5220f605691d` / `90f5010c4ea1`).

**Speed (interleaved, 9 rounds, cache wiped per run, `tests/run.sov`):** the port
is a real win on the arm64 family - median deltas: linux/arm64 **-10.5 %**,
android -9.0, apple/ios -8.9, macos-arm64 -7.8, arm64e -6.8, arm64_32 -6.2,
tvos-sim -6.2, ios-sim -6.2, visionos -4.2, tvos -4.0, visionos-sim -4.0,
watchos -3.9, linux/arm64-so -2.5, android-so -0.5, watchos-sim -0.2.  The
earlier "neutral" reading was an instrument artifact (fresh-process spawn cost +
non-interleaved sweep); `ab.py` in-process A/B on the same pair reproduces the
win.  15 binaries changed fleet-wide; everything else byte-identical; the linux
twin still rebuilds to `104faf0335ab`.

**Landing gates:** `cycle.sh --full` - candidate == frozen twin, 157 installed,
behaviour 155 drivers x 2 fixtures with **0 changed artifacts**, `art/check.sh`
ALL MODES IDENTICAL, `fleet_rebuild.py` 0 byte-differ, `refresh_sug.py` green
(regenerated `carm.sov.sug`, 0 problems).

**Harness bug (fixed):** `work/fleet_rebuild.py` appended a step's flag to the
*linux driver* command; the driver ignores target flags, so `launcher-win` built
a Linux launcher silently and step 4 of `cycle.sh` installed it over the
committed `sovren.exe`.  Flagged steps now build through
`./sovren <src> -o <out> <flag>`.  `sovren.exe` restored to the bytes the tree
builds (`4748fecba6c3`, 78,160 B, PE32+); `./sovren` unchanged (`313d693b9c3a`).

**Bootstrap gate, first full run: 158/159.**  The one FAIL is `debugger`:
`tools/debug.sov:103` splices `include inc/inc00.sov 655 3` (a mid-hash block,
hence `bb`/`y`/`z`/`aa`/`x`/`start` "no such name") where the declarator block
`inc00.sov 691 3` - the same slice `chat/split/toml/tsv` use for this - belongs.
Repairing that line makes it compile (107,600 B) but does **not** reproduce the
committed `sovren-dbg` (286,704 B, `1dbc0b8ef4a4`), so that artifact is not
reproducible from the shipped sources; the repair was not shipped.  Source left
at `3b392a2edf56`.

**Refuted by ablation (do not retry):** replacing `build_used_fns`' entire row
loop with `return 0` moved a run.sov build by **+0.02 % min / -0.18 % med** - the
pass is free, so the profile's `ih_find <- build_used_fns: 56 %` caller
attribution is an artifact of map-range naming.  Probe numbers for the record:
8,488 patch rows, 4,272 marking rows, kind-pointer repeat 99.8 %, name content
repeat in a 16-entry window 17.9 %, canonical-pointer identity 0/4,272.

**Hygiene:** running the `bootstrap` binary leaves `<src>.ac` + `<src>.ac.bin`
next to every step source (its `tr_build` shells out without the cache toggles);
`find . -name '*.ac*' -delete` restores 896 files.  After this turn: 896 files,
209 `.sug` all current, no `.ac`/`.state` anywhere.

**Floor:** `tests/fast.sov` 46.4 ms vs `tests/run.sov` 48.0 ms cold - build cost
is dominated by the runtime prefix, not by user source size.  Fresh cold phase
table (stamps): load 0.29, pass1 1.13, loops 1.63, tables 1.97, emit 7.88, dump
9.65, **walk +27.30 -> 36.95**, written 38.29 / 39.14.  `library/.prebuilt/` is
the artifact-cache store (`nrec: 0` when walking), not a runtime precompile.

## 11m — the shipped resume was broken; operator-dispatch bitmap (LANDED); `ab.py` was blind (2026-10-08)

**1. `--usestate` / auto-resume did not reproduce the artifact.  Four defects, all
fixed (`library/state.sov`, `library/cx86.sov`, `inc00`/`inc03` `pro_src`):**

- the header/boundary scan ran only under `sd_dump`, so a resume built its name set
  from the four injected names alone: the boundary fired at fn 0, the jump landed
  mid-`_sov_strcat` and 482 B of the prefix were lost.  Gate is now
  `sd_dump + sd_use > 0`.
- `br_at`/`br_pv`/`br_id`/`br_st` were never dumped or restored (239 144 B of
  garbage diff).  Now in the state; magic bumped `SOVSTA1` -> `SOVSTA2`; a bad
  magic unlinks both `.state*` files in auto mode.
- `sd_reapply` did not roll `br_*` back, so walk-emitted entries shadowed the
  cached ones in `put`'s backward `br_id` scan.
- the boundary function's frame patch landed 11 034 B early (the walk's `pro_at`
  is the previous function's).  `pro_src()` — declared in `state.sov` so both
  backends reach it — returns the region's trailing placeholder; the state stores
  the placeholder's *distance from the region end* (`sd_pro_rel`), the only thing
  a fresh process can know when it never emits that prologue itself.

Gate: `work/art/check.sh` = `*** ALL MODES IDENTICAL ***`, `usestate rc=0` on both
q1.sov and tests/run.sov (state 51 800 B for run.sov).  Honest harness
`work/bench_state2.py`: run.sov cold 61.0 / mkstate 56.1 / usestate 55.6 / auto
55.8 ms (box drifting ~14 %).

**2. LANDED — one byte-presence pass replaces 14 operator scans in `expr_body`.**
The dispatch ran `if cfind1(e, X) > 0 - 1 -> p: fop(e, "op")` once per operator
level: 14 `cfind1` SWAR scans plus the `fop2`/`fop3`/`look` reject scans for every
expression — 22 855 calls per run.sov build (counter probe).  Now one pass sets a
byte-presence bitmap (`ob1` for 0..63, `ob2` for 64..127) and every level tests
two ALU ops; `fop2`, `fop3`, `look(e,"(")`, `look(e," ")` are gated by the same
bits.  Presence is exactly what `cfind1(e, X) > 0 - 1` tested and both are
quote-blind byte scans, so every decision is bit-identical.

Measured with `work/ab2.py` (11 interleaved runs, `--no-cache --no-learn`, same
tree but for the patch): cpu med **-5.5 %**, wall med **-5.4 %**, walk min -2.2 %
(-7.4 % in the first measurement).  Gates: `verify.sh` 242 flat + 21 binaries,
0 failures; fixtures identical; `cycle.sh --full` BEHAVIOUR CLEAN (0 changed on
run.sov and q1.sov); self-build fixed point `30cc57908c4c`.

**3. `work/ab.py` cannot see changes under ~10 % on this box — use `work/ab2.py`.**
ab.py times the whole process and reported 0.0 % for the change above while three
other clocks agreed on 5-8 %.  ab2.py reads the compiler's own `--prof` marks
(walk = 3-scanned -> 4-compiled), `getrusage` cpu, and wall, interleaved.  Any
"neutral" verdict measured with ab.py alone is suspect and must be re-checked with
ab2.py before it is treated as settled.

**4. Counter-probe facts (fresh tree, print at `mark('4-compiled')`).**
expr_body 22 855 calls; cops 23 142; patch rows 8 471 + br rows 3 632 (= ~48 k list
appends/build); intern_fast_do 1 410 (0 misses).  `length`, `intern_kid`, `addp`,
`_sov_list_add` never fire as functions: they are inlined twins, so the ptrace
sampler's per-symbol self-times for those names are mis-attributed (the map names
the standalone blob; the calls are inlined at the call site).  Self-times for
functions that *are* called (expr_body, cops, intern_fast_do) are sound.  A
deliberate 14-call delay probe inside expr_body moved nothing; a 100-iteration
live loop moved 4.4 ms — the walk responds to real work, not to call-count changes.

**Hygiene:** 896 files, 210 `.sug` (207 library + `runtime.sug` + 2 tests), no
`.ac`/`.state`; `refresh_sug.py` green (1 rewritten = `library/cx86.sov.sug`).
Fleet: 142 rebuilt and installed; 16 arm-hosted steps build only on their own host
(pre-existing); 14 launcher-target steps byte-differ from their committed binaries
(pre-existing — `fleet_after2.json` records the same outputs).

**5. State-replay circuit-breaker (LANDED).** `tests/fast.sov` still reproduces a
2-byte-different artifact on replay, so every stateful build of it paid the
fallback: 113 ms (resume attempt + child rebuild) against 44 ms cold, forever,
because auto mode rewrote the pair each time.  A verified mismatch now writes
`<src>.state.poison`; auto mode then skips both reading and writing that input's
state, so builds after the first mismatch run at cold speed (measured: 113.2 ->
47.4 -> 50.7 ms, artifact `4005a6b38a2a` in all three).  Explicit `--mkstate` /
`--usestate` ignore the marker (`work/bench_state2.py` deletes it with the pair),
the line is printed when it is written, and deleting the file restores the
default-on path.

Open root cause for the next attempt — the exact divergence, measured today with
a capture build: `tests/fast.sov` replay differs from cold in exactly two 3-byte
instructions, both a `mov rdi,rax` that becomes a store:

    code 10769  _sov_realloc+264   cold 48 89 c7   replay 48 89 06   (mov [rsi],rax)
    code 86144  suite+4245         cold 48 89 c7   replay 48 89 00   (mov [rax],rax)

`tests/run.sov` reproduces byte-for-byte (region 13 342 B), `tests/fast.sov` has a
644 B region and diverges in functions far outside it, so the cause is compiler
state that emitting the skipped functions mutated and the state does not carry —
not the region bytes.  The state dumps 10 list globals plus ~28 scalars
(`state.sov` dump/restore); `locals`, `pad_ver`, `fn_names`, `glob_names`,
`kv`/`kn`, `cval`/`cval_var` are not among them, and `sub_into`'s slot choice is
the place to trace (a register move turning into a memory store is a slot
decision).  Reproduce with the capture branch on the linux driver:
`bb: ac_slurp(outf) ;; file_write_bytes(str_cat(outf,'.stateout'), bb, ac_len) ;;
sys_exit(9)` before `sys_unlink(sd_path)`, then map the offsets with a `--bytes`
build of the same input.

**Fleet after this turn:** `cycle.sh --full` = candidate `04d0a5866686` installed,
**0 byte-differ** across the 142 rebuildable steps (the 14 launcher-target diffs
that were there this morning are gone now that the fleet was refreshed with the
new compiler), BEHAVIOUR CLEAN, and the leashed-target bench shows
watchos 165.7 ms cold / 1.30 ms repeat (127x), android 115.4 / 3.39 (34x),
windows 64.1 / 3.51 (18.3x) — windows cold fell from 114.5 ms when its committed
binary was refreshed from the stale one.

## 11n — replay circuit-breaker upgraded; two silent defects found and fixed; probe-attribution rule (2026-10-08)

**1. `tests/fast.sov`'s replay divergence — what was ruled out.**
Dumping and restoring `locals` (the slot table `slot()` appends to) was tried as the
missing-state hypothesis: it did **not** fix fast.sov's two bytes and it *broke*
`tests/run.sov`'s replay badly (282 525 bytes differ, the whole prologue on).
Reverted.  The reason is visible in the driver: `locals` is explicitly reset per
function (`locals: _sov_list_new()` at the top of each function's emission), so the
snapshot's copy is discarded immediately.  The two-byte divergence in fast.sov is
therefore still open; it is bounded by the circuit-breaker below and does not
affect run.sov, q0, q1 or the fleet.

**2. Replay circuit-breaker, now fingerprint-keyed (LANDED).**
The marker written on a verified mismatch carries the **fingerprint of the compiler
that failed** (`ac_fh(argv[0])`, the same helper the artifact cache uses).  Auto mode
skips reading *and* writing that input's state only while the marker names the
running binary; a rebuilt or replaced compiler silently clears it and gets one fresh
attempt.  Verified end to end: first auto build 142.1 ms (mismatch, marker written),
second 59.8 ms (cold path, no mismatch), a foreign marker is ignored and rewritten.
`work/bench_state2.py` grew an `auto2` leg that reports the *steady-state* auto build
(the number a user sees from the second build onward): fast.sov `auto 148.1` vs
`auto2 59.9 ms`, run.sov `auto 66.9` / `auto2 66.7 ms`.

**3. Two silent defects found while sweeping — both fixed.**
* **Shipped:** the committed compiler still printed `SH3 headers` / `names` / the
  header and name counts on every state reuse (leftover instrumentation from the
  first defect hunt).  Removed; the landed compiler no longer prints it.
* **Debug damage:** a blanket cleanup regex (`sys_exit(9)` anchors) deleted the
  `bb: ac_slurp(outf)` line from the driver's `ac_store`, which left `bb` undefined
  and broke the *artifact cache store* path — the compiler would not even build
  itself.  Repaired; the build is byte-identical to the shipped binary again and the
  fleet behaviour gate is clean.  Lesson: never run broad regex cleanups over the
  driver; strip instrumentation by exact anchor string only.

**4. Probe-attribution rule (cost several rounds this session).**
98 emitter helpers are **native twins** (`emit`, `emit2`, `emit3`, `emit4`, `emit8`,
`ocput`, `ocset`, `ocget`, `oc_here`, `here`, `put`'s neighbours, `strip`, `look`, …).
For those functions the source body is *not emitted*: an instrumentation line placed
inside one is dead code and will never print, even though the flat text shows it.
Instrument only non-twinned code (`expr_body`, `cops`, `nind`, `slot`, `state.sov`,
driver code).  Positive/negative controls recorded: a probe in `cops` printed, probes
in `ocput`/`ocset`/`emit2`/`emit3`/`strip` never do.

**5. Also verified this session (no change needed).**
The sugar cache's consumer-side check is exact: after a same-second edit that
`refresh_sug.py` reports as "already current" (its mtime+size key collides), the
compiler still re-sugars from the live source — the flat text contains the new
marker.  The stat-only report is a reporting inaccuracy, not a correctness hole;
still run `refresh_sug.py` after every edit so the *cache* (not just the build)
reflects the tree.

**Fleet after this turn:** `cycle.sh --full` = candidate `bbb45cc25426` installed,
**0 byte-differ**, BEHAVIOUR CLEAN on 155 drivers x 2 fixtures; art gate
`*** ALL MODES IDENTICAL ***` (state 51 800 B for run.sov, 71 285 B for fast.sov);
watchos 214.6 ms cold / 1.31 ms repeat (164x), android 164.2 / 3.43 (48x),
windows 114.0 / 3.46 (33x); tree 896 files, 210 `.sug` all current, no
`.ac`/`.state`, launcher `313d693b9c3a` unchanged.

**Open queue for the next session:** (a) the fast.sov replay byte (two `mov rdi,rax`
turned `mov [rsi],rax` / `mov [rax],rax`, code 10769 `_sov_realloc+264` and 86144
`suite+4245`; the write happens inside the emission walk, before `warn_unused`);
(b) **re-check the parked "neutral" verdicts with `work/ab2.py`** — every negative
measured with the old whole-process harness (`shared prefix state`, `build_used_fns`,
native-twin slice, driver re-sugar removal) is suspect and must be re-run before it
is treated as settled.

## 11o — what the state reuse is actually worth, and the next lever (2026-10-08)

**Measured with the honest harness on the shipped tree.**

* The prelude skip **does** save real time: walk `3-scanned -> 4-compiled`
  **40 737 us cold vs 37 278 us with the state reused** (min of 7 interleaved
  reps, same binary) = **3 459 us, 8.5 % of the walk.**
* It is invisible in the total clock because the state costs about as much as it
  saves: file read + text decoding of every restored list + `sd_reapply` rollback
  + region copy + `sd_seed_intern` + verification ≈ 3 ms.  cold 63.6 / mkstate
  66.3 / usestate 66.1 / auto 64.3 / auto2 65.3 ms on run.sov.
* **Why only 3.5 ms:** the cached region ends at the *first user function*
  (`snap_fi = 45` of 600 functions, 13 342 B of a 303 624 B artifact).  The
  runtime and the library chunks - the 21.27 ms item in `EMIT_WALK_BUDGET.md` -
  sit *after* it and are recompiled every build.  The fix is a boundary-rule
  change (cache the library suffix, not the prelude); the plan and the gates it
  must pass are written up in `work/SHARED_PREFIX_STATE.md`, which this session
  re-opened with the measurements above.

**LANDED this session (small, resume clock only):** `sd_fh` (the state's
integrity fingerprint) folded one byte per interpreted step; it now folds 8 bytes
per step with a byte tail.  Every byte of the file still enters the fold and the
writer and the checker are always the same binary, so the artifact is unaffected.
Measured interleaved: resume builds **-0.74 ms (-1.2 %)**, cold unchanged (-0.16 %).
Candidate `3d324b880482`; `cycle.sh --full` 0 byte-differ, BEHAVIOUR CLEAN; art
gate `ALL MODES IDENTICAL` (state 51 800 B).

**Measured-and-killed this session (do not re-chase):**
* cache-key fingerprints (the 580 KB compiler binary + the input, four
  fingerprints per build): **0.4 ms total** — not a target.
* `lines_of`: 7 calls, **1 237 002 bytes split per build** — inherent input size,
  no repeated split to memoise.
* `cut` and `lines_of_fast` already copy/scan 8 bytes per step (SWAR) — nothing
  left there.
* `locals` in the state: tried, **regressed run.sov** (the driver resets it per
  function) — reverted; the open fast.sov two-byte replay divergence is untouched
  by it.

**Current cold profile of the shipped linux compiler** (207 220 samples,
`work/sampler2.py`, self time): `ih_find` 9.19 (twin), `compile` 7.14, `length`
6.82 (twin), `call_args` 6.05, `_sov_list_add` 5.93 (twin), `expr_body` 5.37,
`body` 3.77, `ih_put` 3.77, `_sov_strlen` 3.37 (twin), `num_value` 3.32,
`_sov_find_text` 3.24 (twin), `intern_kid` 3.00 (twin), `cut` 2.32, `_sov_strcat`
2.07, `stmt` 2.02 %.  The three biggest items are hand-emitted **twin blobs**
(`ih_find`, `length`, `_sov_list_add`), so the next front-end win on the x86 path
means editing those blobs, not their source bodies.

## 11p — what this session killed, and what the harness can and cannot see (2026-10-08)

**NEGATIVE 1 — the builtin-dispatch first-byte gate changes the artifact (do not retry blind).**
`call_args` runs **108** literal `_sov_str_eq(name, '<builtin>')` tests per call
(96 distinct names; 58 in the linux driver, the rest injected by the `inc00` /
`inc03` slices; 6 430 calls per run.sov build).  The names' first bytes are 95 97
98 99 100 104 105 106 108 110 112 114 115 117 119.  Two variants were built:

* one gate in front of the whole chain (`if band(bshl(1, band(peek_byte(name,0),63)), MASK) = 0 -> return 0`):
  compiles, but the artifact changes — and the reason is **not** the mask: the
  chain's tail (in the slices) emits `calln(name)` for anything unmatched, so
  short-circuiting the chain skips that fall-through.
* 41 per-test gates (`if peek_byte(name,0) = <b> -> if _sov_str_eq(name,'<lit>') = 1 -> ...`),
  driver + inc00 + inc03, line-preserving: compiles clean (0 errors) but the
  artifact still changes.  `_sov_str_eq` (`runtime.sov:577`) is byte-exact
  (compares `peek_byte` one at a time and returns at the first difference), so a
  first-byte test *cannot* change a test's verdict — the cause has to be an
  interaction with the shared slices (their parameter substitution / the
  `if A -> if B = 1 -> <stmt>` inline nesting, which parses differently from the
  block form the tree already proves).  **Reproduce before retrying: build either
  variant, run `tests/run.sov`, expect `6b9c3f7c193c`; both give something else.**
  Everything was reverted: the tree rebuilds byte-identical to the shipped
  compiler after the revert (checked).

**NEGATIVE 2 — the walk-min metric is order-biased; the CPU median is the metric to trust.**
Re-checking the `build_used_fns` refutation with `work/ab2.py`, 25 reps each way:

| leg order | walk min | cpu med | wall med |
|---|---|---|---|
| A=ablated, B=shipped | +0.86 % | -0.82 % | -0.80 % |
| A=shipped, B=ablated | +13.43 % | -0.61 % | -0.68 % |

The walk-min column flips sign (and magnitude) with the leg order, so it is a
sampling artefact; the CPU and wall medians agree with each other and stay inside
±0.8 %.  Conclusion: `build_used_fns` is neutral — **the earlier refutation stands**
— and **the harness' noise floor is ≈ ±0.7 % on CPU/wall medians, while walk-min
alone must never be used as a verdict.**  The bitmap win recorded in 11m was
corroborated by CPU and wall in *both* leg orders, so it is unaffected by this.

**Tool added:** `work/fixtree.sh` — restores the exec bits the workspace snapshot
drops between turns (all committed binaries under `compilers/`, `sovren`,
`sovren.exe`).  Without it every harness fails with rc=126 / `Permission denied`;
run it first whenever a build call reports rc=126.

**Session verification at the end of this turn:** tree == shipped compiler
(`3d324b880482`) by rebuild-and-compare, 0 `.ac`/`.state` files, 210 `.sug` all
current, launcher `313d693b9c3a`.  No source change landed in this turn; the
landed change of this session is `3d324b880482` (8-byte state fingerprint, 11o).

## 11q — the `--bytes` writer was 42 ms of quadratic string building; the walk is linear after all (2026-10-08)

### The defect
`compilers/linux/compiler.sov`, the `bytes_mode` block (≈:981-1011).  The `.map`
was assembled by appending **one `str_cat` per emitted function onto the whole
growing text** (`mt`), i.e. ~600 reallocations of a string that ends up 13 KB —
plus a byte-wise copy of the entire code image into a heap buffer before
writing `.bin`.  Direct measurement with two extra marks in a scratch driver:

    tests/run.sov   4-compiled 69379 µs | b1-bin-written 850 µs | b2-map-written 42262 µs
    /tmp/gen_800    4-compiled  7931 µs | b1-bin-written 154 µs | b2-map-written 40712 µs

The map write alone was **larger than the whole emission walk**.  `--prof` could
never see it: the marks end at `4-compiled`, and `mark('5-written')` at :1036 is
dead text inside `mark`'s own body.  Sampler confirmation on a `--bytes` build:
`_sov_strcat` **15.03 % self** (2.07 % without `--bytes`).

### The fix (landed)
`work/patch_map_write.py`: write `.bin` straight from the code image `oc` (the
copy bought nothing), and build the map by sizing it in one pass, filling **one**
`_sov_heap_alloc` buffer byte-wise, and writing once.  Output is byte-identical —
`.bin` **and** `.map` md5s match the old writer on q0, q1, gen_800, run.sov,
fast.sov.

| input | old | new | Δ |
|---|---|---|---|
| run.sov | 93.70 ms | **63.04** | **−32.7 %** |
| fast.sov | 85.40 ms | **57.59** | **−32.6 %** |
| gen_800 (800 fns) | 39.42 ms | **10.51** | **−73.3 %** |
| q0 / q1 | 0.93 / 0.90 | 1.06 / 0.91 | noise |

Candidate **`840aa713f5ff`**: art gate ALL MODES IDENTICAL on 4 programs,
verify 247 flat / 25 binaries / 0 failures, cycle 142 built / 16 fail /
0 byte-differ, BEHAVIOUR CLEAN.

### Second landing: nine full-text scans with no early exit
`library/inc/inc00.sov:173-181` scanned the entire spliced source **nine times**
(`look(src, '_sov_list')`, `look(src, 'load_file')`, … `join `) to set one
boolean, with no early exit and no ordering by likelihood.  `need` is the OR of
the nine, so guarding each with `if need = 0 ->` cannot change the result.
Edited in place to preserve the file's 2039 lines (`inc00.sov` is referenced by
line number from dozens of files: `2016`, `1697`, `1863`, `781`, `491 9`, …).

* byte-identical on run.sov `6b9c3f7c193c`, fast.sov `4005a6b38a2a`,
  q0 `5655d3b6aca4`, q1 `d65814f686b3`
* A/B (ab2.py, 13 interleaved reps, both leg orders): **cpu −3.24 %, wall
  −3.35 %** — above the ±0.7 % noise floor.  `inc00.sov` is shared by all 155
  drivers, so this is a fleet-wide cold-build win.

Candidate **`6ef2d4181ac7`**: self-build reproduces the exact A/B'd binary;
art ALL MODES IDENTICAL; verify 247/25/0; cycle BEHAVIOUR CLEAN
(watchos 217.4/1.46, android 165.8/3.55, windows 114.4/3.47).

### Corrections to beliefs recorded earlier in this file
1. **"cost grows super-linearly past ~256 functions" was the map writer.**  On
   the plain path the marginal cost is **8.2-9.5 µs/function and linear**
   (gen_200 2.68 → gen_400 4.35 → gen_800 7.62 ms).  The `--bytes` tax is now
   **±0.3 ms** across the whole 1-800 fn series (it was +6 to +31 ms).
2. **There is no dead-code elimination at all.**  All 800 user functions appear
   in the map at every scale while only `f0` is called (the compiler even prints
   799 `Warning: never used`).  The constant 4,128 B artifact through n ≤ 64 is
   **ELF page rounding**, not DCE.
3. **The marks fully cover a build**: 1.35 ms (2 %) unaccounted on run.sov and
   fast.sov.  The "15 ms invisible" gap of the earlier session was the map
   writer plus box drift.
4. `1-rt-loaded` proper (the `look`/`u_sugar` part) is **0.07 ms** — the sugar
   cache already serves it.  The 8.64 ms (run.sov) / 6.20 ms (fast.sov) is
   `1a-rt-slice`: input load + splice/`u_sugar` + `pull_uses`/`apply_aliases` +
   the nine scans + runtime load.
5. Default builds are already **2.17 ms** for run.sov (2.29 ms warm) vs 63.89 ms
   with `--no-cache` — the shipped `.prebuilt` closure gives 29×, so the honest
   cold clock and the default clock differ by an order of magnitude.

### Tree hygiene defect found
167 ELF files had lost their execute bit (`sovren`, every `compilers/*/compiler`)
— the workspace snapshot does not preserve file modes.  A non-executable tree
looks exactly like a hang: the build returns 126 and the binary is never
written.  Restored with `chmod +x`; the self-build then reproduced
`3d324b880482`.  `cycle.sh` sets exec bits on the drivers it installs, but a
fresh checkout needs it too.

### Do not retry
* The 188 other self-growing accumulators in the tree are all bounded: the
  ~180 `blk: str_cat(blk, nr)` sites are an embedded `eval_block` **source-block**
  accumulator inside backend drivers (bounded by one block), `ccore.sov:1025`
  builds one line per sugar value, `inc02.sov:1807` is bounded by word length.
* **Sovren loop idiom**: only the FIRST statement after `as long as c -> …` is
  guaranteed to run as the loop body.  Loop-carried increments go on the next
  indented line.  A chained `;; mj: mj + 1` after the arrow produced a real
  infinite loop in the first draft of the map writer (`bmp.sov:6` looks like a
  counter-example but its first statement *is* the increment, so it terminates
  either way).

## 11r — three prefix probes instead of six in the lint gate; a permanent lint behaviour gate; four refuted candidates (2026-10-08)

### Fresh caller attribution (sampler2.py, run.sov, 160,636 samples)

    17241   9.41%  compile        <- main
    15427   8.42%  _sov_strcat    <- main
    11434   6.24%  expr_body      <- expr
    10885   5.94%  length         <- main
    10456   5.71%  _sov_strlen    <- length
     9038   4.93%  _sov_find_text <- u_scan
     3511   1.92%  _sov_find_text <- sg_num
     1614   0.88%  cops           <- expr

`_sov_find_text` is 9.88 % self and its single biggest caller was **`u_scan`**,
not the parser: the raw-memory lint gate ran up to six separate full-source
substring searches, and every *absent* needle costs a complete pass (~0.7 ms on
run.sov).  `cops`, the suspected caller, is 0.88 %.

### LANDED: `work/patch_uscan_probes.py`
All six counted tokens contain `peek_`, `poke_` or `port_`, so three probes
decide the gate.  Conservative in the only direction that matters: a prefix can
match without a counted token (the walk then runs and counts nothing, exactly as
it already does for a clean file), but a counted token can never appear without
its prefix — so the gate can never skip a file it must lint.

* ab2.py, 21 interleaved reps, both leg orders: run.sov **cpu −2.27 %, wall
  −2.27→−2.12 %**; fast.sov cpu −0.92 %, wall −0.82 %
* artifacts byte-identical on run.sov `6b9c3f7c193c`, fast.sov `4005a6b38a2a`,
  q0 `5655d3b6aca4`, q1 `d65814f686b3`, self-build `6ef2d4181ac7`; note counts
  733 / 212 / 312 unchanged
* candidate **`af42da18c56f`**: art ALL MODES IDENTICAL (4 programs), verify
  247 flat / 25 binaries / 0 failures against `6ef2d4181ac7`, cycle 142 built /
  16 fail / 0 byte-differ, **BEHAVIOUR CLEAN** (watchos 214.7/1.43, android
  167.7/3.58, windows 114.7/3.54)

### New permanent gate: `work/lint_tests.sh`
15 cases (`work/make_lint_tests.py` regenerates them, `work/lint_baseline.txt`
is the reference table) pinning every decision the lint makes: deny vs pass,
note vs no note, `# unsafe` per-line marker, `# unsafe-module`, `unsafe:` block
scoping, comment-only mentions, and CRLF endings.  It earned its place
immediately — see the fast-path defect below.

**The harness must run from the tree.**  A candidate in `/tmp` cannot resolve
`runtime.sov`, so every case fails with "cannot read runtime" — which looks
exactly like a lint verdict.  The first comparison reported "identical on all
deny cases" purely because those cases fail anyway.  `lint_tests.sh` now cds
into the tree.

### Refuted this session (do not retry without new evidence)
1. **u_scan rewritten to skip `strip()`** (two index walks per line instead):
   run.sov cpu −1.43 % but **fast.sov +2.95 %**.  The per-line *walk* is the
   cost, not the allocation.
2. **u_scan fast path** (when the source has neither `unsafe:` nor `# unsafe`,
   skip the indent walk / `strip` / block logic): `3a-uscan` went 4.32 → **4.97
   ms** on run.sov.  The two extra marker probes cost as much as the walk they
   avoided.  Its first draft also **turned checked primitives into denials**:
   the px00.sov:2018 macro sets `uraw` *and* `ubare` for the four raw tokens
   while `peek_byte(`/`poke_byte(` set `uraw` alone, and that distinction is the
   whole difference between "denied" and "noted".  Artifact byte-identity would
   not have caught it; the lint gate did.
3. **`length_cache` 1 MB/65,536 → 16 MB/1,048,576** (twin and source patched
   together): cpu −0.36 % / −0.16 % — neutral.  The misses are compulsory, not
   collisions.
4. **"`cops`' `look` guards are redundant"** — false.  `repl` opens with the
   identical `_sov_find_text` test, so the guard *saves* a search whenever the
   operator is absent.

### Twin-hardcoded constants (the list grows)
`emit_nt_length` hardcodes the length-cache allocation (`mov rdi,0x00100000`,
bytes `87 72 199 199 0 0 16 0`) and its slot mask (`and ecx,0xFFFF`, bytes
`129 225 255 255 0 0`) exactly as `emit_nt_ih_find` hardcodes the interner mask.
`strip_cache` uses the *identical* 1 MB / 65,536 geometry and therefore the
identical machine-code byte sequence, so a patch of those immediates must be
anchored on the surrounding `load_glob("length_cache")` block — matching on the
byte string alone hits two sites.

### Two harness rules added
* **Compare the candidate's md5 against the baseline before any A/B.**  Editing
  the source body of `length` produces a byte-identical binary (the twin
  replaces it), and that A/B reported a confident −0.93 % for a no-op.
* `--prof` marks now cover 98 % of a build, so a stage mark is trustworthy;
  `3a-uscan` (added by patching `inc00.sov:415` in a scratch tree) is what
  refuted the fast path in one measurement.


## 11s. `_sov_strcat` / `join` thread — measured, and one wrong inference corrected

**Target.** `_sov_strcat <- main` was the #2 caller pair in the 6ef2d4181ac7
profile (8.42 %).  Every `join`/`str_cat` in every program funnels through it.

**What the tree actually does.**  `emit_nt_strcat` (cx86.sov:1072) is a
hand-written twin.  Decoded: it strlens **both** arguments with a
byte-at-a-time loop (`cmp byte [r8+r10],0 / jz / inc / jmp`), then copies with
`rep movsb` (`243 164`) twice.  So the copy is already optimal and the only
waste is the two byte-loop strlens.  The *source* `_sov_strcat`
(runtime.sov:526) is the mirror image: SWAR `_sov_strlen` twice, then 8-byte
`poke_i64` copy loops.

**Refuted 1 — disable the twin and use the source.**  Disabling
`kid__sov_strcat -> return emit_nt_strcat()` at cx86.sov:3545 gave a different
compiler (7bc7f9036919) and byte-identical artifacts for run.sov, fast.sov, q0,
q1.  Three `ab2.py` legs on that *same* binary pair, 21 reps each:
cpu **+0.49 %**, **-1.60 %**, **+1.49 %** — i.e. noise around zero, direction
not even stable.  NEUTRAL, not landed.

**Refuted 2 — widen the source copy loops 8 -> 32 bytes/iter**
(`work/patch_strcat_wide.py`).  Self-built compiler **byte-identical**
(af42da18c56f) both with the twin on and with it off, and the twin-off + widened
build is the same md5 (7bc7f9036919) as twin-off alone.  The source body never
reaches the binary: a second path (`try_native_body`) emits the native body, so
`:3545` is only the call-site half.  INERT.

**Inference rule learned (this is the part that cost a wrong claim).**
Byte-identical artifacts do **not** prove a twin is unreachable.  run.sov/q0/q1
never call `join`/`str_cat`, so they are twin-insensitive either way.  The
decisive test is to edit the **runtime source** of the twinned function and see
whether the self-built compiler changes: it did not, which proves the twin body
path is live.

**What is left on this thread.**  Only hand-assembling the emitted byte stream
in `emit_nt_strcat` to replace its two byte-loop strlens with SWAR ones.  The
copy is already `rep movsb`.  Payoff is bounded by the strlen share of ~5 %,
so <= ~2-3 %; deferred as poor risk/reward against the remaining levers.

**Harness fix landed.**  The exec bit is lost on every snapshot restore, which
presents as rc=126 and looks like a hang.  `work/lint_tests.sh` now runs
`work/fixtree.sh` and `chmod +x "$CC"` itself, so the lint gate can no longer
report a permissions failure as a verdict.


## 11t. Four candidates measured neutral, one real correction, and a toolchain

**Toolchain landed: `work/twin_asm.py`.**  Every hot function here is a
hand-written x86 twin (`length`, `lines_of_fast`, `ih_find`, `_sov_strcat`,
`_sov_find_text`), which is why source-level edits keep coming back inert.  The
remaining levers all live in emitted byte streams, so there is now a way to edit
them without hand-encoding decimal byte lists: write assembly, `as` + `objcopy`
it, `objdump` the result, print both.  `twin_asm.py --bytes f.bin` disassembles
an existing twin for reading.

**CORRECTION to an earlier note.**  The record said `_sov_find_text` "is already
SWAR; its cost is call volume".  Half right.  `emit_nt_find` (cx86.sov:920, 355
bytes) uses SWAR for the two **strlens** only — the *search* itself is
`cmp %dl,(%r10,%rcx,1) / jne / inc %rcx / jmp`, i.e. byte-at-a-time, five
instructions per byte.  Registers: r10 = haystack, r11 = needle.

**Refuted 1 — use the SWAR source `_sov_find_text` instead of that twin.**
Disabling `:3534` is behaviour-clean (fixtures run identical, lint 15/15
identical to `lint_baseline.txt`).  Six `ab2.py` legs: run.sov +0.32 / +0.46 /
+0.11 %, fast.sov -1.71 / +0.56 % (one leg read +6.23 % on a polluted baseline
of 67.09 ms and is discarded).  Mean of the clean legs ~0.  The SWAR source is
not faster because the workload is short needles in short haysticks, where its
two strlens cost more than the byte scan.  **This also explains the 9.88 % self
time: it is call volume on short strings, not per-call inefficiency.**

**Refuted 2 — `repnz scasb` for `emit_nt_strcat`'s two byte-loop strlens**
(`work/patch_strcat_scasb.py`, 87 -> 100 bytes, register state at the
`calln("_sov_heap_alloc")` boundary preserved exactly, fixtures byte-identical
and run identical).  Two legs: +0.39 % / -0.20 %.  `repnz scasb` is not
ERMSB-optimised the way `rep movsb` is, and the byte loop was already near one
cycle per byte.

**Refuted 3 — remove `length_cache` entirely** (twin off, source reduced to
`return _sov_strlen(s)`; fixtures run identical).  Two legs: +0.23 % / -1.38 %.
Together with the earlier result that *enlarging* it 16x is neutral, the cache
neither helps nor hurts: `length()` is not dominated by long strings.  **No
cache tuning can cut `length`'s ~6.8 %; only the -8 header can.**  That is now
the single well-evidenced lever left, and its hazard gate is cleared
(`work/LENGTH_HEADER.md`).

**Harness note.**  `/tmp/lint` does not survive a segment boundary; regenerate
with `work/make_lint_tests.py` (15 cases) or `lint_tests.sh` silently reports a
single `*.sov rc=1` line instead of 15 verdicts.  The regenerated base matches
`work/lint_baseline.txt` exactly.

**Nothing landed as a speedup this turn.**  Installed compiler is still
`af42da18c56f`; `cx86.sov` is still `19351af915be`; `runtime.sov` unmodified.


## 11u. INCIDENT (tree deleted and recovered), and the phase table replaces the sampler

**INCIDENT.**  I ran `python3 work/phases.py /home/user/projects/sovren`.  That
argument is the *scratch* directory, and `build_probe()` does `rm -rf SCRATCH`
before copying the repo into it — so it deleted the landed tree, then failed to
restore it (`cp: cannot stat`).  Recovered from `/tmp/t1`, a full 896-file copy
made earlier in the same turn, and reversed the one patch it carried.
Post-recovery verification: `cx86.sov` `19351af915be`, `runtime.sov`
`5bd2dc9c21ea`, `ccore.sov` `f70a77cd46a0`, installed compiler `af42da18c56f`,
self-build fixed point `af42da18c56f`, all four artifacts byte-identical
(run `6b9c3f7c193c`, fast `4005a6b38a2a`, q0 `5655d3b6aca4`, q1 `d65814f686b3`),
`refresh_sug.py` 209 green / 0 problems, 896 files / 37 MB.
**`work/phases.py` now refuses any scratch dir that is not under `/tmp` or that
equals the repo.**  Rule: never pass a real tree as a scratch argument.

**The sampler does not predict wins.**  Seven candidates in two turns, every one
derived from ptrace self-time / caller-pair shares, every one measured neutral
within +-0.5 %: SWAR `_sov_find_text`, `repnz scasb` strcat strlens, no
`length_cache`, widened strcat copy, `ds_pl` guard, `dce_stores` early-out.  Two
of those (`work/patch_dce_pl_guard.py`, `work/patch_dce_earlyout.py`) are
provably output-identical — all four artifacts came back byte-identical — and
still measured +0.13 % and -0.11 %.  **Stop ranking work from the sampler.**

**Cold phase table for tests/run.sov** (`phases.py`, `--no-cache --learn`), the
instrument that predicted every landed win:

    tA_load_done     0.39   tK2_pass1done   1.52 (+1.10)
    tP0_compile      0.41   tK3_loopsdone   2.24 (+0.72)
    tK1_linesdone    0.42   tK5_tablesdone  2.69 (+0.44)
    tE0_emit        10.65 (+7.96)           <- unexplained gap
    tD0_dump        12.47 (+1.82)  tD1_dumped 12.67 (+0.19)
    tP1_compiled    46.22 (+33.56)          <- emission walk, user side
    tP2_written     48.03 (+1.80)  tS0_sum 48.04  tW_written 48.67 (+0.63)

**REFUTED: "the cold build is ~95 % fixed cost".**  I inferred that from
fast.sov (21 lines, 59.4 ms) costing about the same as run.sov (3459 lines,
63.2 ms).  A genuine 3-line program compiles cold in **1.0 ms**, so there is no
large fixed cost.  fast.sov is small textually but calls `suite()` and
`tr_use('./sovren')`, which transitively reach most of the tree.

**Corollary, and it closes a lever I was about to open: the compiler already
compiles only what a program reaches.**  3 lines = 1.0 ms cold proves
reachability-based skipping is already in place, so "skip unreferenced library
functions" is not available work.  The remaining cold cost is genuine codegen
for reachable code, and the two concrete targets the phase table leaves are the
**7.96 ms gap** before the emission walk starts and the **33.56 ms** emission
walk itself.


## 11v. addp is a twin (fusion retracted), and ablation replaces the sampler

**Retraction.**  `work/patch_addp_fuse.py` is INERT, not neutral.  The map from a
`--bytes` build lists `emit_nt_addp` at offset 102364, so `addp` is a native
twin and the source body at cx86.sov:305 never reaches the output.  Proof:
changing that body to record `at + 7` — which would corrupt every relocation —
produces a binary bit-identical to `af42da18c56f`.  The fused build's different
md5 (`bc5245ff146e`) came only from the two new global names `ap_n`/`ap_n1`
shifting the global table.  Its "-0.09 %" measured nothing.  Same trap as
`_sov_strcat`, `length`, `_sov_find_text`: check for `emit_nt_<name>` first.

**Ablation harness landed: `work/ablate.py FN OUT`.**  Stubs one function out of
a scratch tree and builds it.  It handles both mechanisms — `emit_nt_<FN>` is
reduced to leave/ret, a plain source body gets `return` inserted with the body
kept as unreachable code (deleting it fails the build with "no such name").
Output is garbage by design; only the timing means anything.

**Measured costs (cpu %, cost of the ablated code, run.sov):**

| ablated | cpu saved | sampler had said |
|---|---|---|
| `pull_uses` | **47 % of the build** | 2.27 % |
| `dce_stores` | 3.17 % | ~3.65 % (1.38 self + 2.27 via _sov_list_add) |
| `cflush_globs` | 2.63 % | 2.64 % |
| `emit_nt_addp` (all patch recording) | 0.83 % | ~5.2 % via _sov_list_add |

**So the sampler is not uniformly wrong, and my "off by 40x" claim was too
strong.**  It is exact for `cflush_globs` (2.64 predicted vs 2.63 measured) and
close for `dce_stores`.  It is ~6x over for `addp`, and ~20x *under* for
`pull_uses`.  Verdict: usable as a rough map, useless as a ranking, and the
caller-pair percentages are the least trustworthy part.

**The `pull_uses` number is the important one and it is not its own overhead.**
Stubbing it makes the build 1.89x faster because the compiler then never pulls
in the modules the source `use`s.  So ~47 % of a cold build of tests/run.sov is
spent compiling code the user did not write in that file.  That is consistent
with the 3-line program costing 1.0 ms: cold cost tracks *reachable* code, and
`use` is what makes run.sov reach most of the tree.  Any serious move toward
sa's throughput has to reduce reachable code, not speed up the emitter — the
emitter's own passes (dce_stores 3.17 %, cflush_globs 2.63 %, addp 0.83 %) sum
to single digits.


## 11w. The gap is 17.3x, not 42x; the biggest lever is 1.55x; parity is not reachable

**Corrected denominator.**  The 42x figure divided by run.sov's own 147,401 B.
The compiler translates the *spliced* source, which is **361,153 B** (41% run.sov,
59% pulled in by `use`).  Cold 60.1 ms over 361,153 B = **6.01 MB/s vs sa's
104.2 MB/s = 17.3x**, i.e. 499 cycles per source byte against sa's 28.
Calibration per source byte: sa 9.4 ns, tcc ~31 ns (3.3x sa, recorded figure —
the binary is absent this segment), sovren 166 ns, gcc -O0 4350 ns.
**tcc is the fastest C compiler in common use and it is 3.3x off sa.**  A
compiler at assembler throughput does not exist; the realistic ceiling from here
is tcc-like, about 5.3x.

**Only 2 cores on this machine**, so parallelism caps at 2x.  Not the lever.

**No function-level pruning exists.**  run.sov's spliced source defines **600**
functions and the output .map contains **607** — every spliced function is
compiled and emitted whether main reaches it or not.  Static reachability from
main, deliberately over-approximated (any bare mention counts as an edge, so the
prize below is conservative): **306 reachable / 294 unreachable (49%)**, and
**35% of function-body bytes unreachable**.

    now              361,153 B in 60.1 ms =  6.01 MB/s   gap 17.3x
    perfect pruning  361,153 B in 38.8 ms =  9.31 MB/s   gap 11.2x

**1.55x is the whole of the biggest lever found in this tree.**  See
`work/FUNCTION_PRUNING.md` for the design and the staging (record mention sets
and report first; skip nothing until the count is validated against the real
compiler).

**Why the existing unused pass does not already do this.**  `warn_unused` gates
on `_sov_list_get(task_user, ui) is 1` and excludes `_sov_`-prefixed names, so it
only ever inspects *user* functions.  A run.sov build emits exactly **1** "never
used" warning against 294 statically unreachable functions.  The analysis exists;
it is scoped to the wrong set and is not transitive.

**Ablation, real numbers (cpu cost of the ablated code, run.sov).**
`expr_body` ~40% and `call_args` ~8.5% are *pipeline* figures — stubbing them
removes everything downstream, not their own cost.  Every true leaf ablates to
~1%: `num_value` 0.43%, `intern_kid` 1.06%, `intern_fast` 0.11%,
`emit_nt_addp` 0.83%, `dce_stores` 3.17%, `cflush_globs` 2.63%.  There is no
dominant leaf, so 17x means every one of them at once.

**And the strategy the user asked for has already been run.**  `grep -c
'^emit_nt_' library/cx86.sov` = **76** hand-written x86 twins, including
`num_value`, `intern_kid`, `intern_fast`, `ih_find`, `length`, `emit`, `ocput`,
`addp`, `word_id`, `strlen`, `strcat`, `substr`, `lines_of_fast`.  Rewriting hot
paths in assembly is not a lever left to pull; it is 76 levers already pulled,
and the result is 6.01 MB/s.

**Conclusion, stated plainly.**  First-build parity with sa is not reachable by
any change available in this tree: the biggest single lever is 1.55x and the
remainder is distributed across the whole pipeline.  The clock that is near
parity is the repeat build — 2.6 ms, 56.4 MB/s, 1.85x from sa — and that is
reuse, not translation.

## 11x. Pruning: what this pass established
- `compile source:` = signature line in slice library `library/inc/inc05.sov:738`;
  444 `include inc/inc05.sov` directives ⇒ line count frozen, no shared hook.
- `u_sugar` on assembled source: 13/155 drivers. `warn_unused` gates on
  `task_user` ⇒ 1 warning vs 294 unreachable. Neither is a pruner.
- CORRECTION: repeat clock is 2.83 ms / 361,153 B = 127.8 MB/s = 1.23x FASTER
  than sa. Earlier "1.85x behind" used the wrong denominator. Gap is
  first-build only: 17.3x.
- Prize: provably-dead 109 fns / 6.5% = 1.07x; transitive 294 fns / 35% = 1.55x.
  Safe version is break-even once the tokenising analysis pass is paid for.
- NOT SHIPPED: mark-sweep needs ~70 lines of sovren + a hook in all 155 drivers
  + full fleet validation. Analysis cost (1-3 ms) extrapolated from lines_of
  0.42 ms / pass1 1.10 ms, NOT measured. Details: work/FUNCTION_PRUNING.md §4.

## 11y. Pruning pass BUILT, MEASURED, VALIDATED, not landed
- Shared edit point found: inc00.sov:498 `compile(all)` -> `compile(prune_dead(all))`,
  rewritten in place so the file stays 2039 lines and all 841 slice directives hold.
  Hooking at the driver's mark('2-all-spliced') was wrong: all is only 37,566 B
  there; includes resolve later inside `include inc/inc00.sov 413 10`.
- run.sov: 60.1 -> 48.7 ms = 1.235x, 6.01 -> 7.42 MB/s, gap 17.3x -> 14.0x.
  307 kept / 293 dropped (Python predicted 306/294). Binary 303,624 -> 191,888 B.
- compiler.sov (680,272 B): 123.4 -> 130.0 ms = 0.949x LOSS. Almost no dead code,
  so the ~7 ms analysis is not repaid. Break-even ~= 18% dead bytes. Fix = native
  twin for the token walk.
- Correct: q0/q1 byte- and run-identical; suite output identical to the timeout
  cut; self-hosts (564,088 B) and gen2 builds q0 to 5655d3b6aca4; 3 builds -> 1 md5.
- Files: work/prune_dead.sov (the pass), work/apply_prune.py on|off.
- NOT LANDED: art check.sh, verify.sh refreeze, refresh_sug.py, fleet cycle,
  lint 15/15 all still owed; settle the compiler.sov regression first.
- Tree verified pristine after restore: 896 files, 0 residue, inc00.sov 2039 lines,
  rebuilds to af42da18c56f.

## 11z. Pruning measured broadly; found rt_init; still not correct
- 21 buildable test sources (12 of 33 fail for BOTH compilers, pre-existing).
  reachability+main-only: median 1.477x, max 2.729x, 19W/2L. Small programs win
  biggest (49 B source = 2.73x) - they splice the whole runtime and use little.
- CRASH bisected: main-only version segfaults on `p:'A'; return peek_byte(p,0)-28`.
  Cause = rt_init (runtime.sov:130), sets g_argc/g_argv, named NOWHERE in the
  tree, reached by emitted startup with no literal. Rooting it alone fixes it.
  Ruled out: sg_text round-trip (control byte-identical 98be33d653e2), thin_main,
  want_args (g_argc survives at column 0 so the probe is unchanged).
- Root list now = main + _sov_thread_exit + rt_init + 36 backend-hardcoded
  calln() names. With it: 17/21 behaviour-identical; 3 of the 4 diffs segfault
  in the baseline too (pre-existing).
- REMAINING DEFECT: tests/bench.sov prints 19 bytes vs 20 - print's trailing
  newline lost, so the exit-time flush path has a SECOND implicit dependency.
  Not shippable until the emitted startup/teardown reference set is complete.
- Mention-count (provably dead) variant built as the safe fallback: 1.078x median.
- Files: work/prune_dead_reach.sov, work/prune_dead.sov, work/apply_prune.py,
  work/prune_sweep.json. Tree restored + verified: 896 files, 0 residue,
  inc00.sov 2039 lines / line 498 = compile(all), rebuilds to af42da18c56f.

## §12 Dead-function pruning — LANDED as `ebd2415c15ef`

`library/ccore.sov` gains a mark-and-sweep `prune_dead pd_src pd_lim pd_inf`, and
`library/inc/inc00.sov:498` becomes `compile(prune_dead(all, snap_m, inf))`.
Unreachable library/runtime bodies are replaced by empty lines (line count, and with
it every diagnostic offset, is preserved).

Two things had to be got right before this was safe:

1. **Root completeness.** The backend names functions through `_sov_list_add(fn_names,
   "…")` and `str_fns`, not just `calln("…")`. Deriving roots from `calln` alone drops
   `_sov_alloc`, the heap allocator, and `print` silently loses its trailing newline.
   The shipped root set is 144 names: every quoted literal in the backend, drivers and
   `library/inc/` that is also a definition name.

2. **User code is never pruned.** Blanking an unreachable *user* function deletes its
   diagnostics — `d2.sov` calls an unknown `peek_raw` from a function `main` never
   reaches, and pruning it turned a hard `Error: no such task` into a clean build.
   Definitions whose name appears in `load_file(inf)` are kept and rooted, so their
   callees survive too. Only library and runtime code is removed.

Gates: fixed point YES (`ebd2415c15ef` twice) · behaviour 28/28 · lint 15/15 ·
verify.sh 0 failures, 0 FLAT-DIFF and 0 RC-DIFF vs the pristine baseline ·
art ALL MODES IDENTICAL · refresh_sug.py 207/0 problems · fleet q1.sov RC-DIFF 0 and
md5-changed 0 · fleet run.sov RC-DIFF 0 · 15 drivers fail to build, all 15 pre-existing.

Cold translation, 28 sources: 683.1 -> 619.3 ms = **1.103x** total, **1.214x** geomean,
best 1.594x (`kpci_test.sov`), worst 0.928x (`compiler.sov`, which is nearly all live
code and pays the ~7 ms analysis for nothing).

Reaches **28 of 155 drivers**. Counting `inc00.sov N M` directives in the driver files
says 1; that is the wrong instrument, because the hook also arrives through nested
includes. The reachable ceiling is 28: 2 more drivers have an unhooked `compile(all)`
but do not build at all, and 125 have no `compile(all)`.

Rollback: `work/bin/cc_preprune_af42` is the pristine compiler and
`work/drv_backup/` holds the unpatched driver sources.

## §13 `scan_prints` loop-body defect — fixed in 32 drivers

32 drivers carried a compile-time constant-folding interpreter fed **one source line at
a time**. For the idiomatic loop

    as long as i < 5 -> print i
        i: i + 1

`rv_stmt` saw only the first line, took the body as the text after `->`, and never saw
the increment. The loop variable never advanced and the 100,000-iteration guard always
fired: ~108 ms of compile time, and an emitted binary containing 99,708 copies of `0`
and none of 1–4 where the program should print `0\n1\n2\n3\n4\n` — a 1.6 MB wrong
binary.

Fix: `rv_span` extends an `as long as` statement over its deeper-indented continuation
lines, and `rv_bodies` runs a loop body line by line. 31 of the 32 now emit the correct
folded bytes; the 32nd (`harmonyos`) is a ZIP package generator and went from emitting
0 bytes to a valid 268 B package. `q1.sov` output is byte-identical because folding a
function call is beyond this interpreter either way.

Fleet: mean 23.78 -> 1.55 ms, max 122.51 -> 8.09 ms, the 32 affected drivers 108-122 ms
-> 4-8 ms (21.8x combined). Gates all green; fleet RC-DIFF 0.
Backups: `work/drv_backup/scan32/`.

## §14 User function calls folded — 32 drivers

`rv_fac` returned `rv_get(nm)` for any identifier without checking for a following `(`,
so `add(s, i)` looked up `add` as a variable, got 0, and left the argument list
unconsumed. Every program calling a user function folded to 0 and the driver emitted a
literal `0` in place of the real value — including `print add(2, 3)` outside any loop.

`rv_call nm` parses the arguments, binds parameters in a fresh environment via the
existing `load_fn`/`fn_params`/`fn_bodies` tables, evaluates the body's `return`
expression, and restores the caller's parse state and variable environment, so nested
calls work. On `linux/riscv64`: 6 cases fixed, 4 kept correct, 0 regressions; `q1.sov`
now emits `1999000` where it emitted `0`. 31 of the 32 patched drivers verified correct
against the runnable linux driver (`harmonyos` emits a ZIP package, not program output).

Cost: `q1.sov` 4.19 -> 6.02 ms on `linux/riscv64`, because folding now genuinely runs
2000 iterations with a call in each.

Fleet after §13 + §14: mean 23.78 -> 1.62 ms (14.6x), max 122.51 -> 7.90 ms (15.5x),
total 3662 -> 250 ms. Gates all green; fleet RC-DIFF 0; `q1.sov` md5-changed 31, which
is the fix. Backups: `work/drv_backup/precall/`.

## 15. Language-completeness audit + two fleet-wide fixes

Measured with a hash oracle (two same-length sources differing in one feature; artifact
md5 differs => feature honoured), validated against `compilers/linux/compiler` first.
Full write-up: `/home/user/projects/sovren/work/STUB_STATUS.md`.

Populations: **52 full-artifact** drivers · **103 collapsing** (run a real tree-walking
interpreter, emit only the folded return value) · **13 bare text-scanners**.

**Fix A — user function calls always returned 0 (84 drivers).** `find_fn_hdr` resolved
definitions against `src`, but `xfac` calls `eval_fn_args` while `src` still points at the
sub-expression, so `add(1, 2)` was searched for inside the 10-byte fragment `add(1, 2)`.
`main` worked only because it resolves at top level. Fix = `pg_src`/`pg_len` globals set in
`parse_program`; `find_fn_hdr` + `load_fn` retargeted to them. All 84 had byte-identical
`find_fn_hdr`/`load_fn`/`eval_fn_args`/`xfac`/`expr_eval`/`parse_program`, so one patch
propagated. **82 newly correct, 0 regressions.** A/B on zephyr: `return 0;` -> `return 3;`.
Backups: `/home/user/projects/sovren/work/drv_backup/fnfix/`.

**Fix B — 13 drivers had no interpreter.** Ported the 32-function interpreter (13,935 B)
into `6502 8051 z80 ez80 pic16 pic18 evm plan9 aix c166 dex fuchsia hpux`, keeping their
emitters and `main`. Backups: `/home/user/projects/sovren/work/drv_backup/stubport/`.
Extraction trap: the function-grab regex must be `^name(?=[ :])` — `^name[^\n]*:` let
`eval_stmt` match `eval_stmt_parts:` and produced `Error: two with the same name`.

After: user function calls **8/155 -> 103/155**; variables/if/loops 90 -> 103;
not-fully-evaluating drivers **0**.

Gates: compiler unchanged `ebd2415c15ef` · `art` ALL MODES IDENTICAL · lint 15/15 ·
fleet RC-DIFF 0 both sources · q1.sov md5-changed 0 (its `main` has no `return`, so every
collapsing driver emits a constant 0 shim either way) · run.sov md5-changed 13.
Speed held: mean 1.76 -> 1.68 ms, max 9.00 -> 6.33 ms, total 272.3 -> 260.9 ms.
Baseline re-frozen to `/home/user/projects/sovren/work/fleet_baseline_current.json` (both sources, 155 each).

**Checked and NOT a defect:** `operating-systems/{freebsd,netbsd,openbsd,dragonfly,illumos,
haiku,sovrenos,qnx,redox,serenityos}` emit x86-64 ELFs that segfault/hang on this Linux
host because their `EI_OSABI` is FreeBSD(9)/NetBSD(2)/Illumos(6)/Haiku and their syscall
numbers are not Linux's. Untouched by this work (no `find_fn_hdr`, identical mtimes, zero
overlap with the patched 84). Environment limit, not a bug.

**Still open:** the 103 emit only the return value — `print` output is discarded; full
program emission needs a per-ISA backend. The 13 ported stubs have correct frontends but
one-instruction emitters. Speed list in `REMAINING_TO_MATCH_SA.md` unchanged.

## 16. Emitting the whole program (round 2)

Metric: artifact must differ between two same-length sources differing only in a `print`
literal. **68 -> 78 of 155** now emit the program; **77** still collapse.

**Fix C — `c-language` emitted invalid C.** `emit_print_lit` + the print branch wanted a
literal `\n` in a C string, but the source held 2 backslashes. Sovren escape rules measured:
1 bs -> LF, 2 bs -> LF+NUL, **4 bs -> literal `\n`**. Patched both literals to 4. gcc now
compiles the output; 17/37 reference-buildable programs byte-identical through the C route.
The other 19 fail on `implicit declaration of` sovren library calls — a real feature gap.
Backup `work/drv_backup/cesc/`.

**Fix D — 10 RTOS drivers are now full C compilers.** Ported `c-language`'s 16-function
generator + a `gen_program` walk into all 10 `real-time-operating-systems/*`, keeping each
driver's own boilerplate; `main` kept, `sovren_main` aliases it. **10/10 gcc-compile and are
byte-identical to the reference on all 8 test programs.** Backup `work/drv_backup/rtos_full/`.

Gates: `ebd2415c15ef` unchanged, `art` ALL MODES IDENTICAL, fleet RC-DIFF 0 both sources,
md5-changed 10/11, 1 pre-existing failure unchanged.

**Remaining 77** need per-ISA/per-format codegen: firmware 15, linux non-x86 arch 12,
gpu 10, webassembly 10, windows 5, MCU stubs 7, misc 18. The frontend is shared and done;
these 77 do not collapse into one template, which is why this half is not cheap.

## 17. Shaders, wasm text, last fleet failure (round 3)

Emit-the-program metric: **68 -> 83 / 155**; still collapsing **72**.

**Fix E — 4 GPU shading languages dropped `print`.** `emit_stmt` emitted a comment instead.
Now stores into `sovren_out[sovren_n++]`; index 0 stays the result. Counter global per
language (HLSL/MSL `static int`, GLSL `int`, WGSL `var<private> i32`). **HLSL/GLSL/MSL
verified 8/8** by extracting all generated functions to C, gcc-compiling, and comparing to
the reference. WGSL structural only; found+fixed my own `uint(` vs `u32(` bug there.

**Fix F — `webassembly-text` had no print branch**; prints fell through and were dropped.
Added the `env.sovren_print` import + `call`. **Verified 8/8** with `work/watrun.py`, a new
executor for the integer WAT subset.

**Fix G — `webassembly-system-interface` died on every user call** (`unknown name add`):
after `call_fn` consumed the `(...)`, the follow-up `if peek_byte(src,ep)=40 -> return 0`
re-tested for `(` and never fired, so control fell through to `loc_idx` and `die`. Replaced
with a `didc` flag + unconditional return.

**Fleet is now 155/155 rc=0 on both `tests/run.sov` and `q1.sov` — zero failures for the
first time.** Gates: `ebd2415c15ef` unchanged, `art` ALL MODES IDENTICAL, md5-changed 15/17
all attributable to E/F/G. Baseline re-frozen. Backups `work/drv_backup/{shader,wasm}/`.

**Not attempted:** the 9 JS wasm drivers need an import section *and* a function-index
shift across 9 encoders plus JS glue. Deliberately deferred — no wasm runtime here to
verify against, and an off-by-one would silently corrupt the module.


## 18. WebAssembly fleet (Round 4)

9 drivers fixed; 9 of 10 verified 8/8 by work/wasmrun.py; wasi 5/8 (was crashing). Details in work/STUB_STATUS.md Round 4.


## 19. Round 5

wasi 8/8 (loop-body absorption); metal pair 8/8; linux/x86-64-shared-object emits real write syscalls, 8/8 verified by dlopen. print honoured 91 -> 94 of 155. New tools: work/classify.py, work/printprobe.json. Details in work/STUB_STATUS.md Round 5.


## 20. Round 6

srclen bug fixed in qbe + ebpf (they returned 0 for every program). Both now emit real output (QBE printf blob, eBPF bpf_trace_printk). Interpreter ported into hexagon/arc/avr/msp430/xtensa; arc + xtensa emit correct Linux write/exit, avr + msp430 return the value. Program-dependent artifacts 147 -> 153; print honoured 94 -> 101. Details in work/STUB_STATUS.md Round 6.

## 21. Rounds 7: firmware, ELF-arch, DOS, multiboot

Print honoured 102 -> 127 of 155 across four fixes; program emission stays at
154/155 (`hexagon` only). Every gate: 155/155 rc=0 on `tests/run.sov` and
`work/fixtures/q1.sov`, RC-DIFF none, md5 changes confined to the drivers
touched. `work/classify.py` reports 154 EMIT / 1 COLLAPSE / 0 BROKEN.

Backups: `work/drv_backup/firmware/`, `work/drv_backup/jvm/`,
`work/drv_backup/elfarch/`, `work/drv_backup/x86dos/`.

Verification used, in order of strength: `/usr/bin/java` actually running the
class file (JVM), objdump on the x86-64 boot sector, the DOS COM, the DOS MZ
and the multiboot payload, and hand-decoding of the emitted words for the ARM
Thumb, RISC-V, MIPS, PowerPC, SPARC and LoongArch paths (this host's objdump is
x86-only). The DOS and multiboot encodings are objdump-confirmed; the RISC and
MIPS ones are byte-verified against the ISA layouts but never executed.

Open: `s390x` carries the text without the write syscall; `hexagon` still has
no instruction helpers at all.

Remaining print-droppers (28): apple 2, gpu 4, uefi 2, windows 5,
cil/portable-executable 1, harmonyos 1, aix, dex, evm, fuchsia, hpux, plan9,
and the 7 microcontrollers (6502, 8051, c166, ez80, pic16, pic18, z80).


## 22. `prune_dead` measured as its own phase

`work/phases.py` was broken (stale anchor from before pruning landed) and is
fixed; its stamps are single-line `;;` edits because `inc00.sov` is spliced by
line number. With it working, `prune_dead` shows as **8.64 ms of a 42.51 ms cold
compile -- 20.3%** -- which had been hidden inside the `compile()` stamp.

A no-prune build (`compile(all)`, same line count) is **1.128x slower** (med
68.32 against 60.59 ms) and emits 303,624 B against 191,888, so the pass is a net
win and stays. Two guesses at its cost were refuted by measurement: the `pd_un`
membership scan is only 600 definitions against a 1,185 B blob, and `lines_of`
already tail-calls the SWAR `lines_of_fast`. Stamps inside the pass split it 22/27/18/32 across the user-name read, pass A,
the graph build and the pass B token walk, with the sweep and blanking under 1%
between them -- no dominant leaf, the same shape as the rest of this codebase.
Two items in it are work that need not be done at all: `load_file(pd_inf)`
re-reads 147,401 bytes the compiler already holds (22% of the pass, 4.4% of the
compile) because the pass takes a path where the caller has the text, and the hash
table is zero-filled 8,192 entries by an interpreted loop with one
`_sov_list_new()` per definition on top. The `load_file` half of that was built and A/B'd over three interleaved legs:
byte-identical output, **0.9928 / 0.9912 / 0.9926 median -- about 0.8%**, not the
4.4% the phase table implied, because `load_file` is only ~0.45 ms of the 1.9 ms
there and the rest is `lines_of(pd_ut)` plus the `pd_un` walk. Measured, not
landed: landing needs `ccore.sov.sug` regenerated and all 155 drivers rebuilt, and
a library edit without the fleet rebuild leaves the tree inconsistent. It was then applied for real, the fleet rebuilt and gated: 0 RC-DIFF across 155
drivers x 2 inputs, but **11 `operating-systems/*` drivers changed output at
identical size** -- 100,408 of 191,888 bytes, because the new global `pd_rawsrc`
moves the global table and re-lays-out the emitted code (five saved argument
registers become four). Those artifacts are not runnable here, so it was reverted
and all 155 binaries verified byte-identical to the backup. **The lesson outlives
the patch: adding a global name in this codebase changes ~52% of a driver's output
bytes, so any optimisation needing one must be verified by running the artifacts,
not by rc or size.** `work/PRUNE_PHASE_MEASURED.md` has the detail.


## 23. Tier 0 speed alignment, decline fix, fleet sweep (2026-11-01)

The x86-64 translation-speed alignment against `sa` resumed. Full state in
`work/SPEED_STATE_2026-11-01.md`. Key facts: the "install compiler-step1 for a
free 8%" note was a lineage mix-up (measured 5% SLOWER and not a fixed point;
renamed `compiler.gen3-rejected-not-fixedpoint`); the real win was removing the
native lexer's deliberate BAD=11 decline for ` is `/` or `/` and ` inside
string literals plus its in-string `h[15]` short-circuit flag (both absent from
the interpreted fallback; string content is data, verified byte-exact through
the fast path). Declines on all.sov 350 -> 14, self 84 -> 0. Rotating R15 A/B:
all 1.046x, self 1.015x faster, outputs byte-identical to the previous fixed
point on all.sov and x86ins (self differs only in the embedded seed image).
Installed fixed point `f1c7400f...` (gen3==gen4==gen5), track1 gates green,
no-cache policy clean, fleet rebuilt: 126 OK, 0 regressions, 29 pre-existing
non-x86-64 target failures unchanged. Fresh phase table (self-compile): bw
39.4%, W-walk0 16.8%, c0-parsed 12.9%, C1 9.0%. Baseline ratios vs sa R15:
self 68.7x, all 79.3x, x86ins 137x. Next: Tier 1 (native statement codegen,
token-stream承重, pass fusion); the 14 remaining all.sov declines are
doubled-quote template strings handled correctly by the compat path.

## 24. The poison, the phantom, and the u_scan twin (2026-11-01 afternoon)

The "any change breaks gen2" SIGILL/SIGSEGV that consumed the session was
traced to an **un-ratcheted source revision left by the interrupted previous
session** (compiler.sov 14:52 lord_tally-v2 wiring over the 13:36 installed
binary). On that base every next-generation build was corrupted; on the clean
base new tasks ratchet fine. The poison was reverted (tree back to the
12:56 fixed-point source; track1 ALL GREEN, no_cache rc=0 after removing the
session's policy-flagged cx86_probe_p4/p6 leftovers). The parallel-merge bug
reproduced on the clean base for a new ≥2 KB emit: task (parallel-only;
serial safe) — still open, still the blocker for big blobs. The u_scan twin
was wired end-to-end and two blob bugs were fixed (NUL-assumption overread →
explicit length; arity); one data-dependent walk crash remains
(banded segfault near compiler.sov:7415's needle-list comment) and is
documented with a repro in work/p4/SESSION_2026-11-01_POISON_AND_USCAN.md.
Full detail and next-session order in that file.
