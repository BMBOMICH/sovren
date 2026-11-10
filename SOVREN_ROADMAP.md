# Sovren — master roadmap and direct answers

This is the index. Each section below is a separate document in this folder,
written against the tree as it stands on 2026-09-30. Everything here is scoped
to be *done after* the translation-speed goal (all compilers matching `sa`) is
met, as agreed.

| document | covers |
|---|---|
| [RUNTIME_MODEL.md](RUNTIME_MODEL.md) | allocator, GC, what we actually use, is it automatic |
| [DIAGNOSTICS.md](DIAGNOSTICS.md) | error/warning message quality, current state, how to make them the best |
| [SOVREN_AUDIT.md](SOVREN_AUDIT.md) | add / improve / remove / merge / split / rename / relocate |
| [LANGUAGE_GAPS.md](LANGUAGE_GAPS.md) | what other languages have that sovren does not |
| [LANGUAGE_SCORECARD.md](LANGUAGE_SCORECARD.md) | sovren rated against other languages, category by category |
| [PATH_TO_BEST.md](PATH_TO_BEST.md) | everything needed to make sovren "the best" language |
| [PATH_TO_FASTEST.md](PATH_TO_FASTEST.md) | fastest in execution, everywhere |
| [PATH_TO_LIGHTEST.md](PATH_TO_LIGHTEST.md) | lightest binary, lightest runtime, lightest build |
| [PATH_TO_PRIVATE.md](PATH_TO_PRIVATE.md) | most private language and toolchain |
| [PATH_TO_SECURE.md](PATH_TO_SECURE.md) | most secure language and toolchain |

---

## Direct answers to the questions asked

### 1. What allocator or GC do we use? Is it the best? Is it automatic?

**We use a manual, size-classed allocator. There is no GC.** Verified in
`runtime.sov`:

| component | where | what it is |
|---|---|---|
| `rt_init` / `rt_heap` | `runtime.sov:133` | bootstrap of the metadata region |
| `_sov_small_region` / `_sov_small_try` / `_sov_alloc_small` / `_sov_free_small` | `runtime.sov:137-200` | 16-byte-unit size classes, per-class free list, 2 MB regions |
| `_sov_med_region` / `_sov_med_try` / `_sov_alloc_med` / `_sov_free_med` | `runtime.sov:206-262` | 4096-byte page classes, free list indexed by page |
| `_sov_alloc_large` / `_sov_free_large` | `runtime.sov:266+` | direct `mmap` |
| `_sov_fast_alloc` / `_sov_heap_alloc` / `_sov_alloc` | `runtime.sov:290+` | fast path + general path |
| `_sov_arena_new` / `_sov_arena_alloc` / `_sov_arena_destroy` | `runtime.sov:422-446` | bump arena, opt-in |
| `_sov_free` / `_sov_realloc` / `_sov_heap_wipe` | `runtime.sov:351/382/...` | manual free, manual realloc, bulk wipe |

**Is it automatic? No.** `_sov_free` is manual. There is no tracing collector, no
reference counting, no finaliser, no cycle detection anywhere in `runtime.sov`
(grep for `gc`, `mark`, `sweep`, `collect` matches only `g_argc`, a false
positive). Memory that is not explicitly freed is reclaimed only by process exit
or `_sov_heap_wipe`.

**Is it the best?** For what sovren is trying to be — a systems language that
emits standalone binaries with no runtime dependency — **manual allocation is
the right default and what you want.** A tracing GC costs a runtime, a
write barrier on every pointer store, and pauses; it is the wrong default for
kernels, bootloaders, firmware and `#![no_std]`-style targets, and sovren
targets all of those. So: correct choice, and it matches C, Rust and Zig.

The gap is not the default, it is that **there is no opt-in automatic option at
all.** See [RUNTIME_MODEL.md](RUNTIME_MODEL.md) for what to add: an opt-in
arena/region mode that is automatic-by-scope, an optional deferred reference
count, and a `defer`-driven ownership lint. `kdefer.sov` and `arena.sov` already
exist as libraries, so the pieces are there — they are just not wired into the
language as a mode.

### 2. Do we have the best error/warning messages?

**No, and this is the single largest quality gap in the toolchain.** Measured
live, compiling a program with one undefined name:

```
Compiling
/tmp/w/e1.sov
note: compiler sees raw memory/io sites without unsafe markers; library/sbuf.sov covers checked buffers (count follows)
7
Error: no such name
undefined_thing
/tmp/w/e1.sov
4
Warning: locals
main
2
1
```

Every piece of information is on its own unlabelled line. There is no source
line, no column, no caret/underline, no colour, no error code, no `help:`
suggestion on the main path, and no grouping. `err_where()` — the function that
is supposed to attach a location — is a **stub**: its entire body is
`had_err: 1` then `return` (`library/inc/inc03.sov:60`), and 18 call sites use
it. Rust, Elm, and even GCC-10+ are dramatically better than this.

