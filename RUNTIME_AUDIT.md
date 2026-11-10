# Sovren Runtime Audit — invariant pass (L7, 2026-09-09)

Scope honesty up front: this is a systematic enumeration of every
runtime invariant/law with its enforcement mechanism and its test
evidence, plus an explicit risk register of what is *not* proven.
It is not a mathematical formal verification; where a claim needs
one, the row says so.

## Laws and how they are enforced

| # | Law | Mechanism | Evidence in battery |
|---|-----|-----------|---------------------|
| 1 | Small integers are never dereferenced as pointers | `_sov_strlen`/`_sov_substring` head-guard (`if s < 4096 → treat as empty/blank`) | every string use across 606 gates |
| 2 | A failed allocation returns 0, and no accessor writes through 0 silently | `_sov_alloc` contract + accessor guards | "zero returned … too quiet a way to fail" rule in `mem_zero` (returns dst); sbuf/bounds fail-closed |
| 3 | Private/wipe programs never leak through core dumps | compile-time statement scan (`private` / `wipe`) sets `need_priv`; emitted code calls `prctl(PR_SET_DUMPABLE,0)` (pass: line-matched statements, not substrings — the comment-class false trigger was found and removed) | suite's `private` gates + compile scan in `compile source:` |
| 4 | Plans that copy data copy exactly, with checked extents | `bounds.sov` check-on accessors (default live) | "bounds:*" + sbuf overflow gates |
| 5 | Lists grow only by capacity-doubling reallocation; never write past `cap` | `_sov_list_add` (*table: [cap,len,slots]*) | every list use in the suite (kanban/gantt/tui/zoo etc.) |
| 6 | Threads see only one shared mapping; guest page is the only boundary crossing | spawn/join control blocks; `x86` emulator guest-page rule | "windows PIE … at slid bases", "thread … shared-page" gates |
| 7 | The guest emulator refuses to run a page that is not executable and to write a code page | `x86` emulator page checks (emu real memory / code page refuses writes / data page refuses runs) | `emu *` gates |
| 8 | Compiled output keeps literals read-write / code read-execute; no string lives in executable memory | two-LOAD ELF layout in `write_elf` ("e_ident rider is gone") | "windows PIE …" structural gates + linux ELF coexist checks |
| 9 | Absolute addresses travel in one relocation table; nothing absolute hides in code | patch-list walk, counted before addresses are chosen | "windows PIE carries a .reloc … / blocks fill the table exactly / random base" |
| 10 | Indirect-branch targets are endbr64; binaries declare IBT | cx86 prolog passthrough + GNU property note in every linux ELF | three cet gates |
| 11 | Secret comparisons never early-exit | `ct_eq` everywhere tag/password/tag-sized values meet; x25519 ladder swap is a masked select | hmac_verify, x25519 vector, auth/chachapoly gates |
| 12 | Raw memory / hardware access is greppable and machine-flagged | `--unsafe` lint (line `# unsafe`, file `# unsafe-module`, block `unsafe:`) in all five compilers | 8 lint/block gates |
| 13 | Error diagnostics carry the original user line numbers through every transform | u_prep rewrites 1:1 by line count | block-gate error-position checks (lint lists exact line) |
| 14 | The compiler never emits unknown words silently | codegen refuses with named task and file:line | "do not know these words" behaviors across suite years |

## Risk register (open by admission, not accident)

- **No formal proof engine** was applied; laws are enforced by construction
  and regression-guarded by 606 gates, not verified by a prover.
- **AES is table-based**: documented non-constant-time vs cache channels
  (fenced in aes.sov; chachapoly is the timing-safe default).
- **Shadow stack** (return-address protection) requires OS-level SHSTK
  support; IBT is delivered. Windows `.so`/PIE IBT and ARM BTI are rows.
- **The compiler's own source lint surface**: `unsafe:` syntax is new;
  marking the *kernel's* 5.6k-site inventory mechanically is the next
  migration row (inventory + ratchet already exist).
- **Sandbox-external determinism**: qemu runs depend on the host's TCG
  exactness; two-boot green runs on one class of machine.

## Sweep method used for this pass

Statement-level inventory (the same approach as the 68,393-site unsafe
inventory), plus targeted inspection of: allocation/strlen/substring
guards, list growth, thread clone-refusal fallback, ELF layout tables,
relocations, the CET note, crypto compare paths, and the u_prep rewrite
(byte-level, allocation-free, provably terminating by branch coverage).
