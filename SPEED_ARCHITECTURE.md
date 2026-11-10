# PURGE NOTICE (2026-10-25, Track 0.0)
All cache machinery described below (artifact cache, .prebuilt, .ac/.ac.bin, .plk, .lsug/.sug/runtime.sug, state dumps, deep/.deepoc replay, prefix replay, cache flags) has been **fully removed from this tree** in Track 0.0; every compile is cold and no persisted intermediate can ever be produced again. Sections below are retained as dated history. See `work/attic/purge20261025/PURGE_REPORT.md`.

# Sovren compiler speed architecture

The acceptance target is the `sovren-assembler/sa` process-level benchmark, not a microbenchmark inside the compiler.

## Measurement (2026-09-27, this workspace)

Fresh process, output redirected, best of repeated runs:

| translator | source | bytes | best | throughput |
|---|---:|---:|---:|---:|
| `sa` | `bench.sa.asm` | 695,246 | 2.28 ms | 305.5 MB/s |
| `sa` | `bench6.sa.asm` | 4,196,595 | 9.58 ms | 438.0 MB/s |
| Sovren x86-64 compiler | `tests/run.sov` input | 41,141 | 5.30 s | 0.0078 MB/s input |
| Sovren x86-64 compiler | `tests/run.sov` expanded | 304,442 | 5.30 s | 0.057 MB/s expanded |

The compiler is therefore not yet at the acceptance target. Do not describe it as matching `sa` until the same process-level harness says so.

## Changes landed in the first speed pass

1. Library aggregation no longer repeatedly concatenates the complete accumulated source. `pull_uses` writes imported chunks into one preallocated arena buffer. `tests/run.sov --flat` remains byte-identical.
2. The repeated compiler analysis now reuses the first source line table instead of allocating two additional identical line tables.
3. Repeated analysis passes reuse the first immutable line table instead of splitting the same normalized source three times.
4. Per-emitted-byte debugging assertions and per-function counter printing were removed from production compilation.
5. Whole-program DCE moved behind `--release`. The normal edit/build path preserves behavior but may retain dead functions; release builds retain the compact artifact path.
6. A direct name-pointer cache and sugar pre-scan were measured and rejected: both added overhead on the large-source gate. They are not retained.
7. Every committed backend was rebuilt and the full multi-backend bootstrap returned `bootstrap clean`.
8. The runtime allocator no longer performs a `gettid` syscall on every allocation when no thread-local allocation contexts exist. An active-context count gates context lookup and uncontended allocation locking. On the compiler workload this reduced a fixed-point Linux compiler from roughly 5.4–5.8 seconds to roughly 3.8–4.4 seconds in repeated local runs. This is a real process-level improvement, but remains far short of the `sa` gate.
9. Source expansion now sugars runtime, imported modules, and user source separately and skips the redundant whole-program sugar pass; pre-expanded standard modules remain byte-identical.
10. `lines_of` now creates one immutable backing arena and compact line pointers instead of allocating and copying every line separately. Pointer-keyed caches for immutable length, character, trim, substring, and search results remove repeated rescans without changing generated output. `_sov_byte_at` and `_sov_set_byte` use direct ABI-register machine sequences in generated compilers. Together these changes reduce `tests/run.sov` to about 0.68 seconds normal and 0.18 seconds `--flat` on this workspace, with fixed-point and output comparisons byte-identical. The compiler is substantially closer but still does not meet `sa`.

On `tests/run.sov`, moving DCE out of the default path reduced an uncontended build from about 9 seconds to about 5.3–5.9 seconds. This is useful but still orders of magnitude short of `sa`.

## Installed checkpoint (2026-09-27, direct-match pass)

The compiler now lowers fixed literal prefix/range comparisons to `sg_match` instead of allocating `cut` substrings and then calling `starts`/`same`. Direct byte-digit checks similarly replace allocation-heavy `digit(letter(...))` sites. The complete 25-target fleet and launchers were regenerated; `./bootstrap` reports `bootstrap clean`, and `tools/sync_kits.sh` synchronized the Linux kit into SovrenOS.

Fresh-process formal gate, best of seven runs:

| translator | source | bytes | best | median | throughput |
|---|---:|---:|---:|---:|---:|
| `sa` | `bench6.sa.asm` | 4,196,595 | 6.483 ms | 7.108 ms | 647.279 MB/s |
| installed Sovren x86-64 | `tests/run.sov` input | 41,141 | 589.398 ms | 600.356 ms | 0.070 MB/s |
| installed Sovren x86-64 | expanded source | 304,686 | 589.398 ms | 600.356 ms | 0.517 MB/s |

The expanded-throughput ratio is `0.000799x sa`; this does not satisfy the gate. Local A/B testing of the final direct include-pattern match showed a lower mean (about 583.8 ms versus 594.4 ms over 15 runs), but the subsequent formal run was noisier and must be treated as authoritative. Emitter batching experiments were rejected: six-, four-, and two-byte helper variants built a first generation but produced invalid self-hosted compilers, including missing leading prologue bytes. A semantically exact direct `_sov_list_add` lowering reached fixed point and preserved output, but was slower. A recursive one-pass include expander also preserved fixed point and exact output but was neutral on `--flat` and slightly slower on the full gate. All rejected variants were fully reverted.

## Required architecture for the remaining gap

Small local caches cannot close a ~7,000x throughput gap. The production fast path must adopt the assembler's shape:

- one mmap/read of each input;
- one lexical pass into compact line/token descriptors (offsets into immutable source, not allocated substring copies);
- intern every identifier once into an open-addressed table;
- resolve names by stable IDs, never repeated string scans;
- build function metadata and the text-return call graph during that same pass;
- solve type/call propagation with a work queue, not repeated whole-source fixed-point scans;
- emit directly into a pre-sized/growing byte arena;
- retain bounded fixup vectors for calls/branches;
- make DCE a release-only graph walk;
- share this front end, arena, interner and fixup engine across every backend;
- benchmark every backend with fresh processes and byte-identical correctness fixtures.

## Gates

A speed change is accepted only when:

1. fixed-point self-hosting is byte-identical;
2. `bootstrap clean` passes for every backend;
3. target fixtures remain byte-identical unless an intentional output-mode change is documented;
4. `sa` and Sovren are measured by the same fresh-process wall-clock harness;
5. no cache hit is reported as cold translation throughput;
6. debug assertions are outside hot loops or are enabled only in an explicit diagnostic build.

---

# Call-overhead pass (2026-09-30)

The remaining gap was attacked by profiling rather than by adding caches.
Recipe that finally produced attributable samples: a ptrace sampler that reads
`/proc/<pid>/maps` for the real load base (the compiler is `ET_DYN`, so the
static `0x400000` vaddrs are meaningless), plus an `endbr64`-derived function
map over the `R E` LOAD. Earlier "unattributable" profiles were an ASLR
artifact, not a profiler limitation.

## What the profile said

| function | share of `tests/run.sov` | nature |
|---|---:|---|
| `_sov_list_get` | 16.7% | real call, not inlined |
| `_sov_alloc` wrapper | 12.6% | pure pass-through to `_sov_heap_alloc` |
| `letter` (memoised char) | 8.2% | 2 MB direct-mapped memo |
| `_sov_list_len` | 6.8% | real call, not inlined |
| string compare | 6.0% | |
| `_sov_find_text` | 6.0% | runtime brute-force search |
| `_sov_substring` | 4.8% | |
| `_sov_strcat` | 3.9% | |
| `same` wrapper | 2.9% | pure pass-through to `_sov_str_eq` |
| `look` (memoised find) | 2.6% | |

`peek_i64` *is* inlined by the code generator to a single load, while
`_sov_list_get`/`_sov_list_len` are not — that asymmetry is the whole
opportunity.

## Landed

1. **Removed two pure call layers.** `same a b: return _sov_str_eq(a, b)` and
   `_sov_alloc size: return _sov_heap_alloc(size)` are pass-throughs, so every
   compiler-side call site now targets the callee directly (435 `same`, 153
   `_sov_alloc`). Only compiler-side sources were touched; `runtime.sov` is
   untouched, so the bytes emitted for user programs never move.
2. **De-virtualised list access.** 34 loop conditions had `_sov_list_len(L)`
   hoisted into a local and their element reads inlined as
   `peek_i64(L, 16 + i * 8)`; 25 more element reads were inlined in place inside
   `library/inc/`. Loops whose body grows or shrinks the list keep the original
   form (4 skipped) — a hoisted length would change the iteration count.
3. **`sg_toks`** built each token with `cur: str_cat(cur, letter(t, i))` — one
   allocation and one full copy per character. Tokens are contiguous runs, so
   each is now a single `cut(t, start, end)`.
