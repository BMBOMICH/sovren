# Next-phase plan

Two work items requested by the user.

- **Task A — Compiler completeness audit. DONE** — see `COMPILER_COMPLETENESS.md`.
- **Task B — `sa` assembler at the hardware limit.** Rephrased below after the
  user corrected the goal. **Not started.**

---

## Current state (baseline, 2026-09-29)

| fact | value |
|---|---|
| `compiler.sov` sources in the fleet | **155** |
| built `compiler` binaries in the fleet | **155** (1:1, none missing) |
| structurally validated (Task A) | **155 / 155 COMPLETE** |
| bootstrap | **159 steps**, `bootstrap clean` |
| `tools/targets_audit.py` | **320 passed / 0 failed** |
| test suite (`tests/run.sov`) | **227 passed / 0 failed / 4 skipped** |
| ledger | BLOCKED=0, DEFERRED=1, IMPLEMENTED=98, RUNS-AS-IS=5 |
| container classes recognised by the audit | 20+ (incl. `OMF166`, `HP-UX-SOM`, `EVM-bytecode`) |

### Task A outcome

Every backend compiles a probe and writes output, and every artifact now passes a
**structural** validator for its container class (not just a magic-byte check).
Five real defects were found and fixed:

| backend | defect |
|---|---|
| `riscv64-be` | `at64` emitted `[low32 BE][high32 BE]` — neither endianness; `e_entry`/`e_phoff`/`e_shoff` were garbage |
| `linux/sparc_v8` | `PT_LOAD` written in ELF64 field order inside an ELF32 header |
| `dex` | `checksum`/`signature` covered `[112,total)` instead of `[12,total)`/`[32,total)`, and ran before the fields they cover |
| `dos/mz-executable` | `e_cblp=38` declared a 38-byte load image in an 80-byte file |
| `firmware/usb-flashing-format` | UF2 `magicEnd` was `0x0AB433F0`, not `0x0AB16F30` |

None was visible to `tools/targets_audit.py`, which checks only leading magic
bytes. The validators live in `tools/validate_elf.py`,
`tools/validate_containers.py` and `tools/inventory.py`; `tools/completeness.py`
regenerates the report.

**What Task A does *not* claim:** structural completeness says the container is
well-formed and internally consistent. It does **not** claim the emitted *machine
code* is correct for the target ISA. Two ISA-level items remain open and are
recorded in the ledger: the PA-RISC `BV` encoding in `hpux`, and the C166 4-byte
`MOV reg,#data16` immediate byte order.

### Fleet composition

| group | members |
|---|---|
| top-level single-target backends | 6502, 8051, aix, android, arm64-mte, arm64-sve, arm64-sve2, c166, c-language, common-intermediate-language, csharp, dex, evm, extended-berkeley-packet-filter, ez80, fuchsia, harmonyos, hexagon, hpux, java-virtual-machine, javascript, llvm-intermediate-representation, pic16, pic18, plan9, qbe-intermediate-representation, riscv64-be, typescript, unified-extensible-firmware-interface, windows |
| `linux/` | 43 sub-targets + the shared ELF template |
| `apple/` | 14 (macos, macos-arm64, ios, ios-framework, ios-simulator, tvos, tvos-simulator, watchos, watchos-simulator, visionos, visionos-simulator, arm64e, arm64_32, macos-dynamic-library) |
| `webassembly/` | 10 |
| `firmware/` | 13 |
| `real-time-operating-systems/` | 11 |
| `operating-systems/` | 12 |
| `graphics-processing-units/` | 11 |
| `windows/` | 7 |
| `dos/` | 2, `boot/` | 1, `android/shared-object` | 1, `cil/portable-executable` | 1 |

---

# Task A — Compiler completeness audit

## The question

"were all compilers fully added like they werent partials and minimals and stubs?"

There are two distinct things that could be called "minimal", and they must be
separated before any judgement is made:

1. **Genuinely small containers.** A 6502 or 8051 raw image *is* ~80 lines: the
   whole artifact is `MOV A,#n; HALT`. A short backend here is correct and
   complete, not a stub. Line count alone must **not** be the metric.
2. **Stubs** — code that emits a header but omits structures the format
   requires, or hardcodes fields it should compute.

So the audit needs a **per-format completeness rubric**, not a line count.

## Completeness rubric (what "fully added" means)

