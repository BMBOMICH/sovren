# Sovereign Compiler Bootstrap Guide

## Overview

This guide explains how to bootstrap Sovereign from its Rust implementation into a self-hosting compiler written in Sovereign itself.

## The Self-Hosting Architecture

The self-hosted compiler is implemented in pure Sovereign across 6 phases:

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: stdlib_native.sov (1200+ lines)                   │
│  Extended standard library with collections and file I/O     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 1b: stdlib_ast.sov (1100+ lines)                      │
│  AST type definitions (Token, Expr, Stmt, Program)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: lexer_self.sov (700+ lines)                        │
│  Self-hosted lexer - tokenizes source files                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: parser_self.sov (1000+ lines)                      │
│  Self-hosted parser - builds AST from tokens                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: codegen_self.sov (900+ lines)                      │
│  C code generator - emits portable C from AST                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Main Entry: compiler_self.sov (300+ lines)                  │
│  Orchestrates entire compilation pipeline                    │
└─────────────────────────────────────────────────────────────┘

TOTAL: ~5,200 lines of Sovereign code (self-hosting compiler)
```

## Directory Structure

```
sovereign/
├── src/
│   ├── main.rs                  # Rust entry point + CLI
│   ├── lib.rs                   # Library interface
│   ├── self_hosting.rs          # Rust integration layer
│   ├── stdlib_native.sov        # Phase 1: Collections & I/O
│   ├── stdlib_ast.sov           # Phase 1b: AST definitions
│   ├── lexer_self.sov           # Phase 2: Lexer
│   ├── parser_self.sov          # Phase 3: Parser
│   ├── codegen_self.sov         # Phase 4: C Codegen
│   └── compiler_self.sov        # Main compiler
├── tests/
│   ├── test_self_hosting.sov    # Sovereign test suite
│   └── integration_self_hosting.rs  # Rust integration tests
├── docs/
│   ├── SELF_HOSTING.md          # Technical details
│   └── bootstrap/               # Generated documentation
└── BOOTSTRAP_GUIDE.md           # This file
```

## Bootstrap Process (Step-by-Step)

### Step 1: Build the Rust Compiler (Initial Bootstrap)

```bash
# Compile the original Rust-based compiler
cd sovereign
cargo build --release

# Verify it works
./target/release/sovereign --version
# Output: Sovereign v1.0.0
```

At this point, you have a working Rust-based compiler that understands Sovereign syntax.

### Step 2: Load Self-Hosting Components

```bash
# Verify all .sov compiler components are present and valid
./target/release/sovereign bootstrap validate

# Output:
# ✅ All components loaded successfully!
# === Self-Hosting Compiler Statistics ===
# stdlib_native.sov:  1204 lines
# stdlib_ast.sov:     1162 lines
# lexer_self.sov:      799 lines
# parser_self.sov:    1095 lines
# codegen_self.sov:    963 lines
# compiler_self.sov:   308 lines
# ----------------------------------------
# TOTAL:              5531 lines
```

### Step 3: Compile Self-Compiler to C

The self-hosted compiler is written in Sovereign but compiles to C. This is the key insight: the compiler can compile itself to C, which is then compiled with a standard C compiler.

```bash
# Compile the self-hosted compiler to C code
./target/release/sovereign bootstrap compile --target c -o bootstrap

# Output:
# Compiling self-hosted compiler to c...
# ✅ Self-compiler compiled to bootstrap.c
```

The generated `bootstrap.c` is the self-hosted compiler itself, now in C.

### Step 4: Compile C to Native Binary

```bash
# Compile the generated C code with standard C compiler
gcc -O3 bootstrap.c -o bootstrap

# Now 'bootstrap' is a working Sovereign compiler written in Sovereign!
./bootstrap --version
# Output: Sovereign v1.0.0
```

### Step 5: First Self-Compilation

Now the interesting part: use the bootstrapped compiler to compile itself again.

```bash
# Use bootstrap to compile the self-compiler to C
./bootstrap compile src/compiler_self.sov --target c -o bootstrap2

# Compile again with C compiler
gcc -O3 bootstrap2.c -o bootstrap2

# Now 'bootstrap2' is the self-hosted compiler, version 2
./bootstrap2 --version
```

### Step 6: Convergence Test

To verify the bootstrap is working correctly, compare the two binaries:

```bash
# If they're identical, bootstrap has converged!
diff bootstrap bootstrap2
# (no output = success)

# If different, there may be non-determinism in the toolchain
# Re-run steps 5-6 a few more times - they should converge eventually
```

### Step 7: Verify Correctness

Test the self-hosted compiler with the test suite:

```bash
# Run tests with Rust compiler
./target/release/sovereign test tests/test_self_hosting.sov

# Run tests with self-hosted compiler
./bootstrap test tests/test_self_hosting.sov

