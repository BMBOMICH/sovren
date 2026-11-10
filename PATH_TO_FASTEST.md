# Path to fastest — execution speed, everywhere

## The question answered first

**Is there a "fastest compiler" in execution speed? No.** GCC and LLVM/Clang
trade wins workload by workload and neither dominates:

| evidence | result |
|---|---|
| 10-case `-O3` C++ batch (2026) | GCC ahead more often; Clang won branch-heavy by 21.3%, small-sort 9.6%; GCC won 2D stencil 24.3%, strided 4.2% |
| AmpereOne AArch64 survey | Clang ~5% faster on QuantLib; GCC consistently faster on miniBUDE and simdjson |
| Arch/Linux-kernel compile speed | GCC beats Clang even with LLVM built LTO+PGO |

The benchmark's own conclusion: *"benchmark the real code you care about before
choosing a winner."* So "match LLVM" is the wrong goal — the right goal is
**match C `-O2` on a representative loop suite**, which is a concrete, measurable
target.

**Current distance from that target, measured:** sovren's loop code is
**1.84x slower than C `-O2`** (1524 vs 2801 MB/s on an 80 MB byte-sum).

## What actually determines execution speed, in order

1. **Register allocation** — *"the most important optimisation performed by the
   compiler"* (a register is <1 cycle, DRAM is hundreds). **This is sovren's
   weakest point and the biggest win available.**
2. **Instruction selection / memory-operand folding** — partly landed (Pass 7).
3. **PGO** — largest single win available for the effort; needs a profile format
   and a recompile mode, no new backend machinery.
4. **LTO / whole-program view** — cross-module inlining and DCE.
5. **Auto-vectorisation** — high ceiling but needs a cost model: picking the
   wrong vectorisation/interleaving factor pair cost **5.57x** in one study
   while the right pair gained 1.60x.

## The plan

### Tier 1 — register allocation (the big one)

The backend currently computes everything into `%rax` and spills with
`push`/`pop`. Evidence from `_sov_list_add`'s growth path: six `push`/`pop`
pairs to copy one element, and `push $n; pop %rax` to materialise a constant.

Steps, in order:
1. **Linear-scan register allocation over the expression tree** for the
   x86 backend. Live ranges are already computable — `try_scaled_mem` and the
   `peek_home`/`reg_slot` machinery already track which locals live in which
   registers, so the infrastructure exists and is simply not used for
   temporaries.
2. **Two scratch registers** (`%rcx`, `%rdx`) for binary operands, so
   `bin(a, b, op)` stops doing `push_rax(); expr(b); pop_rax()`.
3. **Rematerialisation** of constants instead of spilling them.
4. Repeat for `carm.sov` and the other first-class backends.

Target: within 1.2x of C `-O2` on the loop suite.

### Tier 2 — instruction selection

1. **Addressing-mode selection**: `base + index*scale + disp` in one operand.
   Pass 7 landed `disp(%rdi)` and `disp(%rdi,%rsi,8)`; the remaining form is
   `peek_i64(base + K, C)` (base with a constant offset *and* a constant
   displacement) which appears in the `look`/`letter` memo caches — 816 constant
   `peek_i64` sites exist but only 50 fold today.
2. **Strength reduction**: `x * 8` -> `shl $3`, `x % 2` -> `and $1`.
3. **Peephole pass** over the emitted byte stream: `push`/`pop` pair
   elimination, jump-to-jump shortening, redundant `mov %r,%r`.
4. **Branch layout**: fall-through for the taken edge.

### Tier 3 — PGO

1. `--pgo-generate`: emit a counter increment per function entry and per
   backward branch.
2. A profile file format (fixed-size records, no parsing cost).
3. `--pgo-use`: feed counts into inlining, block layout, and register
   allocation.

This is the highest value-per-effort item after register allocation because it
needs no new analysis — only counters and a recompile mode.

### Tier 4 — LTO and vectorisation

1. **LTO**: keep the per-module code in a re-readable form so the final link can
   inline and DCE across modules.
2. **Vectorisation**: start with the two loops that already have closed forms
   (`emit_sum_closed`, `emit_sumsq_closed` in `cx86.sov`) and widen from there.
   Always gate on a cost model — the 5.57x downside is real.

### Tier 5 — the loop suite (measurement)

Before any of this, build the harness: a set of ~20 loops (byte sum, string
search, list walk, hash, sort, matrix, CRC, memcpy, struct walk) compiled by
sovren and by `gcc -O2`, run on the same input, with the ratio reported. This is
the only way to know whether a change helped, and it is the harness that says
"1.84x" today.

## Should execution work go into `sa` too?

**Yes, but it is a separate track and it does not help sovren-compiled
binaries.**

- `sa` is the assembler. It legitimately owns execution-speed work that is local
  to an instruction stream: **peephole rewriting, instruction scheduling,
  branch-target alignment, jump-chain shortening, redundant-load elimination.**
  These are real wins and they belong in an assembler.
- **`sa` is not in the execution path of sovren-built binaries.** Sovren's
  compilers emit machine-code bytes directly via `emit:`/`emit4:`/`emit8:` in
  `library/cx86.sov`. A binary from `compilers/linux/compiler` never touches
  `sa`.
- So: improving `sa` speeds up `sa`-assembled programs; improving `cx86.sov`
  speeds up sovren-compiled programs. **Both are worth doing; neither
  substitutes for the other.** If the goal is "sovren is fastest everywhere",
  both tracks must land, and the compiler backends are the one that matters for
  sovren's own output.

## Success criteria

- Loop suite: sovren/C-`-O2` <= 1.2x on every loop.
- No `push`/`pop` spill pair in any hot loop.
- `--pgo-generate` / `--pgo-use` round-trip works on the e_run corpus.
- An `-O0/-O1/-O2/-O3` switch exists and each level is measurably different.
