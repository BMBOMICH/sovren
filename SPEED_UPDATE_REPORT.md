# PURGE NOTICE (2026-10-25, Track 0.0)
All cache machinery described below (artifact cache, .prebuilt, .ac/.ac.bin, .plk, .lsug/.sug/runtime.sug, state dumps, deep/.deepoc replay, prefix replay, cache flags) has been **fully removed from this tree** in Track 0.0; every compile is cold and no persisted intermediate can ever be produced again. Sections below are retained as dated history. See `work/attic/purge20261025/PURGE_REPORT.md`.

# Sovren v55 — rebuild repairs, cache correctness, and measured speed

**Date:** 2026-10-14 · **Measured host:** Linux x86-64 · **Status: partial completion, not SA parity**

## Bottom line

- **All 102 previously failing driver-source builds are repaired.** All **155/155** drivers now build twice with identical bytes and have been installed as Linux-hosted compiler executables.
- **930 probe-artifact comparisons match the supplied drivers:** 155 × the original two fixtures, plus 155 × four additional probes. Matching existing output is regression evidence, **not** proof that each backend implements the language correctly.
- **80/80 cache/rebuild regression checks**, **4/4 nested-dependency cache checks**, **12/12 auxiliary-artifact mode checks**, **11/11 real edit-matrix cases**, **219 sugar differentials**, and **6 large lexical-boundary cases** pass. The Linux compiler reproduces itself byte-for-byte.
- The 90-byte native fingerprint helper passed **262,404 differential/single-byte-sensitivity checks**, including guard-page boundaries and every length from 0 through 65,536.
- **SA parity is not achieved. All 20 measured parity cells fail the strict acceptance gate.** All fourteen workstreams are **not** complete.

**Installed Linux compiler SHA-256:**
`cd214ed8712d8a130f05b9ea18839df9fe3287dc719ed190af51cc6608993f24`

**Frozen, unchanged SA reference SHA-256:**
`4db5fa04d063e4869a6cf9d44a63bf054cb965b5014dd80afd872b463527f63a`

The full updated trees, runnable checks, source patch, and evidence are in `sovren-speed-update.tar.gz`. The package checksum is in the separate `work/package-sha256.txt` file.

## What changed

### 1. Source-generation and interface repairs

The previous result was 53 successful builds and 102 failures. The first migration pass reached 126; the final pass reaches 155.

- Expanded incompatible compact syntax in 73 driver sources using the certified sugar transform. This repairs source compatibility; it does not claim the general nested-arrow language issue has been eliminated.
- Added missing shared state declarations where compiler diagnostics identified them.
- Corrected the ARM `fn_locs` duplication by repairing the **1-based include slice**, not by shifting the shared include files.
- Moved x86-only incremental machine-code re-emission out of the shared deep-replay module and into `cx86.sov`. ARM explicitly declines that optional optimization and falls back rather than emitting x86 instructions.
- Added older-driver adapters for profiling and checked cold retry. No fake code-generation implementations were added to make builds pass.
- Preserved the **2,039-line `inc00.sov` invariant** and the numbered include-slice structure.

One supplied target, `apple/macos`, had no standalone `compiler` file; its supplied `compiler.sov.ac.bin` served as the original comparison binary. That distinction is recorded in the fleet evidence. It now has a rebuilt standalone compiler.

### 2. False success, stale caches, and failed replay