# Both should pass!
```

## What Gets Generated in Each Phase

### Phase 1: stdlib_native.sov

**Purpose:** Provide data structures and utilities needed by the compiler itself.

**Key Components:**
- `Vec<T>`: Dynamic arrays for token lists, AST nodes
- `HashMap<string, int>`: Symbol tables for variable/function lookup
- String methods: `split()`, `join()`, `find()`, `replace()`, `substring()`, `trim()`
- File I/O: `open()`, `read_line()`, `write()`, `close()`
- Byte utilities: for binary data in generated code

**Why:** The lexer, parser, and codegen all depend on these data structures.

### Phase 1b: stdlib_ast.sov

**Purpose:** Define the abstract syntax tree structure.

**Key Components:**
```sovereign
enum Token {
    Keyword(string),
    Identifier(string),
    IntLiteral(int),
    StringLiteral(string),
    Operator(string),
    // ... 40+ token types
}

struct Expr {
    kind: int,
    value: int,
    string_value: string,
    children: Vec<Expr>,
}

enum Stmt {
    VarDecl(string, Expr),
    FunctionDecl(string, Vec<string>, Stmt),
    If(Expr, Stmt, Stmt),
    Return(Expr),
    // ... more statement types
}

struct Program {
    statements: Vec<Stmt>,
    imports: Vec<string>,
}
```

### Phase 2: lexer_self.sov

**Purpose:** Convert source code (string) into tokens.

**Main Tasks:**
- `tokenize(source: string) -> Vec<Token>`
- `advance()` - move to next character
- `current_char()` -> char
- `peek() -> char`
- `collect_number()` -> Token
- `collect_string()` -> Token
- `collect_identifier()` -> Token

**Input:** Raw source code as string
**Output:** `Vec<Token>` ready for parsing

### Phase 3: parser_self.sov

**Purpose:** Convert tokens into an abstract syntax tree.

**Main Tasks:**
- `parse_program(tokens: Vec<Token>) -> Program`
- `parse_statement() -> Stmt`
- `parse_expression() -> Expr`
- `parse_task_decl() -> Stmt`
- `parse_if() -> Stmt`
- `parse_loop() -> Stmt`

**Recursive Descent Algorithm:**
```
parse_program():
    statements = []
    while tokens not empty:
        stmt = parse_statement()
        statements.push(stmt)
    return Program(statements)

parse_statement():
    match current_token():
        Keyword("task"):   return parse_task_decl()
        Keyword("check"):  return parse_if()
        Keyword("loop"):   return parse_loop()
        Keyword("set"):    return parse_var_decl()
        // ... more cases
```

**Input:** `Vec<Token>`
**Output:** `Program` (the AST)

### Phase 4: codegen_self.sov

**Purpose:** Convert AST into C code that can be compiled to native binary.

**Main Tasks:**
- `codegen(program: Program) -> string` - returns C code
- `emit_c_headers()` -> string
- `emit_c_includes()` -> string
- `codegen_task(task: Stmt) -> string`
- `codegen_expr(expr: Expr) -> string`

**Example Transformation:**

Sovereign input:
```sovereign
task add(a: int, b: int) -> int {
    return a + b
}
```

Generated C output:
```c
int add(int a, int b) {
    return a + b;
}
```

Security-critical example:

Sovereign input:
```sovereign
sensitive set password = "secret123"
```

Generated C output:
```c
unsigned char password[] = {0x73, 0x65, 0x63, 0x72, 0x65, 0x74, 0x31, 0x32, 0x33};
// Generated code to auto-zero after use
memset(password, 0, sizeof(password));
```

**Input:** `Program` (AST)
**Output:** Valid ANSI C code (string)

### Phase 5: compiler_self.sov

**Purpose:** Orchestrate the entire pipeline.

**Main Tasks:**
- `task main(argv: Vec<string>) -> int`
- `read_file(path: string) -> string`
- `compile_file(input: string, output: string)`

**Pipeline:**
```sovereign
task main(argv: Vec<string>) -> int {
    input_file = argv[0]
    output_file = argv[1]
    
    // Phase 2: Tokenize
    source = read_file(input_file)
    tokens = tokenize(source)
    
    // Phase 3: Parse
    program = parse_program(tokens)
    
    // Phase 4: Codegen
    c_code = codegen(program)
    
    // Write output
    write_file(output_file, c_code)
    return 0
}
```

## Security Implications

The self-hosted compiler preserves all Sovereign security features:

### Sensitive Data Handling

Variables marked `sensitive` are automatically zeroed:

```sovereign
sensitive set api_key = read_env("API_KEY")
// Sovereign compiler generates C code that:
// 1. Stores the value
// 2. Uses it
// 3. Calls memset() to zero the memory when out of scope
```

### Constant-Time Operations

Blocks marked `constant_time` prevent timing side-channels:

```sovereign
constant_time {
    // Compiler generates code without early exits/branches
    // All operations execute in fixed time
    check is_equal(password, expected) { }
}
```

## Performance Characteristics

| Phase | Input Size | Output Size | Time |
|-------|-----------|------------|------|
| Lexer (Phase 2) | 1 KB source | 500 tokens | < 1ms |
| Parser (Phase 3) | 500 tokens | 50 AST nodes | < 5ms |
| Codegen (Phase 4) | 50 AST nodes | 5 KB C code | < 10ms |
| **Total** | 1 KB Sovereign | 5 KB C | **< 20ms** |

## Troubleshooting

### Compilation Fails at Phase X

**Problem:** Compiler errors in one of the .sov files

**Solution:**
```bash
# Check specific phase with Rust compiler
./target/release/sovereign check src/lexer_self.sov

