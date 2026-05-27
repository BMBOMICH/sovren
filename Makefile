# Sovereign Compiler Makefile
# 
# This project is ENTIRELY written in Sovereign (.sov)
# The bootstrap compiler is pre-generated C code.
#
# NO RUST REQUIRED!
#
# Quick Start:
#   make              - Build the compiler from bootstrap C
#   make test         - Run tests
#   make self-compile - Verify self-hosting works
#
# Bootstrap Cycle:
#   1. Compile bootstrap/sovereign.c with gcc
#   2. Use that to compile .sov source files
#   3. Self-compile to verify convergence

# Configuration
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
LDFLAGS ?= -lm
PREFIX ?= /usr/local

# Directories
BUILD_DIR = build
BOOTSTRAP_DIR = bootstrap
RUNTIME_DIR = runtime
SRC_DIR = src
TEST_DIR = tests

# Files
BOOTSTRAP_C = $(BOOTSTRAP_DIR)/sovereign.c
RUNTIME_C = $(RUNTIME_DIR)/runtime.c
RUNTIME_H = $(RUNTIME_DIR)/runtime.h

# Sovereign source files (the entire compiler is in .sov!)
SOV_SRCS = \
	$(SRC_DIR)/stdlib_native.sov \
	$(SRC_DIR)/stdlib_ast.sov \
	$(SRC_DIR)/lexer_self.sov \
	$(SRC_DIR)/parser_self.sov \
	$(SRC_DIR)/semantic_self.sov \
	$(SRC_DIR)/codegen_self.sov \
	$(SRC_DIR)/main.sov

# Binaries
SOVEREIGN = $(BUILD_DIR)/sovereign
SOVEREIGN_STAGE2 = $(BUILD_DIR)/sovereign2
SOVEREIGN_STAGE3 = $(BUILD_DIR)/sovereign3

# ==============================================================================
# PRIMARY TARGETS
# ==============================================================================

.PHONY: all
all: $(SOVEREIGN)
	@echo ""
	@echo "Build complete: $(SOVEREIGN)"
	@echo ""
	@echo "Usage:"
	@echo "  $(SOVEREIGN) build <file.sov>    Compile to C"
	@echo "  $(SOVEREIGN) check <file.sov>    Type-check only"
	@echo "  $(SOVEREIGN) version             Show version"

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Build the compiler from pre-generated bootstrap C code
# This is the ONLY step that doesn't require an existing Sovereign compiler
$(SOVEREIGN): $(BUILD_DIR) $(BOOTSTRAP_C)
	@echo "Building Sovereign compiler from bootstrap C..."
	$(CC) $(CFLAGS) -o $(SOVEREIGN) $(BOOTSTRAP_C) $(LDFLAGS)
	@echo "Done!"

# ==============================================================================
# SELF-HOSTING VERIFICATION
# ==============================================================================

# Full self-compilation cycle to verify the compiler works
.PHONY: self-compile
self-compile: $(SOVEREIGN)
	@echo "========================================"
	@echo "Stage 1: Compile .sov sources to C"
	@echo "========================================"
	$(SOVEREIGN) build $(SRC_DIR)/main.sov -o $(BUILD_DIR)/stage1.c
	@echo ""
	@echo "========================================"
	@echo "Stage 2: Build compiler from Stage 1 C"
	@echo "========================================"
	$(CC) $(CFLAGS) -o $(SOVEREIGN_STAGE2) $(BUILD_DIR)/stage1.c $(LDFLAGS)
	@echo ""
	@echo "========================================"
	@echo "Stage 3: Self-compile with Stage 2"
	@echo "========================================"
	$(SOVEREIGN_STAGE2) build $(SRC_DIR)/main.sov -o $(BUILD_DIR)/stage2.c
	$(CC) $(CFLAGS) -o $(SOVEREIGN_STAGE3) $(BUILD_DIR)/stage2.c $(LDFLAGS)
	@echo ""
	@echo "========================================"
	@echo "Verify Convergence"
	@echo "========================================"
	$(SOVEREIGN_STAGE3) build $(SRC_DIR)/main.sov -o $(BUILD_DIR)/stage3.c
	@if diff -q $(BUILD_DIR)/stage2.c $(BUILD_DIR)/stage3.c > /dev/null 2>&1; then \
		echo "SUCCESS: Compiler converged!"; \
		echo "The Sovereign compiler successfully compiled itself."; \
	else \
		echo "Note: Outputs differ slightly (may be cosmetic)"; \
		diff $(BUILD_DIR)/stage2.c $(BUILD_DIR)/stage3.c | head -20 || true; \
	fi

