# PATH_TO_FLOOR — everything required for sovren to match best-written assembly, everywhere

Goal: for every program, from one portable source, on every supported CPU, sovren's output
matches the shortest machine code anyone could have written by hand — and leaves no witness
(no human artifact, no competing toolchain does better on anything measured).

Status legend: [x] exists already, [ ] to build. Nothing below is started unless marked.

Honest ceiling (applies to everyone forever): proving the TRUE floor on big programs is
undecidable. "Matched" is therefore defined operationally: every measurable opponent beaten
or tied, every known human artifact tied on small programs, provable minimality certificates
where exhaustiveness is possible. That standard is winnable; a stronger one does not exist.

---

## Track 0 — The referee (measure or it didn't happen)

- [x] **F1. Size-race harness — SHIPPED v62 turn.** `work/floor/size_race.py`: 6 programs x {sovren, gcc -Os dyn, gcc -Os static, tcc dyn}, every entrant EXECUTED and byte-compared; ledger `work/floor/size-ledger.json`. Corpus (toy → real, reuse speed-work corpus + conformance 13) ×
  toolchains (sovren, gcc -Os, tcc, +rustc/go/zig when installed) × arches (x86-64 now, arm64 later).
  Every artifact behavior-verified (outputs must match), sizes banked to a ledger, one command.
- [x] **F2 — SHIPPED.** `work/floor/tinyelf.py`: hello_asm 163 B, exit0_floor 129 B, count_asm 173 B — all executed-verified, deterministic rebuild = the bank. Known-optimal hand artifacts as tie targets:
  tiny-ELF family (we hold the 163 B hello, builder script in-session), plus shortest-known
  hand asm for a dozen small kernels (echo, cat, fib, fizzbuzz, strlen-family).
- [x] **F3 — SHIPPED.** `work/floor/lightness_gate.py`: floor-corpus + race + size-regression ratchet (baselines.json auto-ratchets down). WIRED INTO mkrelease.sh as a blocking step (release fails on regression). Privacy-gate-style one-command PASS table (sizes, ties, regressions),
  wired into mkrelease.sh. Extends the existing gate pattern; blocks releases on size regressions.

## Track 1 — Regime 1: small programs (provable ties)

- [x] **F4 — SHIPPED (v69 4f503ea5: + NOTE elision + dead-slot elision, HDR 320→232, hello 888 B; slide-reloc table bake fixed for dva — see LEDGER 11).** Text padto: 16 B below 64K text, else 4096 (page-exact tier unchanged); data VA diverges via dva (vaddr = BASE+pad+gfoff+gfoff%4096: congruence + page-disjointness + W^X all hold; dva=0 degrades exactly to old layout for large images). hello 4,248 -> 968 B. No flags. The 4 KB exact-page floor is our
  choice; keep it for normal/large images (safety/alignment/reproducibility), automatically pick
  minimal ELF layout below a size threshold. hello 4,248 B → few hundred B zone. No flags — heuristic.
- [x] **F5 — SHIPPED (audit).** hello 968 = 320 hdr (ELF64+4 phdr+NOTE) + 496 text (syscall-direct) + 152 data. Future micro: NOTE removable (-32 B -> ~936). GNU_STACK kept (NX). Minimal _start, syscall-direct exit/write paths, count every byte
  of startup stub in a small binary; shrink to floor. (What remains after F4 is this stub.)
- [x] **F6 — PROTOTYPE SHIPPED.** `work/floor/superopt.py`: size-layered exhaustive search, dominance-pruned, EXECUTION-verified via tiny-ELF probe; certificates = exhaustive-per-size-layer within stated domain. 0.2 s, 640 values. Compiler integration = next. Exhaustive/branch-and-bound search over
  instruction sequences for leaf kernels up to N instructions; emits the provably shortest form;
  certificate = search exhaustiveness. Runs automatically on qualifying code. Per-arch search backends.