| container class | required for "complete" |
|---|---|
| ELF32 / ELF64 | `e_ident` (magic, class, data, version, OSABI), `e_type`, `e_machine`, `e_version`, `e_entry`, `e_phoff`, `e_shoff`, `e_flags`, `e_ehsize`, `e_phentsize`, `e_phnum`, `e_shentsize`, `e_shnum`, `e_shstrndx`; `PT_LOAD` segments with correct `p_flags`/`p_align` covering text and data; section headers with valid `sh_type`/`sh_offset`/`sh_size`/`sh_link`/`sh_info`/`sh_addralign`/`sh_entsize`; a valid `.shstrtab`. Must survive `readelf -a` with no structural error. |
| PE / COFF | DOS stub + `PE\0\0`, `IMAGE_FILE_HEADER`, `IMAGE_OPTIONAL_HEADER` (magic 0x10b/0x20b), data directories, section table, `.text`/`.rdata`, relocations where the format demands them. |
| Mach-O | header, load commands, `LC_SEGMENT_64`/`LC_UNIXTHREAD`, valid `cmdsize` chain, code signature fields where applicable. |
| SOM (hpux) | 128 B header, exec aux header, space + subspace dictionaries, string table, XOR checksum = 0. **Done and verified.** |
| XCOFF64 (aix) | file header, optional header, section headers, loader structures. |
| Plan 9 `a.out` | 32 B `Exec`, `HDR_MAGIC` expansion handling. |
| FAR (fuchsia) | index, `DIR-----`, `DIRNAMES`, 4096-aligned content. |
| DEX | 112 B header, SHA-1 + Adler-32, all seven id sections, map list, data. |
| ZIP / HAP (harmonyos) | local headers, central directory, EOCD. |
| OMF166 (c166) | record framing, little-endian `RecLen`, per-record 2's-complement checksum. **Done and verified.** |
| raw images (6502, 8051, z80, ez80, evm, pic16, pic18) | correct opcode bytes for the ISA and a well-formed end. These are *expected* to be ~80 lines. |

## Method

1. **Enumerate** all 155 `compiler.sov` and pair each with its built binary.
2. **Classify** each by container class (extend `classify()` in
   `tools/targets_audit.py` where a class is missing).
3. **Apply the rubric above** with an automated structural validator per class,
   not a manual read. Where no local validator exists (`readelf`, `objdump`,
   `nm`), write one in Python against the format spec.
4. **Flag three outcomes per compiler:** `complete`, `partial` (named missing
   structures), `stub` (header only / hardcoded fields that should be derived).
5. **Record** every finding as a row in `IMPLEMENTATION_LEDGER.md` so the
   completeness claim is auditable rather than asserted.

## Known-suspect list to check first (from work already done)

These are places where I already know a backend is *narrower* than the format
allows. They are the first things to look at, and none of them is currently
documented as a defect:

| target | known narrowness |
|---|---|
| `hpux` | PA-RISC `BV`/branch-return encoding is unpinned. The backend emits `ldi n,%r28` + 3 NOPs and says so in a comment. A real PA-RISC epilogue is missing. |
| `c166` | uses the documented 2-byte `MOV Rw,#data4`; the 4-byte `MOV reg,#data16` immediate byte order is unverified, so 16-bit immediates are not emitted. |
| `riscv64` / `riscv64_v` | `readelf -S` prints "extends past end of file for section/program headers". Inherited from the LE template; reproduces identically on the pre-existing `riscv64`. **Not a defect introduced by `riscv64-be`**, but it *is* an open structural question about the shared template. |
| `pic24` / `dspic33` | not built (container magic unverified). |
| raw-image backends (6502, 8051, z80, ez80, evm, pic16, pic18) | verify each opcode against the vendor manual, and that the emitted sequence is a legal, terminating program — not just a plausible byte string. |

## Deliverables

- `COMPILER_COMPLETENESS.md` — one row per compiler, with class, rubric verdict,
  and any missing structures.
- A new `tools/validate_containers.py` (or an extension of
  `targets_audit.py`) that checks structure, not just magic bytes.
- Ledger rows for anything found `partial` or `stub`.

---

# Task B — `sa` assembler at the hardware limit

## What `sa` is

`sovren-assembler/sa` — a **self-hosted x86-64 assembler written in its own
assembly**. It is not a benchmark; it is a real tool, and it is the fast thing in
this workspace.

- source: `sovren-assembler/sa.asm` (419,050 bytes)
- binary: `sovren-assembler/sa` (57,724 bytes / 4 passes)
- built by fasm (the bootstrap, which stays the bootstrap) **and by itself** —
  `python3 t/selfhost.py` prints *"it assembles sa.asm to itself, byte for byte:
  self-hosted"*

## Where `sa` already is (measured, 2.7 GHz, process start included)

| shape | throughput |
|---|---:|
| `mov rax, rbx`, unique lines | **1.2–1.9 GB/s** |
| a line of comment | **1.4 GB/s** |
| `nop`, unique lines | 0.7–1.2 GB/s |
| `bench6` (4.2 MB of code) | 570–635 MB/s |
| a jump to a name | 258 MB/s |
| `db 0`, unique lines | 295 MB/s |
| labels and no code | **76 MB/s** |
| fasm, for comparison | 29.9 MB/s |

So `sa` is already **23.3x fasm** on `bench6`. The problem is not the average —
it is that **throughput varies by 25x depending on input shape**. Two shapes drag
the whole distribution down.

