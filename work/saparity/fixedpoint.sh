#!/bin/sh
# fixedpoint.sh - the self-hosting gate. g2 = candidate compiling
# compiler.sov; g3 = g2 compiling compiler.sov; g2 must equal g3 byte for
# byte. usage: ./fixedpoint.sh [candidate]  default: ../../compilers/linux/compiler
set -u
cd "$(dirname "$0")/../.."
CAND=${1:-compilers/linux/compiler}
SRC=compilers/linux/compiler.sov
TMP=${TMPDIR:-/tmp}/sap_fp
mkdir -p "$TMP"

timeout 300 "$CAND" "$SRC" -o "$TMP/g2" > "$TMP/g2.cout" 2>&1
rc=$?
if [ "$rc" != 0 ]; then echo "FIXED POINT FAIL: g2 build rc=$rc"; tail -3 "$TMP/g2.cout"; exit 1; fi
timeout 300 "$TMP/g2" "$SRC" -o "$TMP/g3" > "$TMP/g3.cout" 2>&1
rc=$?
if [ "$rc" != 0 ]; then echo "FIXED POINT FAIL: g3 build rc=$rc"; tail -3 "$TMP/g3.cout"; exit 1; fi

if cmp -s "$TMP/g2" "$TMP/g3"; then
    echo "FIXED POINT OK"
    md5sum "$TMP/g2" "$TMP/g3" "$CAND"
    exit 0
else
    echo "FIXED POINT FAIL: g2 != g3"
    ls -la "$TMP/g2" "$TMP/g3"
    cmp "$TMP/g2" "$TMP/g3" | head -2
    exit 1
fi