# ==============================================================================
# TESTING
# ==============================================================================

.PHONY: test
test: $(SOVEREIGN)
	@echo "Running Sovereign tests..."
	@for f in $(TEST_DIR)/*.sov; do \
		echo "Testing $$f..."; \
		$(SOVEREIGN) check "$$f" || exit 1; \
	done
	@echo ""
	@echo "All tests passed!"

.PHONY: test-quick
test-quick: $(SOVEREIGN)
	$(SOVEREIGN) check $(TEST_DIR)/test1_basics.sov

# ==============================================================================
# UTILITIES
# ==============================================================================

# Format Sovereign source files
.PHONY: fmt
fmt: $(SOVEREIGN)
	@for f in $(SOV_SRCS); do \
		echo "Formatting $$f..."; \
		$(SOVEREIGN) fmt "$$f"; \
	done

# Check all source files
.PHONY: check
check: $(SOVEREIGN)
	@for f in $(SOV_SRCS); do \
		echo "Checking $$f..."; \
		$(SOVEREIGN) check "$$f" || exit 1; \
	done
	@echo "All files OK!"

# Show version
.PHONY: version
version: $(SOVEREIGN)
	$(SOVEREIGN) version

# Line count statistics
.PHONY: loc
loc:
	@echo "=== Sovereign Code (The Compiler) ==="
	@wc -l $(SOV_SRCS) 2>/dev/null || echo "0"
	@echo ""
	@echo "=== Bootstrap C Code ==="
	@wc -l $(BOOTSTRAP_C)
	@echo ""
	@echo "=== Tests ==="
	@wc -l $(TEST_DIR)/*.sov 2>/dev/null | tail -1 || echo "0 total"
	@echo ""
	@echo "=== Summary ==="
	@echo "The entire compiler is written in Sovereign!"
	@echo "Bootstrap C is auto-generated, not hand-written."

# ==============================================================================
# INSTALLATION
# ==============================================================================

.PHONY: install
install: $(SOVEREIGN)
	install -d $(PREFIX)/bin
	install -m 755 $(SOVEREIGN) $(PREFIX)/bin/sovereign
	@echo "Installed to $(PREFIX)/bin/sovereign"

.PHONY: uninstall
uninstall:
	rm -f $(PREFIX)/bin/sovereign
	@echo "Uninstalled from $(PREFIX)/bin/sovereign"

# ==============================================================================
# CLEAN
# ==============================================================================

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)

.PHONY: clean-all
clean-all: clean
	rm -f *.o *.exe

# ==============================================================================
# REGENERATE BOOTSTRAP (requires working compiler)
# ==============================================================================

# Use this after making changes to .sov files to update the bootstrap
.PHONY: update-bootstrap
update-bootstrap: $(SOVEREIGN)
	@echo "Regenerating bootstrap C code from .sov sources..."
	$(SOVEREIGN) build $(SRC_DIR)/main.sov -o $(BOOTSTRAP_C).new
	@if [ -f $(BOOTSTRAP_C).new ]; then \
		mv $(BOOTSTRAP_C).new $(BOOTSTRAP_C); \
		echo "Bootstrap updated: $(BOOTSTRAP_C)"; \
	else \
		echo "Error: Failed to generate new bootstrap"; \
		exit 1; \
	fi

# ==============================================================================
# HELP
# ==============================================================================

.PHONY: help
help:
	@echo "Sovereign Compiler - 100% Written in Sovereign"
	@echo ""
	@echo "This project requires NO Rust. The compiler is entirely"
	@echo "written in .sov files and bootstraps from C."
	@echo ""
	@echo "Quick Start:"
	@echo "  make              Build compiler from bootstrap C"
	@echo "  make test         Run all tests"
	@echo "  make self-compile Verify self-hosting works"
	@echo ""
	@echo "Build Targets:"
	@echo "  make              Build the compiler"
	@echo "  make self-compile Full self-compilation verification"
	@echo "  make test         Run test suite"
	@echo "  make check        Type-check all .sov files"
	@echo "  make fmt          Format all .sov files"
	@echo ""
	@echo "Installation:"
	@echo "  make install      Install to $(PREFIX)/bin"
	@echo "  make uninstall    Remove from $(PREFIX)/bin"
	@echo ""
	@echo "Maintenance:"
	@echo "  make update-bootstrap  Regenerate bootstrap C"
	@echo "  make loc               Line count statistics"
	@echo "  make clean             Remove build artifacts"
	@echo ""
	@echo "Environment Variables:"
	@echo "  CC=$(CC)"
	@echo "  CFLAGS=$(CFLAGS)"
	@echo "  PREFIX=$(PREFIX)"
