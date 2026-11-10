#!/bin/bash
# bench.sh - the speed harness.  Min-of-9 wall time per compilation, then
# bytes of source per second.  Same-session reference: sa assembling its own
# source (sa.asm), the same way t/selfhost.py measures it.
#
# usage: ./bench.sh            (prints one results block)
# Paths assume sc/ lives inside sovren/ (tests are ../tests and the
# assembler is ../../sovren-assembler/). sa output is positional argv[2].
# C.32e: --prof endpoints are PHASE-ENDPOINT AGGREGATES (nested).
#        They are never an exclusive sum: do not add them up, and do not
#        compare their sum to wall-clock time. min-of-9 wall time here is
#        the latency measure.
# C.34: every row reports input bytes and the MB/s column is input-based;
#       source-byte rates across an assembler and a high-level language are
#       diagnostic only, not proof of equal frontend work.
set -u
cd "$(dirname "$0")"

SC=./sc
T=../tests
SA=../../sovren-assembler/sa
SASRC=../../sovren-assembler/sa.asm
TMP=${TMPDIR:-/tmp}/sc_bench
mkdir -p "$TMP"

# C.32b: the shipped layout must resolve. The old T=../sovren/tests and
# SA=../sovren-assembler/sa silently produced 17 rows of "0 bytes" and a
# 260 us no-op sa reference. Refuse to run on a broken layout instead.
for need in "$T" "$T/q0.sov" "$SC" "$SA" "$SASRC"; do
    if [ ! -e "$need" ]; then
        echo "bench: layout error: missing $need (cwd=$(pwd))" >&2
        exit 2
    fi
done
echo "bench: layout OK (T=$T SA=$SA)" 

# min-of-9 of one command, in microseconds (EPOCHREALTIME = secs.usecs)
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

# one line: NAME  BYTES  USEC  MB/s
row() { # name path...
    local name=$1 path=$2; shift 2
    local bytes us
    bytes=$(stat -c %s "$path")
    us=$(min9 "$@")
    awk -v n="$name" -v b="$bytes" -v u="$us" \
        'BEGIN { printf "%-26s %10d bytes %9d us %10.2f MB/s\n", n, b, u, b / (u / 1e6) / 1e6 }'
}

# ---- synthetic sources, sa's shapes translated to .sov ------------------
# vars: a long run of assignments then prints (parse + emit + locals)
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

# fns: many tiny functions called forward from main (symbol table + patches)
awk -v NV=24000 'BEGIN { n = NV
    print "main:"
    for (i = 0; i < n; i++) print "    r: f" i "()"
    print "    return 0"
    for (i = 0; i < n; i++) { print "f" i ":"; print "    return " i } }' > "$TMP/fns1m.sov"

# sanity: every synthetic must actually compile before it is timed
for f in "$TMP/vars512k.sov" "$TMP/vars4m.sov" "$TMP/fns1m.sov"; do
    $SC "$f" -o "$TMP/sanity" || { echo "bench: sc refused $f" >&2; exit 1; }
done

echo "==== sc, PASSLIST sources (min-of-9 each) ===="
row q0.sov           "$T/q0.sov"            $SC "$T/q0.sov"            -o "$TMP/out"
while read -r f args; do
    [ -f "$T/$f" ] || continue
    row "$f"        "$T/$f"                $SC "$T/$f"                -o "$TMP/out"
done < PASSLIST

echo
echo "==== sc, synthetic large sources (min-of-9 each) ===="
row vars512k.sov     "$TMP/vars512k.sov"    $SC "$TMP/vars512k.sov"    -o "$TMP/out"
row vars4m.sov       "$TMP/vars4m.sov"      $SC "$TMP/vars4m.sov"      -o "$TMP/out"
row fns1m.sov        "$TMP/fns1m.sov"       $SC "$TMP/fns1m.sov"       -o "$TMP/out"

echo
echo "==== the floor ===="
# Process-spawn floor indicator ONLY; its "MB/s" is not a throughput number.
row true             /bin/true              /bin/true
row sc-minimal       "$T/q0.sov"            $SC "$T/q0.sov"            -o "$TMP/out"

echo
echo "==== sa, its own source (same-session reference) ===="
row sa-on-sa.asm     "$SASRC"               $SA "$SASRC"               "$TMP/sa_out"
