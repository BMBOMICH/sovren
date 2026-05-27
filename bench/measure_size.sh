#!/bin/bash
# Sovereign vs C binary size comparison
# Usage: ./measure_size.sh

set -e

echo "========================================"
echo "  Sovereign vs C — Binary Size Test"
echo "========================================"
echo ""

# Build Sovereign hello world
echo 'print "Hello, World!"' > hello_sov.sov
echo "Building Sovereign hello world (--size)..."
sovereign build hello_sov.sov --size -o hello_sov
SOV_SIZE=$(stat -f%z hello_sov 2>/dev/null || stat -c%s hello_sov)

# Build C hello world (default)
cat > hello_c.c << 'EOF'
#include <stdio.h>
int main() { printf("Hello, World!\n"); return 0; }
EOF

echo "Building C hello world (default gcc -O2)..."
gcc -O2 hello_c.c -o hello_c_default
C_DEFAULT_SIZE=$(stat -f%z hello_c_default 2>/dev/null || stat -c%s hello_c_default)

# Build C with aggressive flags
echo "Building C hello world (aggressive flags)..."
gcc -O2 -flto -Wl,--strip-all -Wl,--gc-sections \
    -ffunction-sections -fdata-sections \
    hello_c.c -o hello_c_aggressive -lm 2>/dev/null || true
C_AGGRESSIVE_SIZE=0
if [ -f hello_c_aggressive ]; then
    C_AGGRESSIVE_SIZE=$(stat -f%z hello_c_aggressive 2>/dev/null || stat -c%s hello_c_aggressive)
fi

echo ""
echo "========================================"
echo "  RESULTS"
echo "========================================"
echo ""
echo "  Sovereign (--size):     $SOV_SIZE bytes"
echo "  C (default -O2):        $C_DEFAULT_SIZE bytes"
if [ $C_AGGRESSIVE_SIZE -gt 0 ]; then
    echo "  C (aggressive LTO):     $C_AGGRESSIVE_SIZE bytes"
fi
echo ""

if [ $SOV_SIZE -lt $C_DEFAULT_SIZE ]; then
    DIFF=$((C_DEFAULT_SIZE - SOV_SIZE))
    echo "  ✅ Sovereign is $DIFF bytes SMALLER than default C"
elif [ $SOV_SIZE -eq $C_DEFAULT_SIZE ]; then
    echo "  ✅ Sovereign equals default C"
else
    DIFF=$((SOV_SIZE - C_DEFAULT_SIZE))
    echo "  ⚠️  Sovereign is $DIFF bytes larger than default C"
fi

# Cleanup
rm -f hello_sov.sov hello_sov \
      hello_c.c hello_c_default hello_c_aggressive

echo ""
echo "Done."