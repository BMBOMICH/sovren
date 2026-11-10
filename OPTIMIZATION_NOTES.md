# sovren → sa speed-matching: status

Updated: after round 3 — call_args inliner for _sov_list_len/_sov_list_get.
All work on the x86-64 Linux box.

## Official numbers (repo's own tools/speed_gate.py, fresh process, no cache)

| workload | expanded B | sovren | sa | ratio |
|---|---|---|---|---|
| tests/all.sov (full suite closure) | 332,158 | 1.869 MB/s (178 ms best) | 694.2 MB/s | 0.00269x |
| compilers/linux/compiler.sov (self-compile) | 478,773 | 1.364 MB/s (351 ms best) | 678.3 MB/s | 0.00201x |

Paired best-of-11, cumulative session: pre-opt 191.7/375.7 ms → now 175.3/352.9 ms
(all.sov/self) ≈ **1.09-1.21x** depending on run; per-round: pool opts 1.11x,
list-inlining 1.06-1.09x. Gate noise: sa swings ±10%; trust paired runs.

## What was done this round (all in the durable tree)

0. **Fleet census**: 152/155 target compilers compile cleanly with the optimized
   build (arm64 ✓). The 3 failures (windows, windows/store, apple/macos) are
   UPSTREAM snapshot drift — their source decl lines were never updated for the
   pool's dbg feature (masked cascading errors: dbg_mode → sxe_mode → bare-name
   lines). Verified IDENTICAL failures with the pre-optimization compiler; the 3
   files were re-downloaded pristine from MediaFire after fix experiments.
   Language facts learned: top-level `name: 0` assignments are order-independent
   globals; bare indented names inside spliced block contexts are STATEMENTS
   (need the name to exist), `0:`/`blank:` sections declare; px00-6 param names
   become globals; a declaration-section opener (e.g. px00 3772) placed mid-file
   breaks the parse state of everything after it — placement matters.
1. **SWAR `_sov_find_text`** (runtime.sov): needle-first-byte scan 8 bytes/step
   with branchless zero-propagate detect. Old: 11.5 MB/compile, one call PER BYTE.
2. **`lines_of` → `lines_of_fast`** (inc05.sov): the author's own unreleased opt,
   present in their committed linux listing (line 7242) but not the published source.
3. **`sg_extra` fast path + `sg_qend` prefilter** (ccore.sov): no-`;` lines skip
   the per-char list build; no-`"` lines skip quote-state scan (ins unchanged —
   NOT reset; the reset variant corrupted src_base, caught + fixed same day).
4. **`pull_uses` chunk concat** (cx86.sov 2245, exactly 3150 lines preserved):
   per-byte `_sov_set_byte` copy → one `join` memcpy per chunk.
5. **sugar-once driver** (inc00.sov 189/491, count 2040 preserved): rt sugared at
   injection, full-source `all: u_sugar(all)` re-scan dropped. Verified PURE
   REFACTOR: flat outputs byte-identical on 6 sources. Measured win: ~0
   (sugar2 phase was already ~0-1 ms — the phase table said so; trust the table).
6. Differential scaling probes (synthetic sources): compile cost is a UNIFORM
   ~6-7.5 µs/line — identical bodies cost the same as unique bodies (no caching
   to exploit, no memoization jackpot). Stage-2 (safe pool edits) is exhausted;
   the compile phase is irreducibly interpreted dispatch per line.
