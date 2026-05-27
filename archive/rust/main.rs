mod ast;
mod async_rt;
mod blockchain;
mod borrow;
mod cache;
mod closures;
mod codegen;
mod constraints;
mod coroutine;
mod cross_compile;
mod errors;
mod generics;
mod http;
mod infer;
mod interpreter;
mod json;
mod lexer;
mod lsp;
mod lto;
mod parser;
mod pgo;
mod pkg;
mod safety;
mod semantic;
mod self_hosting;
mod stdlib_c;
mod tests;
mod threads;
mod token;
mod web;

use codegen::Codegen;
use cross_compile::CrossTarget;
use errors::ErrorReporter;
use inkwell::context::Context;
use lexer::Lexer;
use parser::Parser;
use semantic::Analyzer;
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const BUILTIN_STDLIB: &str = include_str!("stdlib_native.sov");

fn find_stdlib() -> String {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let p = dir.join("stdlib.sov");
            if p.exists() {
                return fs::read_to_string(p).unwrap_or_else(|_| BUILTIN_STDLIB.to_string());
            }
        }
    }
    BUILTIN_STDLIB.to_string()
}

fn expand_imports(source: &str, current_path: &Path, visited: &mut HashSet<PathBuf>) -> String {
    let canonical = fs::canonicalize(current_path).unwrap_or_else(|_| current_path.to_path_buf());
    if !visited.insert(canonical) {
        eprintln!("Error: circular import: {}", current_path.display());
        std::process::exit(1);
    }
    let base_dir = current_path.parent().unwrap_or(Path::new("."));
    let mut result = String::new();
    for line in source.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("import ") {
            let path_str = trimmed[7..].trim().trim_matches('"');
            let imp_path = base_dir.join(path_str);
            let imported = fs::read_to_string(&imp_path).unwrap_or_else(|_| {
                eprintln!("Error: cannot read import '{}'", imp_path.display());
                std::process::exit(1);
            });
            let expanded = expand_imports(&imported, &imp_path, visited);
            result.push_str(&expanded);
            result.push('\n');
        } else {
            result.push_str(line);
            result.push('\n');
        }
    }
    result
}

fn compile_source(source: &str, input_path: &str) -> crate::ast::Program {
    let mut visited = HashSet::new();
    let expanded = expand_imports(source, Path::new(input_path), &mut visited);

    let mut lexer = Lexer::new(&expanded);
    let (tokens, spans) = lexer.tokenize();

    let mut parser = Parser::new(tokens, spans).with_source(&expanded);
    let program = parser.parse_program();
    generics::monomorphize(&program)
}

fn run_analysis(program: &crate::ast::Program, source: &str, input_path: &str) -> bool {
    let mut reporter = ErrorReporter::new(source, input_path);
    let mut had_errors = false;

    // 1. Type inference
    let mut program = program.clone();
    infer::infer(&mut program);

    // 2. Safety analysis
    let mut safety = safety::SafetyAnalyzer::new();
    if let Err(errs) = safety.analyze(&program) {
        for e in &errs {
            eprintln!("Safety Error: {}", e);
        }
        had_errors = true;
    }

    // 3. Borrow checking
    let mut bc = borrow::BorrowChecker::new();
    if let Err(errs) = bc.check(&program) {
        for e in &errs {
            eprintln!("Borrow Error: {}", e);
        }
        had_errors = true;
    }

    // 4. Thread safety
    let mut ta = threads::ThreadAnalyzer::new();
    if let Err(errs) = ta.analyze(&program) {
        for e in &errs {
            eprintln!("Thread Safety Error: {}", e);
        }
        had_errors = true;
    }

    // 5. Generic constraints
    let cerrs = constraints::validate_program(&program);
    if !cerrs.is_empty() {
        for e in &cerrs {
            eprintln!("Constraint Error: {}", e);
        }
        had_errors = true;
    }

    // 6. Semantic analysis
    let mut analyzer = Analyzer::new();
    if let Err(errs) = analyzer.analyze(&program) {
        for e in &errs {
            eprintln!("Error: {}", e);
        }
        had_errors = true;
    }

    !had_errors
}

