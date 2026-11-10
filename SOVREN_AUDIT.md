# Sovren audit — add / improve / remove / merge / split / rename / relocate

Everything below is grounded in the tree as of 2026-09-30. `X` marks items with
a concrete, known-good first step.

## ADD

| # | item | why | where |
|---|---|---|---|
| X | `err_where()` real implementation | it is a stub; 18 sites depend on it | `library/inc/inc03.sov:60` |
| X | column tracking in the lexer | no diagnostic can have a caret without it | `lines_of`/`cut`/`look` in `library/inc/` |
| X | stable diagnostic codes | errors are undocumented free text | new `library/diag.sov` |
| X | `--error-format=json` | editor + CI integration | `compilers/*/compiler*.sov` main |
| X | scoped `region:` construct | makes allocation automatic by scope | `library/arena.sov` already exists |
| X | `defer` as a keyword | deterministic automatic reclamation | `kdefer.sov` already exists |
| X | `enum` construct | 0 hits in the whole library; everyone hand-rolls it | new surface form + `u_sugar` |
| X | `trait` construct | no polymorphism story today | new |
| X | `generic` / type parameters | no parametric polymorphism; every container is `i64`-only | new |
| X | closure / lambda | 0 hits; no first-class function values | new |
| X | `match` / `case` as a **construct** | `match.sov` and `case.sov` exist as libraries, which is the wrong layer | promote to syntax |
| X | register allocator in the x86 backend | backend is a stack machine; 1.84x off C -O2 | `library/cx86.sov` |
| X | PGO mode | largest execution-speed win per unit of new machinery | new `--pgo-generate` / `--pgo-use` |
| X | interner for token strings | 435 `_sov_str_eq` call sites, all on 1-3 char operands | `library/inc/` |
| X | arena/byte-buffer emitter | 351 `str_cat` sites, 1.76M allocations per compile | `library/inc/` |
| X | `-O0/-O1/-O2/-O3` flags | there is no optimisation-level control at all | compiler mains |
| X | `--emit-asm` / `--emit-llvm`-style inspection | cannot inspect what the backend produced | compiler mains |
| X | ownership/escape **lint** (warnings only) | cheapest path to a memory-safety story | new analysis pass |
| X | `NO_COLOR` / `isatty` gating | diagnostics will need colour | new |
| X | fuzz target for the front end | `fuzzlib.sov` exists but is not wired to a harness | `tools/` |
| X | property tests for the allocator | free-list/carve correctness is untested | `tests/` |
|  | SIMD abstraction layer | `simd` appears twice in the whole tree, both incidental | new |
|  | `async`/`await` or structured concurrency | `async` appears twice, both incidental; only raw `spawn` exists | new |
|  | `atomic` as a keyword | `atomic_load`/`atomic_store` exist only in kernel code | new |
|  | fixed-width integer type names (`i8/i16/i32/u64`) | only `int`-ish values today | new |
|  | `bitfield` construct | 0 hits; bit packing is hand-written everywhere | new |
|  | `Option`/`Result` in the type system | `result` appears 6 times as a word, not as a type | new |
|  | language-level test attribute | tests live in a separate `tests/run.sov` harness | new |
|  | package manager / manifest | no dependency story beyond `use <lib>` | new |
|  | LSP server | no editor integration at all | new |
|  | formatter (`sovren fmt`) | no canonical formatting; indentation is load-bearing | new |

## IMPROVE

| # | item | current | target |
|---|---|---|---|
| X | diagnostics | unlabelled lines, no source line/col/caret | rustc-class, see `DIAGNOSTICS.md` |
| X | x86 codegen | stack machine, `push $n; pop %rax`, spills via `push`/`pop` | register allocation + constant folding (Pass 7 landed part of this) |
| X | front-end allocation | 1,759,867 allocations / 147 KB input | offset descriptors + interner + arena emitter |
| X | `_sov_str_eq` | 11.8% of profile, 435 sites, all 1-3 char operands | delete the calls via interning |
| X | compile-time self-consistency | 3-stage bootstrap is manual | one command, verified fixed point |
| X | `tests/run.sov` | 224 passed / 3 failed, 3 pre-existing failures | 0 failures, more cases |
| X | library doc coverage | ~190 modules, almost none documented | every public task has a doc comment |
| X | error recovery | first error aborts (`had_err` + `fail()`) | recover and report several |
| X | `use` resolution | 3 hardcoded fallback paths | explicit `-I` search path |
| X | unsafe gate | `# unsafe` is a comment the compiler greps for | a real attribute with a manifest |

## REMOVE

The dead platforms (ia64, alpha, tru64, irix, osf, windows-ce, windows-phone,
arm_wince, vax) are already gone. Verified 2026-10-08: all 155 drivers under
`compilers/` were globbed recursively and none of the nine names appears as a
directory or a `compiler.sov`; the only references left in the tree were the
documentation rows removed here. The earlier removal is recorded in
`IMPLEMENTATION_LEDGER.md`.

Also candidates for removal, to be confirmed case by case:

| item | reason |
|---|---|
| `library/ktest_a.sov` … `ktest_n.sov` (14 files) | kernel test scaffolding, not language surface |
| `library/chat.sov`, `discord.sov`, `telegram.sov`, `invite.sov`, `presence.sov`, `feed.sov`, `room.sov`, `notify.sov`, `site.sov` | application demos, not a language standard library |
| `library/roman.sov`, `calc.sov`, `game.sov`, `face.sov`, `draw.sov` | demos |
| `sovren-dbg` | a debug build artefact committed into the tree |
| duplicate `blank:`/globals blocks in `cx86.sov` | `blank:` is defined twice (lines ~2083 and ~2740); this is fragile |
| the `err_where()` stub | replace with a real implementation, then delete the stub |
| `# unsafe` comment convention | replace with a real unsafe marker |

## MERGE

| from | into | why |
|---|---|---|
| `library/string.sov` + `library/inc/inc02.sov` string helpers | one string module | string ops are split across a library and the compiler pool |
| `library/list.sov`, `vec.sov`, `deque.sov`, `queue.sov`, `seq.sov`, `array.sov` | one collections module with a shared core | five near-identical dynamic-array implementations |
| `library/set.sov` + `map.sov` + `dict.sov` + `hash.sov` | one hash-map module | four overlapping hash tables |
| `library/sha1/sha256/sha512/md5.sov` | one hash module | same structure, four times |
| `library/aes.sov`, `chacha20.sov`, `gcm.sov`, `chachapoly.sov`, `poly1305.sov` | one cipher module | shared block/stream scaffolding |
| `library/json.sov` + `jsonp.sov` + `toml.sov` + `ini.sov` + `csv.sov` + `tsv.sov` | one serialisation module | five parsers with the same shape |
| `library/winapi.sov`, `winwin32.sov`, `winx11.sov`, `browser.sov`, `window.sov`, `term.sov`, `termkit.sov`, `tui.sov`, `ui.sov` | platform-ui modules grouped by platform | 9 UI modules, unclear boundaries |
| `library/ktest_*.sov` | one kernel-test module | 14 files, one purpose |
| `library/sov*_abi.sov` (7 files) | one ABI module | 7 ABI description files |

## SPLIT

| file | problem | action |
|---|---|---|
| `library/cx86.sov` (3000 lines) | one file holds the whole x86 backend: lexer, expression evaluator, codegen tables, optimisers, kernel support | split into `cx86/` — lexer, expr, emit, opt, kernel |
| `library/ccore.sov` (702 lines) | mixes core language semantics with the sugar expander | split core semantics from `u_sugar` |
| `runtime.sov` (~1050 lines) | allocator + strings + IO + lists + interning in one file | split into `runtime/alloc`, `runtime/str`, `runtime/io`, `runtime/list` |
| `compilers/linux/compiler.sov` (734 lines, 142 includes) | a single monolithic driver | split into driver / passes / backends |
| `library/inc/inc00..inc06.sov` | the shared pool is sliced by absolute line number — any edit desyncs every consumer | convert to named includes (`include <name>`) so slices are not line-coupled |
| `SPEED_ARCHITECTURE.md` / `NEXT_PHASE_PLAN.md` | two overlapping planning docs | merge into one roadmap |

## RENAME

| current | proposed | why |
|---|---|---|
| `_sov_*` runtime functions | keep, but document as the private runtime ABI | the `_sov_` prefix is currently the only signal that these are not user API |
| `try_mem` / `try_scaled_mem` / `try_opt_while` / `try_patfill_while` / `try_def_peek` / `try_lea_arg` / `try_sel_if` | `mem_fold`, `mem_fold_dispatch`, … | `try_*` reads like exception handling; these are optimisation attempts |
| `u_scan` / `u_prep` / `u_sugar` | `lex` / `prep` / `desugar` | `u_` prefix is unexplained |
| `sg_*` (sugar) family | `sugar_*` | `sg_` collides visually with `sg_ind`/`sg_sp` |
| `inc00..inc06` | semantic names | numbered includes are the single biggest maintenance hazard in the tree |
| `px00` / `px01` | semantic names | same |
| `bo_step` | `bootstrap_step` | fine internally, unclear to newcomers |
| `cr_*` (corpus/test helpers) | `test_*` | `cr_` is used for both corpus and cross-reference |

## RELOCATE

| from | to | why |
|---|---|---|
| `tools/speed_gate.py`, `tools/completeness.py` | `tools/` is right, but they should be documented in one `tools/README.md` | discoverability |
| `/home/user/tD/*` scratch (prof9/prof10.c, agg.py, ident.py, patch_*.py) | `tools/profiling/` and `tools/patches/` | 25+ scripts in a scratch dir outside the repo |
| `library/suite.sov` | `tests/suite.sov` | it is a test, not a library |
| `library/testrun.sov`, `test.sov`, `run.sov`, `check.sov`, `assert.sov`, `fuzzlib.sov` | `tests/` | six test-support modules living in `library/` |
| `library/bench.sov`, `profile.sov` | `tools/` | benchmarking is a tool, not a language feature |
| dead-platform backends (see REMOVE) | delete | they are maintained at a cost with no user |
| `SPEED_ARCHITECTURE.md` | `docs/` | planning docs mixed with language docs at the root |
