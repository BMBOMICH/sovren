# Path to most private — language, toolchain, and runtime

"Most private" decomposes into four separate properties. Sovren is currently
strong on the first and absent on the other three.

## 1. What the binary reveals — sovren is already strong

Standalone binaries with **no runtime, no libc, no telemetry, no phone-home**.
Nothing in `runtime.sov` opens a network connection or reads a config file. This
is already better than most language ecosystems, where the default build links a
runtime that may have update checks.

**Keep it that way, and make it a guarantee:**
1. A `--audit-privacy` flag that scans the linked symbol set and reports every
   `syscall` the binary can reach, grouped by class (network, file, process,
   time, entropy). Today there is no way to answer "what can this binary do?"
   without reading it.
2. A documented, closed syscall allowlist per target, enforced by the compiler:
   a program that calls `sys_open` on a `firmware` target should be a warning.
3. `sovnet_abi.sov`, `sovsys_abi.sov`, `sovservice_abi.sov` and friends already
   describe the ABI surface — turn them into the machine-checked source of that
   allowlist.

## 2. What the compiler reveals — currently absent

The compiler reads the source file and nothing else, which is good. But:

1. **No build provenance.** There is no way to record which compiler built a
   binary, from which source hash, with which flags. Add a reproducible-build
   mode (`--reproducible`) that zeroes timestamps and paths, and emits a
   `SOVREN_BUILD_ID` note so two builds of the same source are byte-identical.
2. **`self_dir` and absolute paths leak into output.** `tidy_path` and
   `dirname(self_dir)` are used for library resolution; make sure no absolute
   build path is embedded in the emitted binary (verify with
   `strings` on a reproducible build).
3. **No environment isolation.** The compiler reads `argv` and `env_at`; document
   exactly which environment variables affect codegen, and add
   `--ignore-env` for hermetic builds.

## 3. What the language makes easy to leak — needs work

1. **No secret type.** `secret.sov` and `vault.sov` exist as libraries. Promote
   to a `secret` type that:
   - refuses to be printed, logged, or included in an error message by default;
   - is zeroed on scope exit (`_sov_bzero` already exists);
   - cannot be compared with `==` in a way that leaks timing (the comparison
     must be constant-time).
2. **No constant-time comparison guarantee.** `_sov_str_eq` is a byte loop with
   an early exit, which is a timing side channel for secret comparison. Add
   `_sov_ct_eq` and use it for every secret/crypto path. `ed25519.sov`,
   `poly1305.sov`, `chachapoly.sov` and `gcm.sov` should all be audited for
   early-exit comparisons.
3. **No automatic zeroisation.** `_sov_bzero` exists but is not called on free.
   Add a `zero_on_free` allocator flag for secret buffers.
4. **No data-flow tracking.** A `taint` analysis (warnings only) that flags a
   value derived from a secret reaching a print, a file, or a network call.

## 4. What the ecosystem reveals — absent

1. **No package manager**, so no third-party code and no supply-chain surface.
   This is a privacy *advantage* today; keep the default dependency-free and
   make any future package system opt-in and auditable.
2. **No telemetry of any kind.** Make this an explicit, tested policy: a test
   that asserts the compiler makes no network syscall.

## Ranked plan

| # | item | effort | privacy gain |
|---|---|---|---|
| 1 | `--audit-privacy` syscall report | low | high — makes the property checkable |
| 2 | `--reproducible` builds | low | high |
| 3 | `secret` type + no-print-by-default | medium | high |
| 4 | constant-time `_sov_ct_eq` + crypto audit | medium | high |
| 5 | zero-on-free for secret buffers | low | medium |
| 6 | per-target syscall allowlist | medium | medium |
| 7 | `--ignore-env` hermetic builds | low | medium |
| 8 | taint analysis for secrets | high | medium |

## Success criteria

- `strings` on two reproducible builds of the same source differs only in the
  build ID.
- `--audit-privacy` lists every reachable syscall and it matches a documented
  allowlist.
- A `secret` value cannot reach stdout, a file, or the network without an
  explicit `reveal` call.
- A test asserts the compiler opens no socket.

## Audit addendum (2026-10-14, tree audit vs this plan)

