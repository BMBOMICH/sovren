#!/bin/sh
# P0-BUG-001: compiler SIGSEGV walking the runtime list-task codegen path.
# Provenance: pre-dates 2026-10-25 session (present in keeper-restore build
# /tmp/cr1). --flat (parse) is clean; --prof masks it via heap layout.
# Repro: c09b_minimal.sov = _sov_list_new + _sov_list_add.
# exit 0 only when FIXED. Non-blocking: not part of track1_gates.sh yet.
set -eu
C=${1:-./compilers/linux/compiler}
if ! "$C" tests/conformance/corpus/c09b_minimal.sov -o /tmp/c09b.bin >/dev/null 2>&1; then
  echo "P0-BUG-001: STILL BROKEN (compile segv)"; exit 1
fi
if ! [ -x /tmp/c09b.bin ]; then echo "P0-BUG-001: STILL BROKEN (no artifact)"; exit 1; fi
out=$(/tmp/c09b.bin) || { echo "P0-BUG-001: STILL BROKEN (artifact rc)"; exit 1; }
[ "$out" = "1" ] || { echo "P0-BUG-001: STILL BROKEN (output '$out')"; exit 1; }
echo "P0-BUG-001: FIXED"
