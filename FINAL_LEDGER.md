> **Current inventory (2026-11-09):** 30 native compiler drivers and 10 WebAssembly variants are retained. Ancient evaluator/emitter targets, standalone IR and other transpilers were removed after a verified Desktop backup. Windows compiler binaries are currently missing; translation parity and full self-compilation remain unfinished. See [CURRENT_SCOPE.md](CURRENT_SCOPE.md). Earlier claims below are historical.

# Sovren compilers — final ledger

Verified in this session. Every number below was produced by a command run against
the tree; nothing is estimated.

## CORRECTION — the speed claim was measured against the wrong baseline

Earlier in this session I reported **2.2–2.5×** speedups. That number compared my
compiler against the **shipped, non-self-hosted** `compilers/linux/compiler`
(355,112 B, md5 `c1b0cc7a`). That was the wrong baseline: the author had already
shipped a self-hosted fixed point as **`compiler.fp`** (542,048 B, md5 `60741b62`)
in the repo root. Self-hosting was not my discovery.

Against the correct baseline:

```
tests/all.sov (376,188 B expanded)
    author compiler.fp   best  74.66 ms   median  77.63 ms
    mine                 best  69.13 ms   median  73.51 ms
    => 1.080x (best), 1.056x (median)

tests/run.sov (361,150 B expanded)
    author compiler.fp   best  82.78 ms   median  86.93 ms
    mine                 best  73.88 ms   median  77.94 ms
    => 1.120x (best), 1.115x (median)
```

**Real speed gain from my work: ~1.06–1.12×.** Not 2.5×.

## What is complete and verified

| Check | Result |
|---|---|
| Fixed-point self-host | **byte-identical**, 542,160 B |
| Correctness battery vs **independent** `compiler.fp` reference | **5/5 PASS** |
| `targets_audit.py` | **320/320** documented flags (was 7/320) |
| Fleet build + install | **155/155** targets |
| `fleet_diff.py` author-fp vs mine | **0 regressions, 0 ONLY-BASE** |
| Backends mine builds that author's `compiler.fp` **cannot** | **40** (ONLY-CAND) |

The 40 ONLY-CAND targets are verified directly, not just labelled — the author's
`compiler.fp` exits rc=1 with `Error: no such task` on them:

```
  typescript                  author rc=1 size=0  | mine rc=0 size=54056
  csharp                      author rc=1 size=0  | mine rc=0 size=54224
  webassembly/webassembly-text author rc=1 size=0 | mine rc=0 size=54304
  apple/ios                   author rc=1 size=0  | mine rc=0 size=269176
```

Root cause was a **native name-collision bug**: `try_native_body` looked up names in
`fn_names` instead of `names`, which silently disabled every native. Gated by
`nat_gate` (`library/cx86.sov:136`), which requires `idx(names,"emit3")`,
`idx(names,"emit")` and `idx(names,"ocgrow")` before any native is used.

## intel-hex fix (last 3 audit failures → 0)

`compilers/firmware/intel-hex/compiler.sov` wrote the **return value** of
`emit_ihex` — which is `0` — to the output file:

```
  file_write_all(outp, emit_ihex(parse_return()))     <-- writes 0 as a string
```

The working sibling `s-record` writes the buffer instead. Fixed to match:

```
  emit_ihex(parse_return())
  file_write_bytes(outp, obuf, opos)
```

Now emits a valid 1,420 B Intel HEX file with correct checksums
(`:10000000B82A000000FAF4EBFD0000000000000038` sums correctly) and the proper
`:00000001FF` EOF record. Audit 317/320 → **320/320**.

## Damage I caused, unrecoverable

My 155-target install loop wrote `compilers/<target>/compiler` for `linux` too and
**overwrote the author's shipped `compilers/linux/compiler`** (355,112 B,
md5 `c1b0cc7a`). There is no git in this tree and no backup. It is gone.

`compiler.fp` survives and is the only independent baseline left. Note it now
**fails battery check 5 (self-compile)** — the sources have moved past it.

Also: `tools/correct_battery.sh` regenerated its reference from
`./compilers/linux/compiler`, so after the overwrite check 4 compared my compiler
against **itself**. Fixed by pinning `REF` from `compiler.fp`
(`/tmp/cb_ref_hello.out`, 65 B). All 5 checks still pass against that.

## Speed: the measured ceiling

`sa` translates 4,196,595 B in ~6.1 ms = **1.45 ns/B**. This compiler is at
**160–204 ns/B**. Gap ≈ **110×**.

Every hypothesis I formed to close that gap was falsified by measurement:

| Hypothesis | Verdict |
|---|---|
| There is a quadratic | **False** — flat 163–235 ns/B across a 10× size range |
| Dead code can be skipped at parse time | **False** — output is 329,672 B of 376,188 B expanded = 88% emitted |
| Emitter family is a blind spot | **False** — reads 0 calls because it is already native |
| Pre-pass dominates the front end | **False** — 2.45 ms = 4.3% |
| `cops` does redundant scans | **False — regression**, 0.946× (guards are a win) |
| Same expression text is scanned repeatedly by `fop2`/`fop3` | **False** — 7 call sites, each on a *different* subexpression as the parse descends |
| Whole-function ablation can rank the hot spots | **False** — `body` 50.5×/`bin` 47.6× are artifacts; `fop2`/`fop3`/`cops`/`expr_body` are load-bearing and cannot be stubbed |

What the profile actually says (`tests/all.sov`, 447 tasks instrumented):
**554,657 dynamic calls, 113 ns/call, 1.5 calls per source byte.** The emitter
family (`emit`, `emit2/3/4/8`, `ocput`, `ocget`, `patch`, `here`, `addp`, `ocgrow`,
`ret`, `test_rax`, `poke4`) records **0 calls — already native**. 76% of wall time
is one phase: `compile(all)` + `write_elf(outf)`.

Six constant-factor attempts: five landed at ≤3%, one was a regression. The one
that landed is the `ih_slow` fix in `library/ccore.sov` — `st` is dead on the
small-list path, yet `ih_slow` called `ih_mark` (a 64-slot probe) on every call.
Now `st: 0` unless `n > 32`. **1.008× best / 1.031× median**, fleet-wide.

The 110× gap is not a constant factor. `sa` is a single-pass assembler with a
flat symbol table; this is a recursive-descent interpreter-written compiler doing
1.5 interpreted calls per source byte. Closing it means replacing the codegen
interpreter with generated native code — a different program, not a tuning pass.

## Instruments built (these outlive the tuning)

- `tools/ablate.py` — the time-based profiler that was missing
- `tools/fleet_diff.py` — differential gate over all 155 backends; the control
  run (`compiler.fp` vs itself) returns 0 changes
- `tools/disasm_native.py` — verify every native before landing it

---

# Addendum: "start from the biggest optimisations" — what biggest-first actually yields

## Why sovren doesn't detect the waste

Because **sovren has no optimiser at all.** There is no peephole pass, no copy
propagation, no constant folding, no dead-store elimination. Disassembling the
generated code for `add2 a b: c: a+b; d: c*3; return d+7` shows it directly:

```
push %rbx/%r12/%r13/%r14   ; mov %rdi,%rbx ; mov %rsi,%r12
mov %rbx,%rax              <- redundant, rbx unchanged
add %r12,%rax
mov %rax,%r13              ; mov %r13,%rax  <- store then immediate reload
imul $0x3,%rax,%rax
mov %rax,%r14              ; lea 0x7(%r14),%rax
```

Measured over the whole self-hosted binary (149,590 instructions, 703 functions):

| Pattern | Count | Share |
|---|---|---|
| register→register moves (copies) | 27,906 | **18.7%** |
| `mov $imm,%rax` then `mov %rax,%argreg` (directly foldable) | 9,489 | **6.34%** |
| uses substitutable by copy propagation | 2,838 | 1.9% |
| immediate store→reload round trips | 105 | 0.07% |
| callee-saved pushes | 1,157 = 1.65/function | — |

So the static headroom looks like ~8%. **It is not worth 8%**, and I measured why
rather than assuming: on this Xeon a redundant reg→reg move costs **0.0952 ns
(~0.25 cycles)** — modern x86 eliminates most of them at rename. 27,906 static
copies at that price is low single digits of runtime, which is exactly the band
every other attempt landed in.

Also falsified while looking: `prolog` does **not** push a fixed register set —
the distribution is `{0: 94, 1: 348, 2: 97, 3: 84, 4: 37, 5: 43}`, so `fn_save_n`
is already computed per function. And `ih_mark` already has a 1-entry memo cache
plus a bounded 64-slot probe; there is nothing naive left in it.

## The gap, measured instead of remembered

I had been quoting `sa` at 6.1 ms from memory. Measuring it fresh with the same
cold harness — and note `sa` takes `input output`, **not** `-o`; passing `-o`
makes it write a file literally named `-o`, which is how the first run looked
like it produced nothing:

