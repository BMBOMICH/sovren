CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
LDFLAGS ?= -lm
PREFIX ?= /usr/local

BUILD_DIR = build
BOOTSTRAP_DIR = bootstrap
RUNTIME_DIR = runtime
COMPILER_DIR = compiler
STDLIB_DIR = stdlib
TEST_DIR = tests

BOOTSTRAP_C = $(BOOTSTRAP_DIR)/sovereign.c
RUNTIME_C = $(RUNTIME_DIR)/runtime.c
RUNTIME_H = $(RUNTIME_DIR)/runtime.h

SOV_SRCS = \
	$(STDLIB_DIR)/native.sov \
	$(STDLIB_DIR)/ast.sov \
	$(COMPILER_DIR)/lexer.sov \
	$(COMPILER_DIR)/parser.sov \
	$(COMPILER_DIR)/semantic.sov \
	$(COMPILER_DIR)/optimizer.sov \
	$(COMPILER_DIR)/codegen/c.sov \
	$(COMPILER_DIR)/codegen/llvm.sov \
	$(COMPILER_DIR)/codegen/wasm.sov \
	$(COMPILER_DIR)/main.sov

SOVEREIGN = $(BUILD_DIR)/sovereign
SOVEREIGN_STAGE2 = $(BUILD_DIR)/sovereign2
SOVEREIGN_STAGE3 = $(BUILD_DIR)/sovereign3

.PHONY: all
all: $(SOVEREIGN)
	@echo ""
	@echo "Build complete: $(SOVEREIGN)"
	@echo "Usage: $(SOVEREIGN) build <file.sov>"

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(SOVEREIGN): $(BUILD_DIR) $(BOOTSTRAP_C)
	@echo "Building Sovereign compiler from bootstrap C..."
	$(CC) $(CFLAGS) -o $(SOVEREIGN) $(BOOTSTRAP_C) $(LDFLAGS)
	@echo "Done"

.PHONY: self-compile
self-compile: $(SOVEREIGN)
	@echo "Stage 1: Compile .sov sources to C"
	$(SOVEREIGN) build $(COMPILER_DIR)/main.sov -o $(BUILD_DIR)/stage1.c
	@echo "Stage 2: Build compiler from Stage 1 C"
	$(CC) $(CFLAGS) -o $(SOVEREIGN_STAGE2) $(BUILD_DIR)/stage1.c $(RUNTIME_C) $(LDFLAGS)
	@echo "Stage 3: Self-compile with Stage 2"
	$(SOVEREIGN_STAGE2) build $(COMPILER_DIR)/main.sov -o $(BUILD_DIR)/stage2.c
	$(CC) $(CFLAGS) -o $(SOVEREIGN_STAGE3) $(BUILD_DIR)/stage2.c $(RUNTIME_C) $(LDFLAGS)
	@echo "Verify Convergence"
	@if diff -q $(BUILD_DIR)/stage1.c $(BUILD_DIR)/stage2.c > /dev/null 2>&1; then \
		echo "SUCCESS: Self-hosting verified"; \
	else \
		echo "WARNING: Outputs differ"; \
		diff $(BUILD_DIR)/stage1.c $(BUILD_DIR)/stage2.c | head -20 || true; \
	fi

.PHONY: test
test: $(SOVEREIGN)
	@for f in $(TEST_DIR)/*.sov; do \
		echo "Testing $$f..."; \
		$(SOVEREIGN) check "$$f" || exit 1; \
	done
	@echo "All tests passed"

.PHONY: test-crypto
test-crypto: $(SOVEREIGN)
	$(CC) -O2 -DSOV_RUNTIME_STANDALONE $(RUNTIME_C) -o $(BUILD_DIR)/crypto_test $(LDFLAGS)
	$(BUILD_DIR)/crypto_test

.PHONY: bench
bench: $(SOVEREIGN)
	$(SOVEREIGN) build $(TEST_DIR)/bench.sov -o $(BUILD_DIR)/bench.c
	$(CC) -O2 $(BUILD_DIR)/bench.c $(RUNTIME_C) -o $(BUILD_DIR)/bench $(LDFLAGS)
	$(BUILD_DIR)/bench

.PHONY: bench-compare
bench-compare: $(SOVEREIGN)
	@echo "=== C Baseline ==="
	$(CC) -O2 bench/compare_c.c -o $(BUILD_DIR)/bench_c $(LDFLAGS)
	$(BUILD_DIR)/bench_c
	@echo ""
	@echo "=== Sovereign (C backend) ==="
	$(SOVEREIGN) build $(TEST_DIR)/bench.sov -o $(BUILD_DIR)/bench_sov.c
	$(CC) -O2 $(BUILD_DIR)/bench_sov.c $(RUNTIME_C) -o $(BUILD_DIR)/bench_sov $(LDFLAGS)
	$(BUILD_DIR)/bench_sov

.PHONY: check
check: $(SOVEREIGN)
	@for f in $(SOV_SRCS); do \
		echo "Checking $$f..."; \
		$(SOVEREIGN) check "$$f" || exit 1; \
	done

.PHONY: fmt
fmt: $(SOVEREIGN)
	@for f in $(SOV_SRCS); do \
		$(SOVEREIGN) fmt "$$f"; \
	done

.PHONY: version
version: $(SOVEREIGN)
	$(SOVEREIGN) version

.PHONY: loc
loc:
	@echo "Compiler:" && wc -l $(SOV_SRCS) 2>/dev/null | tail -1
	@echo "Runtime:" && wc -l $(RUNTIME_C) $(RUNTIME_H) 2>/dev/null | tail -1
	@echo "Tests:" && wc -l $(TEST_DIR)/*.sov 2>/dev/null | tail -1
	@echo "Bootstrap:" && wc -l $(BOOTSTRAP_C)

.PHONY: install
install: $(SOVEREIGN)
	install -d $(PREFIX)/bin
	install -m 755 $(SOVEREIGN) $(PREFIX)/bin/sovereign

.PHONY: uninstall
uninstall:
	rm -f $(PREFIX)/bin/sovereign

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)

.PHONY: clean-all
clean-all: clean
	rm -f *.o *.exe