## The goal

**Every translation shape should run at the rate of the fastest shape** — i.e. the
assembler should be uniformly **memory-bandwidth bound** at ~1 GB/s+, with no
shape an order of magnitude below the rest. "Maximum the CPU allows" means: no
shape is limited by something other than reading and writing the bytes.

## The two known slow shapes (the actual work)

1. **Label insertion — ~120 ns a name, 76 MB/s.**
   The symbol table is memory bound. This is the single worst shape.

2. **The data path — a byte in, a byte out, per line.**
   295 MB/s on `db 0` lines. A per-byte loop where the fast shapes are not.

## Already tried and rejected — DO NOT RETRY

`STATE.md` is explicit that these were measured and discarded. Re-running them
wastes a session:

- **Large pages on a grown symbol table** — `madvise(MADV_HUGEPAGE)` after the
  mmap in `sa_sym_grow`. No gain at all (45 ms vs 47 ms on 400k names).
- **Growing the symbol table by four** — worse on short names (50 vs 46 ms),
  better only on twelve-byte ones; the memory does not pay.
- **Growing at half load** — clearly worse (65 vs 46 ms on 400k). A bigger table
  costs more cache than shorter probes save.
- **A symbol table sized from the length of the source** — tried long ago, kept
  in the comment on the zeroing in `_start`. A table eight times too large costs
  a cache miss on every name in it.

## Task B — landed: the symbol hash (Phase 0 found it, Phase 1 done)

Phase 0 (`t/shapes.py`, written this round) measures every input shape instead of
the two aggregate benchmarks, and it found the gap is far worse than `STATE.md`
recorded: **65x**, not 25x, with label insertion at 29.8 MB/s against comments at
1940 MB/s.

Ablation (`ret` at the top of `sa_sym_define`) showed the symbol insert is **97%**
of that time — 318 ms of 328 ms on 600k labels. A C model of the same algorithm
did the identical work in 34 ms, so the cost was not the table.

It was the **hash**. `sa_ihash` multiplied the name by `0x9e3779b97f4a7c15` and
shifted the product right by a *fixed* 32. For sequential names (`lbl0`, `lbl1`,
`lbl2`) the keys differ in one byte, so the product's bits 32..63 move by a
constant — the hash is an arithmetic progression:

| names | table | old hash | fib hash |
|---|---|---|---|
| 65536 `lbl%d` | 2^16 | **1000 slots used (1.5%), 200 names/slot** | 49047 (74.8%), 4.08/slot |

The fix is Fibonacci hashing proper — `>> (64 - log2 slots)` instead of `>> 32` —
which is the same one shift and is correct for any table size. Verified as good as
MurmurHash3's fmix64 at 2^16/2^20/2^22/2^24, at fmix64's cost with none of its
extra instructions.

**Measured (`t/ab.py`, interleaved runs, best of seven):**

| source | old | new | |
|---|---|---|---|
| bench | 3.40 ms | 3.39 ms | 1.00x |
| bench6 | 15.63 ms | 15.72 ms | 0.99x |
| mixed | 15.87 ms | 15.89 ms | 1.00x |
| allmiss | 15.87 ms | 15.85 ms | 1.00x |
| **lbl100k** | 32.02 ms | 15.85 ms | **2.02x** (31 → 62 MB/s) |
| **lbl600k** | 215.07 ms | 164.90 ms | **1.30x** (30 → 39 MB/s) |

**Gates:** `t/selfhost.py` 0 refusals and the second build byte-identical (64362
bytes); `t/audit.py` 0 things to look at; `t/regions.py` 0 of 2 out of step; and
all 11 benchmark sources produce byte-identical output to the old binary. The
fasm-comparison suites (`forms`, `isa`, `mnmonly`, `immwidth`, `addrmatrix`,
`sibrules`, `subset`, `ct`, `refuse`, …) **cannot run here — fasm is not in this
container**, so they are unverified for this change.

One bug was made and caught on the way: `bsr` was first run on the *mask*, whose
top bit is log2(slots)−1, so the shift came out one too high, half the table went
dead, and 600k labels took 80 seconds. `patch_hash3.py` is the fix; it is why the
`bsr` runs on `sym_slots`.

### Landed since: the rehash, gone

The symbol table is now **sized once from the source** instead of grown into. A
colon is a label definition and nothing else in a source sa reads, and counted
against every source in the repo the colon count is exactly the label count, so
the table is asked for once, at the size the source actually needs. Growing cost
a fresh mmap plus a re-place of every name at each doubling — 600k labels paid
four of those, ~860k re-places against 600k inserts, and with the rehash skipped
it measured as half the run. The colons are counted eight at a time (a byte at a
time cost 9 cycles a byte = 16 ms on a 4.7 MB source, more than the grows it
replaced).

**Against the build before either change:**

