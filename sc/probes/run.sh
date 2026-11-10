#!/bin/bash
# semantics probes: sc's binary vs the old compiler's binary, same source.
# behavior contract (stdout + exit code), not bytes. run from sc/.
cd "$(dirname "$0")"
OLD=../../sovren/compilers/linux/compiler
SC=../sc
fail=0
for f in p*.sov; do
    $SC "$f" -o /tmp/probe_sc 2>/dev/null || { echo "$f SC-FAIL"; fail=1; continue; }
    $OLD "$f" -o /tmp/probe_old 2>/dev/null || { echo "$f OLD-FAIL"; fail=1; continue; }
    /tmp/probe_sc > /tmp/probe_sc.out 2>&1; a=$?
    /tmp/probe_old > /tmp/probe_old.out 2>&1; b=$?
    if diff -q /tmp/probe_sc.out /tmp/probe_old.out >/dev/null && [ $a = $b ]; then
        echo "$f MATCH"
    else
        echo "$f DIFF (rc $a vs $b)"; diff /tmp/probe_sc.out /tmp/probe_old.out | head -5; fail=1
    fi
done
exit $fail
