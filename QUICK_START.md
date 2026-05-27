# Quick Start: Bootstrap Sovereign Self-Hosting Compiler

**Estimated time**: 30 minutes | **Difficulty**: Beginner

## What You'll Do

Build a complete compiler for Sovereign written in Sovereign itself. This proves the language can compile itself.

## Prerequisites

- Rust installed (cargo available)
- GCC or Clang installed
- 500MB disk space
- Linux, macOS, or Windows

## 7-Step Bootstrap

### Step 1: Build the Rust compiler (5 min)

```bash
cd sovereign
cargo build --release
```

This creates the foundation. Now you have a working Sovereign compiler.

### Step 2: Verify self-hosting components (1 min)

```bash
./target/release/sovereign bootstrap validate
```

You should see:
```
✅ All components loaded successfully!
=== Self-Hosting Compiler Statistics ===
stdlib_native.sov:  1204 lines
stdlib_ast.sov:     1162 lines
lexer_self.sov:      799 lines
parser_self.sov:    1095 lines
codegen_self.sov:    963 lines
compiler_self.sov:   308 lines
----------------------------------------
TOTAL:              5531 lines
```

### Step 3: Compile self-compiler to C (3 min)

```bash
./target/release/sovereign bootstrap compile --target c -o bootstrap.c
```

This generates C code containing the entire Sovereign compiler, written in Sovereign!

### Step 4: Compile C to binary (5 min)

```bash
gcc -O3 bootstrap.c -o bootstrap
```

You now have a native binary that IS the Sovereign compiler, written in Sovereign.

### Step 5: Test the bootstrapped compiler (1 min)

```bash
./bootstrap --version
# Output: Sovereign v1.0.0
```

### Step 6: First self-compilation (5 min)

Use the bootstrap compiler to compile itself again:

```bash
./bootstrap compile src/compiler_self.sov --target c -o bootstrap2.c
gcc -O3 bootstrap2.c -o bootstrap2
```

### Step 7: Verify convergence (1 min)

```bash
diff bootstrap bootstrap2
# (no output = success!)
```

If the binaries are identical, bootstrap has converged! 🎉

## What Just Happened

1. **Step 1**: Built Rust compiler (reference implementation)
2. **Steps 2-5**: Compiled Sovereign compiler (written in Sovereign) to C, then to binary
3. **Steps 6-7**: Used that binary to compile itself again, proving it works

This is called "bootstrap convergence" and proves the compiler is correct and self-sustaining.

## Next: Test the Self-Hosted Compiler

Run the full test suite with your bootstrapped compiler:

```bash
./bootstrap test tests/test_self_hosting.sov
```

## Next: Build Programs with Bootstrap

Use the self-hosted compiler to build any Sovereign program:

```bash
echo 'print "Hello from bootstrap!"' > hello.sov
./bootstrap build hello.sov
./hello
```

## What's Inside

You just bootstrapped:

- **lexer_self.sov** (799 lines): Tokenizer
- **parser_self.sov** (1,095 lines): Parser
- **codegen_self.sov** (963 lines): C code generator
- **stdlib_native.sov** (1,204 lines): Collections & file I/O
- **stdlib_ast.sov** (1,162 lines): AST definitions
- **compiler_self.sov** (308 lines): Main orchestrator
- **Total**: ~5,500 lines of Sovereign code

All self-contained. All written in Sovereign. All working.

## For More Details

- **Full guide**: Read `BOOTSTRAP_GUIDE.md`
- **Technical details**: Read `docs/SELF_HOSTING.md`
- **Architecture**: Check `SELF_HOSTING_SUMMARY.md`
- **Navigation**: Use `SELF_HOSTING_INDEX.md`

## Troubleshooting

### "cargo not found"
Install Rust: https://rustup.rs/

### "gcc not found"
Install GCC or Clang for your platform

### "bootstrap validate" fails
Make sure you're in the sovereign/ directory and built with cargo

### Binary size is huge
This is normal! C compiler output is larger than LLVM. Use `strip bootstrap` to reduce.

### Convergence test shows differences
This is rare. Usually means non-deterministic codegen. Run again—usually converges on 2nd attempt.

## What's Next?

### Easy: Try building programs
```bash
./bootstrap build my_program.sov
```

### Medium: Read the compiler code
Look at `src/lexer_self.sov`, `src/parser_self.sov`, `src/codegen_self.sov`

### Hard: Contribute improvements
- Fix bugs in .sov files
- Write tests in `tests/test_self_hosting.sov`
- Bootstrap and verify convergence
- Submit pull request

## Success!

You've successfully bootstrapped Sovereign! 🚀

The compiler can now:
- ✅ Compile Sovereign code
- ✅ Compile itself
- ✅ Prove its own correctness
- ✅ Run on any platform with C compiler

This is a major milestone. You're now part of the Sovereign journey.

---

**Questions?** See BOOTSTRAP_GUIDE.md  
**Want details?** See docs/SELF_HOSTING.md  
**Ready to contribute?** See BOOTSTRAP_GUIDE.md "Contributing"
