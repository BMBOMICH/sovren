# sa-parity work — baseline (2026-11-07)

The four-phase plan: make the real compiler (compilers/linux/compiler.sov,
in place) match sa's compile speed in every dimension. Gates for every step:

- `oracle.sh` — all 40 tests/*.sov: compile rc + stdout (timing-masked)
  + ELF byte-identity vs work/saparity/oracle-frozen (md5 ef33ce19...,
  the S25 fixed point). Current: 24 pass + 16 refuse-parity, 0 FAIL.
- `fixedpoint.sh` — g2 == g3 == installed (md5 ef33ce19). Current: OK.
- `bench.sh` — the speed ledger, min-of-9, same-session sa reference.

## Baseline numbers (this machine, this session)

| shape | old compiler | sa same-session | ratio |
|---|---|---|---|
| floor (hello.sov 191 B) | 3267 us | ~1181 us (recorded) | 0.36x |
| self-compile (402 KB) | 168.7 ms = 2.38 MB/s | sa-on-sa.asm 3.57 ms = 123.2 MB/s | ~1/52 rate |
| fns1m (950 KB, 24k fns) | 143.9 ms = 6.61 MB/s | — | ~1/19 rate |
| vars512k (12k locals) | SEGFAULT rc=139 | compiles ~113 MB/s (sc ref) | cannot run |
| vars4m (100k locals) | SEGFAULT rc=139 | compiles ~115-124 MB/s (sc ref) | cannot run |
| loc12k / loc100k | SEGFAULT rc=139 | sc eats 100k locals | cannot run |

The flat-rate picture from the earlier census (~3.6 MB/s on non-crashing
shapes, ~12 heap allocs per source byte) plus the cliffs: the old compiler
does not merely lose to sa, it cannot compile the vars shapes at all.

sa reference this session: sa-on-sa.asm 439992 B in 3572 us = 123.18 MB/s.

## Phase order (approved plan)

1. Stop per-byte allocation: heap strings/lists -> (offset,length) views
   into the single source buffer (1.76M allocs on a 147KB file -> single
   digits).
2. Three passes into one: read once, parse once, emit while parsing,
   forward references patched at the end (sa's shape).
3. Fix the name table: short names inline in the hash slot, pre-size by
   file length (kills the 12k-locals segfault cliff).
4. Everywhere-audit: small-file floor, real library, 4MB synthetic, deep
   functions, same-session sa, each dimension >= sa.

## Update 2026-11-07 evening (phase 1 quadratics dead, see SESSION_2026-11-07_PHASE1_QUADRATICS.md)

- BOTH synthetics walls root-caused and killed: st_var/st_expr's
  list_idx(st_vars) linear scan (now an stv_* hash memo, complete,
  no fallback) and lord_build's O(n^2) frequency insertion (now a
  (score desc, arrival asc) merge sort, <32 threshold keeps tiny
  bodies on the classic insert; _sov_lord_build2 migration rename).
- loc100k 15.2 s -> 173 ms (87x), vars4m 15.3 s -> 339 ms (45x),
  loc12k 239 -> 21.5 ms (11x), fns1m/self/deepfns 1.0x (no
  regressions; deepfns' 24% lord/stv-scaffold regression was caught
  by the A/B and fixed). Scaling in locals is linear now.
- Walk-path cuts: st_expr trim-exact strip fast path; lines_of_fast
  byte-loop twin replaced by a SWAR C blob (_sov_lines_of_fast).
- New fixed point 7d930fd5; oracle 24+16+0; outputs byte-identical
  on loc/vars/fns shapes; bench cliff probes loc12k/loc100k rc=0.
- NOT at sa anywhere yet (self 2.01 MB/s vs sa 115.3 same-session):
  phase 2 pass fusion is the lever; walls recorded in the session
  note (st_node adjacency allocs, per-function overhead, lsh twins,
  floor).

## Update 2026-11-07 (session: phase 3 landed, see SESSION_2026-11-07_PHASE3_NAME_TABLE.md)

- Phase 3 COMPLETE: pre-sized name table (pow2 >= srclen/12, floor 16384),
  separate keys/tags arrays, 32-bit gen/idx packing, growth valve.
  Migration bootstrap: lsh_add->lsha2, lsh_find_s->lshf2, reg_slot->regslot2
  (the old binary's baked twin whitelist matches by task name).
- The >65536 wall root-caused OUTSIDE the name table: the cx_read/st_build
  blob arenas allocated a fixed 1MiB chunk for oversized requests (the
  131k-line list growth ran 16 bytes past); both fixed to max(n, AR_CHUNK).
- vars4m: SEGFAULT -> compiles + runs (output verified). loc100k: 26.5s -> 15.0s.
- The new lsh twins are PARKED (lord/home divergence, forensics in the
  session note); the interpreted bodies are certified. Cost: ~13ms on bw.
- New fixed point ea609674; oracle 24+16+0; fixed point one shot.
- Phase 1 census (self-compile): 97,090 allocs — bw 64.7k / C1 24.9k /
  c0-parsed 5.4k phase-attributed. everywhere-audit.sh landed (phase 4 lanes).
- NOT yet at sa anywhere (self 2.10 MB/s vs sa 138 same-session): phases 1-2
  remain the structural lever, untouched beyond the census.
