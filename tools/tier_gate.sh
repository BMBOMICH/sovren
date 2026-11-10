#!/bin/bash
# Tier-0 discipline gate: run EVERY check that a change must pass, in order.
# Usage: tools/tier_gate.sh [compiler] [--full]
#   fast (default): no-cache policy, cache tree guard, track1 gates (fixed
#                   point, hello md5, traps, all.sov), A/A noise sanity,
#                   paired workloads qualification, phase table refresh.
#   --full        : adds the conformance corpus + fleet speed gate.
# Every speed claim still goes through tools/ab_speed.py (rotating interleaved
# medians, R>=12 recommended for claims, N=15 default) per SA_PARITY rules.
set -u
cd "$(dirname "$0")/.."
C="${1:-compilers/linux/compiler}"
FULL="${2:-}"
[ -x "$C" ] || { echo "compiler not executable: $C"; exit 1; }
touch /tmp/sov_nopar 2>/dev/null || true
fail(){ echo "TIER GATE FAIL: $1"; exit 1; }

echo "== 1/6 no-cache policy (in-run reuse only) =="
python3 tools/no_cache_policy.py || fail "no_cache_policy"

echo "== 2/6 cache tree guard (side doors closed) =="
bash tools/cache_tree_guard.sh || fail "cache_tree_guard"
python3 tools/rt_baked_sync.py || fail "rt_baked_sync"

echo "== 3/6 track1 gates (fixed point, hello, traps, all.sov) =="
bash tools/track1_gates.sh "$C" || fail "track1_gates"

echo "== 4/6 A/A noise sanity (same compiler twice, R=21, up to 4 retries) =="
aa_ok=0
# C.32: a 2-CPU sandbox under concurrent load can push even an
# identical-binary R=21 median outside 3% more than once; allow up
# to 4 fresh A/A samples WITHOUT relaxing R=21 or the 3% band.
for attempt in 1 2 3 4; do
  # R=21 (not 8): the SA_PARITY A/B discipline requires >=21 rotated samples;
  # on a 2-CPU host R=8 medians wander +/-5% and produce false A/A failures.
  python3 tools/ab_speed.py "$C" "$C" --runs 21 --output /tmp/aa_sanity.json >/dev/null 2>&1 || fail "A/A run"
  if python3 - <<'EOF'
import json
d = json.load(open('/tmp/aa_sanity.json'))
for w in d['workloads']:
    r = w['baseline_over_candidate']
    if abs(r - 1.0) > 0.03:
        raise SystemExit(1)
EOF
  then aa_ok=1; break; fi
  echo "   A/A attempt $attempt out of band; retrying (transient scheduler noise)"
done
[ "$aa_ok" = "1" ] || fail "A/A noise out of band in 4 samples (expect within ~3%)"
echo "   A/A ratios within 3%: OK"

echo "== 5/6 paired workloads (latency qualification) =="
SA_BIN="../sovren-assembler/sa"
[ -x "$SA_BIN" ] || SA_BIN="$(ls -1 ../sovren-assembler/sa 2>/dev/null | head -1)"
python3 tools/paired_workloads.py "$C" --baseline compilers/linux/compiler --sa "$SA_BIN" || fail "paired_workloads"

echo "== 6/6 phase table refresh =="
python3 tools/phase_table.py >/dev/null || fail "phase_table"
echo "   work/PHASE_TABLE.md refreshed"

if [ "$FULL" = "--full" ]; then
    echo "== full: conformance corpus =="
    python3 tests/conformance/language_conformance.py --output /tmp/tg_conf.json >/dev/null 2>&1 || fail "conformance"
    echo "== full: fleet speed gate =="
    python3 tools/speed_gate_fleet.py >/dev/null 2>&1 || fail "fleet gate"
fi
echo "TIER GATE GREEN ($C)"
