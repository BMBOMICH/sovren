/// Built-in test framework for Sovereign.
///
/// Usage in .sov files:
///   test "my test" {
///       assert(1 + 1 == 2)
///       assert(square(4) == 16, "square should work")
///   }
///
/// Run with: sovereign test <file.sov>
use crate::ast::*;
use crate::codegen::Codegen;
use crate::generics;
use crate::lexer::Lexer;
use crate::parser::Parser;
use crate::semantic::Analyzer;
use inkwell::context::Context;
use std::fs;
use std::path::Path;

pub fn run_tests(source_path: &str) {
    let source = fs::read_to_string(source_path).unwrap_or_else(|_| {
        eprintln!("Error: cannot read '{}'", source_path);
        std::process::exit(1);
    });

    let mut lexer = Lexer::new(&source);
    let (tokens, spans) = lexer.tokenize();
    let mut parser = Parser::new(tokens, spans).with_source(&source);
    let program = parser.parse_program();
    let program = generics::monomorphize(&program);

    // Count tests
    let test_count = program
        .statements
        .iter()
        .filter(|s| matches!(s, Stmt::TestDecl { .. }))
        .count();

    if test_count == 0 {
        println!("No tests found in '{}'", source_path);
        return;
    }

    println!("Running {} test(s) from '{}'", test_count, source_path);

    // Build a modified program that runs each test and reports results
    let mut test_program = build_test_program(&program);
    let mut analyzer = Analyzer::new();
    if let Err(errors) = analyzer.analyze(&test_program) {
        for e in &errors {
            eprintln!("Error: {}", e);
        }
        std::process::exit(1);
    }

    let obj_path = Path::new(source_path)
        .with_extension("test.obj")
        .to_string_lossy()
        .to_string();
    let exe_path = Path::new(source_path)
        .with_extension("test.exe")
        .to_string_lossy()
        .to_string();

    let context = Context::create();
    let mut codegen = Codegen::new(&context, "sovereign_tests", false);
    codegen.compile(&test_program);
    codegen.write_executable(&exe_path, &obj_path);

    // Run the test binary
    let status = std::process::Command::new(&exe_path)
        .status()
        .expect("Failed to run tests");

    let _ = std::fs::remove_file(&exe_path);

    if !status.success() {
        eprintln!("Tests FAILED");
        std::process::exit(1);
    } else {
        println!("All tests PASSED");
    }
}

/// Transform TestDecl statements into callable tasks and a main that runs them.
fn build_test_program(program: &Program) -> Program {
    let mut stmts: Vec<Stmt> = Vec::new();
    let mut test_names: Vec<String> = Vec::new();

    // Keep all non-test statements (task decls, struct decls, etc.)
    for stmt in &program.statements {
        match stmt {
            Stmt::TestDecl { .. } => {}
            _ => stmts.push(stmt.clone()),
        }
    }

    // Convert each test to a task
    for stmt in &program.statements {
        if let Stmt::TestDecl { name, body } = stmt {
            let fn_name = format!("__test_{}", name.replace(' ', "_").replace('"', ""));
            test_names.push((name.clone(), fn_name.clone()));

            // Wrap body in a task that prints pass/fail
            let mut test_body = body.clone();
            // Prepend: print_fmt("Running: name\n")
            test_body.statements.insert(
                0,
                Stmt::PrintFmt {
                    format: format!("  running: {}\n", name),
                    args: Vec::new(),
                },
            );
            // Append: print("  PASS")
            test_body.statements.push(Stmt::PrintFmt {
                format: format!("  PASS: {}\n", name),
                args: Vec::new(),
            });

            stmts.push(Stmt::TaskDecl {
                name: fn_name,
                type_params: Vec::new(),
                params: Vec::new(),
                return_type: Type::Void,
                body: test_body,
                is_inline: false,
                is_async: false,
            });
        }
    }

    // Build main that calls all test tasks
    let mut main_stmts: Vec<Stmt> = Vec::new();
    main_stmts.push(Stmt::PrintFmt {
        format: format!("Sovereign Tests — {} test(s)\n", test_names.len()),
        args: Vec::new(),
    });

    for (_, fn_name) in &test_names {
        main_stmts.push(Stmt::ExprStmt(Expr::Call {
            func: Box::new(Expr::Identifier(fn_name.clone())),
            args: Vec::new(),
        }));
    }

    main_stmts.push(Stmt::PrintFmt {
        format: "All tests passed.\n".to_string(),
        args: Vec::new(),
    });

    // The main program is just these statements (not wrapped in a task — they go in main())
    for s in main_stmts {
        stmts.push(s);
    }

    Program { statements: stmts }
}

// Helper to clone test_names properly
impl Clone for (String, String) {} // already clone