4. **`sg_sp`** built an n-space indent with n `str_cat` calls (O(n^2) copy).
   Now one allocation and n byte writes.
5. **`sg_numt`** prepended each digit with `str_cat(str_chr(...), out)` — O(d^2)
   copy plus a one-character allocation per digit. Now digits are written into
   the tail of one buffer and the string is an interior pointer.
6. **`plain_name`** tested each byte against fifteen one-character strings via
   `_sov_str_eq`. Now one 256-entry table lookup, built once.
7. **`num_value`** memo enlarged from 1 MB/65,536 slots to 8 MB/524,288 slots;
   the old `band(s/16, 65535)` aliased roughly 2:1.

## Measured and rejected

- **Any hash index over `idx`'s linear scan.** Single slot, 16 slots and 1024
  slots were all byte-identical and all *slower* on `tests/run.sov` (16x, 12x,
  10x) while `a_functions` was unaffected. Instrumentation showed 43,916 index
  rebuilds on 150 functions: the compiler alternates between ~13 lists and
  `_sov_list_add` hands back a fresh pointer on growth, so a pointer-keyed
  cache thrashes. Slot count is not the variable. Do not retry.
- **Hoisting `_sov_list_len` inside `idx` alone** — 1.00x/1.02x, byte-identical.
  Proved the cost was the `same()` compares, not the loop condition, and pointed
  at the call-layer work above instead.
- **Removing the `letter` memo** — 0.86x. It earns its keep: `_sov_char_at`
  allocates a fresh two-byte string per call.
- **Enlarging the `letter` memo to 8 MB** — 0.93x. Random access over 8 MB
  costs more than the extra hit rate saves. `num_value` benefited from the same
  change; `letter` did not.

## Result

Same fresh-process gate, best/median of seven:

| | best | median |
|---|---:|---:|
| before | 926.167 ms | 981.097 ms |
| after | 743.199 ms | 768.551 ms |

**1.28x faster (median)**, expanded-throughput ratio `0.000756x` -> `0.000876x sa`.
The ratio moves less than the raw time because `sa`'s own throughput varies
between runs; the Sovren wall-clock is the honest figure.

Correctness: 5/5 corpus sources byte-identical, 13/13 sampled backends
(6502, 8051, z80, ez80, evm, pic16, msp430, avr, riscv64, arm64, windows,
dos-mz, dex) byte-identical, test suite **640 passed / 0 failed / 14 not run**.

## Still open

The gate is not met. `_sov_alloc` is now the largest single item (~15%) and it
is reached from `runtime.sov`'s own string helpers, which cannot be edited
without moving the bytes emitted for user programs. Closing the rest needs the
architecture described above, starting with an offset-based token descriptor
pass so that `cut`/`letter`/`str_cat` stop allocating per character.

## Fleet rollout (same day)

The changes above live in the shared pool, so all 155 backends pick them up.
`./bootstrap` was run once: it staged every rebuilt binary to `/tmp/sov-boot-*`
and reported 157 byte mismatches (expected — the compiler binaries themselves
change). Before installing anything, all **155/155** rebuilt backends were
checked against the previously committed binaries on the whole corpus: every one
emits byte-identical output. The staged binaries were then installed and
`./bootstrap` re-run:

```
159 ok, 0 FAIL
bootstrap clean
```

The launchers (`sovren`, `sovren.exe`, `sovren-dbg`) are part of that set and
were rebuilt and committed with the rest.

Final gate, best/median of seven, after the fleet rollout:

| | best | median |
|---|---:|---:|
| Sovren x86-64 | 756.128 ms | 765.926 ms |

Expanded-throughput ratio `0.000935x sa` (baseline `0.000756x`). The ratio
wobbles run to run because `sa`'s own throughput moves between 597 and 648 MB/s;
the Sovren wall-clock is the figure to trust.

Test suite after the rollout: **640 passed, 0 failed, 14 not run**.

---

# Second call-overhead pass (2026-09-30, later)

Method that made the remaining work possible: **sample the return address while
inside a hot function.** A ptrace sampler that reads `[rsp]` is useless here
because every prologue pushes callee-saved registers first, so the top of stack
is a saved `%rbx`, not the return address. Scanning 24 stack slots for the first
value inside the executable's mapping recovers the real caller. That turned
"`letter` is 8% but only 746 calls" from a contradiction into a direct answer.

## What the caller attribution showed

`letter` is called 4,595,365 times on a 147 KB source. 68% of those calls come
from **one** site: the string-literal scanner at `inc01.sov:652`, spliced into
the argument-list splitter by `inc05.sov:951`. Per character it did a 2 MB
direct-mapped memo lookup and then, three lines later, only ever asked whether
the character was `(`, `)` or `,`.

The `--flat` expansion is what finally made the loop readable: the body is split
across four pool files, and the unconditional `i: i + 1` lives in a slice that
is nowhere near the loop header. It also showed that `c` is captured at the top
of the iteration, *before* the `i: i + 1` on the backslash-escape path, so the
punctuation tests must read the captured byte rather than the current index.

## Landed

1. **The literal scanner no longer calls `letter`.** `c: letter(inside, i)`
   became `c: _sov_byte_at(inside, i)` and the three `_sov_str_eq(c, "(")`
   tests became `c = 40` / `c = 41` / `c = 44`. One inlined load and three
   register compares replace a memo lookup plus three string compares per
   character. All four edits are in place, so every slice range still holds.
2. **Fourteen more `letter(...)` -> byte compares** in `ccore.sov`, `carm.sov`
   and `compilers/linux/compiler.sov`, covering `sg_unparen`, `sg_stmt`,
   `sg_thresh`, `u_sugar`'s block-header tests and the `law_body` scanners.
3. `digit(letter(inn, 0))` -> `digitb(_sov_byte_at(inn, 0))`.

## Trap worth recording

An earlier attempt at the same loop rewrote `c` to a byte but left the three
punctuation tests reading `_sov_byte_at(inside, i)` at the *current* index. That
is wrong on the escape path and segfaults. A second attempt stored `c: blank`,
which also segfaulted -- and the real cause turned out to be an unrelated,
never-reverted edit at `inc00.sov:112` from an earlier experiment. **Always
restore pool files after a failed experiment before drawing conclusions from
the next build.**

## Result

Same harness, best/median of seven, against the compiler as it stood at the
start of this pass:

| | best | median |
|---|---:|---:|
| before | 926.167 ms | 981.097 ms |
| after | 504.011 ms | 546.876 ms |

**~1.8-2.0x faster.** Expanded-throughput ratio `0.000756x` -> `0.001145x sa`.
The ratio moves less than the wall clock because `sa`'s own throughput also
moved between runs (603 -> 731 MB/s); the Sovren wall clock is the figure to
trust. Gate variance is high -- repeated 7-run gates gave medians between
470 ms and 552 ms -- so treat the wall-clock A/B, not a single gate, as
authoritative.

Correctness: 5/5 corpus sources byte-identical, **155/155** rebuilt backends
byte-identical, `bootstrap clean` (159 ok / 0 FAIL), test suite
**640 passed / 0 failed / 14 not run**.

## Still open

`_sov_alloc` is the largest single item (~15%) and is reached from
`runtime.sov`'s own string helpers, which cannot be edited without moving the
bytes emitted for user programs. After that: `_sov_list_get` (~10%, 310 static
call sites, only 34 loops de-virtualised so far), the memo wrappers `letter`
and `num_value`, and `_sov_substring`. The gate is still not met.

---

# Third call-overhead pass (2026-09-30, final)

Caller attribution again, this time on every hot function rather than just the
top one. `letter` dropped out of the top twelve entirely after the operator
scanners were fixed, which confirmed the scan loops -- not the memo itself --
were the cost.

## What the attribution showed

| function | share | dominant caller |
|---|---:|---|
| `_sov_alloc` | 17.98% | three list/string builders |
| string compare | 9.18% | one function, 58 of 72 samples |
| `_sov_substring` | 7.40% | one function, 39 of 58 samples |
| `_sov_list_get` | 7.27% | two list builders |
| `num_value` | 6.89% | one function, 31 of 54 samples |
| `_sov_list_len` | 5.36% | one function, 16 of 42 samples |

## Landed: the operator scanners

`fop`, `fopn`, `fop2` and `fop3` are the "find this operator at paren depth 0"
helpers, and every one of them runs the same per-character scan:

```
as long as i < n
    c: letter(e, i)          # 2 MB memo lookup, per character
    ...
    if not
        if _sov_str_eq(c, "(") is 1
```

Four pool files feed these loops, so the `c` store and the punctuation tests
live in *different* slices and had to be changed together:

| file | change |
|---|---|
| `inc00.sov:112` | `c: letter(e, i)` -> `c: _sov_byte_at(e, i)` |
| `inc00.sov:90,92` | `_sov_str_eq(c, "(")` / `")"` -> `c = 40` / `c = 41` |
| `inc03.sov:880-883` | `_sov_str_eq(c, "*"/"/"/"%")` -> `c = 42` / `47` / `37` |
| `inc04.sov:472-473` | `_sov_str_eq(c, a)` / `(c, b)` -> `c = _sov_byte_at(a, 0)` / `_sov_byte_at(b, 0)` |

The equivalence argument: in every branch where those comparisons are reached,
`i` has not been advanced since `c` was captured, because each advancing branch
is guarded by the same `if not` chain. Reading the current byte is therefore
identical.

**The `inc04.sov` pair was the missing piece.** A literal-only grep for
`_sov_str_eq(c, "` finds nothing there, because `fop2` compares `c` against its
*parameters* `a` and `b`. Leaving those as string compares against a now-integer
`c` is what produced three consecutive segfaults.

## Also landed

Two `_sov_list_len` loop conditions in `ccore.sov` hoisted into locals (both
loops only read their list), and their element reads inlined as `peek_i64`.

## Result

Same harness, best/median of fifteen:

| | best | median |
|---|---:|---:|
| session start | 926.167 ms | 981.097 ms |
| now | 414.490 ms | 453.855 ms |

**2.16x median, 2.24x best.** Expanded-throughput ratio `0.000756x` ->
`0.001548x sa`.

Correctness held throughout: 5/5 corpus sources byte-identical, **155/155**
rebuilt backends byte-identical, `bootstrap clean` (159 ok / 0 FAIL), test suite
**640 passed / 0 failed / 14 not run**.

## Still open, in profile order

`_sov_alloc` is 18% and is reached only from `runtime.sov`'s own string and list
helpers; editing it moves the bytes emitted for user programs. Then a single
function owning 9.18% (string compares) and another owning 7.40%
(`_sov_substring`), both of which still need their source locations pinned down.
The gate is still not met.

## Pass 4 -- the allocator fast path (runtime.sov, 1.08x)

The user released the byte-identity constraint, which unblocked the one thing the
profile had been pointing at since pass 1: `_sov_alloc`/`_sov_heap_alloc` at
17.98% of compile time. Three call-overhead passes had removed every *library*
caller; the survivors were inside `runtime.sov` itself, so the only way to move
the number was to make the allocation itself cheaper.

`_sov_heap_alloc` is written for the general case -- per-thread allocation
contexts, a lock, an OOM path and a fallback search over descriptors -- and the
compiler (and every generated program) is single-threaded with no contexts and
allocates almost nothing but small blocks. A new `_sov_fast_alloc` answers that
case inline and returns 0 for anything else, letting `_sov_heap_alloc` fall
through to its untouched general path:

    _sov_fast_alloc size:
        if g_ctx_n != 0 -> return 0
        if g_meta = 0 -> return 0
        if g_alloc_dbg != 0 -> return 0
        if size < 1 -> return 0
        if size > 1024 -> return 0
        d: peek_i64(g_meta + ((size + 15) / 16 - 1) * 8, 0)
        if d < 0 -> return 0
        db: g_meta + 1024 + d * 128
        fh: peek_i64(db + 40, 0)
        if fh != 0 -> dummy: poke_i64(db + 40, 0, peek_i64(fh, 0))
            return fh
        carve: peek_i64(db + 32, 0)
        if carve < peek_i64(db + 24, 0) -> dummy: poke_i64(db + 32, 0, carve + 1)
            return peek_i64(db + 0, 0) + carve * peek_i64(db + 16, 0)
        return 0

Descriptor layout: `_sov_dget(i, q)` is `peek_i64(g_meta + 1024 + i*128 + q*8, 0)`,
so slot 0 is base, 2 is unit, 3 is capacity, 4 is the carve cursor and 5 is the
free-list head. `_sov_fast_alloc` reproduces exactly the two success paths of
`_sov_small_try` -- pop the free list, else carve -- and returns 0 on both
failure modes so the general path runs its descriptor search and region growth.

`_sov_alloc` is a pure pass-through (`return _sov_heap_alloc(size)`) and its ten
remaining callers were all inside `runtime.sov`; those now call
`_sov_heap_alloc` directly. The public definition stays.

**Result:** e_run 0.410 s -> 0.380 s, **1.08x** (min of 31 interleaved reps).
Gate best 414.490 ms -> 397.0 ms; median 453.855 -> ~478 ms (gate median noise
is +/-5% and is not the measure -- the wall-clock A/B is).

**Verification.** The change is inside the injected runtime, so it alters the
bytes of every compiled output. Two things make that harmless here. First, the
front end dead-code-eliminates unused runtime helpers, so a program that never
calls the allocator emits byte-identical output: `a_functions.sov` compiles to
the same 45,440-byte binary before and after. Second, correctness is checked
semantically -- the test suite (631 passed / 9 failed, where the control run of
the pre-change compiler fails the *same* nine thread tests, which need a
threading environment this sandbox does not provide), plus `bootstrap clean`
at 159 ok / 0 FAIL, which includes the g3 == g4 == g5 seed fixed point. The
fleet rollout is still byte-checked because the emitted output is unchanged:
155 rebuilt backends emit identical output on all five corpus sources.

The gate is still not met.

## Pass 5 -- three more runtime.sov cuts (1.09x cumulative with pass 4)

The post-pass-4 profile (849 samples, caller attribution by 24-slot stack scan)
left `_sov_substring` at 6.10% and the list cluster -- `_sov_list_new` 3.89%,
`_sov_list_add` 4.5% -- at roughly 15% combined. Three cuts, each verified by
the test suite (631 passed / 9 failed, an identical failure set to the
pre-change control, which fails the same nine thread tests in this sandbox)
and by the bootstrap fixed point:

1. **`print_const` (`library/inc/inc01.sov`) computed `cut(arg, 1, length(arg))`
   twice** for a negative-number constant -- once to test `is_imm` and once to
   feed `num_value`. Hoisted into a `tail` local. Pool line counts must not
   move (the slices are `include inc/inc01.sov <start> <count>`), so the edit
   stays four lines.

2. **`_sov_substring` copied byte-at-a-time.** Each iteration paid three
   `push`/`pop` pairs to marshal the inlined `_sov_byte_at`/`_sov_set_byte`
   arguments. Now an eight-byte `peek_i64`/`poke_i64` loop runs while
   `i + 8 <= L`, with the byte loop as the tail. This is exact, not
   approximate: after clamping, `endd <= n`, so `start + i + 8 <= endd <= n`
   keeps every word read inside the source, and `i + 8 <= L` keeps every word
   write inside the `L + 1`-byte destination. Verified by a 4,141-case
   substring sweep (every start 0..11, every end 1..61, source lengths 62..91)
   whose stdout is byte-identical to the pre-change compiler's.

3. **`_sov_list_add`'s growth copy was one element per iteration**, same
   push/pop marshalling. Now four elements per iteration plus a byte tail.
   `_sov_list_add` is the highest-volume call in the compiler (509,387 on
   e_run) and over half its samples sit in the growth path, not the append.

**Result:** 1.09x on e_run and 1.09x on a_functions versus the post-pass-3
baseline (min of 40 interleaved reps). Gate best 375.9 ms; pristine was
926.167 ms, so the cumulative wall-clock gain is **2.46x**. The expanded
throughput ratio is 0.0016x sa.

**Verification of the whole pass:** test suite 631/9 with an identical failure
set to the control; `bootstrap clean` at 159 ok / 0 FAIL including the
g3 == g4 == g5 seed fixed point; 155 rebuilt backends emit byte-identical
output on all five corpus sources; all 158 binaries installed.

**Honest status of the gate.** The ratio is 0.0016x against a 1.0x target.
Passes 4 and 5 together bought 1.09x. Every remaining item the profiler can
name is between 2% and 5%, and the last three attempts each measured 1-2%.
`SPEED_ARCHITECTURE.md` states the conclusion the numbers keep confirming:
small local caches and call-overhead removal cannot close a gap of this size.
What is left that would move the ratio by an order of magnitude is the
architectural change -- one lex pass into offset-based token descriptors, an
open-addressed interner with stable IDs, an arena emitter -- which is a rewrite
of the front end, not another patch.

## Pass 6 -- `_sov_strcat` and `_sov_find_text` (1.17x cumulative)

A profile aggregated **by function** rather than by instruction (the earlier
per-RIP lists under-ranked functions whose hot code sits in a shared fragment)
gave the true ranking: `_sov_fast_alloc` 15.7%, `_sov_strcat` 9.0%,
`_sov_find_text` 8.1%, `_sov_list_get` 8.1%, `_sov_substring` 5.3%,
`_sov_list_len` 5.0%. Two of the top three were still byte-at-a-time.