- Replay completion now checks compile errors **both before and after the artifact writer**, removes stale destinations, and requires a fresh nonempty output before success/cache storage.
- Failed replay retries with replay disabled; the retry argv allocation is sized from `argc`, rather than fixed at 512 bytes. Wait errors and child failures are preserved.
- **x86ins no longer exits successfully without an artifact.** Its source is still rejected; that rejection is not reported as a successful compilation.
- Empty sugar generation and failed flattened-output writes fail explicitly.
- Repeated Linux `--bytes` and `--debug` builds now regenerate every requested auxiliary output. Artifact-only cache/early-replay routes are bypassed for those modes; the scalar negative control lost `.bin`/`.map` files on the second build.
- Fixed a real fingerprint flaw: masking a mixed 64-bit word to 56 bits discarded every eighth input byte. Same-size edits at those byte positions could silently return an older program. The corrected hash mixes both 32-bit halves, and checks cover every byte alignment.
- Compiler and artifact fingerprints cover the whole file, not just the first/last blocks.
- Retired the unchecked `.prebuilt` shortcut and duplicated per-driver artifact-cache routes. Shared artifact reuse now captures/checks the source identity, validates copied artifact contents, and restores executable permissions.
- Whole-artifact reuse conservatively declines external/implicit runtime dependencies rather than assuming a complete dependency key.
- Library/user sugar caches whose parent expands `include` files are declined because the old header bound only the parent file. The negative control returned stale `3`; the repaired compiler correctly returns `8` after the included child changes.
- Deep/state snapshots carry content-integrity sidecars. Readers reject old unchecked snapshots, validate bounds/counts, and fall back on damaged optional state. These fingerprints detect accidental corruption; they are **not authentication** against a malicious cache author.

New Linux switches:

```sh
./compilers/linux/compiler program.sov -o program --uncached
./compilers/linux/compiler program.sov -o program --no-replay
```

`--uncached` bypasses automatic compiler cache reuse/writes, including library/runtime sugar, artifact, state, deep and prefix paths. It does **not** flush OS page caches. Explicit cache-output commands such as `--mksug` still create the output the caller requested. `--no-replay` disables state/deep/prefix replay, not every independent cache layer.

### 3. Measured fingerprint optimization

A checked native implementation accelerates the now-correct fingerprint calculation. The table compares the final compiler with the retained **scalar-hash v55 checkpoint**, on import-free generated workloads; it is **not a blanket v54-to-v55 speed claim**. That checkpoint is retained for the experiment, not as a recommended release.

25 interleaved paired samples per cell; all compared artifact bytes matched. Ratios are candidate/baseline medians of paired observations; lower is better.

| Reachable functions | Mode | Scalar median ms | Final median ms | Paired ratio | Bootstrap 95% interval |
|---:|---|---:|---:|---:|---|
| 1 | uncached | 1.164 | 1.176 | 0.994 | 0.981–1.022 |
| 1 | identical | 2.799 | 1.152 | 0.415 | 0.402–0.420 |
| 1 | edited | 4.778 | 2.314 | 0.483 | 0.475–0.488 |
| 512 | uncached | 7.814 | 8.145 | 1.025 | 0.997–1.049 |
| 512 | identical | 3.127 | 1.427 | 0.435 | 0.425–0.466 |
| 512 | edited | 11.776 | 9.212 | 0.764 | 0.760–0.800 |
| 2048 | uncached | 22.638 | 22.871 | 1.002 | 0.970–1.033 |
| 2048 | identical | 5.577 | 3.017 | 0.542 | 0.491–0.568 |
| 2048 | edited | 77.306 | 68.238 | 0.849 | 0.830–0.883 |

The fully uncached rows are essentially neutral. The demonstrated improvement is primarily in identical/edited rebuild paths that fingerprint data. This does not remove the frontend, name-resolution, or emission costs on large reachable programs.

## The executable SA parity gate

`parity_gate.py` generates matched observable tasks for Sovren and SA, executes every generated function, validates each artifact's exit code, and times fresh processes including artifact creation. End-to-end rows also include program execution. No missing artifact, rejected input, or incorrect runtime result can count as a speed success.

Four sizes × five modes, **15 retained samples per cell**. Fixed acceptance thresholds: the upper 95% paired latency-ratio bound must be ≤1.0 and the lower throughput-ratio bound ≥1.0. Different languages have different source sizes: source-byte throughput is diagnostic, not an equal-work proof. Shared-host timing has noise; raw samples and confidence intervals are retained.

