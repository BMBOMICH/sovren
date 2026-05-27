# Sovereign

**The privacy-first systems programming language.**

Sovereign is a compiled language that combines the performance of C/C++ with Rust-level safety guarantees and unique privacy-focused features. The **entire compiler is written in Sovereign itself** (self-hosting).

## No External Dependencies

The Sovereign compiler requires **only a C compiler** (gcc or clang):

- No Rust
- No LLVM  
- No npm/cargo/pip
- No runtime libraries

Just `make` and you have a working compiler.

## Quick Start

```bash
# Build the compiler
make

# Compile a program
./build/sovereign build hello.sov -o hello.c
gcc -O2 hello.c -o hello
./hello

# Type-check only
./build/sovereign check myfile.sov
```

## Project Structure

```
sovereign/
├── src/                    # The compiler (100% Sovereign!)
│   ├── main.sov           # CLI entry point
│   ├── stdlib_native.sov  # Collections, I/O, strings
│   ├── stdlib_ast.sov     # AST types
│   ├── lexer_self.sov     # Tokenizer
│   ├── parser_self.sov    # Parser
│   ├── semantic_self.sov  # Type checker
│   ├── codegen_self.sov   # C code generator
│   └── compiler_self.sov  # Compiler orchestrator
├── bootstrap/             # Pre-generated C (for bootstrapping)
│   └── sovereign.c        # The bootstrap compiler
├── tests/                 # Test suite
├── examples/              # Example programs
├── archive/               # Legacy Rust implementation (historical)
└── Makefile              # Build system
```

## Language Features

### Security-First Design

```sovereign
// Sensitive data is automatically zeroed on scope exit
sensitive password: string = get_user_input()
// password is securely wiped here

// Constant-time operations prevent timing attacks
constant_time {
    check hmac_verify(expected, received) {
        return true
    }
}
```

### Clean Syntax

```sovereign
// Functions are called "tasks"
task greet(name: string) -> string {
    return "Hello, " + name + "!"
}

// Variables use "set"
set message = greet("World")
print message

// Conditionals use "check"
check message.len > 0 {
    print "Got a message!"
}

// Loops are intuitive
loop i from 0 to 10 {
    print i
}

loop item in collection {
    process(item)
}

loop 5 times {
    print "Repeat!"
}
```

### Structs and Enums

```sovereign
struct Point {
    x: int,
    y: int
}

enum Color {
    Red,
    Green,
    Blue,
    Custom(r: int, g: int, b: int)
}

task main() {
    set p = Point { x: 10, y: 20 }
    set c = Color::Custom(255, 128, 0)
    
    match c {
        Color::Red => print "Red!"
        Color::Custom(r, g, b) => print_fmt("RGB: %d,%d,%d", r, g, b)
        _ => print "Other color"
    }
}
```

### Concurrency

```sovereign
// Spawn lightweight threads
spawn worker {
    loop {
        set task = receive_task()
        process(task)
    }
}

// Channels for communication
set ch = make_chan(int, 10)
ch <- 42
set value = <-ch

// Async/await
async task fetch_data(url: string) -> string {
    set response = await http_get(url)
    return response.body
}
```

## Self-Hosting

Sovereign compiles itself. The bootstrap process:

1. `bootstrap/sovereign.c` is pre-generated C code
2. Compile it with gcc to get a working compiler
3. Use that compiler to compile the `.sov` source files
4. The output is identical (convergence verified)

To verify self-hosting:

```bash
make self-compile
```

## CLI Reference

```bash
# Build
sovereign build <file.sov>              # Compile to C code
sovereign build <file.sov> -o out.c     # Specify output file
sovereign build <file.sov> --optimize   # Enable optimizations

# Check
sovereign check <file.sov>              # Type-check only

# Format
sovereign fmt <file.sov>                # Format source code

# Info
sovereign version                       # Show version
sovereign --help                        # Show help
```

## Installation

```bash
# Clone
git clone https://github.com/BMBOMICH/sovereign.git
cd sovereign

# Build
make

# Install (optional)
sudo make install
```

## Testing

```bash
make test
```

## Contributing

Contributions welcome! The entire compiler is in `.sov` files:

1. Fork the repository
2. Make changes to the `.sov` files in `src/`
3. Run `make self-compile` to verify nothing broke
4. Submit a pull request

## License

MIT License. See LICENSE file.
