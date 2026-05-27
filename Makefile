# Sovereign Compiler Makefile
# 
# Targets:
#   make              - Build the Rust compiler
#   make bootstrap    - Full bootstrap cycle
#   make test         - Run all tests
#   make clean        - Clean build artifacts
#   make install      - Install to /usr/local/bin
#
# Bootstrap Process:
#   1. Build Rust compiler
#   2. Compile self-hosted compiler to C
#   3. Compile C to native binary
#   4. Self-compile and verify convergence

# Configuration
CARGO ?= cargo
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra
LDFLAGS ?= -lpthread -lm
PREFIX ?= /usr/local

# Directories
BUILD_DIR = build
RUNTIME_DIR = runtime
SRC_DIR = src
TEST_DIR = tests

# Files
RUNTIME_SRC = $(RUNTIME_DIR)/runtime.c
RUNTIME_HDR = $(RUNTIME_DIR)/runtime.h
SELF_HOST_SRCS = \
	$(SRC_DIR)/stdlib_native.sov \
	$(SRC_DIR)/stdlib_ast.sov \
	$(SRC_DIR)/lexer_self.sov \
	$(SRC_DIR)/parser_self.sov \
	$(SRC_DIR)/semantic_self.sov \
	$(SRC_DIR)/codegen_self.sov \
	$(SRC_DIR)/compiler_self.sov

# Binaries
RUST_BIN = target/release/sovereign
BOOTSTRAP1 = $(BUILD_DIR)/sovereign1
BOOTSTRAP2 = $(BUILD_DIR)/sovereign2
BOOTSTRAP_FINAL = $(BUILD_DIR)/sovereign

# Default target
.PHONY: all
all: $(RUST_BIN)

# Build Rust compiler
$(RUST_BIN): Cargo.toml $(shell find src -name "*.rs")
	$(CARGO) build --release

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Full bootstrap cycle
.PHONY: bootstrap
bootstrap: $(RUST_BIN) $(BUILD_DIR)
	@echo "========================================"
	@echo "Sovereign Bootstrap - Stage 1"
	@echo "========================================"
	@echo "Compiling self-hosted compiler to C..."
	$(RUST_BIN) bootstrap compile --target c -o $(BUILD_DIR)/bootstrap1.c
	@echo ""
	@echo "Building Stage 1 binary..."
	$(CC) $(CFLAGS) -o $(BOOTSTRAP1) $(BUILD_DIR)/bootstrap1.c $(RUNTIME_SRC) $(LDFLAGS)
	@echo ""
	@echo "========================================"
	@echo "Sovereign Bootstrap - Stage 2"
	@echo "========================================"
	@echo "Self-compiling..."
	$(BOOTSTRAP1) compile $(SRC_DIR)/compiler_self.sov -o $(BUILD_DIR)/bootstrap2.c
	@echo ""
	@echo "Building Stage 2 binary..."
	$(CC) $(CFLAGS) -o $(BOOTSTRAP2) $(BUILD_DIR)/bootstrap2.c $(RUNTIME_SRC) $(LDFLAGS)
	@echo ""
	@echo "========================================"
	@echo "Sovereign Bootstrap - Verification"
	@echo "========================================"
	$(BOOTSTRAP2) compile $(SRC_DIR)/compiler_self.sov -o $(BUILD_DIR)/bootstrap3.c
	@if diff -q $(BUILD_DIR)/bootstrap2.c $(BUILD_DIR)/bootstrap3.c > /dev/null; then \
		echo "CONVERGENCE VERIFIED!"; \
		cp $(BOOTSTRAP2) $(BOOTSTRAP_FINAL); \
		echo "Installed: $(BOOTSTRAP_FINAL)"; \
	else \
		echo "WARNING: Outputs differ"; \
		diff $(BUILD_DIR)/bootstrap2.c $(BUILD_DIR)/bootstrap3.c | head -20; \
	fi
	@echo ""
	@echo "Bootstrap complete!"

# Quick bootstrap (Stage 1 only)
.PHONY: bootstrap-quick
bootstrap-quick: $(RUST_BIN) $(BUILD_DIR)
	$(RUST_BIN) bootstrap compile --target c -o $(BUILD_DIR)/bootstrap1.c
	$(CC) $(CFLAGS) -o $(BOOTSTRAP1) $(BUILD_DIR)/bootstrap1.c $(RUNTIME_SRC) $(LDFLAGS)
	cp $(BOOTSTRAP1) $(BOOTSTRAP_FINAL)
	@echo "Quick bootstrap complete: $(BOOTSTRAP_FINAL)"

# Validate self-hosting components
.PHONY: validate
validate: $(RUST_BIN)
	$(RUST_BIN) bootstrap validate

# Generate statistics
.PHONY: stats
stats: $(RUST_BIN)
	$(RUST_BIN) bootstrap stats

