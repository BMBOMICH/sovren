# Sovereign Self-Hosting Guide

## Overview

Sovereign is now capable of self-compilation. This document explains the self-hosted compiler architecture and how to bootstrap it.

## Architecture

The self-hosted compiler consists of three main phases:

### Phase 1: Standard Library Extensions (stdlib_native.sov)
Provides foundational utilities:
- **Vec<T>**: Generic dynamic arrays with push, pop, get, set, len, free
- **HashMap<string, int>**: String-keyed hash tables for symbol tables
- **String methods**: split, join, find, replace, substring, trim, starts_with, ends_with
- **File I/O**: open, read, write, close, read_line, file_exists, delete_file
- **Byte arrays**: For binary data manipulation

### Phase 2: Lexer (lexer_self.sov)
Self-hosted tokenizer that:
- Reads Sovereign source files
- Produces Vec<Token> representing the token stream
- Handles all Sovereign keywords, operators, literals
- Tracks line/column information
- Manages indentation for block structure

**Performance:** O(n) single-pass lexing

### Phase 3: Parser (parser_self.sov)
Recursive descent parser that:
- Consumes Vec<Token> from lexer
- Produces Program AST (type-safe using Sovereign enums/structs)
- Implements full Sovereign grammar
- Provides error recovery and meaningful diagnostics

**Performance:** O(n) for well-formed programs

### Phase 4: Code Generator (codegen_self.sov)
Emits C code from Program AST:
- Generates portable ANSI C output
- Preserves security semantics (sensitive auto-zeroing, constant-time blocks)
- Handles all Sovereign constructs (tasks, structs, enums, match, async, etc.)
- Integrates with C runtime and stdlib

**Output:** Valid C files compilable with gcc/clang

## File Structure

```
src/
├── stdlib_native.sov        # Extended stdlib (collections, file I/O)
├── stdlib_ast.sov           # AST type definitions
├── lexer_self.sov           # Self-hosted lexer
├── parser_self.sov          # Self-hosted parser
├── codegen_self.sov         # Self-hosted C codegen
└── compiler_self.sov        # Main entry point (ties all phases together)

tests/
└── test_self_hosting.sov    # Comprehensive test suite
```

## Bootstrap Process

### Step 1: Initial Compilation (Rust Compiler)
```bash
cargo build --release
./target/release/sovereign compile src/compiler_self.sov --target c -o bootstrap.c
gcc -O3 bootstrap.c -o bootstrap
```

This produces the first self-hosted compiler binary.

### Step 2: First Self-Compilation
```bash
./bootstrap compile src/compiler_self.sov --target c -o bootstrap2.c
gcc -O3 bootstrap2.c -o bootstrap2
```

### Step 3: Convergence Test
```bash
diff bootstrap bootstrap2
```

If binaries are identical, the compiler has reached bootstrap convergence.

## Key Implementation Details

### AST Representation (stdlib_ast.sov)

```sovereign
enum Token {
    Keyword(string),
    Identifier(string),
    IntLiteral(int),
    StringLiteral(string),
    // ... 50+ token types
}

struct Expr {
    kind: int,  // discriminant for expression type
    // Various tagged fields depending on kind
    value: int,
    string_value: string,
    children: Vec<Expr>,
}

enum Stmt {
    // Statement variants: VarDecl, FunctionDecl, If, Loop, etc.
}

struct Program {
    statements: Vec<Stmt>,
    imports: Vec<string>,
}
```

### Symbol Table Management

The parser maintains symbol tables for:
- Variables (type, scope)
- Functions (signature, generic instantiations)
- Structs (fields, methods)
- Type aliases

Implementation uses nested HashMap for scope management:
```sovereign
set globals = HashMap::new()
set locals = Vec::new()  // Stack of local scopes
```

### Error Handling

Parser errors include:
- Line/column information
- Expected vs. actual token
- Suggestion for common mistakes

Example:
```
Error at line 42, col 8:
  Expected closing '}' but found 'EOF'
  Hint: Did you mean to close the function body?
```

## Testing

Run comprehensive test suite:
```bash
sovereign test tests/test_self_hosting.sov
```

Tests cover:
- Lexer: tokenization of all Sovereign constructs
- Parser: parsing of valid programs and error recovery
- Codegen: C output correctness and compilation
- Round-trip: compiling self-compiler produces valid output

## Performance Characteristics

| Phase | Input | Output | Complexity |
|-------|-------|--------|------------|
| Lexer | Source code (string) | Vec<Token> | O(n) |
| Parser | Vec<Token> | Program AST | O(n) |
| Codegen | Program AST | C source code | O(n) |

**Total compilation time:** < 500ms for typical programs

## Limitations and Future Work

Current limitations:
- No incremental compilation (full recompile each time)
- No optimization passes (C compiler handles this)
- Limited error recovery (stops on first error)
- No parallel compilation

Future improvements:
- Incremental compilation with cached ASTs
- Sovereign optimizer pass (before codegen)
- Better error recovery for IDE support
- Parallel compilation units

## Security Considerations

The self-hosted compiler preserves all Sovereign security features:

1. **Sensitive auto-zeroing**: Variables marked `sensitive` compile to code that erases memory
2. **Constant-time blocks**: `constant_time { }` prevents timing side-channels
3. **Borrow checking**: Memory safety enforced at parse/semantic analysis time
4. **Thread safety**: Data race prevention in concurrent code

All security operations are preserved in the generated C code.

## Bootstrapping on New Platforms

To compile Sovereign on a new platform:

1. Install C compiler (gcc, clang, or MSVC)
2. Install Rust toolchain (if not already available)
3. Build using Rust compiler as initial bootstrap:
   ```bash
   cargo build --release
   ```
4. Generate self-hosted compiler:
   ```bash
   ./target/release/sovereign compile src/compiler_self.sov --target c
   ```
5. Compile generated C:
   ```bash
   gcc bootstrap.c -o sovereign
   ```

Now the Sovereign compiler is self-hosting on this platform.

## Contributing

To contribute to the self-hosted compiler:

1. Write tests in `tests/test_self_hosting.sov`
2. Implement feature in appropriate `.sov` file
3. Run test suite: `sovereign test tests/test_self_hosting.sov`
4. Bootstrap and verify convergence
5. Submit pull request

## References

- Self-hosting literature: https://en.wikipedia.org/wiki/Bootstrapping_(compilers)
- Sovereign language spec: docs/SPEC.md
- LLVM-based codegen reference: src/codegen.rs (Rust implementation)