7. **call_args inliner** (compilers/linux/compiler.sov, root file): the author's
   own SPEED_ARCHITECTURE.md names the asymmetry — peek_i64 is codegen-inlined,
   _sov_list_len/_sov_list_get are not ("that asymmetry is the whole
   opportunity"). Landed: codegen now emits raw sequences for these two calls —
   len: `test rdi,rdi; xor/j; mov rax,[rdi+8]`; get: null test + unsigned
   `cmp rsi,[rdi+8]; jae 0` (covers negative AND over-limit in one check) +
   `mov rax,[rdi+rsi*8+16]`. Semantics proven identical on null/OOB/negative/
   growth tests; fixed point holds; suite check-set identical (425/425, the one
   flap is environment-sensitive, build-independent). Paired 1.09x/1.06x. This
   lifts EVERY compiled program's list access, not just the compiler.
8. **sg_run_count prefilter** (ccore.sov, line-count free): a run-form line
   needs two ': ' occurrences; two SWAR looks now replace the unconditional
   sg_run_head (list alloc + 2 cuts per line). Folded with fixed point.
9. **rt double-sugar removed** (compiler.sov 715-716 + inc00 189): the driver
   re-applied u_sugar to the runtime text although the load cascade already
   does. CRITICAL LANGUAGE FACT LEARNED THE HARD WAY: **u_sugar is NOT
   idempotent** — sugar-once changed src_base and broke name resolution with
   'do not know these words' at scale. The correct transform replicates the
   driver's EXACT sequence at load (S then conditional-arrow S) and only then
   removes the duplicate. Net ~2-6%. The 12ms window also contained the 9
   full-source `look()` probes feeding `need` (cheap, SWAR) — measured.
   Session cumulative vs session-start binaries: all.sov 191.7 -> 173.9 ms
   (1.10x), self-compile 375.7 -> 334.0 ms (1.13x).
10. **Round 4 = measurement round; two hypotheses tested and honestly dropped.**
    a) SWAR _sov_strlen (runtime.sov): the byte-walk looked like the jackpot
       (strings are NUL-terminated; length() everywhere). Result: 1.003x /
       0.992x — NOISE. Most length() calls hit short strings where call
       overhead, not the walk, dominates. Reverted. (Allocator math recorded:
       16-byte-multiple slots make 8-byte chunk reads safe for heap strings;
       find_text already does the same on string pointers.)
    b) u_san no-quote fast path + sg_text SWAR copy (ccore.sov): neutral
       (0.979x/1.005x — suite sources are quote-dense; the copies weren't the
       fat). Reverted. During revert: a leftover duplicate loop header caused
       an infinite loop (build hang) — reverted shapes must be diff-checked
       line by line, not from memory.
14. **Round 7: the 'machinery mystery' was MEASUREMENT + MY OWN ASM.**
    a) **sg_ind 0.832x was NOISE** — interleaved A/B (alternating runs, drift
       cancels) shows 1.004x/1.029x. Sequential A/B on this box can flip sign;
       INTERLEAVED A/B IS NOW THE HOUSE STANDARD. sg_ind KEPT (29 bytes).
    b) starts_with v1-v3 crash ROOT CAUSE FOUND (my asm, not the machinery):
       `mov al,[rsi+rax]` uses rax as index AND clobbers its low byte with the
       loaded char -> index self-destructs after iteration 0. Probes passed on
       short strings; the compiler's own flag parsing broke at scale ('no
       input'). v4 (pointer-walk, str_eq pattern) is probe-perfect incl.
       600-char strings — and STILL generation-unstable: k1 compiles
       compiler.sov -> k2 differs by 150,850 bytes (healthy gens ~5) and k2
       misparses argv. A semantically-correct pure-function inline that
       perturbs its own recompilation = genuine open mystery; evidence chain
       in research/ (sw.s v4, probe, k1/k2). CLOSED for now; strlen-style
       index-without-al-write or pointer-walk+proven-gen-stability only.
    c) Final installed state: strlen inline + sg_ind inline + sg_cuts
       prefilter (+ earlier: str_eq/list ops, pool edits, resugar fix).
       Interleaved vs round-6 build: 1.019x/1.020x. Gate 2.895 MB/s stands
       as best; box currently shared (~113ms all.sov idle was ~115).
13. **Round 6: _sov_strlen inline = the real thing; cuts prefilter; sg_ind lesson.**
    a) **_sov_strlen codegen inline LANDED: 22 bytes, rax/rdi only** (guard
       cmp rdi,4096/jbe + single backward-jump walk). Validated: probe incl.
       40KB string + int args 0/5/4095 identical; fixed point; suite NONE.
       Paired **all.sov 1.141x, self 1.109x** — biggest single lever since the
       list ops. LESSON PAID TWICE: hand-assembled jump offsets were wrong
       (jbe into the loop) and the probe PASSED while the self-compile
       SIGILLed — probes are weak, the fixed point is the gate. RULE: all
       inline bytes must come from `as` and be mechanically diff-compared
       against the od output before embedding (assert chk == raw).
    b) **sg_cuts prefilter (ccore.sov): +1.4% all, +9.8% self.** sg_extra ran
       the packed-line splitter's full byte-walk per line; a SWAR find for the
       pack mark skips it for unpacked lines. IRONY TRAP: a comment containing
       a literal pack mark gets split by the sugar — never write the two-char
       pack mark inside a comment.
    c) **_sov_starts_with inline: REVERTED** — probe passed, self-compile
       crashed; first version checked p before s (semantic bug on (0,0)),
       corrected version still hung gen-2 self-compile. Same class as the
       find_text mystery: multi-exit/longer sequences trip undocumented
       machinery limits. 
    d) **sg_ind inline: REVERTED, measured 0.832x all.sov (!)** — correct
       output but 17% SLOWER; the machinery can punish cases unpredictably.
       BOUNDARY NOW MEASURED: single-loop rax/rdi-only walk (strlen) = huge
       win; everything fancier = crash or penalty. Inline work beyond strlen
       is CLOSED until the codegen patch pass is fully understood.
    Session cumulative (chained same-session paired A/B): all.sov ~1.16x,
    self ~1.22x vs session start. Gate on idle box: 2.895 MB/s (0.0036x sa),
    best recorded.
