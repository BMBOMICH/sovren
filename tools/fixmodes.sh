#!/bin/sh
# MediaFire strips the exec bit on download, and the workspace snapshot/restore
# round-trip does not preserve mode bits. This tree is NOT a git repo, so git
# cannot restore them either. Re-mark every ELF/PE binary executable.
# Text files DO survive snapshots, so this script persists even though the bits don't.
# POSIX sh (no process substitution) so it runs under dash too.
cd "$(dirname "$0")/.." || exit 1
find . -type f -exec sh -c '
  for f in "$@"; do
    case "$(head -c4 "$f" 2>/dev/null | od -An -tx1 | tr -d " \n")" in
      7f454c46|4d5a*) chmod +x "$f" ;;
    esac
  done
' _ {} +
echo "fixmodes: all ELF/PE binaries re-marked executable"
