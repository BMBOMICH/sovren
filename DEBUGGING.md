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
  `chmod +x sovren compilers/linux/compiler compilers/windows/compiler compilers/macos/compiler
  compilers/ios/compiler compilers/android/compiler compilers/android-so/compiler mac/hello
  tests/arm64/hello tests/macos-check tests/arm64/check`.
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
   model.** The first the script tool mirror reproduced the *buggy*
   algorithm, so it agreed with Sovren and disagreed with the RFC;
   that comparison proved nothing. `cryptography`,
   `pycryptodome`, `the reference client` were installed in minutes and were
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
   reference in the script tool. This is how the limb-9 carry bug and the
   p-constant typo were found: one byte, one limb, one offset.
5. **Keep invariants in the crypto code itself.** Cheap self-
   checks that catch the "one byte off" class forever:
   - the field prime's limbs sum to 2^255 - 19 (p9 = 2097151, NOT
     2097152 — this typo silently corrupted every reduction)
   - `invert(1) == 1`, `invert(2) * 2 == 1`
   - decode(encode(x)) == x round-trips
   - ladder state congruent mod p to a big-int reference
6. **Never trust the client's own view of the protocol.** the reference client
   `s_server -state -msg` logs the real wire bytes; the failing
   run's captures + the server's log together are the truth. The
   "bad_record_mac heisenbug" was a little-endian sequence number
   that only showed up at seq 1; the server log proved the
   handshake was fine and the GET record was not.
7. **The emulators preserve registers across calls; real hardware
   does not.** Both the x86 and the arm emulators keep the
   caller-saved registers alive across a `call`, so a syscall
   builtin that translates its number by calling a helper — and
   then reads the arguments from registers the helper clobbered —
   passes every emulator test and breaks on the real kernel with
   garbage arguments (macOS: instant segfault at heap init, zero
   output; arm64: every syscall with args fails, "cannot read").
   Rule: when a builtin must call a helper before the syscall,
   park the argument registers on the stack first
   (`push_reg(6..1)` / `push rdi..r9`) and restore after. The
   syscall maps themselves were also wrong (the mac one mapped
   nanosleep to 240, accept to 30, getcwd to 12 — the Darwin
   numbers were rewritten from the BSD table; the arm64 one had
   three wrong entries and thirteen missing, all fixed against
   `/usr/include/asm-generic/unistd.h`). Ground truth for the
   mac numbers is xnu's syscall table (unix class 0x2000000).

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
- [ ] Verify against the reference client logs, not against your own model

## The strlen-on-binary trap (found in auth.sov, pass 124)

`_sov_strlen` and every text op stop at the first zero byte. A
random 32-byte digest holds a zero byte 1-(255/256)^32 = 11.8% of
the time, so any check like `strlen(hex_to_bytes(x)) is not 32`
rejects one valid record in nine, at random, only when its digest
happens to contain a zero. Symptom: "password sometimes wrong"
flakes at ~12%, file on disk provably valid, every component
correct when replayed by hand. Rule: validate hex/ascii fields on
their TEXT form (every char in range, length right), convert once,
and treat decoded buffers as bytes with an explicit length forever
after. grep for `strlen` near `hex_to_bytes` when a crypto check
flakes at about one in nine.

## The heap is the machine's home too (found in secret_die, pass 130)

Wiping the whole heap with a poke loop, from inside a task,
crashes some guests deterministically: the VM keeps its own
working slots ("homes") in the same bump region, and the walk
out of the wipe - or the exit sequence itself - steps on them.
A guest that only allocates in main survives; any user task
that allocates first turns the same wipe into a jump to address
2. Three traps lined up on the way to the answer:

- cloning a library module to debug it is unsound: each module
  gets its own view of runtime globals (heap_ptr read real in
  one, zero in another) - probe from the real module or not at all
- the x86 emulator is not the kernel: msync returns success where
  the kernel returns EINVAL, and a guest that crashes on the
  kernel exits cleanly under emulation - trust it for control
  flow, not for memory-model truth
- `out=$(prog | tail -1); $?` is tail's exit code. redirect to a
  file, then read $? - half a bisect was garbage before this

The fix: MADV_DONTNEED. The kernel discards the pages itself -
no userland store ever runs - and reads afterwards fault in as
fresh zeros. Page-precise, verified by discard-and-read-back.
secret_die now wipes the used heap that way and keeps the exit
code in .data, which survives both wipes.

## Traps from the stack-wipe passes (131-133)

- dmesg is ground truth for a crash: fault address, ip, error code,
  and the instruction bytes AT the ip. "segfault at 0, ip
  0x400177" plus zeros at the ip meant executing zeroed text - the
  wipe had anchored on the image, not the stack. Decode branches
  all you want; dmesg settles it.
- emit() takes DECIMAL byte values. emit(48) is 0x30, not REX.W.
  REX.W is emit(72). And emit4() always writes four bytes - an
  imm8 operand after emit4 corrupts the whole stream (a `shr r9,8`
  emitted as emit4(8) cost an hour).
- never raw-emit a branch and put() its offset without registering
  the site through jnz()/jmp()/jz(). br_relax shrinks rel32 to
  rel8 after emission and only re-points registered sites - raw
  sites drift into mid-instruction offsets.
- a mincore vec must point into a page that is mapped AND
  writable, or every probe dies EFAULT (-14) and the loop wipes
  nothing, silently. vec = the anchor page itself is the fix.
- an import is one line: the PE import table is generated from
  imp_name at output time, IAT, thunks and hint names included.
  No header surgery. (The name strings sitting in the head hex
  are leftovers; the writer builds its own.)