| source | before | after | |
|---|---|---|---|
| lbl600k (6.5 MB, 600k labels) | 264.93 ms / 24.5 MB/s | 114.34 ms / 56.7 MB/s | **2.32x** |
| lbl100k | 32.08 ms / 30.8 MB/s | 16.04 ms / 61.6 MB/s | **2.00x** |
| bench, bench6, mixed, allhit, allmiss | — | — | 1.00x (no change) |

**Shape spread, session start → now:** 65x → **15.6x**. labels only 29.8 → 69.9
MB/s, labels+code 43.2 → 108.8 MB/s.

### Landed since: the colon count became lazy

The count was right but it was paid everywhere. comment.asm is 4 MB of
comments: the count read all of it, found nothing, and the shape went
3415 -> 1945 MB/s -- **a 1.79x regression I had reported as "zero regression",
because comment was not in the A/B source list.** The fix was not to remove the
count but to ask at the right time: it now lives in a subroutine the *first
grow* calls, and the grow threshold is half-full rather than seven-eighths
until it has been asked. A source that never reaches 57344 names never asks.

| shape | eager count | lazy count | |
|---|---|---|---|
| comment (4 MB, 0 colons) | 1.93 ms | 1.16 ms | **1.67x** |
| mov rax,rbx | 3.53 ms | 2.40 ms | 1.47x |
| nop | 5.31 ms | 3.84 ms | 1.38x |
| allhit | 3.96 ms | 2.87 ms | 1.38x |
| bench / bench6 / mixed / db 0 / allmiss | -- | -- | 1.07-1.10x |
| lbl600k | 86.59 ms | 97.72 ms | 0.89x |
| lbl100k | 8.67 ms | 12.28 ms | 0.71x |
| L600000 | 72.73 ms | 81.07 ms | 0.90x |
| L200000 | 17.19 ms | 21.40 ms | 0.80x |

Four bugs got found building it, all of them the same shape of mistake -- a
patch that lands but is not the patch that was meant:

1. `rep stosd` was given `HASHSIZE` dwords instead of `HASHSIZE * 4` -- a slot
   is sixteen bytes, four dwords -- so three quarters of the table was never
   zeroed. Segfault on self-hosting.
2. Startup fell through into the new `cc_scan` subroutine and `ret`ed out of
   `_start`. Needs `jmp sym_ready` past it.
3. `cc_scan`'s answer went into `[sym_newsize]` but not into `rsi`, which is
   the length `mmap` takes it in.
4. Extracting the scan body with `block.index("cc_w:")` silently dropped the
   three constant loads (`r8`/`r9`/`r10`) that sat *above* `cc_w:` -- so the
   count ran on garbage and the table came out worse than doubling. The colon
   constant is absent from the binary, which is how it was caught.

And one fasm quirk worth writing down: the two-label form of the half-full
threshold (`sd_eighth:` / `sd_room:`) fails to assemble with
`symbol not defined: err_arg_len (line 10307)` -- an error about a *different*
symbol, in a part of the file the change does not touch. Inserting four `nop`s
at the same place builds fine, so it is the text, not the shift. The one-label
form (`shr rdx,3` / `shl rdx,2`) assembles.

### Landed since: the insert path, inlined

| shape | before | after | |
|---|---|---|---|
| lbl600k | 86.98 ms | 73.46 ms | 1.16x |
| lbl100k | 10.82 ms | 9.95 ms | 1.09x |
| L600000 | 76.47 ms | 74.11 ms | 1.03x |
| L200000 | 23.81 ms | 22.61 ms | 1.05x |

The saving was exactly the ~20 ns/label the three calls cost, which is the
first time a prediction and a measurement have agreed to the nanosecond on this
project.

**Where the insert path stands now, measured by ablation on the installed
build (interleaved, best of 11):**

| shape | total | parse floor | insert | reserved check | C insert floor |
|---|---|---|---|---|---|
| lbl600k | 73.06 ms / 121.8 ns | 12.34 ms / 20.6 | 101.2 ns | 4.5 ns | 22.8 ns |
| L600000 | 71.84 ms / 119.7 ns | 18.33 ms / 30.5 | 89.2 ns | 17.1 ns | 22.8 ns |
| lbl100k | 9.56 ms / 95.6 ns | 3.36 ms / 33.6 | 62.0 ns | 23.7 ns | 22.8 ns |

So the remaining gap is **2.3x on lbl600k** (73.06 ms against a floor of about
32 ms), and it splits into two things:

1. **The reserved-word check: 4.5-23.7 ns a label**, and it is the body, not the
   call -- inlining it bought 1.03x where removing it buys 1.17-1.33x.  Its cost
   is two table walks with data-dependent branches, which mispredict.  The fix
   is a one-load pre-filter: fold the name, index a bitmap by the low bits of
   the folded word, and skip both walks when the bit is clear.  The bitmap has
   to be built once at startup by walking `sa_idx`/`tbl` and `res_idx`/`res_tbl`
   the same way the check does, and the failure mode of getting that wrong is
   *accepting* a reserved word as a label, so the `refuse` and `opkind` gates
   are what stand behind it.