1. **`_sov_strcat` (525,650 calls) copied both operands one byte per
   iteration**, each iteration marshalling the inlined `_sov_byte_at` /
   `_sov_set_byte` arguments through three `push`/`pop` pairs. Now an
   eight-byte `peek_i64`/`poke_i64` loop per operand with a byte tail. Exact
   for the same reason as `_sov_substring`: the word loop only runs while
   `i + 8 <= la` (resp. `j + 8 <= lb`), so every read stays inside the source
   and every write inside the `la + lb + 1`-byte destination.

2. **`_sov_find_text` (233,236 calls, the `look` primitive) ran its inner
   compare loop for all `ln` bytes at every candidate position**, guarded by
   `if ok = 1` so a mismatch at byte 0 still paid for bytes 1..ln-1. Now a
   first-byte prefilter rejects most positions outright, and the tail compare
   lives in `_sov_ft_eq`, which returns 0 on the first mismatching byte.

**Result:** 1.07x isolated (e_run 0.382 s -> 0.356 s), **1.17x cumulative**
against the post-pass-3 baseline. Gate best 379.5 ms; e_run wall clock
0.910 s -> 0.350 s pristine-to-now = **2.60x**.

**Verification:** test suite 631 passed / 9 failed with a failure set identical
to the pre-change control (the nine thread tests); `bootstrap clean` at
159 ok / 0 FAIL; 155 rebuilt backends byte-identical on all five corpus
sources; all 158 binaries installed; plus a direct 49-case `str_cat` sweep
whose stdout is byte-identical to the pre-change compiler's.

**Parser trap found again.** `if A -> if B -> return i` written inline inside a
loop body compiles under the x86 front end and fails under the Windows backend
with `Error: do not know these words / return i`. `_sov_ft_eq`'s
`as long as j < ln -> if ... -> return 0` failed the same way. Both parse once
the `if` body is moved to its own, deeper-indented line. **Rule: in code that
lives in `runtime.sov`, never put a `return` inline as the body of an `if` that
is itself the body of a loop.**

## Pass 7 -- `_sov_str_eq` (measured, not kept) and the profiler's blind spot

**The profiler was mis-attributing the #1 function.** `_sov_strlen` (at 0x214)
and `_sov_str_eq` (at 0x279) are emitted as *shared fragments* that do not begin
with `endbr64`. The function map is built by scanning for `endbr64`, so every
sample taken inside those two bodies was credited to the nearest preceding
`endbr64` function -- `_sov_alloc` at 0x1ea, a pure pass-through. That is why
"`_sov_fast_alloc`" appeared to be 17.3% of runtime when the allocator had
already been cut from 18% to ~5%. Correcting for it moves `_sov_str_eq` to the
top of the table at ~11.8%.

Three attempts at `_sov_str_eq`, all measured with min-of-40 interleaved reps:

| variant | e_run |
|---|---|
| length-check first, then word compare | 1.001x |
| 4x-unrolled byte loop | 1.012x |
| (original byte loop) | 1.000x |

None of them pay. The reason is visible in the shape of the call: `_sov_str_eq`
is called from 435 sites overwhelmingly on *short* operands -- single-character
tokens and 1-3 character keywords. For those the byte loop is already two or
three iterations, and both replacements add fixed overhead (two `_sov_strlen`
calls, or four unrolled bodies with their own early-exit tests) that only pays
off on strings long enough that the loop, not the call, dominates. **Kept the
original.** This is the second time a profile share failed to convert into a
measurable win (the first was `plain_name`), and the pattern is now clear:
`_sov_str_eq`'s 11.8% is call volume, not loop cost, so it can only be reduced
by removing calls, not by making the loop cheaper.

**Also ruled out:** the `_sov_alloc` pass-through still exists and is still
called from nine sites inside `runtime.sov` (fn#374, 381, 387, 409, 410, 416,
446, 462), even though the source contains zero `_sov_alloc(` text -- the
unwrapping in pass 4 replaced every one. The nine surviving calls are generated
by the compiler's own lowering, so they cannot be removed by editing source, and
the wrapper's cost is one prologue/epilogue per allocation, already counted in
the 15.7% that pass 4 cut.

**Current standing:** gate best **357.4 ms** (pristine 926.167 ms, **2.59x**);
e_run wall clock 0.910 s -> 0.350 s (**2.60x**); expanded-throughput ratio
0.0016x sa. Test suite 631 passed / 9 failed with a failure set identical to the
pre-change control; `bootstrap clean` at 159 ok / 0 FAIL; 155 rebuilt backends
byte-identical on all five corpus sources; all 158 binaries installed; and
`runtime.sov` rebuilds `compilers/linux/compiler` byte-for-byte (md5
`d0f60c26ece684b7ef6c9e1b7087e960`).

---

## Pass 7 — memory-operand folding in the x86 backend (LANDED)

**The decisive measurement that redirected this work.** A hand-written sovren
byte-summing loop over 4 MB, scanned 20x (80 MB of work):

```
C     -O2   28.6 ms  ->  2801.2 MB/s
sovren      52.5 ms  ->  1524.2 MB/s      sovren/C = 1.84x
```

So sovren's *codegen* is only 1.84x off `-O2` C on a tight loop. The compiler's
1.185 MB/s against `sa`'s 698.8 MB/s is therefore **not** a codegen problem —
it is an algorithmic/allocation problem, and it is fixable inside sovren without
abandoning self-hosting. (The earlier 3.5 ms-vs-3.5 ms micro-benchmark was
startup-dominated and therefore uninformative; the 80 MB comparison is the one
that counts.)

**What the disassembly actually showed.** `peek_i64(lst, 8)` compiled to five
instructions:

```
mov  %rbx,%rdi          ; loadv_rdi
push $0x8               ; materialise the constant THROUGH THE STACK
pop  %rax
mov  %rax,%rsi
mov  (%rdi,%rsi,1),%rax ; the actual load
```

`mov 8(%rbi),%rax` is one instruction. The backend is a pure stack machine with
no constant folding and no register allocation; `_sov_list_add`'s growth path
spent six push/pop pairs copying a single element.

**Three changes, all in `library/cx86.sov`:**

1. **Constant-displacement `peek_i64` folding.** `try_scaled_mem`'s `peek_i64`
   arm folded *scaled* indices (`i * 8`) but not *constant* offsets, even though
   the `poke_i64` arm right below it already folded constants. Added an
   `is_imm(a2)` branch emitting `mov disp8(%rdi),%rax` (`48 8B 47 d8`) or
   `mov disp32(%rdi),%rax` (`48 8B 87 d32`).
2. **Scaled-displacement `peek_i64` folding.** New `sc_disp e` helper parses
   `K + X * 8` / `X * 8 + K` and emits `mov disp8(%rdi,%rsi,8),%rax`
   (`48 8B 44 F7 d8`). This is the single most common access in the runtime
   (`peek_i64(p, 16 + i * 8)`); `scaled_rsi` had explicitly *rejected* the
   `K + X` case because the emitter could not express a displacement. It now can.
3. **`rax_imm` immediate materialisation.** `push $n; pop %rax` (`6A n 58`)
   became `mov $n,%eax` (`B8 n32`) — 1 uop instead of 2, and no store-to-load
   forwarding stall. 3,978 sites affected; compiler grows 305,712 -> 313,912 B.

**Two traps hit and fixed (recorded so they are not re-hit):**

- `emit:` byte lists take **decimal literals only**; a variable needs its own
  `emit(x)` call (`72 139 71` then `emit(mi4)`).
- A global read after a call can be clobbered: `sc_dx` set by `sc_disp` was
  destroyed by the intervening `loadv_rdi`/`chk_mem`, surfacing as
  `Error: no such name` with an *empty* name from `intern`. Fixed by capturing
  into a local (`sx: sc_dx`) immediately.
- A `poke_i64` constant-displacement branch was attempted and **reverted**: it
  segfaulted the compiler. Do not retry without first finding that crash.

**Verification.**
- Fixed point: stage2 == stage3, md5 `55581640af781226a8fada847cf1db84`.
- Correctness: 210 constant offsets (0-199, 255, 256, 511, 512, 1000, 4095,
  8192, 65535, 100000, 1000000) and 420 scaled displacements (`K + i*8` and
  `i*8 + K`), **0 mismatches**, identical on the pre-change compiler.
- Test suite: 224 passed / 3 failed / 4 skipped — **FAIL set byte-identical**
  to the pre-change control (`arm-emulator-sha256`, `arm64-codegen` are
  pre-existing, not caused by this change).
- `bootstrap` 159 ok / 0 FAIL; 158 backends rolled out and re-committed;
  `sovren.exe` rebuilt in place (PE32+, 76,640 B).

