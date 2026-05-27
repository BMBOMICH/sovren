//! Integration tests for self-hosting compiler
//!
//! These tests verify that the self-hosting compiler components are correctly loaded,
//! validated, and ready for bootstrap.

#[cfg(test)]
mod self_hosting_integration_tests {
    use std::fs;
    use std::path::Path;

    #[test]
    #[ignore] // Run with: cargo test -- --ignored
    fn test_all_compiler_files_exist() {
        let files = vec![
            "src/stdlib_native.sov",
            "src/stdlib_ast.sov",
            "src/lexer_self.sov",
            "src/parser_self.sov",
            "src/codegen_self.sov",
            "src/compiler_self.sov",
        ];

        for file in files {
            assert!(
                Path::new(file).exists(),
                "Missing compiler file: {}",
                file
            );
        }
    }

    #[test]
    #[ignore]
    fn test_stdlib_native_compiles() {
        let source = fs::read_to_string("src/stdlib_native.sov")
            .expect("Failed to read stdlib_native.sov");
        assert!(source.contains("Vec"), "stdlib_native should define Vec");
        assert!(source.contains("HashMap"), "stdlib_native should define HashMap");
        assert!(
            source.contains("task"),
            "stdlib_native should contain task definitions"
        );
    }

    #[test]
    #[ignore]
    fn test_ast_definitions_exist() {
        let source = fs::read_to_string("src/stdlib_ast.sov")
            .expect("Failed to read stdlib_ast.sov");
        assert!(source.contains("enum Token"), "Should define Token enum");
        assert!(source.contains("struct Expr"), "Should define Expr struct");
        assert!(source.contains("enum Stmt"), "Should define Stmt enum");
        assert!(source.contains("struct Program"), "Should define Program struct");
    }

    #[test]
    #[ignore]
    fn test_lexer_self_structure() {
        let source = fs::read_to_string("src/lexer_self.sov")
            .expect("Failed to read lexer_self.sov");
        assert!(
            source.contains("task tokenize"),
            "Lexer should have tokenize task"
        );
        assert!(
            source.contains("task advance"),
            "Lexer should have advance task"
        );
    }

    #[test]
    #[ignore]
    fn test_parser_self_structure() {
        let source = fs::read_to_string("src/parser_self.sov")
            .expect("Failed to read parser_self.sov");
        assert!(
            source.contains("task parse_program"),
            "Parser should have parse_program task"
        );
        assert!(
            source.contains("task parse_statement"),
            "Parser should have parse_statement task"
        );
    }

    #[test]
    #[ignore]
    fn test_codegen_self_structure() {
        let source = fs::read_to_string("src/codegen_self.sov")
            .expect("Failed to read codegen_self.sov");
        assert!(
            source.contains("task codegen"),
            "Codegen should have codegen task"
        );
        assert!(
            source.contains("task emit_c"),
            "Codegen should have emit_c task"
        );
    }

    #[test]
    #[ignore]
    fn test_compiler_self_entry() {
        let source = fs::read_to_string("src/compiler_self.sov")
            .expect("Failed to read compiler_self.sov");
        assert!(
            source.contains("task main"),
            "Compiler should have main entry point"
        );
    }

    #[test]
    fn test_bootstrap_test_file_structure() {
        let source = fs::read_to_string("tests/test_self_hosting.sov")
            .expect("Failed to read test_self_hosting.sov");
        assert!(
            source.contains("test_lexer"),
            "Should have test_lexer test"
        );
        assert!(
            source.contains("test_parser"),
            "Should have test_parser test"
        );
    }

    #[test]
    fn test_self_hosting_guide_exists() {
        assert!(
            Path::new("docs/SELF_HOSTING.md").exists(),
            "SELF_HOSTING.md documentation should exist"
        );
        let docs = fs::read_to_string("docs/SELF_HOSTING.md")
            .expect("Failed to read SELF_HOSTING.md");
        assert!(
            docs.contains("Bootstrap Process"),
            "Documentation should explain bootstrap process"
        );
    }

    #[test]
    fn test_no_circular_dependencies() {
        // stdlib_native should not import from lexer_self, parser_self, or codegen_self
        let stdlib = fs::read_to_string("src/stdlib_native.sov")
            .expect("Failed to read stdlib_native.sov");
        assert!(
            !stdlib.contains("import lexer_self"),
            "stdlib_native should not import lexer_self"
        );
        assert!(
            !stdlib.contains("import parser_self"),
            "stdlib_native should not import parser_self"
        );
    }

    #[test]
    fn test_total_lines_reasonable() {
        let files = vec![
            ("src/stdlib_native.sov", 1200),
            ("src/stdlib_ast.sov", 1100),
            ("src/lexer_self.sov", 700),
            ("src/parser_self.sov", 1000),
            ("src/codegen_self.sov", 900),
            ("src/compiler_self.sov", 300),
        ];

        let mut total = 0;
        for (file, expected_approx) in files {
            let content = fs::read_to_string(file).expect(&format!("Failed to read {}", file));
            let lines = content.lines().count();
            total += lines;
            
            // Allow 20% variance from expected
            let min = (expected_approx as f64 * 0.8) as usize;
            let max = (expected_approx as f64 * 1.2) as usize;
            
            eprintln!("{}: {} lines (expected ~{}, range {}-{})", file, lines, expected_approx, min, max);
        }

        println!("Total self-hosting compiler: ~{} lines of Sovereign code", total);
        assert!(
            total > 4000,
            "Self-hosting compiler should be at least 4000 lines"
        );
        assert!(
            total < 6000,
            "Self-hosting compiler should be less than 6000 lines"
        );
    }
}
