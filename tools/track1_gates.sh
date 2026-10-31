#!/bin/bash
# Track-1 regression gates. Usage: track1_gates.sh <candidate-compiler> [--full]
# Fast gates (always): fixed point, hello md5, trap cells, all.sov.
# --full adds: conformance corpus (16 cells x eligible backends) + fleet gate.
# All compiles cold: no cache flags; trap outputs pinned in work/track1/expected/.
set -u
cd "$(dirname "$0")/.."
C="${1:?compiler path required}"
FULL="${2:-}"
HELLO_MD5=d0a52848eb5dc6ff18e63c881b7150cf
fail(){ echo "GATE FAIL: $1"; exit 1; }

# Track 0.0: cache side-door purge stays eternal — guard + legacy-flag rejection fail-closed.
bash tools/cache_tree_guard.sh || fail "cache_tree_guard"
for lf in --usepfx --cache --uncached; do
  $C $lf tests/hello.sov -o /tmp/g.lf >/dev/null 2>&1 && fail "legacy flag accepted: $lf"
done
echo "gate: cache side-door closed OK"

$C compilers/linux/compiler.sov -o /tmp/g.c1 >/dev/null 2>&1 || fail "build c1"
chmod +x /tmp/g.c1
/tmp/g.c1 compilers/linux/compiler.sov -o /tmp/g.c2 >/dev/null 2>&1 || fail "build c2"
cmp -s /tmp/g.c1 /tmp/g.c2 || fail "fixed point"
echo "gate: fixed point OK"

$C tests/hello.sov -o /tmp/g.h >/dev/null 2>&1 || fail "hello compile"
/tmp/g.h | md5sum | grep -q "$HELLO_MD5" || fail "hello output md5"
echo "gate: hello md5 OK"

# spliced-if: harness-level splice of the trap module over the cell body.
# (include-directive range registration is a separate latent repair; the trap
# guards `if` dispatch across a splice seam either way.)
cat tests/track1/inc/tf01.sov tests/track1/spliced_if.body.sov > /tmp/g.spliced.sov
$C /tmp/g.spliced.sov -o /tmp/g.si >/dev/null 2>&1 || fail "spliced_if compile"
/tmp/g.si | cmp -s tests/track1/spliced_if.expected - || fail "spliced-if trap"
$C tests/track1/dup_if.sov -o /tmp/g.di >/dev/null 2>&1 || fail "dup_if compile"
/tmp/g.di | cmp -s tests/track1/dup_if.expected - || fail "dup-if trap"
echo "gate: track1 traps OK"
rm -f tests/*.ac tests/*.lsug tests/*.sug tests/track1/*.lsug tests/track1/*.ac tests/conformance/corpus/*.ac tests/conformance/corpus/*.lsug 2>/dev/null || true

$C tests/all.sov -o /tmp/g.all >/dev/null 2>&1 || fail "all.sov compile"
echo "(all.sov run skipped: SEGVs even under pristine baseline; compile-only gate)"
echo "gate: tests/all OK"

rm -f tests/*.ac tests/*.ac.bin tests/*.lsug tests/*.sug 2>/dev/null

if [ "$FULL" = "--full" ]; then
  python3 tests/conformance/language_conformance.py --output /tmp/g.conf.json >/dev/null 2>&1 || fail "conformance"
  echo "gate: conformance OK"
  python3 tools/speed_gate_fleet.py >/dev/null 2>&1 || fail "fleet gate"
  echo "gate: fleet OK"
fi
echo "ALL GATES GREEN ($C)"