# Run all tests
.PHONY: test
test: $(RUST_BIN)
	@echo "Running Rust tests..."
	$(CARGO) test
	@echo ""
	@echo "Running Sovereign tests..."
	$(RUST_BIN) test $(TEST_DIR)/test1_basics.sov
	$(RUST_BIN) test $(TEST_DIR)/test2_structs.sov
	$(RUST_BIN) test $(TEST_DIR)/test3_generics.sov
	$(RUST_BIN) test $(TEST_DIR)/test4_security.sov
	$(RUST_BIN) test $(TEST_DIR)/test5_algorithms.sov
	@echo ""
	@echo "All tests passed!"

# Test self-hosting components
.PHONY: test-self-hosting
test-self-hosting: $(RUST_BIN)
	$(RUST_BIN) run $(TEST_DIR)/test_self_hosting.sov

# Format all Sovereign source files
.PHONY: fmt
fmt: $(RUST_BIN)
	$(RUST_BIN) fmt $(SRC_DIR)/stdlib.sov
	$(RUST_BIN) fmt $(SRC_DIR)/stdlib_native.sov
	$(RUST_BIN) fmt $(SRC_DIR)/stdlib_ast.sov
	$(RUST_BIN) fmt $(SRC_DIR)/lexer_self.sov
	$(RUST_BIN) fmt $(SRC_DIR)/parser_self.sov
	$(RUST_BIN) fmt $(SRC_DIR)/semantic_self.sov
	$(RUST_BIN) fmt $(SRC_DIR)/codegen_self.sov
	$(RUST_BIN) fmt $(SRC_DIR)/compiler_self.sov

# Generate documentation
.PHONY: docs
docs: $(RUST_BIN)
	$(RUST_BIN) bootstrap docs docs/bootstrap

# Build runtime library only
.PHONY: runtime
runtime: $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $(RUNTIME_SRC) -o $(BUILD_DIR)/runtime.o

# Clean build artifacts
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)
	rm -rf target
	rm -f *.exe *.o *.obj

# Clean only generated C files
.PHONY: clean-bootstrap
clean-bootstrap:
	rm -f $(BUILD_DIR)/*.c
	rm -f $(BUILD_DIR)/sovereign*

# Install to PREFIX
.PHONY: install
install: $(BOOTSTRAP_FINAL)
	install -d $(PREFIX)/bin
	install -m 755 $(BOOTSTRAP_FINAL) $(PREFIX)/bin/sovereign
	@echo "Installed to $(PREFIX)/bin/sovereign"

# Uninstall
.PHONY: uninstall
uninstall:
	rm -f $(PREFIX)/bin/sovereign

# Development: watch and rebuild
.PHONY: watch
watch:
	$(CARGO) watch -x "build --release"

# Check code without building
.PHONY: check
check:
	$(CARGO) check

# Run clippy lints
.PHONY: lint
lint:
	$(CARGO) clippy -- -D warnings

# Line count statistics
.PHONY: loc
loc:
	@echo "=== Rust Code ==="
	@wc -l src/*.rs | tail -1
	@echo ""
	@echo "=== Sovereign Code ==="
	@wc -l src/*.sov | tail -1
	@echo ""
	@echo "=== C Runtime ==="
	@wc -l runtime/*.c runtime/*.h | tail -1
	@echo ""
	@echo "=== Tests ==="
	@wc -l tests/*.sov tests/*.rs 2>/dev/null | tail -1 || echo "0 total"
	@echo ""
	@echo "=== Total ==="
	@find . -name "*.rs" -o -name "*.sov" -o -name "*.c" -o -name "*.h" | \
		grep -v target | grep -v node_modules | xargs wc -l | tail -1

# Help
.PHONY: help
help:
	@echo "Sovereign Compiler Build System"
	@echo ""
	@echo "Targets:"
	@echo "  make              Build the Rust compiler"
	@echo "  make bootstrap    Full bootstrap cycle (recommended)"
	@echo "  make bootstrap-quick  Quick bootstrap (Stage 1 only)"
	@echo "  make validate     Validate self-hosting components"
	@echo "  make stats        Show compiler statistics"
	@echo "  make test         Run all tests"
	@echo "  make test-self-hosting  Test self-hosting components"
	@echo "  make fmt          Format all Sovereign source"
	@echo "  make docs         Generate documentation"
	@echo "  make clean        Clean all build artifacts"
	@echo "  make install      Install to $(PREFIX)/bin"
	@echo "  make uninstall    Remove from $(PREFIX)/bin"
	@echo "  make loc          Line count statistics"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Environment Variables:"
	@echo "  CC      C compiler (default: gcc)"
	@echo "  CFLAGS  C compiler flags (default: -O2 -Wall -Wextra)"
	@echo "  PREFIX  Installation prefix (default: /usr/local)"
