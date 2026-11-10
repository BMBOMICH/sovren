#!/bin/bash
# bench.sh - the speed ledger for the sa-parity phases. Min-of-9 wall time
# per compile (EPOCHREALTIME us), same-session sa reference (sa assembling
# its own source), plus the loc12k cliff probe. Same synthetic shapes as
# sc/bench.sh so numbers compare across the whole effort.
# usage: ./bench.sh [candidate]   default: ../../compilers/linux/compiler
# NOTE: sa takes its output as positional argv[2]; it does NOT accept -o.
#       Passing -o would create a literal file named -o in the cwd.
#       --prof endpoints are nested aggregates, never an exclusive sum.
#       Every candidate row reports input AND flat-expanded bytes (C.32c/C.34);
#       the MB/s column is input-byte based, never a mix of the two.
set -u
cd "$(dirname "$0")/../.."
CAND=${1:-compilers/linux/compiler}
SA=../sovren-assembler/sa
SASRC=../sovren-assembler/sa.asm
T=tests
TMP=${TMPDIR:-/tmp}/sap_bench
mkdir -p "$TMP"

min9() {
    local best=999999999 t0 t1 d i
    for i in 1 2 3 4 5 6 7 8 9; do
        t0=${EPOCHREALTIME/./}
        "$@" >/dev/null 2>&1
        t1=${EPOCHREALTIME/./}
        d=$((t1 - t0))
        [ $d -lt $best ] && best=$d
    done
    echo $best
}
# Flat-expanded byte count for the candidate (one extra cold --flat compile).
expanded_of() { # path exe
    local path=$1 exe=$2
    if [ "$exe" = "$SA" ]; then echo "n/a"; return; fi
    rm -f "$TMP/expanded.txt"
    if timeout 300 "$exe" "$path" --flat -o "$TMP/expanded.txt" >/dev/null 2>&1 \
       && [ -f "$TMP/expanded.txt" ]; then
        stat -c %s "$TMP/expanded.txt"
    else echo "n/a"; fi
}
row() { # name path cmd...
    local name=$1 path=$2; shift 2
    local bytes us exp
    bytes=$(stat -c %s "$path")
    exp=$(expanded_of "$path" "$1")
    us=$(min9 "$@")
    awk -v n="$name" -v b="$bytes" -v e="$exp" -v u="$us" \
        'BEGIN { printf "%-18s %10d bytes expanded=%s %9d us %10.2f MB/s (input)\n", n, b, e, u, b / (u / 1e6) / 1e6 }'
}

# ---- synthetic sources (same shapes as sc/bench.sh) --------------------
awk -v NV=12000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    v" i ": " (i == 0 ? 1 : "v" (i-1) " + 1")
    for (i = 0; i < n; i++) print "    print v" i
    print "    return 0" }' > "$TMP/vars512k.sov"
awk -v NV=100000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    v" i ": " (i == 0 ? 1 : "v" (i-1) " + 1")
    for (i = 0; i < n; i++) print "    print v" i
    print "    return 0" }' > "$TMP/vars4m.sov"
awk -v NV=24000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    r: f" i "()"
    print "    return 0"
    for (i = 0; i < n; i++) { print "f" i ":"; print "    return " i } }' > "$TMP/fns1m.sov"
# loc12k: the segfault-cliff shape (12000 distinct locals, no prints)
awk -v NV=12000 'BEGIN { print "main:"
    for (i = 0; i < NV; i++) print "    v" i ": " i
    print "    return 0" }' > "$TMP/loc12k.sov"
# loc100k: sc's 100k-locals stress (old compiler expected to die; sc eats it)
awk -v NV=100000 'BEGIN { print "main:"
    for (i = 0; i < NV; i++) print "    v" i ": " i
    print "    return 0" }' > "$TMP/loc100k.sov"

# sanity: a synthetic that segfaults is the cliff, not speed - never time it
ok_synt=""
for s in vars512k vars4m fns1m loc12k loc100k; do
    timeout 300 "$CAND" "$TMP/$s.sov" -o "$TMP/out" >/dev/null 2>&1
    rc=$?
    if [ $rc = 0 ]; then ok_synt="$ok_synt $s"; else echo "NOTE $s.sov: candidate rc=$rc (cliff/refusal - not timed)"; fi
done

echo "==== candidate, real sources (min-of-9) ===="
row floor-hello     "$T/hello.sov"                    "$CAND" "$T/hello.sov"                    -o "$TMP/out"
row self-compile    compilers/linux/compiler.sov      "$CAND" compilers/linux/compiler.sov      -o "$TMP/out"

echo
echo "==== candidate, synthetic large sources (min-of-9) ===="
for s in $ok_synt; do
    row "$s" "$TMP/$s.sov" "$CAND" "$TMP/$s.sov" -o "$TMP/out"
done

echo
echo "==== sa, its own source (same-session reference) ===="
row sa-on-sa.asm    "$SASRC"             "$SA" "$SASRC" "$TMP/sa_out"

echo
echo "==== the locals cliff ===="
timeout 300 "$CAND" "$TMP/loc12k.sov"  -o "$TMP/out" >/dev/null 2>&1; echo "loc12k  rc=$? (139 = the old segfault cliff)"
timeout 300 "$CAND" "$TMP/loc100k.sov" -o "$TMP/out" >/dev/null 2>&1; echo "loc100k rc=$?"
