#!/bin/sh
# sc - build.  gcc -O2, one C file, no dependencies.
set -e
cd "$(dirname "$0")"
gcc -O2 -Wall -Wextra -o sc sc.c
echo "built sc"