- [~] **F7 — AUDITED:** rax_imm already xor-optimal for 0; push/pop small-const form REVERTED (red-zone clobber — LEDGER 7); rdi_imm's existing push/pop flagged for audit. Safe wins pending allocator work. Optimal constant synthesis (shortest
  mov/lea/add chains), shortest encodings (8-bit forms, short jumps, xchg-eax tricks), setcc/cmov
  over branches where smaller. Rule-complete for straight-line x86-64.

## Track 2 — Regime 2: real programs (win by measurement)

- [ ] **F8. Register allocator → graph-coloring grade**, with spill-cost model; current allocator
  audited first. The biggest single lever for big-program code density.
- [ ] **F9. Full addressing-mode + dataflow exploitation.** base+index+scale+disp everywhere it pays,
  lea folding, redundant load/store elimination, flag reuse, branch threading.
- [ ] **F10. Peephole engine with auto-mined rules**, each rule translation-validated (F16) —
  no hand rule ever ships unchecked.
- [ ] **F11. Whole-program size passes.** Identical-code folding (ICF), tail/epilogue merging,
  cross-function dead seams. We emit binaries directly, so linker-class passes are on us.
- [ ] **F12. Data lightness.** rodata/constant pooling, string interning, zero-init → bss elision,
  smallest correct relocation model.
- [ ] **F13. Runtime + library kernels to floor grade.** memcpy/str/print-path kernels are the
  most-linked code in every real binary; they get F6/F7 treatment first (highest leverage).
- [ ] **F14. Per-site calling conventions.** Static/leaf functions get custom conventions when
  measurably smaller (no ABI at boundary nobody crosses).

## Track 3 — Everywhere (arch/OS breadth)

- [ ] **F15. arm64 parity + per-arch superopt tables + per-arch size-parity gate.**
  SEQUENCED: starts only in the 0.1.0 finishing phases (standing rule — do not pull forward).
  Claim "everywhere" only when every supported arch wins or ties the matrix independently.
- [ ] **F16-OS. OS breadth beyond Linux** (macos/windows scaffolding already in tests/) —
  scope decided by 0.1.0 finishing phases, not by this roadmap.

## Track 4 — Correctness under shrinking (continuous, woven through F6–F14)

- [ ] **F17. Translation validation.** Every size pass proves output semantics == input semantics
  (or test-differential evidence where proof is impractical). Shrinking must never break behavior.
- [ ] **F18. Reproducibility + speed neutrality.** Byte-identical builds maintained through all new
  passes; speed gate re-run alongside lightness gate — size wins may not regress banked speed crowns.

## Rules compliance (binding, not items)

All of the above ships default-ON, automatic, per-site heuristics. Zero new user-facing knobs;
disclosure-only flags acceptable. No new dependencies inside sovren.

## Already on the field (assets this roadmap reuses)

[x] built-in dead-code pruning (prune_dead) • [x] unused-module GC linking (census-proven)
[x] exact-page segment emitter (becomes the large-image tier of F4) • [x] reproducible builds +
  byte-identity reference infra • [x] gate pattern + harness discipline from speed work •
[x] corpus + conformance suite • [x] 163 B tiny-ELF builder (Regime-1 tie target exists today)

## Order of attack

1. **F1→F3** referee first (no claims without it).
2. **F4+F5** — quick visible win: Regime-1 sizes collapse into the tie zone.
3. **F6+F7** — superoptimizer: provable ties on the floor corpus → "matches best-written asm"
   becomes a demonstrated fact on small programs.
4. **F8–F14** — the industrial grind for real programs, led by F13 (kernels) and F8 (regalloc).
5. **F15** when the user unpauses arm64 in the 0.1.0 finishing phases.
   F17/F18 run continuously from step 2 onward.

Honest sizing: F1–F5 days-scale; F6 bounded research (kernels only); F8–F14 the long grind;
F15 paused by standing rule. Regime-2 "matched" is re-certified per release via F3 — it is never
permanently closed, only ever green.
