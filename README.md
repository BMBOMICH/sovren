> **Current inventory (2026-11-09):** 30 native compiler drivers and 10 WebAssembly variants are retained. Ancient evaluator/emitter targets, standalone IR and other transpilers were removed after a verified Desktop backup. Windows compiler binaries are currently missing; translation parity and full self-compilation remain unfinished. See [CURRENT_SCOPE.md](CURRENT_SCOPE.md). Earlier claims below are historical.

> **Cleanup completed (2026-11-10):** Firmware, GPU/shader, RTOS and non-WebAssembly transpiler targets are removed, including leftover folders and obsolete compiler snapshots. All ten WebAssembly variants are retained. [TARGETS.md](TARGETS.md) lists the current targets and build availability. The launcher source has been updated; rebuilding its existing Linux executable remains pending.

# Sovren

Sovren is a native programming language and self-hosting compiler created by
Elxan Huseynov. The repository contains first-party compiler backends, runtime
facilities, standard libraries, tests, debugging tools, and the compiler support
used to build SovrenOS.

Sovren is not a Windows compatibility layer. Its Windows executable is a native
PE program, and programs compiled for Windows are native Windows executables.
Backends target Linux, Windows, macOS, Android, iOS, iPadOS, tvOS, visionOS,
their simulators, and freestanding kernels. SOVREN_TARGETS.md in the repository
root and TARGETS.md here list every name, what file each one writes, and how a
new one is added.

## License

Sovren remains source-visible proprietary software under [`LICENSE`](LICENSE).
Programs you write using Sovren remain yours, as described by that license.
Viewing the source does not grant permission to redistribute the compiler.

## Quick start

### Windows

Open PowerShell in the repository directory:

```powershell
.\sovren.exe tests\hello.sov -o hello.exe
.\hello.exe
```

The compiler needs `runtime.sov` and `library\` beside the installed compiler.
The Microsoft Store package includes both automatically.

### Linux

```sh
chmod +x sovren
./compilers/linux/compiler tests/hello.sov -o hello
./hello
```

Run the complete language/library suite:

```sh
./compilers/linux/compiler tests/all.sov -o sovren-all
./sovren-all
```

The default compiler path favors edit/build speed and leaves unreachable functions in the artifact. Use `--release` to run whole-program dead-code elimination and produce the compact release image:

```sh
./compilers/linux/compiler app.sov --release -o app
```

The compiler is fully cold: every run parses, walks and emits from scratch.
There is no artifact cache, no state dump, no prefix replay, no persisted
intermediate of any kind, anywhere in this tree. Every reported translation
number is a fresh whole-run measurement.

Run the fixed-point and multi-target bootstrap:

```sh
chmod +x bootstrap
./bootstrap
```

A successful bootstrap ends with `bootstrap clean`.

## Repository map

- `compilers/` — self-hosting compiler variants and platform backends.
- `library/` — native Sovren standard and systems libraries.
- `tests/` — language, library, malformed-input, ABI, and kernel tests.
- `tools/` — first-party development and release tools.
- `runtime.sov` — runtime source used by generated programs.
- `launcher.sov` — multi-target command launcher.
- `store/` — Microsoft Store MSIX packaging and release instructions.

SovrenOS is maintained as a separate project and consumes this toolchain.

## Windows Store releases

The free individual Microsoft Store route preserves the current proprietary
license. Microsoft signs a certified MSIX package; no private signing key or
identity document is stored in this repository. See
[`store/README.md`](store/README.md) for the one-time setup and automated update
pipeline.

## Source syntax

Four surface-compaction forms are part of the language and expand to the plain
forms before anything else runs, so both spellings are the same program:

```sovren
use:                0:                  emit:               x = 7
    num                 src_base            205
    string              had_err             128
```

`use:` collects library names, `emit:` / `emit4:` / `emit8:` collect one byte
run, `<value>:` collects names that share a constant (`0`, `-1`, `blank`), and
`name = expr` is an assignment without the colon. See [`SYNTAX.md`](SYNTAX.md)
for the rules, the exact desugar table, and the byte-for-byte proof that the
compiler reproduces itself with them.

## Security and privacy

The compiler does not transmit user data by itself. A program compiled with
Sovren can access files or networks only when its own source requests those
operations. Obtain release packages from the official Store or official release
location, and compare published SHA-256 hashes when downloading outside a
managed store.

Report suspected vulnerabilities privately to the author through the official
repository contact channel. Do not include passwords, private signing keys,
government identity documents, or unrelated personal information in a report.

## Project status

The compiler and libraries have extensive automated validation, but Sovren and
SovrenOS remain under active development. Passing a test gate establishes only
the behavior covered by that gate; it is not a general production-readiness or
hardware-certification claim.
