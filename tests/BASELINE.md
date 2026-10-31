# tests/run.sov — first full baseline (2026-09-26)

The suite was never run end-to-end in this environment before. First full run

completed; every non-library check passes (hello, the runtime checks, the

fuzzer, self-host byte-for-byte, the Apple platform walks). The failures are

exactly three classes:

## 1. Organ libraries — the check's own design gap

`use carm`, `use ccore`, `use cx86` can never compile standalone, on ANY

target: they are compiler organs that reference compiler-internal state

`oc`, `patch_kind`, `fn_names`, `src_base`, `had_err`, `u_listing`...),

which only exists inside a compiled compiler. `ck_alllibs` ("every library

on every target") walks every `library/*.sov` and counts them as failures by

design. They are validated where they belong: every kit build compiles them,

and the no-warnings gate covers them. (The suite should skip them with a

comment; left as-is so the failure stays visible until that edit is agreed.)

## 2. x86-isms in some user libraries on the arm64 targets — real backlog

`use browser --android`, `use discord --android`, `use arm --android` (and

`--ios`, `--android-so`) fail at COMPILE time: e.g. browser.sov:1997 emits a

bare `leave`, which the x86-64 backend accepts and the arm64 backend answers

"bad line". Plain and --windows/--mac builds of the same libraries pass.

This is a portability backlog in those libraries, not a compiler defect; it

predates this baseline and is untouched by every round this session.

## 3. Environmental — documented standing debt

`target--android/--ios/--android-so` and "windows compiler in the emulator"

need the arm linker / a Windows loader; this sandbox has neither `ld` is

absent). Unchanged, environmental.

## Passing set (for the record)

hello, the runtime list/tui checks, the fuzzer ("fuzz ok" path), self-host

byte-for-byte (g1 builds the linux compiler, g2 builds g3, identical), the

Apple platform walks (ck_apple: platform/cpu/cmd-table/entry/signature —

now including watchos 4 and watchos-simulator 9), the no-warnings compile of

the base five compilers.
