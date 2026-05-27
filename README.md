# Sovereign

**The privacy-first systems programming language.**

Sovereign is a compiled language that combines the performance of C/C++ with Rust-level safety guarantees and unique privacy-focused features. It compiles to native machine code via LLVM and supports cross-compilation to multiple targets.

## Features

### Language
- **Python-like syntax** with optional type annotations - all types are inferred
- **Variables**: `set x = 10` or just `x = 10`
- **Functions**: `task name(param: type) -> return_type { }`
- **Conditionals**: `check condition { } else { }`
- **Loops**: `loop N times`, `loop from..to`, `loop condition { }`, `for item in array`
- **Structs and enums** with pattern matching
- **Generics** with constraints: `task sort[T where T: Comparable](arr: [T])`
- **Closures**: `|x| x * 2`
- **Async/await** with LLVM coroutines
- **OS threads**: `spawn` / join with channels for communication
- **FFI**: Call any C function with `extern task`

### Security (Unique to Sovereign)
- **`sensitive` keyword**: Variables marked sensitive are automatically zeroed on scope exit using volatile stores
- **`constant_time` blocks**: Code inside executes in constant time to prevent timing side-channel attacks
- **`purge` statement**: Explicitly and securely zero any variable
- **Borrow checker**: Ownership, moves, borrows, and lifetime tracking
- **Thread safety analysis**: Prevents data races at compile time
- **Integer overflow trapping**: Always on in safe mode
- **Array bounds checking**: Always on in safe mode
- **Stack canaries**: Buffer overflow detection
- **ASLR, CFI, NX/DEP**: Enabled by default

### Built-in Cryptography
- SHA-256 (constant-time implementation)
- HMAC-SHA256
- AES-256 (constant-time, no timing side-channels)
- Secure random (OS-provided)

## Installation

### Prerequisites
- Rust 1.70+ with Cargo
- LLVM 18.0 (for the `inkwell` bindings)
- A C compiler (for linking)

### Build from Source

```bash
git clone https://github.com/BMBOMICH/sovereign.git
cd sovereign
cargo build --release
```

The binary will be at `target/release/sovereign`.

## Quick Start

### Hello World

```sovereign
// hello.sov
print "Hello, World!"
```

```bash
sovereign build hello.sov
./hello
```

### Variables and Functions

```sovereign
// Inferred types
set name = "Sovereign"
set count = 42
set pi = 3.14159

// Explicit types (optional)
set message: string = "Hello"
set value: int = 100

// Functions
task greet(name: string) -> string {
    return "Hello, " + name + "!"
}

print greet("World")
```

### Control Flow

```sovereign
// Conditionals
check x > 10 {
    print "big"
} else {
    print "small"
}

// Loops
loop 5 times {
    print "iteration"
}

loop from 0 to 10 {
    print i
}

for item in items {
    print item
}
```

### Security Features

```sovereign
// Sensitive data - auto-zeroed on scope exit
sensitive set api_key = get_env("API_KEY")
sensitive set password = read_password()

// Use the sensitive data...
check verify_password(password, hash) {
    grant_access()
}
// password is securely zeroed here

// Constant-time comparison (prevents timing attacks)
constant_time {
    check secret_a == secret_b {
        return true
    }
}

// Explicit secure zero
set temp_key = derive_key(master)
// ... use temp_key ...
purge temp_key  // Zero immediately
```

### Structs and Enums

```sovereign
struct User {
    name: string,
    age: int,
    email: string?  // Nullable
}

enum Result[T] {
    Ok(T),
    Err(string)
}

task create_user(name: string) -> Result[User] {
    check name.len() == 0 {
        return err("Name cannot be empty")
    }
    return ok(User { name: name, age: 0, email: null })
}

match create_user("Alice") {
    Ok(user) => print user.name,
    Err(msg) => print "Error: " + msg
}
```

### Concurrency

```sovereign
// Spawn OS threads
set result = 0
spawn worker {
    // Runs in a new thread
    result = expensive_computation()
}
// worker.join() is automatic at scope exit

// Channels for thread communication
set ch = make_chan[int]()

spawn producer {
    loop from 1 to 100 {
        ch.send(i)
    }
    ch.close()
}

spawn consumer {
    for value in ch {
        print value
    }
}
```

## CLI Reference