- frame-free ("thin") main has its own exit path. Hooking only the
  standard epilogue silently misses it - decode a guest with no
  main locals before believing the hook is dead.
- aarch64 ADD/SUB immediates stop at 4095 (imm12). Stepping a page
  is two subs of 2048. Fixed 4-byte instructions make branch
  offsets countable by hand; movz/movk sequences make set_reg
  word counts predictable per value - but only per value.
- MEMORY_BASIC_INFORMATION on x64: State sits at offset 32;
  MEM_COMMIT is 0x1000. The uncommitted stack reserve reads as
  reserved, which is what stops a VirtualQuery walk at the guard
  boundary instead of faulting.
- the emulator dispatches windows imports BY NAME (str_eq), and
  mac syscalls through a number map - new imports and mac numbers
  need matching emulator entries or private guests die in testing
  while working everywhere real.
- /tmp files can vanish between tool calls here. Compile, run and
  inspect in one command; do not assume yesterday's (or the
  previous call's) /tmp artifacts exist.

## Traps from the globals pass (135-136)

- patch offsets are per-writer: the linux writer pokes at HDR+at,
  the mac writer at hdr+at (a computed Mach-O header size, not the
  constant), the windows writer at 512+at. Copy a patch kind
  between writers and it lands somewhere else entirely - on mac
  it stamped an address over a print's mov eax, on windows it sat
  silently in the PE head. Symptom on mac: an instruction stream
  with B8 where 48 BF was emitted. Emission was proven correct
  first by printing oc[] from inside the compiler - do that
  before suspecting the emitter.
- 48 B8 is movabs rax; 48 BF is movabs rdi. A stosq after the
  wrong one fires with a stale rdi - ours held fd 1 from print's
  write, so dmesg showed a write fault at address 1.
- aarch64 immediates: movz/movk bases are 3531603968-family
  (0xD2800000 is 3531603968, not 3531587584 - recompute, don't
  reuse from memory). imm12 caps at 4095, so stepping 4096 is two
  subs of 2048.
- when a battery test silently does nothing, check that the guest
  source was actually written to /tmp before tr_build_for - an
  unwritten file fails the load and skips both the ok and the
  FAIL branch.
- the sandbox filesystem can wedge on one directory while echoes
  still work: copy the needed files to a fresh directory, copy
  linux/runtime.sov with them, and keep building there.
- emit(60) is the opcode 0x3C, not "mov al,60": that is
  emit(176) then emit(60). A bare 0x3C eats the next byte as its
  immediate and the syscall after it decodes as garbage - the
  guest segfaults a world away from the cause.
- when a surgery moves or re-appends a block, grep for the
  patch() calls it was supposed to carry: pass 137's re-append
  dropped the down-walk's patch line and the branch relaxer's
  orphan rule silently resolved the site to a plausible target.
  It worked for every layout until pass 138 added a second loop
  and the orphan resolution landed mid-instruction. Symptom was
  an unpatched rel32 jnz (0f 85 00 00 00 00) - a forward branch
  jumping to its own next instruction.
- a task definition pasted inside a running body ends that body
  at its return: everything after it is dead code, and the
  battery count quietly drops with no FAIL lines. The count is
  the alarm - watch it on every rebuild.
- exit codes are low-byte only: 4096 exits as 0. When
  instrumenting with exit-code reports, shift or mask into eight
  bits first, or report small numbers.
- rep stosq consumes rcx: an exit-code report read from rcx after
  the stosq is always 0. Save the count into a callee-saved
  register before the repeat.
- 4C is REX.WR, 49 is REX.WB: emit(76),137,207 is mov rdi,r9;
  emit(73),137,207 is mov r15,rdi. Wrong REX bit = wrong register,
  silently.
- the string-span wipe rounds up to whole qwords and can overrun
  up to seven bytes into the globals area (here fourteen): any
  wipe stage that READS a global slot must run BEFORE the strings
  run, or it reads zero.
- a store to a global the source never reads dies in the diets -
  SSA folding sees right through a compare-and-return planted to
  keep it, even across an inlined guard call. If a value must
  survive to a raw-patch reader, anchor on a global the runtime
  itself reads (heap_ptr), and derive the rest at run time.
- the script tool surgery on a source file: s.replace(anchor, new) keeps
  everything, but s = new + s.split(anchor,1)[1] throws the file
  head away. Assert on the length of the result, not just the
  match count.


## Pass 142 traps (three, all self-inflicted)

37. **Column-0 emit lines are top-level statements.** A the script tool
    heredoc that builds `    emit(49)
emit(219)
` (second line
    unindented) compiles clean - the bare lines become top-level
    bodies that never run. The guest then contains orphan opcode
    bytes (31 31 31 ... 45 45 45) that decode as `xor [rcx],esi`
    with rcx 0: a segfault at exit. Every generated emit line
    needs its indent.

38. **Never hand-convert hex to decimal.** `subs w9,w9,#1` is
    0x71000529 = 1895826729; I shipped 1895858733 (0x7100822D,
    `subs w13,w17,#32`) twice by doing the arithmetic in my
    head, and "verified" it by searching for the same wrong
    number. Compute emitw words in the script tool from the encoding, and
    verify by decoding the INSTRUCTION, never by matching the
    constant you emitted.

39. **A cap you cannot see fire is not a cap.** Pass 141's x86
    `dec r9` was emitted as FF C9 = `dec ecx` (missing REX 41)
    and the arm cap as the garbage word above; both were inert,
    and the battery stayed green because nothing ever walked
    16384 pages. Decode the bytes (41 FF C9 / 0x71000529) in a
    real guest before calling a bound armed.
