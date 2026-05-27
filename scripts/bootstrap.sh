#!/bin/bash
# Sovereign Bootstrap Script
# This script performs the full bootstrap cycle for the self-hosted compiler.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Sovereign Self-Hosted Compiler Bootstrap"
echo "========================================"
echo ""

# Check for required tools
check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is required but not installed.${NC}"
        exit 1
    fi
}

echo "Checking required tools..."
check_tool cargo
check_tool gcc
check_tool diff
echo -e "${GREEN}All required tools found.${NC}"
echo ""

# Step 1: Build the Rust compiler
echo "Step 1: Building Rust compiler..."
cargo build --release
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to build Rust compiler${NC}"
    exit 1
fi
echo -e "${GREEN}Rust compiler built successfully.${NC}"
echo ""

# Step 2: Validate self-hosting components
echo "Step 2: Validating self-hosting components..."
./target/release/sovereign bootstrap validate
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Warning: Validation reported issues.${NC}"
fi
echo ""

# Step 3: Compile self-hosted compiler to C
echo "Step 3: Compiling self-hosted compiler to C..."
./target/release/sovereign bootstrap compile --target c -o build/bootstrap1.c
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to compile to C${NC}"
    exit 1
fi
echo -e "${GREEN}Generated build/bootstrap1.c${NC}"
echo ""

# Step 4: Compile C to native binary
echo "Step 4: Compiling C to native binary..."
mkdir -p build
gcc -O2 -o build/sovereign1 build/bootstrap1.c runtime/runtime.c -lpthread -lm
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to compile C code${NC}"
    exit 1
fi
echo -e "${GREEN}Built build/sovereign1${NC}"
echo ""

# Step 5: Test the bootstrapped compiler
echo "Step 5: Testing bootstrapped compiler..."
./build/sovereign1 --version
if [ $? -ne 0 ]; then
    echo -e "${RED}Bootstrapped compiler failed to run${NC}"
    exit 1
fi
echo ""

# Step 6: Use bootstrap to compile itself
echo "Step 6: Self-compiling (generation 2)..."
./build/sovereign1 compile src/compiler_self.sov -o build/bootstrap2.c
if [ $? -ne 0 ]; then
    echo -e "${RED}Self-compilation failed${NC}"
    exit 1
fi
echo -e "${GREEN}Generated build/bootstrap2.c${NC}"
echo ""

# Step 7: Build generation 2
echo "Step 7: Building generation 2..."
gcc -O2 -o build/sovereign2 build/bootstrap2.c runtime/runtime.c -lpthread -lm
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to compile generation 2${NC}"
    exit 1
fi
echo -e "${GREEN}Built build/sovereign2${NC}"
echo ""

# Step 8: Verify convergence
echo "Step 8: Verifying convergence..."
./build/sovereign2 compile src/compiler_self.sov -o build/bootstrap3.c
diff build/bootstrap2.c build/bootstrap3.c > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}CONVERGENCE VERIFIED!${NC}"
    echo -e "${GREEN}Generation 2 and 3 produce identical output.${NC}"
else
    echo -e "${YELLOW}Warning: Outputs differ - may need investigation${NC}"
    echo "Run: diff build/bootstrap2.c build/bootstrap3.c"
fi
echo ""

# Step 9: Final installation
echo "Step 9: Installing..."
cp build/sovereign2 build/sovereign
echo -e "${GREEN}Installed: build/sovereign${NC}"
echo ""

# Statistics
echo "========================================"
echo "Bootstrap Statistics"
echo "========================================"
wc -l src/stdlib_native.sov src/stdlib_ast.sov src/lexer_self.sov src/parser_self.sov src/codegen_self.sov src/compiler_self.sov 2>/dev/null | tail -1
echo ""

echo "========================================"
echo -e "${GREEN}BOOTSTRAP COMPLETE!${NC}"
echo "========================================"
echo ""
echo "Usage:"
echo "  ./build/sovereign compile <file.sov> -o output.c"
echo "  ./build/sovereign run <file.sov>"
echo "  ./build/sovereign check <file.sov>"
echo ""
