# sa-parity work — session 2026-11-07 (phase 3 + the real 65536 wall)

Deliverable: `sovren-tree-2026-11-07-v8.zip` — the full tree, certified
compiler `ea609674` (md5) installed, oracle 24 pass + 16 refuse-parity +
0 FAIL, fixed point g2 == g3 == installed.

## What was asked

The four-phase sa-parity plan: (1) stop per-byte allocation — heap strings
and lists become (offset,length) views into the one source buffer; (2)
collapse the three passes into one — read once, parse once, emit while
parsing, forward names patched at the end; (3) fix the name table — short
names inline in the hash slot, tables pre-sized from the file length, the
12k-locals cliff gone; (4) the everywhere-audit against sa — tiny floor,
real library files, 4MB synthetics, deep functions, every number >= sa,
oracle and fixed point still green.

## What landed (phase 3, complete + one bonus root-cause)

1. **The name table redesign (cx86_p3.sov).** `lh_alloc` pre-sizes slots
   = pow2 >= `lh_srclen`/12 (floor 16384, so both arrays stay >64KiB =
   fresh zero-filled mmap even for tiny files); keys and tags are separate
   arrays (`lh_tab`/`lh_tgs`); the tag packs `gen<<32 | idx+1` — the old
   16/16 packing wrapped idx into gen past 65536 live locals; `lh_grow`
   doubles and rehashes the current generation as the safety valve.
   `lh_srclen` is a new file-level global seeded from `u_srclen` in main;
   the other x86 backends leave it 0 and take the floor.
2. **The migration bootstrap.** The old binary's baked twin whitelist
   matches by task name, so the change renames `lsh_add`->`lsha2`,
   `lsh_find_s`->`lshf2`, `reg_slot`->`regslot2` (112 sites) — otherwise
   the old binary plants its OLD twins into the first new generation and
   it segfaults on the layout mismatch. `emit_nt_reg_slot`'s baked
   `calln("lsh_find_s")` is why reg_slot had to rename too.
3. **The real >65536 wall was NOT the name table.** A 70k-locals
   differential probe (adds + finds + stale-gen re-adds, `--bare
   --unsafe`, zero failures) cleared lh — then the crash registers
   pinned it: the cx_read and st_build blob arenas allocate a fixed 1MiB
   chunk even when the request is bigger, so the 131k-line list growth
   (16+131072*8 bytes) ran 16 bytes past its chunk into the allocator
   guard page. vars4m died exactly there (write at pool+0x100000, list
   len 131070 = 2*65535; cliff measured 65530-ok / 65540-crash). Both
   `ar_grow`s now take the request and allocate max(n, AR_CHUNK) like
   native_c0parse.c already did.
4. **The new lsh twins are parked, not landed.** Both were rewritten for
   the phase-3 layout (mask/slots stashed at [rbp-0x30]/[rbp-0x38] under
   the twin wrapper's saved regs, r13 probe counter, r15 tags base),
   byte-verified against a capstone simulation of the emit DSL, and they
   pass the differential probe — but real compiles diverge through the
   lord-seeding/register-home machinery (homed locals spill to frame
   slots, then undeclared-name cascades in runtime compiles). The twins
   are disabled in `try_native_body`; the interpreted bodies are the
   certified path. The shadow warnings leave with them: the certified
   binary's lsh path never warned (the old twins bypassed
   `lsh_shadow_warn`), and the interpreted bodies warning changed
   refuse-parity stdout (addons/run each gained two).

## Measured effect (this session's gates)

| shape | before | after |
|---|---|---|
| vars4m (100k locals + 100k prints) | SEGFAULT rc=139 | **compiles + runs, output verified** (15.4s) |
| loc100k (100k locals) | 26.5s | **15.0s** |
| loc12k / loc5040 / loc7k / vars512k | green | green |
| oracle (40 tests) | 24+16+0 | 24+16+0 |
| fixed point | 13c1aaee | ea609674 (converged one shot) |

Speed cost of the parked twins: self-compile 165ms -> 199ms (~13ms of it
on bw, the interpreted lsh calls). Recorded as the twin re-landing debt.

## The everywhere-audit (phase 4, run honestly — NOT yet at sa)

Same-session sa references: sa-on-sa.asm 138.32 MB/s, sa tiny-file floor
575us. Candidate, min-of-9:

| lane | sovren | verdict vs sa |
|---|---|---|
| tiny floor (28-191 B) | 2866-3332 us | not matched (~5-6x) |
| real library files (bigint/tls/suite/x86) | 0.48-4.04 MB/s | not matched |
| 4MB synthetics: vars4m / loc100k / fns1m | 0.26 / 0.12 / 7.33 MB/s | not matched; **no crashes anywhere** |
| deep functions (1500 fns + depth-60) | 8.62 MB/s | not matched |
| self-compile (402 KB) | 191.7ms = 2.10 MB/s | not matched (~66x) |

The bar "every number >= sa" needs phases 1-2; both are data-armed:

## Phase 1 census (measured this session, self-compile)

97,090 heap allocations total (the historical 1.76M/file was already cut
by the blob arenas). Phase-attributed:

| phase | allocations | dominant cost |
|---|---|---|
| bw (walk body codegen) | 64,658 | per-statement lists/strings |
| C1 (cx_read sugar) | 24,933 | T_CUT/T_STRIP/T_CAT*/T_LISTS/T_ONE table calls |
| c0-parsed | 5,351 | parse tables |
| 1-rt-loaded | 1,242 | runtime load |
| everything else | < 1,000 | — |

Attack order for phase 1: convert the cx_read blob's remaining
table-called allocating helpers to in-blob arena mirrors (the mirrors
already exist for cut/strip/toks/cat — the rest need byte-exact C
ports), then the bw walk-side lists.

## Recorded next walls (honest)

1. The 100k-locals shapes compile correctly but at 0.12-0.26 MB/s
   (~155us per local — an O(n^2) in the lord/preseed/frame-patcher path;
   not in lh, the probe cleared it).
2. The lsh twin re-landing (lord/home divergence root-cause; the
   ~13ms/7% self-compile cost rides on it).
3. Phase 1 (the census above) and phase 2 (pass fusion) — the ~50x gap
   to sa is still the allocation-and-passes restructuring.

## How to verify (from the tree root)

    bash work/saparity/oracle.sh                     # 24+16+0
    bash work/saparity/fixedpoint.sh                 # g2==g3==installed
    bash work/saparity/bench.sh                      # speed ledger
    bash work/saparity/everywhere-audit.sh           # the phase-4 lanes
    md5sum compilers/linux/compiler                  # ea609674...
