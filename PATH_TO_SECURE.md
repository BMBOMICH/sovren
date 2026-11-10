# Path to most secure — language, runtime, and toolchain

Sovren's security posture is currently **bare-metal strong, application-layer
weak**: it can build a kernel with no runtime, but a normal program has no
memory safety, no type safety, and an unsafe gate that is a comment.

## 1. Memory safety — the biggest hole

There is no GC, no ownership, no bounds checking by default. `_sov_list_get`
returns `0` for an out-of-range index rather than trapping; `peek_i64` on a bad
pointer is a segfault or silent corruption.

Plan, cheapest first:

| # | item | what it buys |
|---|---|---|
| 1 | **Bounds-checked `peek`/`poke` in safe code.** `chk_mem` already exists and emits a trap; make it the default in safe modules and `# unsafe` the opt-out. Today `chk_mem` is only emitted on some paths. |
| 2 | **`_sov_list_get` traps on out-of-range** in safe code, instead of returning 0. Returning 0 silently turns every typo into a wrong answer. |
| 3 | **A real `unsafe` block, not a comment.** `# unsafe` and `# unsafe-module` are grepped by the compiler. Replace with a lexical construct so unsafe regions are auditable and greppable by tooling. |
| 4 | **An ownership/escape lint** (warnings only): possible leak, double free, use-after-free, escape from region. |
| 5 | **`defer` + scoped regions** so reclamation is automatic by construction. |
| 6 | **Optional deferred reference counting** for programs that want automatic safety. |

Explicitly **not** recommended: a tracing GC as the default. Wrong for kernels,
firmware and bootloaders, which are core sovren targets.

## 2. Type safety

No enums, no sum types, no generics, no null-safety. Every one of those is a
class of bug that the type system should catch:

| missing feature | bug class it prevents |
|---|---|
| `enum` / sum types | invalid state, unhandled case |
| `Option`/`Result` | null dereference, ignored error |
| `generic` | `i64`-only containers force hand-rolled unsafe casts |
| `trait` | wrong-type dispatch |
| null-safety | `0`-as-null dereference |

This is the same work as `LANGUAGE_GAPS.md`; it is listed here because the
security payoff is the main argument for doing it.

## 3. Toolchain and supply chain

1. **Reproducible builds** (`--reproducible`): same source + same compiler =
   byte-identical output. Today nothing guarantees this.
2. **A build manifest** recording compiler hash, source hash, flags, and
   library versions, emitted into the binary as a note.
3. **Compiler self-verification.** `bootstrap` already proves the fixed point;
   make it a release gate that must pass before publishing.
4. **A closed syscall allowlist per target** (see `PATH_TO_PRIVATE.md`), so a
   `firmware` binary cannot contain `sys_open`.
5. **Fuzzing.** `fuzzlib.sov` exists but is not wired to a harness. Fuzz the
   front end (source in, no crash), the allocator (random alloc/free/realloc
   sequences), and every backend (random IR in, valid container out).
6. **A sanitizer mode.** `--sanitize=address,undefined` for the compiler's own
   self-build would have caught the `err_where` stub class of bug.

## 4. Crypto

Coverage is broad (aes, chacha20, gcm, chachapoly, poly1305, ed25519, x25519,
sha1/256/512, md5, hkdf, hmac, pbkdf2). Gaps:

1. **No constant-time guarantee.** `_sov_str_eq` early-exits. Add `_sov_ct_eq`
   and audit every comparison in the crypto modules.
2. **No zeroisation.** Secrets stay in freed memory. Add zero-on-free.
3. **No algorithm agility / deprecation.** md5 and sha1 are present with no
   warning that they are broken.
4. **No test vectors from the standards bodies** for every algorithm.

## 5. Diagnostics as a security surface

Poor error messages are a security problem: they push programmers toward
guess-and-check, which produces silently wrong code. Fixing `err_where()` (18
sites, no location at all) is both the cheapest quality win and a security win.

## Ranked plan

| # | item | effort | security gain |
|---|---|---|---|
| 1 | Fix the `err_where` stub; add codes, columns, carets | low | high |
| 2 | Bounds-check `peek`/`poke` and trap in `_sov_list_get` in safe code | medium | very high |
| 3 | Real lexical `unsafe` construct | medium | high |
| 4 | `--reproducible` + build manifest | low | high |
| 5 | Ownership/escape lint (warnings) | medium | high |
| 6 | `defer` + scoped regions | medium | high |
| 7 | Constant-time compare + crypto audit | medium | high |
| 8 | Fuzz harnesses (front end, allocator, backends) | medium | high |
| 9 | `enum` / `Option` / `Result` / `generic` | high | high |
| 10 | Per-target syscall allowlist | medium | medium |

## Success criteria

- A safe-mode program cannot segfault on an out-of-bounds `peek_i64`.
- `unsafe` is a lexical construct; `grep -c unsafe` answers "how much of this
  program is unchecked".
- Two reproducible builds are byte-identical.
- The allocator survives a 10-minute randomized stress run with no corruption.
- Every crypto module has constant-time comparisons and standard test vectors.