2. **The insert itself: 62-101 ns a label against C's 22.8.**  lbl100k is the
   telling one -- its table is 2 MB and L2-resident, so this is not memory
   latency, it is about fifty instructions with several data-dependent branches
   where C uses ten.  What is left to remove: the `sd_room` fill check (a
   compare against `cc_ran` on every name, for a question that was answered
   once), the double `cmp r11, 8` (once for the key, once for the hash, once
   more for the probe), and `inc qword [sym_use]`, which is a read-modify-write
   on one address that every name in the source serialises behind.

### Landed since: the reserved-word filter

The check was 17-24 ns a name and inlining it had bought only 1.03x, so the cost
was the body -- two bucket walks whose branches depend on the name.  A table of
a byte per low thirteen bits of the folded name now sits in front of them: one
load, one compare, and a name that is not a word skips both walks.  Built once
at startup by walking the same tables the check walks.

| shape | before | after | |
|---|---|---|---|
| lbl100k | 9.44 ms | 6.98 ms | **1.35x** |
| L200000 | 17.86 ms | 14.79 ms | **1.21x** |
| L600000 | 74.53 ms | 66.96 ms | **1.11x** |
| lbl600k | 80.19 ms | 78.67 ms | 1.02x |
| comment, mov, nop, db 0, bench, bench6, mixed, allhit, allmiss | -- | -- | 0.97-1.03x |

Two bugs found building it, both worth remembering:

1. **The builder went in under the small-source branch.**  The table zeroing is
   skipped for sources under 128 KiB (`jb sym_ready`), and the `call rs_build`
   was placed after it -- so a five byte source built no filter at all, every
   reserved word was accepted as a label, and nothing in the self-hosting test
   would have noticed.  Caught by testing `mov:` / `nop:` / `use16:` directly.
2. **It went in the middle of the text.**  Placed after `cc_scan`, it pushed the
   start of the run across cache lines, and two shapes with *no labels at all*
   -- allhit and `mov rax,rbx` -- got six to nine percent slower.  Moved to the
   far end of the text and both came back.  Code placement is not free.

**Where the insert path stands now (installed build, interleaved, best of 11):**

| shape | total | parse floor | insert | C insert floor |
|---|---|---|---|---|
| lbl600k | 78.67 ms / 131.1 ns | ~12.3 ms | ~110 ns | 22.8 ns |
| L600000 | 66.96 ms / 111.6 ns | ~18.3 ms | ~81 ns | 22.8 ns |
| lbl100k | 6.98 ms / 69.8 ns | ~3.4 ms | ~36 ns | 22.8 ns |

So the remaining gap on lbl600k is **~2.2x** against a floor of about 35 ms, and
it is now almost entirely the insert itself rather than anything around it.
What is left there: `inc qword [sym_use]` is a read-modify-write on one address
that every name in the source serialises behind; the probe writes
`[sym_probe0]` on every name for a question only the wrap-around needs; and the
slot is written in four stores where two would do.  Beyond that, software
prefetch -- hashing label *i+K*'s slot while inserting label *i* -- is the only
remaining idea that changes the asymptote rather than the constant.

### Landed since: software prefetch, tried twice

**Attempt 1 -- prefetch inside the insert path, ahead of the fill check.
Worth nothing: 1.00x on lbl600k.**  The reason is structural: the only work
between the prefetch and the probe is the fill check, nine instructions, and a
miss on a 16 MB table is ~84 cycles.  There is nothing there to hide behind.

**Attempt 2 -- prefetch the slot of the name on the *next* line, from
`sa_define`, once the colon is stepped over.  L600000 1.10x** (67.11 → 61.04 ms,
best of 31), everything else 0.98–1.03x, comment 0.995x at 31 reps.  This
overlaps the miss with a whole line of parsing instead of nine instructions,
which is the difference between a prefetch that helps and one that does not.

Two details that mattered: it looks for *a name with a colon after it*, because
that is a label and nothing else, so a source of instructions pays one compare
and no prefetch; and a name over eight bytes is hashed by `sa_ihash` rather than
the Fibonacci multiply, because its word is not its name — a prefetch that lands
on the wrong slot is worse than none.  fasm has no mnemonic for `prefetcht0` at
all, so it is emitted as `db 0x0f, 0x18, 0x08`.

**The verdict on prefetch, stated plainly: ~1.10x on one shape, neutral
elsewhere.**  That is consistent with the ablation, which says the insert costs
110 ns a label where C does the same hash, probe and write in 22.8 — so the
remaining gap is instruction count and dependency chains, not memory latency.
Prefetch was worth trying and it is worth the 1.10x it bought, but it is not the
2x the earlier estimate suggested, because the estimate assumed the gap was
misses and it is not.