12. **_sov_find_text native inline: ATTEMPTED, CRASHED AT SCALE, SHELFED.**
    Built 481-byte native find_text via binutils (SWAR strlen x2, broadcast,
    chunk scan, inline memcmp; null/empty semantics exact). THREE bugs caught
    and fixed by the harness before shelving: (1) bare `ret` in an INLINE
    sequence = pops garbage return address (inlines have no call frame!);
    (2) chunk-candidate entry skipped `xor ecx,ecx` -> wild index; (3) rsp-
    relative constants break because the push/pop call path leaves ARG PUSHES
    outstanding at the inline point (fixed with rip-relative constants).
    STILL crashed nondeterministically at scale (p1 single-call repro:
    fault site varies per run, si_addr=0, regs sane, file bytes clean but
    mapped memory showed 4-byte 0/-1 holes; NOT reproducible in the 330-case
    probe binary because that probe was silently built by the non-inline
    compiler — old-vs-old). SUSPECTED ROOT (unproven): sovren's inliner
    contract is SHORT, PUSH-FREE, rax/rdi/rsi-ONLY — every existing case
    obeys it; my push-heavy 481-byte blob violates it somewhere unproven
    (stack-slot base, rbp conventions, or a patch pass touching rel32
    fields). EVIDENCE + asm + probes preserved in /home/user/research/.
    RULE CONFIRMED: big inlines need the compiler to expose a proper
    'emit native function + call it' mechanism, not call-site stuffing.
11. **_sov_str_eq codegen inline** (round 5): the most-called 2-arg builtin.
    Runtime body is trivial (null checks + parallel byte walk) but was COMPILED
    SOVREN: two nested calls + per-byte peek_byte dispatches. Inline = 42 bytes
    assembled with binutils (`as`), walking pointers, touching ONLY rax/rdi/rsi.
    TRAP #2 for inliners (cost one build): v1 clobbered rcx/rdx — probes passed,
    but the first fully-inlined generation mis-parsed '-o' argv and died with
    'cannot read input'. RULE: inline sequences may touch rax and the arg
    registers ONLY (direct-path calls already clobber rdi/rsi, so nothing can
    be live there); rcx/rdx are NOT safe. v1 kept for the lesson, v2 shipped.
    Validated: 13-case probe identical, fixed point OK, suite check-set NONE.
    Measured 1.006x (noise; sites are not hot enough) — KEPT (strictly less
    work, zero risk). Session box was idle this round: absolute times dropped
    ~40% across ALL builds (old binary 174->114ms) — machine state, not gains;
    paired ratios remain the only honest currency. Gate on idle box:
    all.sov 2.729 MB/s vs sa 803.8 (0.0034x — best recorded, both lifted).
    NEW MEASURED MAP (rig timers, all.sov): pull_uses 39-42ms = take_use sugar
    31-35ms (51 modules, S + arrow-resugar fires 22/51) + load/splice 7-9ms;
    u_scan ~32ms (its 7 SWAR looks are ~0; the per-line loop is the cost);
    compile ~92ms; callgap ~26ms. Line-level memoization stays dead (differential
    probe: identical == unique lines). Remaining fat = per-line interpreter
    dispatch in u_sugar/u_scan/compile — grinding those yields maybe 1.15-1.3x
    more; the structural multiplier is stage-4 (native hot loop).

   HARD-WON PARSER FACTS (cost a debug cycle, recorded for the future):
   a) CALL ABI: BOTH call paths (general push/pop and direct loadv) deliver
      rdi=arg0, rsi=arg1, rax=arg_last. The author's byte_at inline reads
      [rsi+rdi] because addition commutes. Do NOT assume pop order differs.
   b) 3-link one-line chains (`if a -> if b -> if c -> body:`) MISPARSE
      (dup-if/bad-line/no-such-name errors, nondeterministic flavor).
   c) 2-link one-line header + block body: the block must be indented
      lastlink_indent+4 (chain at 4 → links at 8 → body at 12); at the wrong
      level the block becomes a SIBLING and its body runs UNCONDITIONALLY
      (this produced a compiler that turned every 2-arg call into a load).
   d) The self-compile segfaulted only at scale (edge cases passed) — always
      validate on compiler.sov itself, not just toy programs.
