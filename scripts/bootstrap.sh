#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Sovereign Bootstrap v0.1.0"
echo ""

check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 is required but not installed."
        exit 1
    fi
}

check_tool gcc
check_tool diff

mkdir -p build

echo "Stage 1: Building bootstrap compiler..."
gcc -O2 bootstrap/sovereign.c -o build/sovereign -lm
echo "Done."

echo "Stage 2: Compiling .sov sources to C..."
./build/sovereign build compiler/main.sov -o build/stage1.c
echo "Done."

echo "Stage 3: Building compiler from Stage 2 output..."
gcc -O2 build/stage1.c runtime/runtime.c -o build/sovereign2 -lm
echo "Done."

echo "Stage 4: Self-compiling with Stage 3..."
./build/sovereign2 build compiler/main.sov -o build/stage2.c
echo "Done."

echo "Verifying convergence..."
if diff -q build/stage1.c build/stage2.c > /dev/null 2>&1; then
    echo "SUCCESS: Self-hosting verified."
else
    echo "WARNING: Outputs differ."
    diff build/stage1.c build/stage2.c | head -20
fi