### Still open on Task B

Ranked by what the measurements say is left:

1. **sa's own insert path — 5–7x.** A C program doing nothing but hash, probe and
   write the same names into a table of the same size runs at **27.7 ns/label**;
   sa runs at 191. Three calls per label (`sa_key`, `sa_reserved`, `sa_ihash`), a
   store-to-load forward through `[sym_key]` on every probe, `sa_here` behind a
   call and a `push`, and four separate field writes into the slot. None of it is
   hard; it is all inlining and keeping the key in a register.
2. **The line parse — 27–53 ns a line** with the insert removed entirely. `sa_trim`
   is called twice per label line, and `sa_word` once.
3. **The data path** — 305 MB/s on `db 0` lines, "a byte in, a byte out, per line".
4. **`ih_long`** — names over 8 bytes are hashed byte-by-byte with FNV; on a
   label-dense source that is most of the names. Now much less costly than it was,
   because the rehash that used to call it 860k times is gone.

## Phased plan

### Phase 0 — Measure every shape, then rank

`t/speed.py` exists. Extend it to report **all** shapes above in one run, best of
five, fresh process, and produce a ranked table. The work is prioritised by the
gap between each shape and the 1.2–1.9 GB/s ceiling, not by intuition.

### Phase 1 — Label insertion (the 76 MB/s shape)

The symbol table is memory bound at ~120 ns a name. Candidate directions to
*investigate and measure*, none of them on the do-not-retry list:

- reduce the per-name cache footprint (probe length, entry stride);
- separate the hot probe path from the cold insert path;
- prefetch the next bucket while hashing the current name;
- consider whether the hash itself is the cost rather than the memory.

Anything tried must be measured against the rejected variants above, on 400k
names, and kept only if it beats 46 ms.

### Phase 2 — The data path (the 295 MB/s shape)

A per-byte in/out loop. Investigate batching at the line or block level, and
measure whether the assembler's own AVX2 scan path (instruction family 26) can be
reused for the data path the way it already is for the scan path.

### Phase 3 — Re-verify

`sa`'s correctness gates are unusually strong and must all stay green:

| gate | what it proves |
|---|---|
| `t/selfhost.py` | sa builds itself; second build byte-identical to the first |
| `t/wholecmp.py` | bench, bench6, b4k, b12k text identical to fasm's |
| `t/forms.py` | 103/103 agree with fasm byte for byte |
| `t/isa.py` | 522 forms, 0 disagree; 35 names outside, all refused loudly |
| `t/mnmonly.py` | 317 forms agree, 0 differ |
| `t/immwidth.py` | 8041 cases, 0 differ |
| `t/addrmatrix.py` | 5880 addresses, 0 mismatch |
| `t/sibrules.py` | 0 mismatch of 5120 |
| `t/subset.py` | 262 cases: 156 inside, 55 outside, 51 refused by both, 0 bad |
| `t/ct.py` | 50004 named operands, bytes agree |
| `t/refuse.py` | 120/120 agree with fasm on what to accept |
| `t/regions.py` | 0 of 2 generators out of step |
| `t/audit.py` | 0 things to look at |

A speed change is accepted only when **self-hosting stays byte-identical** and
every gate above is still green. Report the honest per-shape number, and do not
describe a shape as fast because a cache was warm.

## Realistic expectation

`sa` is already near memory bandwidth on its fast shapes (1.4 GB/s on comment
lines), so the ceiling is real and close. The win available is **not** making the
fast shapes faster — it is lifting the 76 MB/s and 295 MB/s shapes toward the
ceiling. That is a 4–13x improvement on those shapes, and it is where the
"maximum the CPU allows" actually lives.

---

# Operational notes for the next session

- **Do not re-run the 5m40s test suite inside one shell command.** It was run
  twice back-to-back by accident and hung the turn. Run it once, capture the
  summary line, and stop. The suite's cost is dominated by ~155 fresh compile
  subprocesses.
- `tools/targets_audit.py` has a 120 s per-compile timeout and is flaky if run
  immediately after a ~45 s bootstrap. Leave idle time between them.
- Exec bits are stripped at every tool-call boundary — `chmod +x sovren
  sovren.exe bootstrap tools/fixmodes.sh` before running any workspace binary.
- `/tmp` is wiped between tool-call boundaries. Keep generator scripts in the
  workspace or re-create `/tmp/w`.
- `sovren.exe` is only selected as the windows target when the `-o` path ends
  literally in `.exe`; verify magic `4d5a` before installing.
- Rebuild `sovren`/`sovren.exe` after any `launcher.sov` edit, and verify
  byte-identity against a fresh rebuild before replacing.

---

# Task D — compiler speed (2026-09-30)

Target: every Sovren compiler matches `sa`'s translation speed. The shared
`library/inc/` pool is the right place to work because all 155 backends pull
from it.