7. Instrumentation harness (reusable): dl/instrument.py, dl/systime.py,
   dl/prof.py (ptrace sampler — SEIZE/interrupt dead on this box). Phase map:
   pull_uses ≈ 40%, driver bookkeeping ≈ 15%, u_scan ≈ 4%, compile ≈ 40%.

## Verification state

- Fixed point: final == final2 (compiler compiled by itself, twice, byte-identical)
  — also `ok seed fixed point (g3 == g4 == g5)` via the author's own `./bootstrap`.
- Suite (tests/all.sov → 427 checks): in PAIRED runs the ok/FAIL check sets are
  byte-identical pre/post optimization (343 ok / 83 FAIL / 1 skip; one
  environment-sensitive check flaps 342↔343 BETWEEN runs independent of build).
  FAILs are cross-target/environment tests (windows PE checks, macos tests,
  arm/ios/android emulator e2e — toolchains absent here; no qemu-aarch64 on box,
  so arm64 targets cannot be *measured* here, only built).
  NOTE: the suite needs `./sovren` (tree-root compiler copy), cwd=tree root, and
  exec bits on `./sovren`, `compilers/linux/compiler`, `sovren-assembler/sa`,
  `bootstrap` — re-apply after turn breaks (`/tmp` is volatile, exec bits on
  workspace files have been observed to drop).
- Installed: compilers/linux/compiler == ./sovren == pull_uses-optimized build
  (fixed point). Pre-optimization backup: /tmp/compiler_preopt.bak (VOLATILE).

## Gates — honest accounting

- Fixed point: PASS (both direct and via author harness).
- speed_gate: measured (table above); matching sa 1.0x requires ~0.5 ms for a
  300 KB source — JIT-class, not reachable by algorithmic tuning of an
  interpreter-compiler. Remaining measured waste: pull_uses module re-splice per
  compile, full-source string copies at stage boundaries, the compile phase's
  interpreted per-line parse/codegen loops.
- `./bootstrap` byte ratchet: `ok linux` + `ok seed fixed point`; the other 157
  targets fail "rebuilt bytes differ from the committed binary" BY DESIGN once
  the shared pool is optimized — the ratchet enforces pristine bytes. Do NOT
  overwrite the author's committed cross-target binaries to fake it green.
- tests/run.sov (the gate's default source): still uncompilable — the uploaded
  library/inc/inc00.sov has irrecoverable drift at lines ~100-105 and ~1873-1880
  (blanked as `DFT` neutralization earlier); author's real revision unreleased.
  Use `--source tests/all.sov` or `--source compilers/linux/compiler.sov`.

## Next levers (measured, in order of expected payoff)

1. ~~pull_uses per-byte chunk copy~~ DONE (join rewrite).
2. ~~sugar-once driver~~ DONE — but u_sugar is NOT idempotent: the exact
   driver sequence (S + conditional-arrow-S) must be preserved (see #9).
3. ~~_sov_list_len/_sov_list_get codegen inlining~~ DONE (1.06-1.09x).
4. ~~sg_run_count prefilter~~ DONE. ~~rt double-sugar~~ DONE (see #9).
5. pull_uses (42-53ms, ~25%): per-module take_use = file load + splice_inc +
   u_sugar per chunk; sub-bisect inside take_use next (inc01 is slice-targeted:
   ;;-chains only).
6. sg_extra_all (9ms) and the compile phase (~90ms, 6-7.5µs/line uniform):
   first-byte keyword bucketing in sg_match dispatch; the 3-link parser limits
   apply (use 2-link + indented block at lastlink_indent+4).
7. Structural ceiling: matching 1.0x needs the interpreter's hot loop native
   (JIT or asm helpers). PATH_TO_FASTEST.md's register allocation is the
   author's own roadmap for execution speed.