```bash
# Build
sovereign build <file.sov>              # Compile to native binary
sovereign build <file.sov> --size       # Optimize for smallest binary
sovereign build <file.sov> --debug      # Include debug symbols (DWARF)
sovereign build <file.sov> --target <t> # Cross-compile
sovereign build <file.sov> --pgo-gen    # Instrument for PGO
sovereign build <file.sov> --pgo-use    # Optimize with PGO profile
sovereign build <file.sov> --web        # Web app (HTML+CSS+WASM)
sovereign build <file.sov> --evm        # Smart contract (Ethereum)

# Run
sovereign run <file.sov>                # Interpret (scripting mode)
sovereign repl                          # Interactive REPL

# Tools
sovereign test <file.sov>               # Run built-in tests
sovereign check <file.sov>              # Type-check only
sovereign fmt <file.sov>                # Format source code
sovereign lsp                           # Start language server
sovereign targets                       # List cross-compile targets
sovereign cache clear|stats             # Manage compilation cache
sovereign version                       # Show version and features
```

### Cross-Compilation Targets

- `windows-x64`
- `linux-x64`
- `linux-arm64`
- `macos-x64`
- `macos-arm64`
- `wasm32`
- `evm` (Ethereum Virtual Machine)

## Editor Support

### VS Code

Install the Sovereign extension from `vscode-sovereign/`:

```bash
cd vscode-sovereign
npm install
npm run compile
# Then install the .vsix file
```

Features:
- Syntax highlighting
- Error diagnostics
- Autocompletion
- Hover documentation
- Go to definition
- Rename symbol
- Code formatting

## Self-Hosting Compiler

Sovereign now has a **self-hosting compiler written in Sovereign itself**! This is a major milestone that enables the language to compile itself.

### Quick Start: Bootstrap

```bash
# Step 1: Build the Rust compiler
cargo build --release

# Step 2: Verify self-hosting components
./target/release/sovereign bootstrap validate

# Step 3: Compile self-compiler to C
./target/release/sovereign bootstrap compile --target c -o bootstrap.c

# Step 4: Compile C to native binary
gcc -O3 bootstrap.c -o bootstrap

# Step 5: Test the bootstrapped compiler
./bootstrap --version

# Step 6: Use bootstrap to compile itself again
./bootstrap compile src/compiler_self.sov --target c -o bootstrap2.c
gcc -O3 bootstrap2.c -o bootstrap2

# Step 7: Verify convergence (should be identical)
diff bootstrap bootstrap2
```

### Self-Hosting Architecture

The self-hosted compiler consists of ~5,200 lines of Sovereign code organized in phases:

1. **stdlib_native.sov** (1200+ lines): Extended stdlib with Vec, HashMap, file I/O
2. **stdlib_ast.sov** (1100+ lines): AST type definitions (Token, Expr, Stmt, Program)
3. **lexer_self.sov** (700+ lines): Self-hosted lexer (source → tokens)
4. **parser_self.sov** (1000+ lines): Self-hosted parser (tokens → AST)
5. **codegen_self.sov** (900+ lines): C code generator (AST → C)
6. **compiler_self.sov** (300+ lines): Main orchestrator

For detailed information, see:
- **[BOOTSTRAP_GUIDE.md](BOOTSTRAP_GUIDE.md)** - Step-by-step bootstrap process
- **[docs/SELF_HOSTING.md](docs/SELF_HOSTING.md)** - Technical architecture details

## Editor Support



```
sovereign/
  src/
    main.rs          # CLI entry point
    lexer.rs         # Tokenizer
    parser.rs        # Parser
    ast.rs           # Abstract syntax tree
    semantic.rs      # Semantic analysis
    infer.rs         # Type inference
    borrow.rs        # Borrow checker
    safety.rs        # Safety analysis
    threads.rs       # Thread safety analysis
    codegen.rs       # LLVM code generation
    interpreter.rs   # Script mode interpreter
    lsp.rs           # Language server
    ...
  tests/             # Test files (.sov)
  docs/              # Documentation
  vscode-sovereign/  # VS Code extension
```

## Testing

Run the test suite:

```bash
# Run all Sovereign tests
sovereign test tests/test1_basics.sov
sovereign test tests/test2_control_flow.sov
sovereign test tests/test3_structs.sov
sovereign test tests/test4_security.sov

# Run Rust unit tests
cargo test
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `cargo test` and `sovereign test tests/*.sov`
5. Submit a pull request

## License

See [LICENSE](LICENSE) for details.
