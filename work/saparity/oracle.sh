#!/bin/sh
# oracle.sh - the acceptance gate for the sa-parity phases. For EVERY
# tests/*.sov the candidate must behave exactly like the frozen binary:
#   - compile rc and compile stdout identical (refusals included)
#   - when both compile: the produced ELF byte-identical
# ELF identity subsumes the run side (identical bytes run identically);
# run-output comparison is only needed when outputs are allowed to differ,
# which this contract never permits.
# usage: ./oracle.sh [candidate]     default: compilers/linux/compiler
# NOTE: must run with CWD = the sovren project root (the compiler resolves
# include paths like compilers/shared/... from the CWD).
set -u
cd "$(dirname "$0")/../.."
FROZEN=work/saparity/oracle-frozen
CAND=${1:-compilers/linux/compiler}
T=tests
TMP=${TMPDIR:-/tmp}/sap_oracle
mkdir -p "$TMP"

pass=0; fail=0; refused=0; failed=""

for f in "$T"/*.sov; do
    b=$(basename "$f")

    rm -f "$TMP/o.bin" "$TMP/n.bin" "$TMP/out"
    timeout 120 "$FROZEN" "$f" -o "$TMP/out" > "$TMP/o.cout" 2>&1; orc=$?
    [ -f "$TMP/out" ] && cp "$TMP/out" "$TMP/o.bin"
    rm -f "$TMP/out"
    timeout 120 "$CAND"   "$f" -o "$TMP/out" > "$TMP/n.cout" 2>&1; nrc=$?
    [ -f "$TMP/out" ] && cp "$TMP/out" "$TMP/n.bin"
    rm -f "$TMP/out"

    if [ "$orc" != "$nrc" ]; then
        echo "FAIL $b (compile rc old=$orc new=$nrc)"
        diff "$TMP/o.cout" "$TMP/n.cout" | head -4
        fail=$((fail+1)); failed="$failed $b"; continue
    fi
    if ! cmp -s "$TMP/o.cout" "$TMP/n.cout"; then
        # some tests print elapsed-time marks in compile stdout; those vary
        # run to run even for the same binary. Mask long digit runs and
        # retry; anything else is a real failure.
        sed 's/[0-9]\{7,\}/T/g' "$TMP/o.cout" > "$TMP/o.cm"
        sed 's/[0-9]\{7,\}/T/g' "$TMP/n.cout" > "$TMP/n.cm"
        if ! cmp -s "$TMP/o.cm" "$TMP/n.cm"; then
            echo "FAIL $b (compile stdout differs)"
            diff "$TMP/o.cout" "$TMP/n.cout" | head -4
            fail=$((fail+1)); failed="$failed $b"; continue
        fi
    fi
    if [ "$orc" != 0 ]; then
        refused=$((refused+1))
        echo "ok   $b (both refuse, rc=$orc)"
        continue
    fi
    if ! cmp -s "$TMP/o.bin" "$TMP/n.bin"; then
        echo "FAIL $b (ELF differs)"
        fail=$((fail+1)); failed="$failed $b"; continue
    fi
    pass=$((pass+1))
    echo "ok   $b"
done

echo "----------------------------------------"
echo "oracle: $pass pass, $refused refuse-parity, $fail FAIL"
[ "$fail" = 0 ] || { echo "failed:$failed"; exit 1; }
exit 0
