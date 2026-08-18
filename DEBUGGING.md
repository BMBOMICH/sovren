# Fixing Sovren issues faster — a playbook

This file exists because fixing the X25519 "compiler bug" took far
too long. The compiler bugs were real, but most of the hours went
into verification plumbing that should have been built once, at the
start. This is the playbook so the next agent (or the next session)
does not repeat that.

---

## 1. The environment traps (burned ~2 hours total)

These are specific to this sandbox. Know them before starting:

- **/tmp is wiped between sessions.** Certs, logs, test sources,
  battery output, and the battery itself all died mid-work, more
  than once. Anything you need across turns lives in the repo
  (`check/`, `tests/`, or at least a `tools/` dir), never in /tmp.
- **`./sovren` sometimes silently fails to overwrite the output
  file.** It prints `Wrote` but the binary on disk is the old one.
  A "hang" or "no change" that makes no sense is often this. Rule:
  `rm -f out` before every compile, then check the mtime. Do this
  unconditionally; do not trust `Wrote`.
- **No root, no gdb, no strace.** You cannot attach a debugger.
  The repo's own `debug.sov` runs a program inside the x86
  emulator with registers, memory, breakpoints and stepping:
  `./sovren debug.sov -o debug && ./debug ./prog`. Use it before
  hand-disassembling binaries.
- **Exec bits do not survive sandbox resets.** After any reset:
  `chmod +x sovren linux/compiler windows/compiler mac/compiler
  ios/compiler android/compiler android/compiler_so mac/hello
  arm64/hello mac/check arm64/check`.
- **Arena sometimes re-sends the previous prompt.** If the user's
  message looks like a duplicate of something already handled, say
  "Arena resent that" and confirm state instead of redoing work.

## 2. The compiler quirks (all verified the hard way)

The language has real edges. Writing code that avoids them all at
once is the single best time-saver:

1. **A pointer returned from a call does not survive.** Callers
   that read through a returned buffer are miscompiled — silently,
   and not on every run. Rule: caller makes the buffer, passes it
   in, the job fills it. See `sha256_bytes(data, n, out)`,
   `hmac_raw(key, klen, msg, mlen, out)`, `ae_expand(key, rk)`.
2. **Globals do not stay put across deep calls.** Thread all state
   as arguments; keep only "write as the last thing a job does,
   read immediately after" globals (`tl_clen`, `tl_hslen`,
   `tl_gtot`). Set sequence numbers right before the record call.
3. **`/` and `%` truncate toward zero.** A negative intermediate
   does NOT carry back. Field arithmetic must keep every limb
   non-negative (bias with 4p, then reduce), or use explicit
   borrow.
4. **`is` on integers and strings is pointer/identity
   comparison.** Use `str_eq(a, b) is 1`, and never `if x is 5`.
5. **A job takes at most seven values; big jobs clobber their own
   locals.** Split into small jobs with buffers in a state struct
   (`st + offset`). The x25519 rewrite made every job small, and
   the "ladder miscompiles" report closed.
6. **Never shift by big amounts for bit extraction.** Read bits
   from a byte array (`peek_byte(sb, t / 8)` + small shift), not
   `(x >> 254) & 1`.
7. **Sizes as return values are unreliable.** Return them via a
   global written last (`tl_clen` pattern), or copy into a local
   immediately.

## 3. The verification playbook (the actual time-saver)

Order matters. Doing 4 before 1 is how hours evaporate.

1. **Unit-test the primitives first, in isolation.** For the field
   arithmetic this was: `2*3==6`, `(p-1)^2 mod p == 1`,
   `invert(2)*2 == 1`, decode/encode round-trip, then 1-, 2-, 3-,
   10-, 100-, 200-, 255-bit ladder runs against the reference.
   Each check is one tiny .sov program in the repo.
2. **Use a reference implementation as ground truth — not your own
   model.** The first Python mirror reproduced the *buggy*
   algorithm, so it agreed with Sovren and disagreed with the RFC;
   that comparison proved nothing. `cryptography`,
   `pycryptodome`, `openssl` were installed in minutes and were
   the only tests that mattered. Diff byte-for-byte against them
   from minute one.
3. **Bisect with short runs.** The `st+432` loop-limit trick (run
   N ladder bits, dump state, diff against reference at N = 1, 2,
   3, 10, 100, 200, 255) pinned the first diverging step in
   minutes. Build this scaffolding before the full pipeline
   works, not after.
4. **Dump-and-diff at every boundary.** Capture the arguments at
   the entry of every step and the intermediates between steps
   (`file_write_bytes` to /tmp), then compare each against the
   reference in Python. This is how the limb-9 carry bug and the
   p-constant typo were found: one byte, one limb, one offset.
5. **Keep invariants in the crypto code itself.** Cheap self-
   checks that catch the "one byte off" class forever:
   - the field prime's limbs sum to 2^255 - 19 (p9 = 2097151, NOT
     2097152 — this typo silently corrupted every reduction)
   - `invert(1) == 1`, `invert(2) * 2 == 1`
   - decode(encode(x)) == x round-trips
   - ladder state congruent mod p to a big-int reference
6. **Never trust the client's own view of the protocol.** openssl
   `s_server -state -msg` logs the real wire bytes; the failing
   run's captures + the server's log together are the truth. The
   "bad_record_mac heisenbug" was a little-endian sequence number
   that only showed up at seq 1; the server log proved the
   handshake was fine and the GET record was not.

## 4. The battery and perf (deferred, for the perf pass)

The ~20 minute battery is 90% the "163 libraries x 6 targets"
matrix: 978 fresh `./sovren` builds, single-threaded, no cache.
When the perf pass happens:

- parallelize the matrix (each build is independent) — biggest win
- cache compiled libraries / avoid re-parsing the tree per build
- the compiler's string handling is O(n^2)-ish; profile it
- everything else in the battery is seconds (x86 emulator check is
  ~36s, the rest trivial)

## 5. Checklist for a future agent

Before starting any crypto/compiler task:

- [ ] Recreate /tmp scaffolding from the repo, not from memory
- [ ] `rm -f` outputs before every compile; check mtimes
- [ ] `chmod +x` everything after a sandbox reset
- [ ] Install reference libs (`pycryptodome`, `cryptography`) early
- [ ] Write the tiny unit tests FIRST, with reference vectors
- [ ] Use the `st + offset` state-struct pattern for anything with
      more than a few locals
- [ ] No pointer returns; no global reads across calls; no `is`
      on numbers; byte-array bits, not big shifts
- [ ] Keep every test source in the repo, never /tmp
- [ ] Verify against openssl logs, not against your own model
