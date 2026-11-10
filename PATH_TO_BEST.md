# Path to "best" — what it would actually take

"Best language" is not a single property, so this document ranks by what is
achievable, in the order that compounds. Sovren's genuine, defensible advantage
is **target breadth** (40 targets, ~158 backends, self-hosting across all of
them). Everything else is a gap. The strategy that follows from that: **be the
language that is the only one that can build a given thing, and be excellent at
everything that excellent languages are excellent at.**

## Tier 0 — stop the bleeding (do first, cheap, high daily value)

| item | why first |
|---|---|
| **Fix diagnostics.** `err_where()` is a stub; 18 error sites report no location. No source line, column, caret, code, colour, or `help:`. | It is the worst item in the tree, it is user-visible every day, and it makes every other item easier to land. See `DIAGNOSTICS.md`. |
| **`-O0..-O3` flags** | There is currently no way to ask for speed or size. |
| **`--error-format=json`** | Unblocks editors, CI, and LSP later. |
| **Delete the dead platforms** | DONE 2026-10-08: none of the nine exists as a backend (155 drivers globbed, 0 matches). Only doc rows remained; purged. |
| **Named includes instead of line-number slices** | `inc00..inc06` and `px00/px01` are sliced by absolute line number; every edit risks desyncing every consumer. This is the root cause of most patch friction. |

## Tier 1 — finish what is already scoped

| item | status |
|---|---|
| Translation speed (interner + offset descriptors + arena emitter) | measured at 2.6x from baseline, plan on file |
| Register allocation in the backends | the single biggest execution-speed item; 1.84x off C -O2 today |
| PGO | largest execution-speed win per unit of new machinery |

## Tier 2 — make memory safe without giving up bare metal

This is the differentiator that would let sovren claim "best" rather than
"broadest". The target: **memory safety by default on safe targets, zero cost on
bare-metal targets.**

1. `defer` as a keyword (`kdefer.sov` already proves it).
2. Scoped `region:` construct (`arena.sov` already proves it).
3. Bounds-checked `peek`/`poke` and trapping `_sov_list_get` in safe code.
4. A real lexical `unsafe` construct replacing the `# unsafe` comment.
5. An ownership/escape lint, warnings only.
6. Opt-in deferred reference counting for programs that want automatic
   reclamation.

Explicitly **not** a tracing GC by default — wrong for kernels, firmware and
bootloaders, which are core sovren targets.

## Tier 3 — close the type-system gap

In this order, because each depends on the previous:

1. **`enum`** — cheapest, removes the most boilerplate, zero risk.
2. **`match`/`case` as a construct** — `match.sov`/`case.sov` already prove the
   semantics; promoting them is a desugaring like `u_sugar` already does.
3. **`Option`/`Result`** — needs `enum`; turns `return 0` errors into values.
4. **A real type checker** — the prerequisite for everything below.
5. **`generic`** — unlocks typed containers.
6. **`trait`** — unlocks polymorphism.
7. **`closure`/`lambda`** — unlocks first-class functions.
8. **`async`/`await`** — structured concurrency on top of the existing `spawn`.

Do **not** add `trait` or `closure` before the type checker exists; a
half-working feature is worse than none.

## Tier 4 — tooling and ecosystem

Without these, "best" is not credible regardless of language quality:

1. `sovren fmt` — indentation is load-bearing, so formatting is not cosmetic.
2. LSP server — completion, go-to-definition, inline diagnostics.
3. Package manager + manifest + registry, **dependency-free by default**.
4. Doc comments + a doc generator (the 2026-09-24 migration deleted 15,927
   comment lines; that debt is now visible).
5. A tutorial and a language reference.
6. Fuzz harnesses and a sanitizer mode for the compiler itself.

## Tier 5 — the properties nobody else has

Sovren's unique position, and where "best" is actually winnable:

1. **One language, every target, including the ones nobody else supports.**
   Kernel, bootloader, firmware, wasm component, JVM class, EVM contract, eBPF
   program, iOS/Android/Windows/macOS binary — from one source. No other
   language does this.
2. **A self-hosting compiler that reaches a byte-identical fixed point on all
   158 backends.** Very few languages can prove this.
3. **Zero runtime dependency, including on bare metal.**
4. **A stdlib with real crypto** (aes, chacha20, gcm, chachapoly, poly1305,
   ed25519, x25519, sha1/256/512, hkdf, hmac, pbkdf2) with no external crate.
5. **Privacy as a default, not a mode** — no telemetry, no runtime, no
   phone-home, and an `--audit-privacy` flag that proves it.

## The honest ranking of what to do

| priority | item | reason |
|---|---|---|
| 1 | Diagnostics | worst state, cheapest fix, daily value |
| 2 | Register allocation | largest execution-speed gap |
| 3 | PGO | best speed-per-effort |
| 4 | Translation-speed rewrite | already scoped, already 2.6x in |
| 5 | `defer` + regions + bounds checks | memory safety without a GC |
| 6 | `enum` + `match` construct | type system, cheap |
| 7 | Type checker + generics + traits | the long pole |
| 8 | fmt / LSP / packages / docs | credibility |
| 9 | Unique-position polish | where "best" is winnable |

## What "best" would mean concretely

- Fastest *available* on every target it supports, within 1.2x of C `-O2`.
- Memory-safe by default on safe targets, zero-cost on bare metal.
- rustc-class diagnostics with stable codes and JSON output.
- A real type system with enums, generics, traits and pattern matching.
- fmt, LSP, package manager, docs.
- 40+ targets from one source, self-hosting on all of them.
- Reproducible builds, auditable privacy, no telemetry, ever.

That is a multi-year programme. Tier 0 is a few weeks. Tier 1 is a few months.
Tiers 2-3 are the substance. Tiers 4-5 are what make it a language people
choose rather than a language people admire.