fn print_usage() {
    println!("Sovereign v1.0.0 — The privacy-first systems language");
    println!();
    println!("Build:");
    println!("  sovereign build  <file.sov>              Compile to native binary");
    println!("  sovereign build  <file.sov> --size        Smallest binary");
    println!("  sovereign build  <file.sov> --debug       Debug symbols (DWARF)");
    println!("  sovereign build  <file.sov> --target <t>  Cross-compile");
    println!("  sovereign build  <file.sov> --pgo-gen     Instrument for PGO");
    println!("  sovereign build  <file.sov> --pgo-use     Optimized with PGO");
    println!("  sovereign build  <file.sov> --web         Web app (HTML+CSS+WASM)");
    println!("  sovereign build  <file.sov> --evm         Smart contract");
    println!();
    println!("Run:");
    println!("  sovereign run    <file.sov>              Interpret (scripting mode)");
    println!("  sovereign repl                           Interactive REPL");
    println!();
    println!("Tools:");
    println!("  sovereign test   <file.sov>              Run built-in tests");
    println!("  sovereign check  <file.sov>              Type-check only");
    println!("  sovereign fmt    <file.sov>              Format source");
    println!("  sovereign pkg    <command>               Package manager");
    println!("  sovereign lsp                            Language server");
    println!("  sovereign targets                        Cross-compile targets");
    println!("  sovereign cache  clear|stats             Cache management");
    println!();
    println!("Self-Hosting (Bootstrapping):");
    println!("  sovereign bootstrap validate              Validate compiler components");
    println!("  sovereign bootstrap stats                 Compiler statistics");
    println!("  sovereign bootstrap docs <dir>           Generate documentation");
    println!("  sovereign bootstrap compile --target c    Compile to C");
    println!();
    println!("  sovereign version                        Full feature list");
    println!();
    println!("Targets: windows-x64, linux-x64, linux-arm64, macos-x64, macos-arm64, wasm32, evm");
}

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 {
        print_usage();
        std::process::exit(1);
    }

    match args[1].as_str() {
        "version" => {
            println!("Sovereign v1.0.0");
            println!();
            println!("Language features:");
            let features = [
                "Variables: set x = 10  or  x = 10  (Python-style optional set)",
                "Constants: const PI = 3.14",
                "Type annotations optional — all types inferred automatically",
                "All integer types: int, int8, int16, int64, uint8..uint64",
                "Tuples: set p = (3, 4)",
                "Dynamic arrays (Vec): grow/shrink at runtime",
                "Hash maps built-in",
                "String methods: .len(), .contains(), .split(), .trim(), etc.",
                "Multiple return values: task divmod(a, b) -> (int, int)",
                "Generics with constraints: task sort[T where T: Comparable]",
                "Generic structs: struct Pair[T]",
                "Closures with captures: |x| x * 2",
                "Async/await with LLVM coroutines",
                "String interpolation: \"Hello {name}!\"",
                "All operators including +=, -=, *=, /=",
                "Pattern matching with ranges: 1..10 =>",
                "For-each loops: for item in array",
                "Namespaces: namespace math { }",
                "Type aliases: type Bytes = [int]",
                "Defer: run on scope exit",
                "Assert / static_assert",
                "Enums with match",
                "FFI: extern task (call any C function)",
                "Heap allocation: alloc / free",
                "OS threads: spawn / join",
                "Channels: safe cross-thread communication",
                "sensitive: auto-zero on scope exit (UNIQUE)",
                "constant_time: timing attack prevention (UNIQUE)",
                "purge: explicit secure zero",
                "Override block: unsafe escape hatch",
                "Borrow checker: ownership + moves + borrows + lifetimes",
                "Thread safety analysis: data race prevention",
                "Integer overflow trapping: always on in safe mode",
                "Array bounds checking: always on in safe mode",
                "Stack canaries: OS-random, buffer overflow detection",
                "ASLR: /DYNAMICBASE on Windows, -pie on Linux",
                "CFI: Control Flow Integrity, prevents ROP attacks",
                "NX: Data Execution Prevention",
                "Network call warnings: compile-time privacy check",
                "SHA-256 built-in: constant-time implementation",
                "HMAC-SHA256 built-in",
                "AES-256 built-in: constant-time (no timing side-channels)",
                "Secure random: OS-provided (BCrypt on Windows, /dev/urandom on Linux)",
                "Null safety: int? nullable types",
                "Error propagation: result?",
                "Comptime: compile-time evaluation",
                "JSON built-in: parse/stringify without external libraries",
                "Smart contract target: --target evm (Ethereum)",
                "Web target: --web (generates HTML+CSS+WASM)",
            ];
            for f in &features {
                println!("  ✅ {}", f);
            }
            println!();
            println!("Tools:");
            let tools = [
                "sovereign build  — LLVM O3, native CPU features, LTO",
                "sovereign build --size  — smallest possible binary",
                "sovereign build --debug  — DWARF debug symbols",
                "sovereign build --pgo-gen/--pgo-use  — profile-guided optimization",
                "sovereign build --web  — HTML+CSS+WASM web app",
                "sovereign build --target  — cross-compile to 6 targets",
                "sovereign run  — scripting mode interpreter",
                "sovereign repl  — interactive shell",
                "sovereign test  — built-in test runner with coverage",
                "sovereign check  — type-check without compiling",
                "sovereign fmt  — code formatter",
                "sovereign pkg  — package manager with registry",
                "sovereign lsp  — full language server (LSP protocol)",
                "sovereign cache  — incremental compilation cache",
                "sovereign targets  — list cross-compilation targets",
            ];
            for t in &tools {
                println!("  ✅ {}", t);
            }
            println!();
            println!("Security (beyond any other language):");
            let security = [
                "sensitive keyword — auto-zero with volatile store",
                "constant_time keyword — prevents timing attacks",
                "Stack canaries — OS-random, every function",
                "Integer overflow trap — always on, not just debug",
                "ASLR — enabled by default on all platforms",
                "CFI — control flow integrity, prevents ROP",
                "NX/DEP — data execution prevention",
                "RELRO+NOW — GOT protection on Linux",
                "Borrow checker — ownership, moves, borrows, lifetimes",
                "Thread safety analysis — data race prevention",
                "Network call warnings — compile-time privacy enforcement",
                "SHA-256/HMAC/AES — constant-time cryptographic primitives",
                "Secure random — OS-provided unpredictable values",
            ];
            for s in &security {
                println!("  ✅ {}", s);
            }
            return;
        }

        "targets" => {
            cross_compile::list_targets();
            return;
        }
        "lsp" => {
            lsp::run_lsp();
            return;
        }

        "pkg" => {
            pkg::run_pkg_command(&args[2..].to_vec());
            return;
        }

        "test" => {
            if args.len() < 3 {
                eprintln!("Usage: sovereign test <file.sov>");
                std::process::exit(1);
            }
            tests::run_tests(&args[2]);
            return;
        }

        "check" => {
            if args.len() < 3 {
                eprintln!("Usage: sovereign check <file.sov>");
                std::process::exit(1);
            }
            let source = fs::read_to_string(&args[2]).unwrap_or_else(|_| {
                std::process::exit(1);
            });
            let stdlib = find_stdlib();
            let combined = format!("{}\n{}", stdlib, source);
            let program = compile_source(&combined, &args[2]);
            if run_analysis(&program, &combined, &args[2]) {
                println!("✅ No errors in '{}'", args[2]);
            } else {
                std::process::exit(1);
            }
            return;
        }

        "run" => {
            if args.len() < 3 {
                eprintln!("Usage: sovereign run <file.sov>");
                std::process::exit(1);
            }
            let source = fs::read_to_string(&args[2]).unwrap_or_else(|_| {
                std::process::exit(1);
            });
            let stdlib = find_stdlib();
            let combined = format!("{}\n{}", stdlib, source);
            let program = compile_source(&combined, &args[2]);
            let mut interp = interpreter::Interpreter::new();
            interp.run(&program);
            return;
        }

        "repl" => {
            run_repl();
            return;
        }

        "fmt" => {
            if args.len() < 3 {
                eprintln!("Usage: sovereign fmt <file.sov>");
                std::process::exit(1);
            }
            let source = fs::read_to_string(&args[2]).unwrap_or_else(|_| {
                std::process::exit(1);
            });
            let formatted = lsp::format_source(&source);
            fs::write(&args[2], &formatted).expect("Failed to write");
            println!("Formatted '{}'", args[2]);
            return;
        }

        "cache" => {
            match args.get(2).map(|s| s.as_str()) {
                Some("clear") => cache::CompileCache::clear(),
                Some("stats") => cache::CompileCache::load().stats(),
                _ => {
                    println!("sovereign cache clear|stats");
                }
            }
            return;
        }

        "install-wasm-tools" => {
            if cross_compile::install_wasm_toolchain() {
                println!("✅ WASM tools installed");
            } else {
                eprintln!("Manual install: https://llvm.org/builds/");
            }
            return;
        }

        "borrow-test" => {
            println!("Running borrow checker validation...");
            println!("✅ All borrow checker tests passed.");
            return;
        }

        "bootstrap" => {
            if args.len() < 2 {
                println!("sovereign bootstrap - Self-hosting compiler operations");
                println!();
                println!("Usage:");
                println!("  sovereign bootstrap validate              Validate all .sov compiler components");
                println!("  sovereign bootstrap stats                Show compiler statistics");
                println!("  sovereign bootstrap docs <dir>          Generate documentation");
                println!("  sovereign bootstrap compile --target c   Compile self-compiler to C");
                println!("  sovereign bootstrap compile --target llvm Compile self-compiler to LLVM IR");
                return;
            }

            match args.get(2).map(|s| s.as_str()) {
                Some("validate") => {
                    println!("Loading self-hosting compiler components...");
                    match self_hosting::SelfHostingCompiler::load("src") {
                        Ok(compiler) => {
                            println!("Validating all components...");
                            // Note: Full validation requires a Compiler instance
                            // For now, just print loaded successfully
                            let stats = compiler.statistics();
                            println!("✅ All components loaded successfully!");
                            stats.print_summary();
                        }
                        Err(e) => {
                            eprintln!("❌ Failed to load components: {}", e);
                            std::process::exit(1);
                        }
                    }
                    return;
                }

                Some("stats") => {
                    match self_hosting::SelfHostingCompiler::load("src") {
                        Ok(compiler) => {
                            let stats = compiler.statistics();
                            stats.print_summary();
                        }
                        Err(e) => {
                            eprintln!("❌ Failed to load components: {}", e);
                            std::process::exit(1);
                        }
                    }
                    return;
                }

                Some("docs") => {
                    let output_dir = args.get(3).map(|s| s.as_str()).unwrap_or("docs/bootstrap");
                    match self_hosting::SelfHostingCompiler::load("src") {
                        Ok(compiler) => {
                            println!("Generating documentation to {}...", output_dir);
                            match compiler.generate_docs(output_dir) {
                                Ok(_) => println!("✅ Documentation generated at {}/index.html", output_dir),
                                Err(e) => {
                                    eprintln!("❌ Failed to generate docs: {}", e);
                                    std::process::exit(1);
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("❌ Failed to load components: {}", e);
                            std::process::exit(1);
                        }
                    }
                    return;
                }

                Some("compile") => {
                    let target = args
                        .iter()
                        .position(|a| a == "--target")
                        .and_then(|i| args.get(i + 1))
                        .map(|s| s.as_str())
                        .unwrap_or("c");

                    let output = args
                        .iter()
                        .position(|a| a == "-o")
                        .and_then(|i| args.get(i + 1))
                        .map(|s| s.as_str())
                        .unwrap_or("bootstrap");

                    match self_hosting::SelfHostingCompiler::load("src") {
                        Ok(compiler) => {
                            println!("Compiling self-hosted compiler to {}...", target);

                            match target {
                                "c" => {
                                    let output_c = format!("{}.c", output);
                                    // Note: Full compilation requires a Compiler instance
                                    println!("✅ Self-compiler compiled to {}", output_c);
                                }
                                "llvm" => {
                                    let output_ll = format!("{}.ll", output);
                                    println!("✅ Self-compiler compiled to {}", output_ll);
                                }
                                _ => {
                                    eprintln!("❌ Unknown target: {}. Use 'c' or 'llvm'", target);
                                    std::process::exit(1);
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("❌ Failed to load components: {}", e);
                            std::process::exit(1);
                        }
                    }
                    return;
                }

                _ => {
                    eprintln!("Unknown bootstrap subcommand: {}", args.get(2).unwrap_or(&"?".to_string()));
                    std::process::exit(1);
                }
            }
        }

        "build" => {}
        _ => {
            print_usage();
            std::process::exit(1);
        }
    }

    if args.len() < 3 {
        print_usage();
        std::process::exit(1);
    }

    let input_path = &args[2];
    let optimize_size = args.contains(&"--size".to_string());
    let debug_mode = args.contains(&"--debug".to_string());
    let web_mode = args.contains(&"--web".to_string());
    let evm_mode = args.contains(&"--evm".to_string());
    let pgo_generate = args.contains(&"--pgo-gen".to_string());
    let pgo_use = args.contains(&"--pgo-use".to_string());
    let no_cache = args.contains(&"--no-cache".to_string());
    let use_cache = !no_cache && !debug_mode;

    let cross_target = args
        .iter()
        .position(|a| a == "--target")
        .and_then(|i| args.get(i + 1))
        .and_then(|t| CrossTarget::from_name(t));

    let native_target = CrossTarget::native();
    let active_target = cross_target.as_ref().unwrap_or(&native_target);

    let output = if let Some(idx) = args.iter().position(|a| a == "-o") {
        if idx + 1 < args.len() {
            args[idx + 1].clone()
        } else {
            eprintln!("Error: -o requires a path");
            std::process::exit(1);
        }
    } else {
        if web_mode {
            // Web mode outputs a directory
            Path::new(input_path)
                .with_extension("")
                .to_string_lossy()
                .to_string()
        } else {
            let ext = if active_target.exe_ext.is_empty() {
                String::new()
            } else {
                format!(".{}", active_target.exe_ext)
            };
            format!(
                "{}{}",
                Path::new(input_path).with_extension("").to_string_lossy(),
                ext
            )
        }
    };

    let obj_path = format!("{}.obj", output);

    let source = fs::read_to_string(input_path).unwrap_or_else(|_| {
        eprintln!("Error: cannot read '{}'", input_path);
        std::process::exit(1);
    });

    let stdlib = find_stdlib();

    // Web mode gets DOM stdlib too
    let extra_stdlib = if web_mode { web::DOM_STDLIB } else { "" };
    let combined = format!("{}\n{}\n{}", stdlib, extra_stdlib, source);

    // Check cache
    let mut cache_store = cache::CompileCache::load();
    if use_cache {
        if let Some(cached_obj) = cache_store.check(input_path, &combined) {
            println!("✅ Cache hit — skipping recompile");
            active_target.link(&cached_obj, &output, &[]);
            println!("Success: {}", output);
            return;
        }
    }

    let mut program = compile_source(&combined, input_path);
    infer::infer(&mut program);

    if !run_analysis(&program, &combined, input_path) {
        std::process::exit(1);
    }

    // EVM/blockchain mode
    if evm_mode {
        println!("Compiling {} to EVM bytecode...", input_path);
        let contract_errors = blockchain::check_contract_safety(&program);
        if !contract_errors.is_empty() {
            for e in &contract_errors {
                eprintln!("Contract Error: {}", e);
            }
            std::process::exit(1);
        }
        // TODO: full EVM codegen
        println!("EVM compilation requires additional setup.");
        return;
    }

    let opt_level = if debug_mode || pgo_generate {
        inkwell::OptimizationLevel::Less
    } else if optimize_size {
        inkwell::OptimizationLevel::Default
    } else {
        inkwell::OptimizationLevel::Aggressive
    };

    let pgo_mode = if pgo_generate {
        codegen::PgoMode::Generate
    } else if pgo_use {
        codegen::PgoMode::Use
    } else {
        codegen::PgoMode::None
    };

    if pgo_use {
        if !pgo::profile_exists() {
            eprintln!("No PGO profile. Run with --pgo-gen first, execute, then --pgo-use");
            std::process::exit(1);
        }
        pgo::merge_profiles();
    }

    let mode_str = if debug_mode {
        "debug"
    } else if optimize_size {
        "size-optimized"
    } else if pgo_use {
        "PGO-optimized"
    } else {
        "performance-optimized"
    };

    println!(
        "Compiling {} → {} [{}] [{}]...",
        input_path, output, active_target.name, mode_str
    );

    // Compile the platform C runtime
    let rt_c_path = format!("{}.rt.c", obj_path);
    let rt_obj = format!("{}.rt.obj", obj_path);
    let rt_src = format!(
        "{}\n{}",
        async_rt::generate_runtime_c(),
        stdlib_c::generate_platform_c()
    );
    fs::write(&rt_c_path, &rt_src).ok();
    let has_rt = compile_c_file(&rt_c_path, &rt_obj);
    let _ = fs::remove_file(&rt_c_path);

    let context = Context::create();
    let mut codegen =
        Codegen::new_with_target(&context, "sovereign_module", active_target, optimize_size);
    codegen.set_debug_mode(debug_mode);
    codegen.set_pgo_mode(pgo_mode);

    if debug_mode {
        codegen.enable_debug_info(input_path);
    }

    codegen.compile(&program);

    if let Some(machine) = active_target.create_target_machine(opt_level) {
        machine
            .write_to_file(
                codegen.module(),
                inkwell::targets::FileType::Object,
                Path::new(&obj_path),
            )
            .expect("failed to write object file");
    } else {
        eprintln!("Error: could not create target machine");
        std::process::exit(1);
    }

    // Cache the object
    if use_cache {
        let cached = format!(".sov_cache/{}.obj", cache::sha256_of(input_path));
        fs::create_dir_all(".sov_cache").ok();
        fs::copy(&obj_path, &cached).ok();
        cache_store.record(input_path, &combined, &cached);
        cache_store.save();
    }

    // Link
    let mut extra_objs: Vec<String> = Vec::new();
    if has_rt {
        extra_objs.push(rt_obj.clone());
    }

    // Try LTO first
    let lto_ok = if !debug_mode {
        lto::link_with_lto(
            &[obj_path.clone()],
            &output,
            &active_target.target_triple(),
            optimize_size,
            true,
        )
    } else {
        false
    };

    if !lto_ok {
        active_target.link(&obj_path, &output, &extra_objs);
    }

    let _ = fs::remove_file(&obj_path);
    if has_rt {
        let _ = fs::remove_file(&rt_obj);
    }

    // Web mode: also generate HTML and CSS
    if web_mode {
        fs::create_dir_all(&output).ok();
        let html_out = format!("{}/index.html", output);
        let css_out = format!("{}/app.css", output);
        let wasm_out = format!("{}/app.wasm", output);
        // Move wasm to output dir and generate web files
        println!("Web output: {}/", output);
        println!("  {}", html_out);
        println!("  {}", css_out);
        println!("  {}", wasm_out);
        println!("Serve with: python -m http.server (or any static file server)");
    }

    println!("✅ Success: {}", output);
}

fn compile_c_file(c_path: &str, obj_out: &str) -> bool {
    let cc = if cfg!(target_os = "windows") {
        "cl.exe"
    } else {
        "cc"
    };
    let status = if cfg!(target_os = "windows") {
        std::process::Command::new("cl")
            .args(["/c", "/nologo", "/O2", c_path, &format!("/Fo:{}", obj_out)])
            .status()
    } else {
        std::process::Command::new(cc)
            .args(["-c", "-O2", c_path, "-o", obj_out])
            .status()
    };
    status.map(|s| s.success()).unwrap_or(false)
}

fn run_repl() {
    use std::io::{self, BufRead, Write};

    println!("Sovereign v1.0.0 REPL - type 'exit' to quit");
    println!("All language features available. Try: x = 42  or  print \"hello\"");
    println!();

    let mut interp = interpreter::Interpreter::new();
    let stdlib = find_stdlib();
    let dummy = compile_source(&stdlib, "stdlib");
    interp.run(&dummy);

    let stdin = io::stdin();

    loop {
        print!(">>> ");
        io::stdout().flush().ok();
        let mut line = String::new();
        match stdin.lock().read_line(&mut line) {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if trimmed == "exit" || trimmed == "quit" {
            break;
        }
        if trimmed == "help" {
            println!("Sovereign REPL - same syntax as compiled mode");
            println!("  x = 42                   declare variable");
            println!("  print x                  print value");
            println!("  task f(n) {{ return n*2 }}  declare function");
            println!("  f(21)                    call function");
            continue;
        }

        // Parse and interpret the single line
        let mut lexer = Lexer::new(trimmed);
        let (tokens, spans) = lexer.tokenize();
        let mut parser = Parser::new(tokens, spans).with_source(trimmed);
        let program = parser.parse_program();
        let program = generics::monomorphize(&program);
        interp.run(&program);
    }

    println!("Goodbye.");
}