Verified today:
- No sockets/telemetry in compiler or runtime core. Network exists ONLY as opt-in
  libraries (http.sov, sock.sov, tls.sov, httpd.sov, inc03:1570) — a binary can
  not network unless the author writes it.
- lsug sugar caches store sugared text of LIBRARY chunks only; the main-source
  gate keeps user code out; every serve is hash-checked. Content = sovren's own
  library text, machine-local, in-tree.
- No env-var-driven cache paths (env_at appears only in a diagnostics dump path).
- Builds are byte-deterministic (fixed-point proven repeatedly).

New gaps this audit adds to the plan (not in the ranked table above):
9. Learn/AC artifact-cache flows: confirm the on-disk cache stores only
   hash-keys + derived artifacts, never raw user source; add `--purge-caches`
   and document every path written (ac/learn/lsug/pfx/deep-state).
10. Path-embedding verification: `strings` a default-flags binary built outside
    the tree for absolute build paths (input path, self_dir). Owed — the check
    was planned but /tmp artifacts were wiped before it ran.
11. /tmp hygiene: compiler+suite write build scratch to /tmp; add a
    `--scratch-dir` override and best-effort cleanup on failure.
12. Hermetic docs: one page listing EVERY file the compiler reads/writes outside
    the explicit -o path, per target.
13. Cross-channel note stays: Microsoft Store metadata is outside sovren's
    control (already covered in PRIVACY.md).

## Status ledger (2026-10-14 turn)

| # | item | status |
|---|---|---|
| 1 | --audit-privacy | DONE BOTH FORMS: in-compiler flag (linux backend, per-syscall evidence + indirect-site count) AND work/privacy/prvaudit.sov |
| 2 | --reproducible | DONE BOTH FORMS: in-compiler flag prints SOVREN_BUILD_ID (stable across builds, gate-asserted) + path-embed count; determinism gate-asserted |
| 3 | per-target allowlist | gate enforces NET=NONE policy on artifacts + compiler closure (over-approximated = safe) |
| 4 | path embedding | gate: zero '/'-strings in fresh artifacts (prvaudit p) |
| 5 | --ignore-env | verified: compiler reads no env-var-driven config (only diagnostic dump path); docs |
| 6 | purge + cache inventory | prvpurge.sov shipped (.deep .deepoc .ac .ac.bin .lsug); .lsug holds SUGARED source next to input - documented honestly; .sug holds library text in-tree |
| 7 | scratch hygiene | suite /tmp usage documented; in-compiler --scratch-dir follow-up |
| 8 | secret type | secret.sov restored+extended: seal/open/reveal/is_box + existing mask/wipe/lockdown/noswap/harden/scrub/line kit; type-system promotion = follow-up |
| 9 | ct compare | ALREADY CANONICAL: constant.sov ct_eq used by chachapoly/auth/hmac/gcm, suite-tested; secret.sov delegates |
| 10 | zero-on-free | secret_wipe_bytes used across crypto; no allocator free exists (arena model) - documented |
| 11 | taint analysis | SHIPPED: work/privacy/prvtaint.sov (source-level secret-taint, word-boundary flow, reveal-gate aware, warnings-only) |
| 12 | dependency-free | policy kept; documented |
| 13 | no-socket test | privacy_gate.py: closure scan (NET=NONE, 15 syscalls listed) + artifact scans |
| 14 | state-file enum | DONE: .ac .ac.bin .lsug (input-adjacent), .deep .deepoc (deep flow), .sug (in-tree) |
| 15 | memory lifecycle | emit_stack_wipe + secret_wipe_bytes + MADV_WIPEONFORK/DONTDUMP kit; arena model documented |
| 16 | crash hygiene | ALREADY IMPLEMENTED: secret_lockdown (PR_SET_DUMPABLE 0), secret_harden (MADV_DONTDUMP), secret_die |
| 17 | entropy audit | getrandom-only verified (rand.sov, arm.sov fallbacks); no time-seeded RNG |
| 18 | table-lookup audit | aes.sov = computed GF math, NO T-tables; chacha ARX; poly1305 arithmetic; PASS |
| 19 | builder fingerprint | gate: no 'sovren'/version strings in artifacts |
| 20 | threat model | THREAT_MODEL.md shipped |
| 21 | privacy gate | work/speed/privacy_gate.py shipped, fail-closed |