**Result:** e_run **1.098x**, a_functions **1.068x** (60 interleaved reps).
Gate best 343.7 ms, expanded-throughput ratio **0.001897x** sa (was 0.001599x).

**Why this is only ~1.1x and what it proves.** The folded instructions were
never the dominant cost: `_sov_list_len` is 24 instructions of which the load was
5, so folding saves ~3. The profile shares that *do* dominate are call volume
(`_sov_str_eq` 11.8% is 435 call sites on 1-3 character operands) and the
allocator (`_sov_strcat` 525,650 calls, `_sov_list_add` 509,387). Those are
reducible only by deleting calls and allocations — i.e. the interner and the
arena emitter — not by making individual instructions cheaper. Pass 7 confirms
the diagnosis rather than closing the gap.

---

## Pass 8 attempt — spill-free comparison (ATTEMPTED, REVERTED, DO NOT RETRY BLIND)

**The diagnosis (solid, from disassembly of the hot loop at 0x106e0).** A
comparison `if a = b ->` compiles to:

```
push %rax            ; spill L
mov  %rbx,%rax       ; loadv(R)   -- R lives in %rbx
mov  %rax,%rcx       ; mov_rcx_rax
pop  %rax            ; reload L
cmp  %rcx,%rax       ; the actual compare
```

Five instructions where `cmp %rbx,%rax` is one. `bin` (cx86.sov:2332) has three
existing fast paths and they do **not** cover this case:

| path | condition | emits |
|---|---|---|
| `px01.sov:156` | L **and** R both plain names | `loadv_rcx(R); loadv(L); emit_op(op)` — already spill-free |
| `bin_regop` (cx86.sov:118) | R in a register slot (locals 0-4, or 5-8 with `leaf8`) | `expr(L); cmp_rax_reg(sl); setcc(op)` — spill-free |
| generic | anything else | `expr(L); push_rax(); expr(R); mov_rcx_rax(); pop_rax(); cmp_rax_rcx(); setcc(op)` |

The gap is **L is an expression and R is a plain name outside slots 0-8** — e.g.
`if peek_i64(x, 8) = y ->` where `y` is local #9+. That is exactly the shape in
the hottest loop.

**The attempt.** Insert, after the `bin_regop` branch in `bin`:

```
nc: 1
if look(L, "(") > 0 - 1 -> nc: 0
if length(L) > 0 -> if _sov_byte_at(L, 0) = 34 -> nc: 0
if nc = 1 -> loadv_rcx(R)
    expr(L)
    cmp_rax_rcx()
    setcc(op)
    return 0
```

The guard was meant to exclude calls (which clobber the caller-saved `%rcx`) and
string literals (which need `_sov_txt_eq`, not `cmp`).

**Why it failed — two separate traps, both now recorded:**