# If error, read error message carefully - it points to line number
# Edit the .sov file to fix
# Then retry bootstrap
```

### Bootstrap Doesn't Converge

**Problem:** `diff bootstrap bootstrap2` shows differences

**Possible Causes:**
1. Non-determinism in C code generation (e.g., hash table iteration order)
2. Timestamp/date-based differences
3. Bugs in the self-hosted compiler

**Debug:**
```bash
# Compare the C code files (they should be identical too)
diff bootstrap.c bootstrap2.c

# If C code differs, there's a bug in codegen_self.sov
# If C code is identical but binaries differ, it's the C compiler
# (gcc/clang are deterministic, so this is rare)
```

### Self-Hosted Compiler is Slower

**Problem:** `bootstrap` is slower than `target/release/sovereign`

**Explanation:** This is expected!
- Rust compiler uses LLVM with all optimizations
- Self-hosted compiler generates C, which is then compiled with `-O3`
- C compiler is good but not as aggressive as LLVM

**Improvement:**
Use PGO (Profile-Guided Optimization) to improve generated C:
```bash
# Generate profiling data
./bootstrap compile src/compiler_self.sov --pgo-gen -o bootstrap_pgo

# Use profiling data to optimize
gcc -fprofile-use bootstrap_pgo.c -o bootstrap_optimized
```

## Debugging the Self-Hosted Compiler

### Print Tokens (Debug Lexer)

Add to `lexer_self.sov`:
```sovereign
task tokenize_debug(source: string) -> Vec<Token> {
    tokens = tokenize(source)
    for token in tokens {
        print token
    }
    return tokens
}
```

Compile and run:
```bash
./bootstrap compile my_test.sov -o test_out.c
gcc test_out.c -o test_out
./test_out
```

### Print AST (Debug Parser)

Add to `parser_self.sov`:
```sovereign
task parse_debug(tokens: Vec<Token>) -> Program {
    program = parse_program(tokens)
    print_program(program)
    return program
}

task print_program(program: Program) -> void {
    for stmt in program.statements {
        print_stmt(stmt)
    }
}
```

### Generate Human-Readable C (Debug Codegen)

Check the generated `.c` files directly:
```bash
cat bootstrap.c | less
# Look for the generated function you're testing
```

## Next Steps After Convergence

Once bootstrap converges:

### 1. Compile the Compiler with Itself

```bash
# Use bootstrap compiler to compile itself again
./bootstrap compile src/compiler_self.sov --target c -o bootstrap3.c
gcc -O3 bootstrap3.c -o bootstrap3

# Should be identical to bootstrap2
diff bootstrap2 bootstrap3
```

### 2. Cross-Compile to Other Targets

```bash
# Generate EVM bytecode (smart contracts)
./bootstrap compile src/compiler_self.sov --target evm -o compiler.evm

# Generate WASM
./bootstrap compile src/compiler_self.sov --target wasm32 -o compiler.wasm

# Generate ARM64 (different platform)
./bootstrap compile src/compiler_self.sov --target linux-arm64 -o compiler.c
```

### 3. Integrate with Build System

Add to `Makefile`:
```makefile
bootstrap: target/release/sovereign
    ./target/release/sovereign bootstrap compile --target c -o bootstrap.c
    gcc -O3 bootstrap.c -o bootstrap
    ./bootstrap test tests/test_self_hosting.sov

.PHONY: bootstrap
```

## Contributing to Self-Hosting

To improve the self-hosted compiler:

1. **Write a test** in `tests/test_self_hosting.sov`
2. **Implement the feature** in the appropriate `.sov` file
3. **Test with Rust compiler**: `./target/release/sovereign test tests/test_self_hosting.sov`
4. **Bootstrap**: Follow the bootstrap process above
5. **Verify convergence**: `diff bootstrap bootstrap2`
6. **Submit PR** with both Rust compiler improvements and self-hosting improvements

## References

- **Self-hosting literature**: https://en.wikipedia.org/wiki/Bootstrapping_(compilers)
- **Recursive descent parsing**: https://en.wikipedia.org/wiki/Recursive_descent_parser
- **C code generation**: https://en.wikipedia.org/wiki/Compiler#Code_generation
- **Sovereign spec**: `docs/SPEC.md`
- **Language features**: `docs/LEARN.md`

## Questions?

If you have questions about the self-hosting process:

1. Check `docs/SELF_HOSTING.md` for technical details
2. Review the test cases in `tests/test_self_hosting.sov`
3. Read the generated `bootstrap.c` to see what code is produced
4. File an issue with specific error messages