| Functions | Mode | Sovren median ms | SA median ms | Paired latency ratio | Gate |
|---:|---|---:|---:|---:|---|
| 1 | fresh-application | 1.951 | 0.326 | 5.75× | FAIL |
| 1 | fully-uncached | 1.071 | 0.316 | 3.46× | FAIL |
| 1 | identical | 1.170 | 0.390 | 3.00× | FAIL |
| 1 | edited-function | 2.481 | 0.393 | 6.43× | FAIL |
| 1 | end-to-end | 1.292 | 0.492 | 2.61× | FAIL |
| 64 | fresh-application | 2.634 | 0.552 | 4.73× | FAIL |
| 64 | fully-uncached | 1.809 | 0.529 | 3.49× | FAIL |
| 64 | identical | 1.092 | 0.506 | 2.13× | FAIL |
| 64 | edited-function | 2.964 | 0.532 | 5.57× | FAIL |
| 64 | end-to-end | 2.069 | 0.736 | 2.83× | FAIL |
| 512 | fresh-application | 8.125 | 1.030 | 7.92× | FAIL |
| 512 | fully-uncached | 7.262 | 1.118 | 6.50× | FAIL |
| 512 | identical | 1.319 | 0.971 | 1.35× | FAIL |
| 512 | edited-function | 10.041 | 1.333 | 8.41× | FAIL |
| 512 | end-to-end | 7.573 | 1.395 | 5.49× | FAIL |
| 2048 | fresh-application | 61.498 | 1.626 | 37.72× | FAIL |
| 2048 | fully-uncached | 30.542 | 2.118 | 14.50× | FAIL |
| 2048 | identical | 2.870 | 2.296 | 1.32× | FAIL |
| 2048 | edited-function | 80.292 | 1.920 | 43.76× | FAIL |
| 2048 | end-to-end | 26.621 | 2.017 | 13.18× | FAIL |

There is **no universal speed factor or parity result** here. These are Linux-host native-output workload pairs, not a certification of the other targets, operating systems, filesystems, or complete language semantics.

## Profiling and scaling

13 workload/mode cases, three samples each, all produced fresh artifacts. Workloads include fully reachable expression/call-heavy programs, strings, library-heavy code, a 64-file dependency graph, the compiler, mostly-dead large source, and flat/sugar/bytes modes.

Peak RSS is measured by a small C fork/exec supervisor, avoiding the Python launcher's pre-exec memory floor. Profile wall times include the supervisor and diagnostic output, so do not substitute them for the parity benchmark times. Phase stamps are intervals, not exclusive per-function costs. No instruction-level profiler or full allocation trace was available.

| Workload | Median profile ms | Peak compiler RSS KiB |
|---|---:|---:|
| reachable-32 | 3.546 | 2392 |
| reachable-512 | 13.333 | 7092 |
| reachable-2048 | 43.405 | 18000 |
| reachable-8192 | 142.136 | 51312 |
| library-heavy | 67.126 | 20688 |
| compiler-large-dependencies | 188.848 | 45708 |
| mostly-dead-819KB | 55.004 | 17472 |
| startup-hello | 2.652 | 1876 |
| strings-all-reachable | 17.198 | 8848 |
| 64-source-dependencies | 3.537 | 2988 |
| --flat | 1.613 | 792 |
| --mksug | 1.590 | 868 |
| --bytes | 2.226 | 1872 |

The phase evidence still shows substantial loading/sugar/parsing work and nontrivial emission time. No speculative name-table rewrite, blanket dispatch rewrite, or unmeasured fork-threshold widening was landed.

## Backend semantics: separate from rebuild success

The census uses expanded source, output-container inspection, four accepted program probes, and explicit execution where available:

| Mechanism | Drivers | What this means |
|---|---:|---|
| Shared full frontend + native backend | 30 | Uses the shared frontend; full language/platform correctness is not certified. |
| Compile-time evaluator + format emitter | 86 | Evaluates/bakes behavior while producing the target format; not equivalent to full runtime code generation. |
| Transpiler/text emitter | 31 | Requires a separate downstream toolchain and semantic checks. |
| Unclassified/partial writer | 8 | No full-language performance claim is allowed. |

