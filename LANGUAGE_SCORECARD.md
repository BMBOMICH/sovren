# Sovren scorecard — rated against other languages, category by category

Scale: **0 = absent, 1 = prototype, 2 = usable, 3 = competitive, 4 = best in class.**
Comparators: Rust, C, C++, Zig, Go, Swift, Python, JS/TS, Java, C#.

## Summary

| category | sovren | best comparator | gap |
|---|---|---|---|
| **Target breadth** | **4** | 2 (C, Zig) | **sovren leads** |
| **Self-hosting** | **4** | 3 (Rust, Zig, Go) | **sovren leads** |
| **Binary lightness** | 3 | 4 (C, Zig) | small |
| **Translation speed** | 2 | 3 (Go, tcc) | measured, plan known |
| **Execution speed** | 1 | 4 (Rust/C++ on LLVM) | **largest gap** |
| **Allocator quality** | 3 | 4 (Zig, Rust) | small |
| **Automatic memory (opt-in)** | **0** | 4 (Rust, Swift, Go) | **absent** |
| **Memory safety** | **0** | 4 (Rust) | **absent** |
| **Type system** | **1** | 4 (Rust, Haskell) | **largest gap** |
| **Generics** | **0** | 4 (Rust, C++, Swift) | absent |
| **Error handling** | 1 | 4 (Rust, Swift) | large |
| **Concurrency** | 2 | 4 (Rust) | no borrow model |
| **Diagnostics** | **1** | 4 (rustc, Elm) | **worst item in the tree** |
| **Stdlib breadth** | 3 | 4 (Python, JS, Rust) | small |
| **Crypto** | 3 | 3 (RustCrypto) | parity |
| **Documentation** | 1 | 4 (Rust, Go) | large |
| **Tooling (fmt/LSP/pkg)** | **0** | 4 (Rust, Go, TS) | absent |
| **Metaprogramming** | **0** | 4 (Rust, Lisp, Zig) | absent |
| **Ecosystem** | **0** | 4 (JS, Python, Rust) | absent |
| **Learnability** | 2 | 4 (Python, Go) | medium |

## Detail

### Target breadth — sovren **4**, best in class
40 target directories, ~158 backends: x86-64, ARM (v5/v7/v7a/armel/armhf/arm64
+ SVE/SVE2/MTE), RISC-V, WASM (browser/emscripten/edge/component), JVM bytecode,
LLVM IR, EVM, eBPF, C#, CIL, DEX, DOS, firmware, Fuchsia, AIX, Android, Apple
(macOS/dylib/arm64), Windows (exe/dll/arm64), C166, EZ80, and kernel ABIs.
No other language ships this many first-class backends. **This is the moat.**

### Self-hosting — sovren **4**
The compiler is written in sovren and rebuilds itself byte-for-byte
(`bootstrap clean`, 159 ok / 0 FAIL). Few languages achieve a clean fixed point;
sovren does it across 158 backends.

### Binary lightness — sovren **3**
Standalone binaries, no runtime dependency, no libc requirement on bare-metal
targets. C and Zig still edge it out on absolute size because they have decades
of size tuning, but sovren is close and has no GC/runtime overhead at all.

### Translation speed — sovren **2**
Measured: 1.185 MB/s expanded vs `sa` at 698.8 MB/s (0.0019x). Improved 2.6x
from the pristine baseline. The remaining work is understood (interner + offset
descriptors + arena emitter) but not done.

### Execution speed — sovren **1**
Measured: sovren's generated loop code is **1.84x slower than C `-O2`** on a
tight byte-sum (1524 vs 2801 MB/s). The cause is structural: the backend is a
stack machine with no register allocation. `peek_i64(lst, 8)` compiled to five
instructions where `mov 8(%rbx),%rax` is one; `_sov_list_add`'s growth path used
six `push`/`pop` pairs to copy one element. Pass 7 landed constant and scaled
displacement folding (~1.10x) but register allocation is untouched.

