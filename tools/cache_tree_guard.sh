#!/bin/bash
# Eternal guard: cache/sugar sidecars and cache-capable executables must never
# exist in the tree. Runs in every gate. Exit 1 on any violation.
cd "$(dirname "$0")/.." || exit 1
bad=0
hits=$(find . -path ./work/attic -prune -o -path ./.git -prune -o -path ./target -prune -o \( -name "*.ac" -o -name "*.ac.bin" -o -name "*.lsug" -o -name "*.sug" -o -name "*.plk" -o -name "*.deepoc" -o -name "*.state_o" -o -name ".prebuilt" \) -print 2>/dev/null)
if [ -n "$hits" ]; then echo "GUARD FAIL: sidecar files in tree:"; echo "$hits"; bad=1; fi
while IFS= read -r b; do
  if [ -f "$b" ] && strings -n 4 "$b" 2>/dev/null | grep -q "\.lsug\|\.deepoc\|no-lsug"; then
    echo "GUARD FAIL: cache-capable executable: $b"; bad=1
  fi
done < <(find compilers backends -maxdepth 4 -type f -name "compiler*" -size +100k 2>/dev/null)
[ $bad -eq 0 ] && echo "cache guard OK"; exit $bad