1. **First attempt used `look(L, "\"")`** — a string literal containing a double
   quote. This breaks the sovren front end (a known trap: *"A single-quoted
   string literal containing a double quote breaks the sovren front end"*). The
   compiler built, but the binary it produced was not executable. Replaced with
   the numeric check `_sov_byte_at(L, 0) = 34`.
2. **Second attempt still broke the self-build.** Stage 2 built fine, but the
   binary stage 2 produced was **24 bytes** — i.e. the compiler emitted a
   truncated, unusable compiler. The `%rcx` guard is not sufficient: `expr(L)`
   can clobber `%rcx` through paths the `look(L, "(") < 0` test does not exclude
   (notably `chk_mem`, `chk_ov` and `chk_zrcx` all touch `%rcx`, and `expr` on a
   subscripted or cast expression reaches them without a literal `(` in the text
   at the point `bin` sees it).

**State after revert:** `library/cx86.sov` and `library/inc/inc03.sov` restored;
the compiler rebuilds to `55581640af781226a8fada847cf1db84`, identical to the
installed Pass-7 build, `bootstrap clean`.

**Also measured and rejected this turn:** hoisting the loop-invariant
`_sov_list_len(lst)` out of `idx` (inc03.sov:412) — **1.009x**, i.e. nothing.
This re-confirms the earlier finding now that Pass 7 has made `_sov_list_len`
cheap (the load is folded, 21 instructions): hoisting a cheap call buys nothing.

**What a correct version needs.** The spill can only be removed safely if the
register holding R is *callee-saved* (rbx, r12-r15) or if `expr(L)` is proven
call-free. `bin_regop` is safe because slot registers are callee-saved. So the
correct fix is to **widen slot coverage**, not to reorder — and slot coverage is
capped at 5 by the available callee-saved registers (rbp is the frame pointer).
Widening past that requires a real register allocator with liveness, which is
the Tier-1 item in `PATH_TO_FASTEST.md`.

---

## Pass 9 — the open-addressed name index and a single-pass front end (LANDED)

Target: the gate source (`tests/run.sov`, 147,391 B in, 423,643 B expanded).
Start of pass: **459.7 ms** best. End of pass: **394.8 ms** best (**1.164x**).
Isolated `e_run` **1.11x**, `a_functions` **1.06x**. Installed compiler md5
`474972c59be71306c4ff75af132f8902`; `bootstrap` **159 ok / 0 FAIL**; suite
**224 passed / 3 failed / 4 skipped** with the FAIL set identical to the control
(`arm-emulator-sha256`, `arm64-codegen`, both pre-existing); 158 backends rolled
out; `sovren` and `sovren.exe` both rebuild byte-identical.

### 1. `idx` — O(names) walk replaced by an open-addressed index

`idx lst name` (`inc03.sov:412..417`) walked the whole list calling
`_sov_str_eq` on every element: O(names) per lookup, O(names^2) per module.
It must stay exactly six lines at 412..417 because `carm.sov:29` and
`cx86.sov:1567` both slice `inc03.sov 412 6` and the next slice starts at 418.
It now reads:

```
idx lst name:
    # one open-addressed probe replaces the old O(names) walk; a hit is
    # verified against the live list, so a rebuilt list cannot alias.
    i: ih_find(lst, name)
    if i > 0 - 1 -> return i
    return 0 - 1
```

The index itself lives in `library/ccore.sov` (included once per compiler via
`inc05.sov:731`). A slot is 32 bytes: `[0]` list pointer, `[8]` name pointer,
`[16]` position, `[24]` name hash. Entries are never deleted and insertion is
never hooked, so the index is **self-populating**: a probe miss falls through
to the original walk, which inserts what it finds. Three properties make that
safe without any invalidation machinery:

* a hit is only trusted when the slot's name pointer is still the element at
  that position in the list being probed — a rebuilt list (`glob_names: live`
  in `dce_globals`) or a pointer the allocator handed out twice therefore
  cannot make a stale entry answer for a different list;
* the stored hash is checked first, so a hash collision cannot return another
  name's position — **this was a real bug in the first version**, which matched
  on list pointer and element pointer only and produced
  `Error: no such name pt` at `tests/run.sov:3519`;
* the probe is bounded at 64 slots and falls back to the walk, so a full table
  degrades instead of spinning.

The index is **adaptive**: only lists longer than 32 names are indexed at all.
Hashing every name cost more than a short scan, which measured 0.847x on
`a_functions` before the gate was added.

### 2. `u_san` — O(L^2) per line became O(L)

`u_san` blanks the inside of string literals and ran on nearly every line. It
grew its result with one `str_cat` per character, i.e. quadratic in the line
length. It now sizes one buffer from `length(ln)` and writes into it.

### 3. `sg_match`, `sg_sp`, `sg_one`, and the `str_cat` chains

* `sg_match` recomputed `length(s)` on every iteration and walked the whole
  pattern even when byte 0 differed. It now hoists both lengths and bails on
  the first byte.
* `sg_sp` allocated a fresh run of spaces for every indent. Indents come from a
  handful of values, so each one is built once and handed back thereafter.
* `sg_one`'s `name = value` rewrite chained four `str_cat`s. Fourteen such
  chains across `u_sugar` were collapsed into `sg_cat6`, one buffer sized from
  the six lengths. (`sg_cat2..sg_cat5` are thin wrappers.)
* `_sov_list_get` was inlined at four loops whose bound already is the list
  length, and the block-file cache `inc_c_get` — a linear scan with a
  byte-by-byte compare over up to 142 block files — now answers through the
  same index.

### 4. Also measured and rejected this pass

* **`_sov_str_eq` SWAR, length-bounded** (`_sov_strlen` both sides, then
  compare whole words): **0.995x**. Reverted.
* **`_sov_str_eq` SWAR, no length at all** (compare eight bytes, then words
  with a `haszero` terminator test — provably safe because eight agreeing
  bytes mean the allocator has already rounded both strings to a whole 16-byte
  unit): **0.965x**. Reverted.
* **`_sov_substring` bounded scan** (stop the clamp scan at the requested end
  instead of walking the whole string): **0.938x** — slower, because the common
  call is `cut(t, i, length(t))` where the end already is the length. Reverted.
* `str_cat` chain collapse and `_sov_list_get` inlining: individually neutral
  (kept — they are strictly less work per call).

`_sov_str_eq` is ~12% of self samples and has now failed to convert four times
(length-first, 4x unroll, length-bounded SWAR, haszero SWAR). The share is call
and prologue cost, not loop-body cost.

### 5. Landmine found and recorded

**An apostrophe inside a `#` comment in `runtime.sov` segfaults the compiler**
(`rc=139`, fault in the installed `compilers/linux/compiler`, in `sg_match`
reached through the sugar's quote-state machine). `ccore.sov` tolerates
apostrophes in comments; `runtime.sov` does not. Every comment added to
`runtime.sov` must avoid `'`.

### 6. Where the remaining time is

Profile of the landed build (`e_run`, 2,354 samples): the shared
`_sov_str_eq`/`_sov_strlen` fragment region 15.9%, `_sov_list_get` 7.8%,
`_sov_strcat` 7.3%, `_sov_substring` 6.5%, `fn#156` 5.8% (the `glob`/`grel`
patch path, 6,500 B), `_sov_list_add` 4.1%, `fn#305` 3.7%, `fn#154` 3.4%,
`_sov_list_new` 3.1%. Roughly 40% of the compiler is now string and list
primitives, and each of them has been measured as immovable by local edits.

Closing the remaining ~666x to `sa` needs the rewrite already scoped in this
document — offset-based token descriptors instead of freshly allocated strings,
so the front end stops copying the program once per sugar pass — not further
patches to these primitives.

---

## Pass 9 addendum — the `u_sugar` no-change fast path (LANDED)

`u_sugar` ended with `return sg_text(out)`, which allocates a fresh buffer the
size of the whole expanded program and copies every line into it — on every
pass, even when not one line was rewritten. It now first walks `out` against
`sls` comparing pointers (O(lines), no byte scan) and, if every entry is the
same object, checks `sg_len(out) = length(source)` and returns `source`
itself. The pointer walk proves no line changed; the length check proves the
join is an exact inverse of the split, so the two together make the
substitution byte-for-byte safe.

The fast path turns out to fire rarely on the gate source — most lines are
rewritten somewhere — so it measured **1.000x on `e_run`, 1.029x on
`a_functions`**. It is kept because it is free when it does not fire and it
removes a multi-hundred-kilobyte allocation when it does.

Installed compiler md5 after this addendum:
`6b99998ecedfbd3cc0f0c9ab6683f136`. `bootstrap` **159 ok / 0 FAIL**; suite
**224 passed / 3 failed / 4 skipped**, FAIL set unchanged; 158 backends rolled
out; `sovren` and `sovren.exe` both still rebuild byte-identical. Gate source
best **402.3 ms** (459.7 ms at the start of Pass 9, **1.14x**; best single run
394.8 ms, **1.16x**).

### Three further dead ends, recorded so they are not retried

* **`_sov_str_eq` SWAR, length-bounded** — 0.995x. Reverted.
* **`_sov_str_eq` SWAR, no length call at all** (eight bytes then words with a
  `haszero` terminator test, provably in-bounds because eight agreeing bytes
  mean the allocator has already rounded both strings to a whole 16-byte unit)
  — 0.965x. Reverted.
* **`_sov_strcat` word tail for short remainders** (one `poke_i64` instead of
  up to seven single-byte stores, with the in-bounds argument written out in
  the comment) — 0.985x. Reverted.
* **`_sov_substring` bounded clamp scan** — 0.938x, i.e. slower, because the
  dominant call is `cut(t, i, length(t))` where the end already is the length.
  Reverted.

`_sov_str_eq` has now failed to convert **six** times (length-first, 4x unroll,
length-bounded SWAR, haszero SWAR, and the two above counted from the earlier
record). Its ~12% profile share is call and prologue cost, not loop-body cost,
and no edit confined to the loop body will move it.

### The honest position

Pass 9 delivered **1.14x** on the gate source and is fully landed and verified.
The remaining gap to `sa` is roughly **666x per byte** and is not reachable by
further edits to the primitives — instruction count, call count, allocation
count and memory layout have each now been measured neutral or negative across
two passes of experiments. What is left is the rewrite already scoped above:
replace the freshly-allocated-string representation of the program with
offset-based descriptors into one buffer, so the front end stops copying the
program once per sugar pass and the back end stops rebuilding it once per
relocation. That work is started, not finished.

---

## Pass 9 second addendum — `fopn`'s single-character compare (LANDED)

`fopn e op nxt` (`inc03.sov:424..429`, the word-boundary check that backs
`expr`'s operator scan) decided whether the character next to a matched
operator was a word character like this:

```
if i + length(op) < n -> if _sov_str_eq(letter(e, i + length(op)), nxt) = 1
if i > 0 -> if _sov_str_eq(letter(e, i - 1), nxt) = 1
```

`nxt` is bound by `fopn`'s only two call sites — `fopn(e, "<", "<")` and
`fopn(e, ">", ">")` — so **both operands are always single characters**. Each
check therefore paid for a lookup in `letter`'s two-megabyte hash cache (two
`peek_i64`s into a scattered table, i.e. L2/L3 misses) plus a `_sov_str_eq`
call and its byte loop, to answer a question two byte loads answer:

```
if i + length(op) < n -> if _sov_byte_at(e, i + length(op)) = _sov_byte_at(nxt, 0)
if i > 0 -> if _sov_byte_at(e, i - 1) = _sov_byte_at(nxt, 0)
```

The two guards make the index valid, `letter` returns the one-character string
for a valid index, and `nxt` is non-empty, so the forms are equivalent —
including the case where `nxt` were empty, since `e[p]` is then non-zero.

Measured **1.003x on `e_run`, 1.005x on `a_functions`** against a rebuild of
the previous tree — inside the ±3% noise floor, so effectively neutral, but
strictly less work per call and byte-identical output. Kept for that reason.

**This is the shape of the remaining problem, and it is worth stating plainly.**
The change removes a 2 MB hash probe and a function call and buys 0.3%. Every
primitive in the top of the profile has now been edited at least twice with
the same outcome. The compiler is not bound by the work these functions do; it
is bound by the fact that they are called at all, roughly 1.76 million times
per compile, once per freshly allocated string.

Installed compiler md5 `abdd33b714d6941201bfd4ee1213f420`. `bootstrap`
**159 ok / 0 FAIL**; suite **224 passed / 3 failed / 4 skipped**, FAIL set
unchanged; 158 backends rolled out.

### The rewrite, started

The first piece of the offset-descriptor work that is actually safe to land
incrementally is the **linear line writer**. `ren_word`, `qualify` and
`apply_aliases` (`inc01.sov:1146..1245`) build their results with
`join(out, letter(s, i))` — one fresh two-byte string per character and one
full copy of the result per character, so a line of length L costs O(L^2)
bytes copied. Those three live behind `apply_aliases`, which returns
immediately when `alias_pairs` is empty, so they are dead on the gate source
and the win only appears once aliasing is switched on. The writer is specced
in the notes below and is the next thing to land:

* `bw_new cap` — a 40-byte header (cursor, capacity, buffer, piece list) plus
  a scratch buffer of `cap` bytes.
* `bw_b bw v` — append one byte; folds the scratch into the piece list and
  starts a fresh one only when it fills.
* `bw_s bw s` — append a whole string byte by byte through `bw_b`.
* `bw_done bw` — terminate the scratch, push it, and join the pieces once.

That makes the pass O(L) with one call per byte and no per-byte allocation,
against today's two calls and a growing copy per byte. The fragment pool at
`inc01.sov:1146..1245` is sliced in ten-line blocks by `inc05.sov:263..277`
and `inc05.sov:981` and by nothing else, so the blocks can be rewritten as
long as each stays exactly ten lines.

---

## Pass 9 third addendum — `sg_match_n`, the length recomputed per byte (LANDED)

`sg_match t i s` opens with:

```
sg_match t i s:
    ls: length(s)
    if i + ls > length(t) -> return 0
```

`length(t)` is recomputed on **every call**. `fop e op` — the operator scanner
that backs `expr` — calls `sg_match(e, i, op)` at every position of every
expression, and `expr` tries roughly thirty operators in precedence order, so
one expression of length L cost about `30 * L` strlens of `e`, each O(L): a
quadratic scan hidden behind a helper that looks linear.

`sg_match_n t i s tn` is the same test with the length handed in, and `fop`'s
loop — whose prologue already computes `n: length(e)` from
`inc00.sov:106..114` — now calls `sg_match_n(e, i, op, n)`:

```
if sg_match_n(e, i, op, n) = 1 -> f: i
```

`e` is a parameter and is not written inside the loop, so `n` stays valid for
the whole scan. Measured **1.005x on `e_run`, 1.011x on `a_functions`** —
inside the ±3% noise floor, so neutral in wall clock, but it deletes a
stride-length strlen per position per operator and is byte-identical.

`fopn` has the same shape at `inc03.sov:424` and will take the same treatment
once its `n` binding is traced; it was left alone rather than guessed at.

Installed compiler md5 `aa40eb3f978784dbb0a1b32238dc3a77`. `bootstrap`
**159 ok / 0 FAIL**; suite **224 passed / 3 failed / 4 skipped**, FAIL set
unchanged; 158 backends rolled out.

### The library split, measured

`library/` holds 215 modules. The compiler itself needs only:

* `library/ccore.sov` — the front end
* `library/inc/*.sov` — the shared fragment pool, **line-number sliced, so it
  can never move**
* `library/cx86.sov` and its sibling backends — pulled in by `use cx86` at
  `inc03.sov:1617` and equivalents
* `runtime.sov` — at the repo root, injected into the compiler and every user
  program
* `library/sbuf.sov` — named in the unchecked-memory error message

The other ~190 modules (`audio`, `aes`, `array`, `base64`, `bmp`, `msg`,
`match`, `case`, `arena`, ...) are **user-program libraries**. They are not
referenced by any of the 158 `compilers/*/compiler.sov` drivers and never
enter the compiler binary. That is the ecosystem, and it does not belong in
the compiler's source tree — but it must move as a deliberate, versioned
extraction, because `use <name>` currently resolves only against the in-tree
`library/` directory and every one of those files sits in the build's search
path today.

---

## Pass 9 fourth addendum — the index that was not a index (LANDED, 2x)

### The measurement that found it

Compile time was measured against source size on generated inputs. ns/byte
fell to a minimum near 190 KB and then **rose again**: 4x the bytes cost 6.6x
the time. Bisecting by shape isolated it:

| shape | 400 -> 6400 | ns/byte 400 | ns/byte 6400 |
|---|---|---|---|
| N functions, no globals | 17.1x bytes | 3039 | 4354 |
| **N global definitions, nothing else** | 19.5x bytes | 14679 | **26569** |
| N functions each referencing one global | 16.7x bytes | 3066 | 5724 |

Just *defining* globals — `g0: 0` ... `g6399: 6399` and a two-line `main` —
went from 0.056 s to 1.98 s. Profiling that input put **59% of self samples
in `_sov_str_eq`'s byte loop**, 17% in `_sov_list_get`, and 10% in `patch`,
which alone accounted for 5,521 sampled calls into the string-compare region.
Roughly 700 million loop iterations to resolve 6,400 names.

### The bug

`ih_find` probes the open-addressed table and, on reaching an empty slot,
does this:

```
if lp = 0 -> t: 64      # leave the loop ...
...
return ih_slow(lst, name)   # ... and scan the whole list anyway
```

An empty slot ends the probe chain, so the loop exit was correct — but the
code then fell through to `ih_slow`, a **full linear scan with `_sov_str_eq`
on every element**. Every miss was O(names). And misses are the common case:
`patch` looks up relocation targets that are not globals, `store_glob` probes
before every insert, and the globals emitter resolves one name per global.
6400 globals x 6400 names compared is the 700 million iterations.

Worse, `ih_slow` only indexed the prefix it walked **up to the hit**:

```
if _sov_str_eq(s, name) = 1 -> if n > 32
        ih_put(lst, s, i)
    return i          # <-- returns here, so the tail is never indexed
```

So the index was permanently incomplete for any list that had ever been
missed on, which is why the empty slot could not simply answer "not present":
the tail beyond the indexed prefix had never been inserted.

### The fix

1. **`ih_mark` / `ih_put_mark`** — each indexed list owns one mark slot
   (`[0]`=list, `[8]`=0 as the sentinel, `[16]`=how many leading entries the
   index covers). A zero name pointer is unambiguous because a real entry
   always stores a name.
2. **`ih_slow` indexes the tail the mark says is uncovered**, then updates the
   mark. It no longer returns early, so the whole list gets covered.
3. **`ih_find` answers a miss in O(1)**: on an empty slot it asks
   `ih_mark(lst) >= _sov_list_len(lst)` and, when the index covers the whole
   list, returns -1 immediately. If the list has grown since it was indexed it
   still falls through and indexes the new tail, so appends stay correct.

The mark lives in the same table using the same linear-probing rules, so
`ih_put` treats it as occupied and nothing else changes. `ih_clear` wipes the
marks along with the entries, after which the first miss re-indexes — correct,
just not free, and clearing only happens at 50% load.

### Result

| N globals | before | after | speedup |
|---|---|---|---|
| 1600 | 0.2183 s | 0.0772 s | **2.83x** |
| 3200 | 0.5553 s | 0.2772 s | **2.00x** |
| 6400 | 2.0960 s | 1.0710 s | **1.96x** |

Functions referencing a global: 1.53x / 1.13x / 1.02x at the same sizes — the
same fix, diluted because a second quadratic takes over at large N and is
still unhunted.

On the shipped benchmarks `e_run` **1.032x**, `a_functions` 0.970x (noise;
identical binaries measure 0.993x). The gate source has only 11 globals, so it
is not the beneficiary — this fixes a class of program, not that one input.

**Output is byte-identical** on the gate source and all 9 corpus programs.

**A segfault was repaired as a side effect.** The suite's meta-test
(`the Sovren suite`) printed `Segmentation fault` and failed on the previous
build; it now reports `ok`. Nothing else in the suite changed.

Installed compiler md5 `fc0bd4eeb96bdebc1bf2895be8dd8b17`. `bootstrap`
**159 ok / 0 FAIL**; suite **225 passed / 2 failed / 4 skipped** (was
224/3/4), the two failures being the pre-existing `arm-emulator-sha256` and
`arm64-codegen`; 158 backends rolled out.

---

## Pass 9 fifth addendum — the second quadratic, attempted and reverted

### What the profile said

The `gref` shape (N functions each referencing one global) still decayed:
1.53x at N=1600 down to 1.02x at N=6400, so a second quadratic takes over at
scale. Profiling N=6400:

| function | self | note |
|---|---|---|
| fn#0 @0x1ea | 54.07% | shared `_sov_str_eq` / `_sov_strlen` region |
| fn#71 @0x4ed6 | 10.89% | `_sov_list_get` |
| **fn#362 @0x3242d** | **10.67%** | 630 B, literals `main`, `_sov_`, `spawn_emit`, `rel`, `fnaddr` — the relocation pass; **makes no outgoing calls**, so all of its time is its own loop |
| fn#156 @0x1097a | 8.14% | `patch` |
| fn#563 @0x42bcd | 2.34% | 264 B, calls `_sov_str_eq` 1,123 times |

Disassembling fn#563 showed it **is** the new `ih_slow`: `_sov_list_len`, then
`ih_mark`, then a loop of `peek_i64(lst, 16 + i*8)` / `_sov_str_eq` /
`ih_put`, then `ih_put_mark`. So the index was still doing full scans.

### The attempt

`ih_slow` scanned **all** n elements with `_sov_str_eq` even for the prefix the
mark already covered — the index was only consulted for *insertion*, never to
*shortcut the scan*. The fix was to split it: `ih_slow` keeps the full scan for
short lists and for inconclusive probes, and a new `ih_tail` starts at
`st = ih_mark(lst)` and scans only the tail, on the reasoning that `ih_find`
has just missed on the indexed prefix.

### Why it was reverted — 5x slower

| shape | N | landed | attempted |
|---|---|---|---|
| gdef | 3200 | 0.5186 s | 2.7974 s |
| gdef | 6400 | 1.9199 s | 10.1443 s |
| gref | 3200 | 0.5097 s | 1.2602 s |
| gref | 6400 | 1.6880 s | 4.8938 s |

`ih_mark` probes `band(lst, ih_mask)` and gives up after 64 slots. A list's
mark slot can be displaced further than that once the table holds several
lists' worth of entries, and `ih_put_mark` has the same 64-slot ceiling — so it
can silently fail to store a mark at all. When `ih_mark` then returns 0,
`ih_tail` starts at zero and re-inserts every element on every call, which is
strictly worse than the landed version (which at least skipped `ih_put` for the
already-indexed prefix).

The mark needs a reliable home — either a dedicated side table with its own
probe limit, or the mark stored inside the list object — before the tail scan
can be trusted. That is the next thing to build, and it is not a small edit.

### Landed state, unchanged and re-verified

Tree rebuilds byte-identically to the installed compiler
(`fc0bd4eeb96bdebc1bf2895be8dd8b17`). `bootstrap` **159 ok / 0 FAIL**. Suite
**225 passed / 2 failed / 4 skipped**. Output byte-identical on the gate source
and all 9 corpus programs. `sovren` `b00801a14e0043731d40d6ddc3b02e85`,
`sovren.exe` `9e5f78d3558fce568db5fd8c3267fb77` (PE32+, 76,640 B).

### Cumulative for Task D

| | |
|---|---|
| gate source, best clean reading | 459.7 ms -> **394.8 ms (1.16x)** |
| globals-heavy code (N global definitions) | **2.83x / 2.00x / 1.96x** at N = 1600 / 3200 / 6400 |
| `e_run` isolated | 1.03x |
| segfaults repaired | 1 (the suite meta-test) |
| backends rolled out | 158 |

The gate source has 11 globals and 34 functions, so it is not the beneficiary
of the index fix; that fix repairs a class of program rather than that input.

---

## Correction to the fourth addendum — the "repaired segfault" was wrong

The fourth addendum reported that the suite's meta-test went from
`Segmentation fault` / FAIL to `ok`, and credited the index fix with repairing
a crash. **That was a flake and the claim is withdrawn.**

Re-running the suite gives 224 passed / 3 failed again, with
`FAIL the Sovren suite` back and `Segmentation fault` at the top of the log.
The test is flaky run to run.

Running the underlying check directly settles what it actually is:

```
$ ./sovren tests/all.sov -o /tmp/w/all.bin      # rc=0, builds fine
$ timeout 120 /tmp/w/all.bin                     # rc=124 -- TIMED OUT
ok plain builds stay 0755
ok thread slot round trip
ok thread join waits for the job
```

`ck_all` builds `tests/all.sov` and executes it. It runs **thread tests**, and
threads do not work in this sandbox, so the run hangs until the harness's
300-second limit kills it. The `Segmentation fault` line in the captured log is
the harness's own teardown after the kill, not a crash in the compiler.

**Conclusion: `the Sovren suite` is a pre-existing environmental failure,
present before every change in this pass, and it is not evidence either way
about the index fix.** The correct suite baseline for this work is
**224 passed / 3 failed / 4 skipped**, the three failures being
`the Sovren suite` (thread-dependent, sandbox), `arm-emulator-sha256` and
`arm64-codegen`. Nothing in Pass 9 changed that set.

Everything else in the fourth addendum stands: the scaling measurement, the
`ih_find` empty-slot fallback bug, the `ih_mark`/`ih_put_mark` fix, the 2.83x /
2.00x / 1.96x result on globals-heavy code, and the byte-identical output.

---

# Fleet status, 2026-10-03 (round: cache correctness + honest gate)

Harness: fresh process, output redirected, best of N, `library/.prebuilt`
read-only for the whole run so a hit cannot be served, and `--no-cache` passed
where the compiler supports it.  `sa` is the same harness on `bench6.sa.asm`
(4,196,595 B).

| translator | best | median | throughput |
|---|---:|---:|---:|
| `sa` bench6.sa.asm | 5.734 ms | 6.880 ms | 731.9 MB/s |
| Sovren linux `tests/run.sov` (expanded 359,951 B) | 189.0 ms | 216.1 ms | 1.904 MB/s |

Fleet sample, same source, same harness (`--no-cache`, best of 3):

| backend | best | expanded throughput | ratio to sa |
|---|---:|---:|---:|
| linux | 189.0 ms | 1.904 MB/s | 0.002602x |
| operating-systems/redox | 201.9 ms | 1.783 MB/s | 0.002436x |
| operating-systems/serenityos | 202.2 ms | 1.780 MB/s | 0.002432x |
| operating-systems/freebsd | 209.0 ms | 1.722 MB/s | 0.002353x |
| operating-systems/menuetos | 218.8 ms | 1.645 MB/s | 0.002248x |
| operating-systems/sovrenos | 219.2 ms | 1.642 MB/s | 0.002243x |
| operating-systems/illumos | 219.8 ms | 1.638 MB/s | 0.002238x |
| operating-systems/qnx | 222.3 ms | 1.619 MB/s | 0.002212x |
| operating-systems/netbsd | 225.6 ms | 1.595 MB/s | 0.002180x |
| operating-systems/dragonfly | 225.9 ms | 1.593 MB/s | 0.002177x |
| operating-systems/haiku | 227.0 ms | 1.586 MB/s | 0.002167x |
| operating-systems/openbsd | 232.6 ms | 1.548 MB/s | 0.002115x |
| linux/arm64 | 247.9 ms | 1.452 MB/s | 0.001984x |
| android | 250.7 ms | 1.436 MB/s | 0.001961x |
| apple/macos-arm64 | 689.5 ms | 0.522 MB/s | 0.000713x |

The whole fleet is therefore in the same 0.0007x–0.0026x band.  Nothing in this
round was accepted as a speed change; the round landed correctness and
measurement, not throughput.

## Where a `tests/run.sov` compile actually goes

Phase hooks in an instrumented build (microseconds, best of runs, 213 ms total):

| phase | µs | note |
|---|---:|---|
| load + `splice_inc` | 4,100 | one read, include splice |
| `u_sugar` (pad + pass, twice when arrows appear) | 35,800 | 17% |
| `pull_uses` (chunk load + per-chunk sugar + closure) | 30,000 | 14% |
| `need` probes | 3,400 | 9 `look()` scans |
| runtime load + sugar | 4,700 | 33 KB, sugared once |
| src_base accounting (`lines_of` x2, `sg_extra_all` x2) | 3,900 | 4 passes over rt+extra |
| `u_scan` + alias pass | 6,100 | |
| pre-pass (arg names, string marks) | 14,900 | per-line, over every line |
| **emit loop** | **89,300** | **42%** |
| `dce_stores` / `dce_litter` / `dce_globals` | 1,200 / 1,200 / ~0 | |
| `write_elf` | 2,300 | |

Self-time from the ptrace sampler (fresh run, names via `endbr64` + `.map`):
`_sov_find_text` 14.4%, `length` 10.5%, `_sov_substring` 9.8%, `_sov_list_add`
5.8%, `_sov_strcat` 4.1%, `_sov_list_new` 3.2%, `num_value` 2.7%, `intern`
2.7%, `put` 2.7%, `strip` 2.5%, `ih_find` 2.1%, `expr_body` 2.1%, `call_args`
2.1%, `lines_of_fast` 1.9%.  The emit loop and the sugar pass between them are
90% of the time, and both are the "cheap pass over every line with allocating
string helpers" shape.

## Landed

1. **Cache correctness.** The artifact cache keyed on the input file's bytes,
   the compiler path and a size, but not on the library files the input
   includes.  Reproduced: append a global to `library/ccore.sov`, rebuild a kit,
   and the compiler writes the pre-edit bytes back — silently, with exit 0.
   Now the cache is **off unless `--cache` is passed**; `pb_save` honours the
   same switch, `--cache`/`--no-cache` are the only switches the fast path lets
   through, and every other switch is folded into the key, so `--release`
   cannot be answered with a default-mode entry.
2. **`dce_globals`** no longer asks every global about every patch (G x P
   `_sov_str_eq` calls).  Patch values are hashed once and the inner scan is an
   integer compare that falls back to `_sov_str_eq` on a hit.  Same answer on
   all fixtures; measured neutral on `tests/run.sov` (the phase table puts the
   pass at ~0 µs anyway — the sampler had been mis-attributing `dce_litter` to
   it).
3. **`tools/speed_gate.py`** now measures cold translation (`--no-cache` plus a
   read-only `.prebuilt`) instead of reporting the cache hit as throughput; the
   warm number is printed separately and labelled.
4. **Fleet rebuilt and re-gated.**  All 159 bootstrap steps re-run; 158 `ok`,
   the one failure is the pre-existing `debugger` step (`tools/debug.sov` does
   not build).  The linux compiler is at a true fixed point (it rebuilds itself
   byte-identically).  21/21 compilable `tests/*.sov` fixtures and 29/29
   regenerated backends produce byte-identical output against the pristine
   binaries the project shipped, and `tests/fast.sov` reports 428 passed /
   0 failed / 14 not run.

## Why micro-optimisation cannot close this

The emit loop costs ~9 µs per source line and the sugar pass ~4 µs; `sa` runs
its whole translation in ~0.05 µs per line.  A ~100x gap is not a constant
factor that a faster `look()` or a memo table buys back — it is the
representation: every pass re-splits the text into allocated line strings,
looks names up by comparing strings, and walks a byte list for output.  The
required shape is unchanged from the section above: one read, offset
descriptors, one interner, one pass, arena emission, work-queue propagation --
shared by every backend, with the same fresh-process gate per backend.