### Allocator quality — sovren **3**
Size-classed, per-class free lists, page-indexed medium classes, direct-mmap
large class, bump arenas. Genuinely good. Loses to Zig (comptime-configurable,
allocator interface) and Rust (global + arena + custom) on composability.

### Automatic memory — sovren **0**
No GC, no opt-in region construct, no `defer` keyword, no ownership lint.
`arena.sov` and `kdefer.sov` exist as libraries. The default choice (manual) is
*correct* for the target set; the absence of *any* automatic option is the gap.

### Type system — sovren **1**
One machine-word integer, strings as heap byte buffers, lists of raw words.
No enums, no sum types, no generics, no traits, no Option/Result, no
null-safety. `ceval` gives compile-time evaluation of integer expressions only.

### Error handling — sovren **1**
`try`/`except` by task name, plus a global `had_err` flag and `fail()`. Errors
are not values, cannot be propagated, and abort the compile. `err_where()` is a
stub, so 18 error sites report no location at all.

### Concurrency — sovren **2**
`spawn`, `job`, `thread_*`, `mutex`, `channel.sov`, `race.sov`. Real threads
exist. But with no borrow model or `Send`/`Sync` equivalent, data races are
possible and `race.sov` exists to catch them at runtime rather than at compile
time. (Threads also do not function in the current sandbox, which limits
testing.)

### Diagnostics — sovren **1**
See `DIAGNOSTICS.md`. Unlabelled lines, no column, no source echo, no caret, no
codes, no colour, no `help:`, no JSON output, and a stub `err_where`.

### Stdlib breadth — sovren **3**
~190 modules: crypto (aes, chacha20, gcm, chachapoly, poly1305, ed25519,
x25519, sha1/256/512, md5, hkdf, hmac, pbkdf2), data (json, toml, ini, csv,
tsv, base32/64, hex), net (http, httpd, sock, tls, url, urlenc), sys (file,
dir, os, proc, pipe, port, mmio, env, time, date), collections (list, vec,
deque, queue, seq, array, map, dict, set, trie, heap, bitset), graphics
(bmp, image, draw, color, face, kfont8, kdisplay, ksurface), UI (tui, term,
termkit, ui, window, winwin32, winx11, browser), plus kernel support
(kacpi, kblock, kdma, kdriver, kirq, kio, kiommu, kpci, kusb). Breadth is
genuinely strong; depth and docs are not.

### Crypto — sovren **3**
Broad algorithm coverage. No constant-time guarantee, no formal audit, no
side-channel documentation.

### Documentation — sovren **1**
The 2026-09-24 migration **removed 15,927 comment lines**. Planning docs exist
(`SPEED_ARCHITECTURE.md`, `NEXT_PHASE_PLAN.md`, `COMPILER_COMPLETENESS.md`) but
there is no language reference, no stdlib reference, and no tutorial.

### Tooling — sovren **0**
No formatter, no LSP, no package manager, no manifest, no doc generator. The
only tooling is `tools/speed_gate.py` and `tools/completeness.py`.

### Metaprogramming — sovren **0**
The sugar pass (`u_sugar`) is powerful but compiler-internal. Users cannot
extend the syntax or write macros.

### Ecosystem — sovren **0**
No package registry, no third-party libraries, no community.

## Where sovren wins outright

1. **Target breadth** — 40 targets / 158 backends, no close competitor.
2. **Self-hosting across all of them** — a clean byte-identical fixed point.
3. **No runtime dependency** — bare-metal, firmware, kernels, bootloaders.
4. **Crypto breadth in the stdlib** — most languages need external crates.

## Where sovren loses outright

1. **Execution speed** — 1.84x off C -O2 and no register allocator.
2. **Diagnostics** — the worst item in the tree, and the cheapest to fix.
3. **Type system** — no generics, no enums, no traits, no sum types.
4. **Memory safety** — no ownership, no opt-in automatic memory.
5. **Tooling and ecosystem** — nothing.
