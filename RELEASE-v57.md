# Sovren v57 — shared architecture and verified release

**Installed: 155 reproducibly rebuilt Linux x86-64 driver executables.** This is a verified scoped release, **not completion of all advertised backend semantics**. SA translation-speed work was deferred as requested; no new parity claim is made.

## Implemented

- Active shared frontend → SIR 1 → C/JavaScript/TypeScript lowering, with complete semantic analysis before lowering for the supported subset.
- Typed expression nodes, resolved function/local IDs, structured statements and deterministic `--emit-ir` JSON; cross-target IR checks and a validator.
- Correct left-to-right C operand/argument side effects, including nested calls, short circuiting and repeated while conditions. Native negative-RHS parsing, escaped strings and signed division/remainder boundary fixes are also included in the deployed native core.
- Real separation of frontend, IR, shared lowering, generated arithmetic runtime and Linux host I/O. Compatibility-safe `transpilers/` and backend-family views without duplicate implementations.
- One authoritative 155-backend registry, capability profiles, integrity checks, explicit experimental opt-in, source-only/end-to-end build pipelines, and a Linux correctness CI workflow.
- Source/binary-bound release records and fail-closed full-language/universal-completion gates. The latter remain red rather than mislabeling the subset as full support.

## Verification

| Gate | Result |
|---|---:|
| Deterministic backend rebuilds | 155 / 155 |
| Existing fixture artifacts | 304 exact; 6 explicitly approved semantic changes |
| C / JS / TS conformance | 249 / 249, no skipped toolchains |
| Native differential cases | 57 / 57 |
| Shared IR checks | 41 |
| Output failure / alias / concurrency checks | 30 / 30 |
| Frontend sugar | 220 exact |
| Native suite | 21 exact; 13 matching rejections, not successful compilations |
| Native self-host | Byte-identical fixed point |
| Cache / dependency / output-mode / edit gates | 80 / 4 / 12 / 11 passed |
| Worker fault/fallback checks | 12 passed |
| CPU-affinity equivalence cells | 8 passed; not SA speed measurements |
| Installed end-to-end pipelines | C, JS and strict TypeScript each execute the expected result |

Installed binaries were rechecked after deployment. 214 library sugar caches plus runtime cache were refreshed; optional prefix snapshots remain quarantined. Numbered `inc00.sov` remains exactly 2,039 lines. Local CI commands were run; no hosted CI or foreign-host run is claimed.

## Still unfinished

The shared frontend remains a structured i64 / literal-text subset. General text values, collections, structs, pointers/memory, globals, imports and libraries, floating point, argv access and platform services need implementation and tests. Native and other backend families are not yet migrated to SIR. Legacy evaluator/partial emitters are not full-language compilers. Foreign compiler-host ports and actual-host/target execution remain unvalidated.

The new registry build tool rejects experimental targets by default, but preserved legacy direct paths can bypass that policy. JSON SIR export is not an importable backend protocol. Atomic output publication does not promise power-loss durability.

## Use

```sh
python3 tools/backend.py list
python3 tools/backend.py verify
python3 tools/transpile_build.py tests/hello.sov --target c -o /tmp/hello
./compilers/c-language/compiler tests/hello.sov --emit-ir -o /tmp/hello.sir.json
python3 tools/validate_sir.py /tmp/hello.sir.json
```

For TypeScript, install TypeScript 5.9.3 outside the source tree and pass its `tsc` path. See [architecture](docs/architecture/README.md), [capabilities](targets/capabilities.json), [plan](PLAN.md) and the machine-readable evidence in `work/releases/v57/`.

The compact download excludes the duplicate `previous-fleet.tar.gz` rollback archive; that backup remains in the workspace. The Sovren Assembler project is unchanged and is not duplicated into this package.