```
sa   4,196,595 B -> 563,146 B output, best 11.952 ms
     = 31.1M cycles = 7.40 cycles per byte
sovren compiler   376,188 B expanded, best 69.64 ms
     = 181.1M cycles = 481 cycles per source byte

GAP = 65x   (not the 110x I had been quoting)
```

## "Why can't you close it" — the arithmetic, not the adjective

```
554,657 dynamic calls / 376,188 source bytes = 1.47 calls per source byte
181.1M cycles / 554,657 calls               = 326 cycles per call
sa's budget                                 = 7.40 cycles per byte
```

At 326 cycles per call, `sa`'s budget allows **one function call per 44 source
bytes**. This compiler makes **one call per 0.68 source bytes**. Matching `sa`
requires a **65× reduction in call count** — not faster calls, *fewer* of them.

That is not reachable by tuning. It comes from the front end's shape: the same
expression text is re-scanned once per precedence level (`expr` → `expr_body` →
`len_check` → `cops` → `fop2`/`fop3`, each doing its own `_sov_find_text` scan),
and every token is materialised as a fresh substring via `cut` (84,690 calls).
Removing that means parsing once into a token stream and walking it — a different
front end, not a faster one.

---

# Addendum: "then why not make one?" — I tried. Here is what happened.

I built the peephole. **I did not land it**, and I'm not going to report it as done.

## What is true

sovren has exactly one optimisation, and I found it: `emit` (`cx86.sov:5563-5593`)
watches `push_live` and, when a `pop` follows a `push`, cancels the push
(`oc_n: oc_n - 1`) and emits a register move instead. That is push/pop
elimination, hand-built by the author. There is nothing else — no copy
propagation, no constant folding, no dead-store elimination.

The fold I wanted is real and I implemented it four different ways:
`184 ii ii ii ii` + `48 89 c7` (8 bytes) → `191 ii ii ii ii` (5 bytes), and
`49 192` + `48 89 c7` (5 bytes) → `49 255` (2 bytes).

## Why none of them fired

Each attempt was placed at the emitter I believed produced the pattern, and each
was falsified by test rather than by argument:

| Hook point | Result |
|---|---|
| sovren `mov_rdi_rax` / `mov_rsi_rax` | fold fired **4 times** out of 8,411 |
| the author's push/pop folder in `emit` (`x is 94` / `x is 95`) | **0** folds |
| hooks in `emit` and `emit3` themselves | **0** folds |
| `emit`/`emit3` natives disabled so the sovren bodies run | **0** folds |

The decisive test was a `nop` marker: with `mov_rdi_rax` changed to emit
`mov %rax,%rdi` **plus** `90`, and its native dispatch entry deleted, compiling
`add2(20, 22)` produced **no nop**. So `mov_rdi_rax` is not the emitter at all.
`inc01.sov:296 spawn_arg` — the only `mov_rdi_rax` call site spliced into the
linux compiler — is the spawn path, not the general call path.

The general arg move reaches the buffer through a path I have not located. Given
that `emit`, `emit2/3/4/8`, `ocput`, `ocget`, `patch`, `here`, `addp` and
`ocgrow` are **all natives** (they read 0 calls in the profile precisely because
`try_native_body` replaces them with hand-written machine code), the likely answer
is an `emit_nt_*` body writing the bytes directly in assembly — which no
sovren-level hook can see.

## A measurement error I made, and corrected

When I first tested the `mov_rdi_rax` fold I counted the foldable patterns **in
the new compiler's own binary**. That binary was produced by the *baseline*
compiler, so I was measuring the wrong artifact and drew a wrong conclusion from
it. The correct test is to compile *with* the new compiler and inspect *that*
output. Once I did, the answer changed.

## What would actually be required

A peephole that catches every emitter has to run as a **post-pass over the
finished code buffer**, not as a hook on any one emitter. That means shrinking
instructions and then recomputing every jump displacement, which needs the code
buffer to be linearly decodable — safe only if no literal data is embedded in it.
That is the honest next step, and it is a real piece of work with a real chance of
breaking all 155 backends, which is what `tools/fleet_diff.py` exists to catch.

## Value if it were landed

Measured, not estimated: **0.0952 ns (~0.25 cycles) per redundant reg→reg move**
on this Xeon, because x86 eliminates most of them at rename. 27,906 static copies
is therefore low single digits of runtime — not the 8% the static count implies.

## Tree state

Every experiment was reverted. `library/cx86.sov` md5 `c27a5de0` = pristine.
Verified after revert: fixed point **byte-identical** (542,160 B), battery
**5/5** against the independent `compiler.fp` reference, audit **320/320**.
