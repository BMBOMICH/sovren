#!/bin/bash
# everywhere-audit.sh - the sa-parity phase-4 lane audit, same session.
# Lanes: tiny-file floor, real library files, 4MB synthetics, deep functions.
# Every lane runs the candidate and a same-session sa reference; the sa
# reference for lanes without an .asm equivalent is sa on its own source
# (rate only). Min-of-9 wall time, cliff-guarded (a segfault is never timed).
# sa output is positional argv[2] (no -o). This audit now reports BOTH input
# bytes and flat-expanded bytes on every candidate row (C.32c / C.34); sa rows
# print expanded=n/a because sa has no --flat mode. Never mix the two rates.
# --prof endpoints are nested aggregates, never an exclusive sum (C.32e).
set -u
cd "$(dirname "$0")/../.."
CAND=${1:-compilers/linux/compiler}
SA=../sovren-assembler/sa
SASRC=../sovren-assembler/sa.asm
TMP=${TMPDIR:-/tmp}/sap_audit
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
# Flat-expanded byte count for the candidate. One extra cold --flat compile;
# never used as a throughput denominator here (that would mix C.34 units).
expanded_of() { # path exe
    local path=$1 exe=$2
    if [ "$exe" = "$SA" ]; then echo "n/a"; return; fi
    rm -f "$TMP/expanded.txt"
    if timeout 300 "$exe" "$path" --flat -o "$TMP/expanded.txt" >/dev/null 2>&1 \
       && [ -f "$TMP/expanded.txt" ]; then
        stat -c %s "$TMP/expanded.txt"
    else
        echo "n/a"
    fi
}
row() { # name path cmd...
    local name=$1 path=$2; shift 2
    local bytes us rc exp
    bytes=$(stat -c %s "$path" 2>/dev/null || echo 0)
    exp=$(expanded_of "$path" "$1")
    "$@" >/dev/null 2>&1; rc=$?
    if [ $rc -ge 128 ]; then
        awk -v n="$name" -v b="$bytes" -v e="$exp" -v r="$rc" \
            'BEGIN { printf "%-24s %10d bytes expanded=%s  CRASH rc=%d\n", n, b, e, r }'
        return
    fi
    us=$(min9 "$@")
    awk -v n="$name" -v b="$bytes" -v e="$exp" -v u="$us" \
        'BEGIN { printf "%-24s %10d bytes expanded=%s %9d us %10.2f MB/s (input)\n", n, b, e, u, b / (u / 1e6) / 1e6 }'
}

echo "==== lane 1: tiny-file floor (min-of-9) ===="
printf 'main:\n    print 1\n    return 0\n' > "$TMP/tiny.sov"
row tiny-30B          "$TMP/tiny.sov"   "$CAND" "$TMP/tiny.sov" -o "$TMP/out"
row floor-hello       tests/hello.sov   "$CAND" tests/hello.sov -o "$TMP/out"
printf 'main:\n    x: 1\n    return 0\n' > "$TMP/t2.sov"
row tiny-bare-28B     "$TMP/t2.sov"     "$CAND" "$TMP/t2.sov" --bare -o "$TMP/out"

echo
echo "==== lane 2: real library files (min-of-9) ===="
for f in library/bigint.sov library/tls.sov library/suite.sov library/x86.sov; do
    [ -f "$f" ] || continue
    row "$(basename $f .sov)" "$f" "$CAND" "$f" -o "$TMP/out"
done

echo
echo "==== lane 3: 4MB synthetics (min-of-9, cliff-guarded) ===="
awk -v NV=100000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    v" i ": " (i == 0 ? 1 : "v" (i-1) " + 1")
    for (i = 0; i < n; i++) print "    print v" i
    print "    return 0" }' > "$TMP/vars4m.sov"
awk -v NV=100000 'BEGIN { print "main:"
    for (i = 0; i < NV; i++) print "    v" i ": " i
    print "    return 0" }' > "$TMP/loc100k.sov"
awk -v NV=24000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    r: f" i "()"
    print "    return 0"
    for (i = 0; i < n; i++) { print "f" i ":"; print "    return " i } }' > "$TMP/fns1m.sov"
row vars4m            "$TMP/vars4m.sov" "$CAND" "$TMP/vars4m.sov" -o "$TMP/out"
row loc100k           "$TMP/loc100k.sov" "$CAND" "$TMP/loc100k.sov" -o "$TMP/out"
row fns1m             "$TMP/fns1m.sov"  "$CAND" "$TMP/fns1m.sov" -o "$TMP/out"

echo
echo "==== lane 4: deep functions (min-of-9) ===="
# deep nesting: expressions nested 60 deep inside a function, 1500 fns
awk 'BEGIN {
    print "main:"
    print "    r: deep(60)"
    print "    print r"
    print "    return 0"
    print "deep n:"
    print "    if n < 1"
    print"         return 1"
    print "    return deep(n - 1) + deep(n - 1)"
    for (i = 0; i < 1500; i++) { print "g" i " a b c:"
        print "    x" i ": a + b + c + " i
        print "    return x" i " + " i } }' > "$TMP/deepfns.sov"
row deepfns           "$TMP/deepfns.sov" "$CAND" "$TMP/deepfns.sov" -o "$TMP/out"
row self-compile      compilers/linux/compiler.sov "$CAND" compilers/linux/compiler.sov -o "$TMP/out"

echo
echo "==== sa, same-session references (min-of-9) ===="
row sa-on-sa.asm      "$SASRC"          "$SA" "$SASRC" "$TMP/sa_out"
# tiny floor for sa: a 2-instruction asm file
printf 'nop\nmov rax, 60\nmov rdi, 0\nsyscall\n' > "$TMP/tiny.asm"
row sa-tiny-27B       "$TMP/tiny.asm"   "$SA" "$TMP/tiny.asm" "$TMP/sa_out"