**62 drivers emit the same artifact for all four probes.** That is a measured collapse warning, not a proof that every possible program is ignored. All four-probe artifacts also match the supplied original drivers: these limitations are pre-existing, not hidden rebuild regressions. Historical documentation claiming near-universal program dependence is not accepted as current evidence.

The native Linux dynamic-input probe prints `1` with no extra arguments and `3` with two arguments. It performs actual runtime computation.

The C route was tested end-to-end: C generation → host C compiler → execution. The loop should print `45`; the resulting executable prints **`0`** because the generated C omits the loop. Thus that pipeline **fails semantic acceptance**, even though both translation and the C compiler exit successfully. It receives no parity credit.

All **155 rebuilt driver executables themselves are ELF machine 62 (Linux-host x86-64 tools)**. Generating ARM, PE, Mach-O, or other output does not demonstrate that the compiler runs natively on those hosts. No real Windows/macOS/ARM-host measurements or foreign-target execution were performed in this turn.

## The thirteen source rejections

The direct suite has **21 byte-exact successful artifacts and 13 matching pre-existing rejections**. Diagnostics are classified separately in `source-rejections.json`:

- Seven kernel/driver fixtures: task-indentation diagnostics in their expanded input.
- `macos-check`: unresolved names.
- `pbtest`: missing `snew` task.
- `security`: rejected `string` line.
- `windows-run`: missing `x_set_cmdline` task.
- `x86raw`: missing flag-query tasks.
- `x86ins`: duplicate `damage_note` definitions and unresolved names.

These are diagnostic categories, not claims that every root cause has been fully determined or fixed. They are excluded from successful translation timing.

## Cache refresh and prefix quarantine

Refreshed **213 library sugar caches plus runtime sugar**. Removed about **9.79 MB** of obsolete compiler-source sidecars after preserving their original comparison provenance.

Fresh prefix snapshots passed integrity checks, but the prefix-learn command exited 1 after removing the stub main. A runtime allocation probe produced `42` on both warm and cold paths, **but their artifacts differed**. Artifact difference alone does not prove wrong semantics. Nevertheless, the strict byte-equivalence release policy did not certify this optional path, so the snapshots were **quarantined** rather than silently shipped as verified. Ordinary translation and other checked cache paths remain available. Prefix replay performance is therefore still unfinished.

## Status of all fourteen requested workstreams

| # | Workstream | Actual outcome this turn |
|---:|---|---|
| 1 | Quantitative parity gates | Implemented and run for 20 Linux-native cells; 0 pass. Other populations/hosts remain unmeasured. |
| 2 | Repair 102 rebuild failures | Completed for source rebuilds: 155/155 reproducible, installed; six-fixture differential evidence retained. |
| 3 | Correctness and false successes | Fixed replay/no-output paths, hash blindness, dependency cache staleness, executable cache outputs, and legacy gate weaknesses. Rejections remain explicitly classified. |
| 4 | Representative profiling | Added reachable/library/string/dependency/mode workloads and RSS/phase measurements. Instruction/allocation-level profiling remains open. |
| 5 | Repeated text/materialization work | Retired duplicate unchecked cache paths and retained v54 representation reuse. A complete reduced-pass frontend was not implemented. |
| 6 | Name resolution/reachability | Reachable workloads now expose this cost; no new validated name-resolution redesign was landed. |
| 7 | Emission/native helpers | Added and fuzzed the native fingerprint helper, bootstrapped to a fixed point. Broader codegen/relocation optimization remains open. |
| 8 | Startup/scaling/memory | Measured and improved checked rebuild overhead; large-input scaling and peak RSS recorded. Universal startup/scaling parity is not achieved. |
| 9 | Safe parallel splitting | Six boundary/newline differential cases pass; limits unchanged. Worker-failure injection and worker-count scaling remain open. |
| 10 | Edited rebuilds | Verified actual comments/body/signature/global/import edits, child-only changes, cache corruption, compiler identity and repeated edits. Nested-cache negative controls reproduce the old bugs. |
| 11 | Broader identical rebuilds | Checked integrity, permissions and 16 concurrent builds to distinct outputs. Other filesystems, same-output concurrency, and other hosts are not certified. |
| 12 | Separate semantic populations | Census completed; collapse warnings and a failing C end-to-end test exposed. Missing language semantics were not implemented across the fleet. |
| 13 | Host portability | Host/target distinction audited. Real foreign-host ports, ABI validation and measurements remain blocked/unperformed. |
| 14 | Deployment and continuous gates | All 155 host drivers installed; sugar caches refreshed; prefix quarantined; local correctness runner passes; CI workflow added but not executed remotely. Parity gate remains red. |