## Landed this pass (see SPEED_ARCHITECTURE.md for the full write-up)

| change | files |
|---|---|
| `same(x,y)` -> `_sov_str_eq(x,y)`, `_sov_alloc(x)` -> `_sov_heap_alloc(x)` at every compiler-side call site | `library/inc/*.sov`, `library/ccore.sov`, `library/cx86.sov`, `library/carm.sov`, `compilers/linux/compiler.sov` |
| hoist `_sov_list_len` out of 34 loops, inline `_sov_list_get` as `peek_i64` (40 + 25 sites) | `library/ccore.sov`, `library/cx86.sov`, `library/carm.sov`, `compilers/linux/compiler.sov`, `library/inc/*.sov` |
| `sg_toks`: one `cut` per token instead of one `str_cat` per character | `library/ccore.sov` |
| `sg_sp`: one allocation + n byte writes instead of n `str_cat` | `library/ccore.sov` |
| `sg_numt`: fill one buffer from the tail instead of prepending digits | `library/ccore.sov` |
| `plain_name`: 256-entry table instead of 15 one-char string compares | `library/cx86.sov` |
| `num_value` memo 1 MB -> 8 MB | `library/ccore.sov` |

`compilers/linux/compiler` was rebuilt and installed
(md5 `b50f4f78c077d789c0808d1e709220d0`).

## Verification

- 5/5 corpus sources byte-identical against the pristine compiler.
- 13/13 sampled backends byte-identical (6502, 8051, z80, ez80, evm, pic16,
  msp430, avr, riscv64, arm64, windows, dos-mz, dex).
- Test suite: **640 passed, 0 failed, 14 not run**.
- Speed gate, best/median of seven: 926.167/981.097 ms -> 743.199/768.551 ms
  = **1.28x**. Expanded-throughput ratio 0.000756x -> 0.000876x sa.

## Dead ends recorded so they are not retried

- Hash indexes over `idx` (1, 16 and 1024 slots): all byte-identical, all
  slower on `tests/run.sov` (16x, 12x, 10x). Pointer-keyed caches thrash
  because the compiler alternates between ~13 lists and `_sov_list_add`
  returns a fresh pointer on growth.
- Hoisting `_sov_list_len` inside `idx` alone: 1.00x. The cost was the
  `same()` compares.
- Removing the `letter` memo: 0.86x.
- Enlarging the `letter` memo to 8 MB: 0.93x (cache misses).

## Constraint that shaped the work

`runtime.sov` is injected wholesale into every compiled program, so editing it
moves the bytes emitted for user programs. Every change above therefore lives in
compiler-side sources only, which is why byte-identity could be held throughout.

---

# Task D — second call-overhead pass (2026-09-30, later)

## The measurement that unlocked it

`letter` was 8% of runtime but a counter said it ran only 746 times. The
contradiction was resolved by attributing callers properly: sample RIP **and**
scan the stack for the first value inside the executable mapping (the prologue
pushes clobber `[rsp]`, so a naive return-address read returns a saved `%rbx`).

Answer: `letter` runs 4,595,365 times, and 68% of those come from the
string-literal scanner at `inc01.sov:652` -- one memo lookup per character to
answer "is this byte `(`, `)` or `,`".

## Landed

| change | files |
|---|---|
| literal scanner: `c: letter(inside, i)` + 3 `_sov_str_eq(c, "X")` -> one inlined byte load + 3 register compares | `library/inc/inc01.sov`, `library/inc/inc02.sov` |
| 14 more `letter(...)` -> byte compares (`sg_unparen`, `sg_stmt`, `sg_thresh`, `u_sugar`, `law_body`) | `library/ccore.sov`, `library/carm.sov`, `compilers/linux/compiler.sov` |
| `digit(letter(inn, 0))` -> `digitb(_sov_byte_at(inn, 0))` | `compilers/linux/compiler.sov` |

`compilers/linux/compiler` md5 `485978333de645d0e4f86ebfb50989fd`, then the whole
fleet was rebuilt and committed (`bootstrap clean`, 159 ok / 0 FAIL).

## Result

| | best | median |
|---|---:|---:|
| before this pass | 926.167 ms | 981.097 ms |
| after | 504.011 ms | 546.876 ms |

**~1.8-2.0x**, expanded-throughput ratio `0.000756x` -> `0.001145x sa`.
Verification: 5/5 corpus byte-identical, 155/155 backends byte-identical,
suite 640 passed / 0 failed / 14 not run.

## Two traps to remember

- The loop at `inc01.sov:652` captures `c` **before** the `i: i + 1` on the
  backslash path. Rewriting the punctuation tests to read the current index is
  wrong and segfaults.
- A failed pool experiment left `inc00.sov:112` modified; that stale edit, not
  the change under test, caused the next two segfaults. Restore pool files
  after every failed experiment.

---

# Task D — third call-overhead pass (2026-09-30, final)

## What was done