Full analysis and the concrete plan to make them the best in class:
[DIAGNOSTICS.md](DIAGNOSTICS.md). The short version: fix the `err_where` stub,
add a column and source-line echo, add stable error codes, add `help:` hints,
and add colour + `--error-format=json`.

### 3. What is the fastest compiler in execution speed? LLVM or what?

**There is no single fastest compiler, and the premise that one exists is
wrong.** Measured head-to-head, GCC and LLVM/Clang trade wins workload by
workload and neither dominates:

- A 10-case `-O3` C++ batch had **GCC ahead more often**, but Clang won the
  branch-heavy case by 21.3% and small-sort by 9.6%, while GCC won 2D stencil by
  24.3% and strided access by 4.2%.
- Other surveys report the opposite split on the same code. The honest summary
  from that benchmark: *"the safest conclusion is still to benchmark the real
  code you care about before choosing a winner."*
- On compile *speed* (a different question) GCC currently beats Clang on the
  Linux kernel, even with LLVM built with LTO+PGO.

**What actually determines execution speed is not the compiler brand, it is
which optimisations you run, in this order:**

1. **Register allocation** — called "the most important optimisation performed
   by the compiler", because a register is <1 cycle and DRAM is hundreds. This
   is exactly where sovren is weakest today: the backend is a stack machine that
   spills via `push`/`pop` and materialises constants with `push $n; pop %rax`.
2. **Instruction selection and memory-operand folding** — partially landed
   (Pass 7).
3. **PGO** — profile-guided inlining, block layout, and register allocation.
   Typically the largest single win available, and it needs no new backend
   machinery, only a profile file format and a recompile mode.
4. **LTO / whole-program view** — needs cross-module inlining.
5. **Auto-vectorisation** — high ceiling (a 1.60x speedup from picking the right
   vectorisation/interleaving factor pair in one study, and a 5.57x *slowdown*
   from picking the wrong one), so it needs a cost model, not just a flag.

**Does that mean we can add execution stuff to `sa` too, not only translation
stuff?** Yes, and it is worth separating two things:

- **`sa` is the assembler.** It translates assembly text to machine code. It
  *can* legitimately own execution-speed work that is local to an instruction
  stream: peephole rewriting, instruction scheduling, branch-target alignment,
  jump-chain shortening, and redundant-load elimination. Those are real
  execution-speed wins and they belong in an assembler.
- **`sa` is not in the execution path of sovren-built binaries.** Sovren's
  compilers emit machine code bytes directly (`emit:`/`emit4:`/`emit8:` in
  `library/cx86.sov`), so a binary built by `compilers/linux/compiler` never
  touches `sa`. Improving `sa` therefore improves `sa`-built programs, not
  sovren-compiled ones.
- **Conclusion:** the execution-speed work that matters for sovren's own output
  belongs in the compiler backends (`cx86.sov`, `carm.sov`, …), and `sa` is a
  separate, parallel track. Both are worth doing; they do not substitute for
  each other. See [PATH_TO_FASTEST.md](PATH_TO_FASTEST.md).

### 4. Is only execution speed left?

No. Translation speed is the current goal and it is close in *kind* (the
front-end rewrite), but three things are in worse shape than execution speed:

| area | state |
|---|---|
| **Diagnostics** | `err_where()` is a stub; no source line, column, caret, codes, colour or `help:`. This is the worst item in the tree. |
| **Memory safety story** | manual allocation with no opt-in automatic mode, no ownership lint, `# unsafe` gate is comment-based |
| **Language surface** | no enum / trait / generic / closure / lambda / bitfield / pattern-match construct |

Execution speed is *large* but it is at least measured and has a known plan.
Diagnostics and the type surface are unmeasured and have no plan on file. Fix
diagnostics first — it is cheap, it is user-visible every single day, and it
makes every other item on this list easier to land.

---

## Suggested order

1. **Diagnostics** (`DIAGNOSTICS.md`) — cheap, high daily value, unblocks everything else.
2. **Finish translation speed** — the front-end rewrite (interner + offset descriptors + arena emitter).
3. **Register allocation** in the backends — the single biggest execution-speed item.
4. **PGO** — largest execution-speed win per unit of new machinery.
5. **Opt-in automatic memory** (`RUNTIME_MODEL.md`).
6. **Type surface** — enum, trait, generic, closure (`LANGUAGE_GAPS.md`).
7. **Security / privacy hardening** (`PATH_TO_SECURE.md`, `PATH_TO_PRIVATE.md`).
8. **Lightness** (`PATH_TO_LIGHTEST.md`).
