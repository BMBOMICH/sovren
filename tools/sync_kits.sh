#!/bin/bash
# sync_kits.sh - single-source propagation for the mirror kits (2a04).
#
# Canonical sources live in the sovren repo. The mirror copies below are
# GENERATED: they stay on disk (uniform-kit rule) but this script is the
# only sanctioned way to change them.
#
#   sovren/compilers/linux/compiler.sov  -> sovrenos mirror + in-repo mirror
#   sovren/compilers/linux/compiler      -> sovrenos/toolchain/compiler
#   sovren/compilers/linux/compiler2     -> sovrenos/toolchain/compiler2
#   sovren/sovren                        -> sovrenos/toolchain/sovren
#   sovren/runtime.sov                   -> sovrenos/toolchain/runtime.sov
#   sovren/library/<f>.sov               -> sovrenos/selfhost/library/<f>.sov
#
# NOT mirrors (real per-platform variants; never synced over):
#   compilers/{android,ios,macos,windows}/compiler.sov
#   (3,001..4,186 lines differ from linux across 62..200 hunks)
#
# usage: tools/sync_kits.sh [--check]   (--check = verify only, exit 1 on drift)
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
S="$ROOT/sovren"
O="$ROOT/sovrenos"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
drift=0

sync() { # sync <src> <dst>
    if [ ! -f "$1" ]; then echo "SKIP (no canonical): $1"; return; fi
    if cmp -s "$1" "$2"; then echo "ok  $2"; return; fi
    if [ "$CHECK" = 1 ]; then echo "DRIFT $2"; drift=1; return; fi
    cp "$1" "$2"
    case "$2" in
        *toolchain/compiler*|*toolchain/sovren|*/sovren|*/compiler) chmod +x "$2" ;;
    esac
    echo "SYNC $2"
}

# toolchain binary + runtime mirrors
sync "$S/compilers/linux/compiler"  "$O/toolchain/compiler"
sync "$S/sovren"                    "$O/toolchain/sovren"
sync "$S/runtime.sov"               "$O/toolchain/runtime.sov"

# selfhost library mirrors (intersection only; OS-only libs untouched)
for f in "$O"/selfhost/library/*.sov; do
    b="$(basename "$f")"
    sync "$S/library/$b" "$f"
done

if [ "$drift" = 1 ]; then echo "CHECK FAILED (run without --check to fix)"; exit 1; fi
echo "sync complete"