`letter` fell out of the top twelve after the operator scanners were fixed, so
the scan loops -- not the memo -- were the cost all along.

`fop` / `fopn` / `fop2` / `fop3` each ran `c: letter(e, i)` per character and
then only tested `c` against `(`, `)`, `*`, `/`, `%` or a parameter. The `c`
store and those tests live in four different pool files, so all of them had to
move together:

| file | change |
|---|---|
| `library/inc/inc00.sov:112` | `c: letter(e, i)` -> `c: _sov_byte_at(e, i)` |
| `library/inc/inc00.sov:90,92` | `_sov_str_eq(c, "(")`/`")"` -> `c = 40`/`41` |
| `library/inc/inc03.sov:880-883` | `_sov_str_eq(c, "*"/"/"/"%")` -> `c = 42`/`47`/`37` |
| `library/inc/inc04.sov:472-473` | `_sov_str_eq(c, a)`/`(c, b)` -> `c = _sov_byte_at(a, 0)`/`_sov_byte_at(b, 0)` |
| `library/ccore.sov` | two `_sov_list_len` loop conditions hoisted, two element reads inlined |

`compilers/linux/compiler` md5 `0b698f7bd8f44b425906e9d79f26ee91`; whole fleet
rebuilt and committed (`bootstrap clean`, 159 ok / 0 FAIL).

## Result

| | best | median |
|---|---:|---:|
| session start | 926.167 ms | 981.097 ms |
| now | 414.490 ms | 453.855 ms |

**2.16x median / 2.24x best**, expanded-throughput ratio `0.000756x` ->
`0.001548x sa`. 5/5 corpus byte-identical, 155/155 backends byte-identical,
suite 640 passed / 0 failed / 14 not run.

## Trap recorded

`fop2` compares `c` against its *parameters*, so a grep for
`_sov_str_eq(c, "` misses them. Changing `c` to an integer without also
rewriting those two sites segfaults -- that cost three consecutive failed
builds before the cause was found. When changing a shared pool variable's type,
enumerate every `_sov_str_eq(c,` / `same(c,` use, not just the literal ones.

## Pass 4 notes -- traps found while editing `runtime.sov`

1. **`d` in `_sov_alloc_small` is a descriptor INDEX, not a pointer.** The class
   table lives at `g_meta + c*8`; a descriptor's fields live at
   `g_meta + 1024 + i*128 + q*8`. Writing `peek_i64(d + 40, 0)` instead of
   `peek_i64(g_meta + 1024 + d*128 + 40, 0)` reads address 40 and segfaults on
   the first allocation. Compute `db: g_meta + 1024 + d * 128` once.

2. **The Windows backend's parser rejects a 3-deep `if A -> if B -> if C` chain
   whose last test has no inline body.** `compilers/linux/compiler.sov` accepts
   it; `launcher.sov --windows` fails with `Error: do not know these words /
   if g_alloc_dbg`. `runtime.sov` is injected into *every* backend, so a
   construct only the x86 front end tolerates still breaks the fleet. Flatten
   into early `return 0` guards in a helper function -- that parses everywhere.

3. **`commit_fleet.py` verifies, it does not install.** It writes
   `/tmp/w/fleet_map.txt`; the staged binaries are `/tmp/sov-boot-<name>` and
   must be copied to their committed paths by hand. Its map file has **no
   trailing newline**, so `while IFS=$'\t' read -r name path; do ...; done <
   fleet_map.txt` silently skips the last line -- which is `debugger ->
   sovren-dbg`. Always install that one explicitly and confirm with md5sum.

4. **Threads do not work in this sandbox.** Nine tests fail regardless of any
   change: thread slot round trip, thread join, thread six value spawn, thread
   eight way sum, mutex serialises, thread private context, thread free list
   recycles, context exhaustion falls back, eight threads churn. Diff the `FAIL`
   lines against a control run of the unmodified compiler before blaming an edit.
   A further five cross-backend tests (atomics/cffi/wipe/spawn builds) are flaky
   and fail intermittently.

5. `pkill -9 -f <name>` matches the bash command line itself and kills the
   shell running it (the tool then returns rc -1 with no output). Use
   `pkill -9 -x <name>` for exact process-name matches.

6. The corpus programs are output fixtures, not runnable tests -- they exit 6
   with no stdout. Do not try to verify semantically by running them; use the
   test suite and the bootstrap fixed point.

**Remaining open targets** (post pass 4): `_sov_substring` 7.40% (39 of 58
samples from fn@0x03ad5, which calls `_sov_strlen` + `_sov_substring`),
`_sov_list_get` 7.27%, `_sov_list_len` 5.36%, `num_value` 6.89% (31 of 54 from
`print_const`, which also computes `cut(arg, 1, length(arg))` twice per
negative-number constant). The string-compare owner at 9.18% and
`_sov_list_get`/`_sov_list_len` are the largest single remaining items.
