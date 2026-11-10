#!/bin/sh
# oracle.sh - the acceptance contract, behavior not bytes: for each .sov in
# the PASSLIST, compile with the OLD compiler and with sc, run both, and
# demand identical stdout and exit code.
#
# usage: ./oracle.sh            (run over PASSLIST)
set -u
cd "$(dirname "$0")"
OLD=../sovren/compilers/linux/compiler
SC=./sc
T=../sovren/tests
TMP=${TMPDIR:-/tmp}/sc_oracle
mkdir -p "$TMP"
pass=0; fail=0; failed=""

# NORM in the second column: outputs embed run-varying addresses; those
# lines are masked to ADDR before the comparison.
while read -r f args; do
    case "$f" in ''|'#'*) continue ;; esac
    norm=0
    case "$args" in NORM*) norm=1; args="";; esac
    [ -f "$T/$f" ] || { echo "?? missing $f"; fail=$((fail+1)); failed="$failed $f"; continue; }
    rm -f "$TMP/n"
    if ! $OLD "$T/$f" -o "$TMP/o" >/dev/null 2>&1; then
        echo "?? old compiler refused $f"; fail=$((fail+1)); failed="$failed $f"; continue
    fi
    if ! $SC "$T/$f" -o "$TMP/n" >/dev/null 2>&1; then
        echo "FAIL $f (sc: compile error)"; fail=$((fail+1)); failed="$failed $f"; continue
    fi
    "$TMP/o" $args > "$TMP/o.out" 2>/dev/null; orc=$?
    "$TMP/n" $args > "$TMP/n.out" 2>/dev/null; nrc=$?
    if [ "$norm" = "1" ]; then
        sed 's/^[0-9]\{7,\}$/ADDR/' "$TMP/o.out" > "$TMP/o.nrm"
        sed 's/^[0-9]\{7,\}$/ADDR/' "$TMP/n.out" > "$TMP/n.nrm"
        mv "$TMP/o.nrm" "$TMP/o.out"; mv "$TMP/n.nrm" "$TMP/n.out"
    fi
    if [ "$orc" != "$nrc" ] || ! cmp -s "$TMP/o.out" "$TMP/n.out"; then
        echo "FAIL $f (rc old=$orc new=$nrc)"
        diff "$TMP/o.out" "$TMP/n.out" | head -6
        fail=$((fail+1)); failed="$failed $f"
    else
        echo "ok   $f"
        pass=$((pass+1))
    fi
done < PASSLIST

echo "----------------------------------------"
echo "oracle: $pass passed, $fail failed"
[ $fail -eq 0 ] || { echo "failed:$failed"; exit 1; }