**Therefore: the rebuild-repair subtask is complete, but “all fourteen done” and “matches SA everywhere” would be false.**

## Reproduce

From the `sovren` directory on a Linux x86-64 host with Python 3 and a C compiler:

```sh
# Correctness, self-host fixed point, fleet differential, native fuzzing:
sh work/session20261014/run_checks.sh

# Also require strict measured SA parity (currently exits nonzero):
sh work/session20261014/run_checks.sh --parity

# Individual measurements:
python3 work/session20261014/parity_gate.py --compiler work/speed/v55.bin
python3 work/session20261014/profile_v55.py
python3 work/session20261014/native_hash_benchmark.py --baseline work/speed/v55-scalar.bin

# Rebuild the Linux compiler to a fixed point and refresh checked caches:
sh work/speed/mkcompiler.sh

# Rebuild the fleet against the installed reference; installation is all-pass only:
python3 work/session20261014/verify_fleet.py --builder work/speed/v55.bin --install
```

The aggregate `mkcompiler.sh` script and legacy `validate.py`/`churn_batt.py` were hardened but not run end-to-end; component bootstrap, refresh, and regression operations were executed separately. The full new correctness runner **was** executed successfully. Hosted CI was not dispatched.

The original supplied-driver evidence is in `fleet-v55-verification.json` and `backend-populations.json`. A subsequent local runner compares against the installed release and writes `fleet-latest-check.json`; it does not pretend that the installed release is the original download.

Generated compiler binaries, benchmark inputs and intermediate artifacts stay in `/tmp`. One-shot migration scripts are retained as history and **must not be rerun on an already-migrated tree**. Use the final source tree or the patch against the original sources instead.

## Evidence map

All paths below are under `sovren/work/session20261014/` unless noted.

- `deployment-v55.json`: installed hashes, source hashes, library hashes, retired-cache record.
- `fleet-v55-verification.json`: both builds and original/candidate fixture results for each driver.
- `fleet-verification.json`: retained earlier 53/155 baseline (historical).
- `frontend-verification.json`, `source-rejections.json`: sugar and direct-suite outcomes.
- `regression-v55.json`, `artifact-modes-v55.json`, `artifact-modes-negative-control.json`, `dependency-caches-v55.json`, `dependency-caches-negative-control.json`: safety/edit evidence.
- `matrix-v55-final.log`, `split-stress-v55.json`: applied-edit and boundary checks.
- `native-hash-benchmark.json`, `parity-v55.json`, `profile-v55.json`: raw samples and measurements.
- `backend-populations.json`: all 155 classifications, additional original comparisons, dynamic-input and C-pipeline results.
- `cache-refresh-v55.json`: refreshed caches and prefix quarantine decision.
- `acx-native-fuzz.log`, `../probes2/acx_mix/`: native reference test, assembly and disassembly.
- `../../compiler-speed.patch`: source changes against the original compiler/library archive.
- `../reference/`: pinned SA executable and reference fingerprint.
- `continuous-gate.log`: local correctness-only runner result. The added workflow is configuration, not evidence of a hosted CI run.

Workspace usage is recorded separately in `work/workspace-budget.json` after packaging. The release is kept below the 100 MB internal safety cap, leaving headroom under the user's 128 MB / 10,000-file persistence limit.
