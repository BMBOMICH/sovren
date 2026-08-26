# Sovren

A self-hosted programming language that compiles straight to machine
code. The compiler is written in Sovren, builds itself, and emits raw
ELF, Mach-O and PE binaries for five machines.

## Start

```
./sovren examples/hello.sov -o hello
./hello
```

That is the whole story: one small launcher, one source file, one
native binary. Read [docs/BOOK.md](docs/BOOK.md) to learn the language — it is
short, like the language.

## What it runs on

| target | output |
| --- | --- |
| linux | ELF x86-64 |
| macos | Mach-O x86-64 |
| windows | PE32+ x86-64 |
| android | ELF aarch64 |
| ios | Mach-O arm64, code signed |
| android-so | shared library, loads in the arm machine |

Cross-compile with a flag: `./sovren prog.sov -o prog --android`.
Phone binaries run on a desktop too — `use arm` is a whole aarch64
machine in the library, and `os.sov` is a small shell over it.

## Numbers

| thing | size |
| --- | --- |
| the launcher (`sovren`) | 9.7 KB |
| the linux compiler | 198 KB, one static file |
| whole system, Sovren source | ~70,000 lines in 347 files |
| the same, packed by `dist.sov` | one 569 KB download |
| check battery | 307 checks, all green |

The repository is its own proof: every compiler binary in `compilers/`
was built by the compiler in this tree, and the battery rebuilds and
re-runs the pieces as it checks them.

## What is in the box

- `compilers/<os>/` — six self-hosted back ends sharing two cores
- `library/` — 100+ libraries: crypto (TLS 1.3, x25519, chacha20,
  sha256), compression (`lz`, `lz2`, `lz2h`), web (http, httpd,
  browser), an arm64 emulator, text, math, games, sound
- ``repl.sov`, `edit.sov` — a shell and an editor with a run key
- `os.sov` — a small operating-system shell over the arm machine,
  with compressed executables
- `dist.sov` — the whole repo as one verified download
- `tests/all.sov` — the 307-check battery
- `docs/BOOK.md` — the manual
- `examples/` — hello, play, show, mysite, guess, music

## The shape of it

Programs are plain text with plain words:

```
twice n:
    return n * 2

main:
    print twice(21)
```

`main:` runs. Jobs take and return values. Four spaces mean a line
belongs to the one above it. That is most of the language; the book
covers the rest in ninety short chapters.

Security is a design rule here, not a library: no syscalls beyond
read, write and exit in the shipped runtime; stack canaries, frame
wipes and core-dump refusal compiled in; buffers refuse lengths that
lie; a byte value is never treated as a pointer.

Lightness is the other rule: no dependencies, no build system, one
binary per tool, and a download that fits on a floppy.

## Layout

```
sovren            the launcher (picks a machine, runs its compiler)
compiler.sov      the launcher source
runtime.sov       the runtime every program carries
compilers/        one folder per target
library/          the libraries
tests/            the batteries
docs/             the book
examples/         the starter programs
scratch/          build output (git-ignored)
```
