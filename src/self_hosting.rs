//! Self-hosting compiler integration
//!
//! This module provides support for compiling the self-hosted Sovereign compiler.
//! It loads, parses, and compiles the .sov compiler components using the existing
//! Rust compiler infrastructure.

use std::fs;
use std::path::Path;

pub struct SelfHostingCompiler {
    stdlib_native: String,
    stdlib_ast: String,
    lexer_self: String,
    parser_self: String,
    codegen_self: String,
    compiler_self: String,
}

impl SelfHostingCompiler {
    /// Load all self-hosting components from source directory
    pub fn load(src_dir: &str) -> Result<Self, String> {
        let stdlib_native = fs::read_to_string(Path::new(src_dir).join("stdlib_native.sov"))
            .map_err(|e| format!("Failed to load stdlib_native.sov: {}", e))?;
        
        let stdlib_ast = fs::read_to_string(Path::new(src_dir).join("stdlib_ast.sov"))
            .map_err(|e| format!("Failed to load stdlib_ast.sov: {}", e))?;
        
        let lexer_self = fs::read_to_string(Path::new(src_dir).join("lexer_self.sov"))
            .map_err(|e| format!("Failed to load lexer_self.sov: {}", e))?;
        
        let parser_self = fs::read_to_string(Path::new(src_dir).join("parser_self.sov"))
            .map_err(|e| format!("Failed to load parser_self.sov: {}", e))?;
        
        let codegen_self = fs::read_to_string(Path::new(src_dir).join("codegen_self.sov"))
            .map_err(|e| format!("Failed to load codegen_self.sov: {}", e))?;
        
        let compiler_self = fs::read_to_string(Path::new(src_dir).join("compiler_self.sov"))
            .map_err(|e| format!("Failed to load compiler_self.sov: {}", e))?;

        Ok(SelfHostingCompiler {
            stdlib_native,
            stdlib_ast,
            lexer_self,
            parser_self,
            codegen_self,
            compiler_self,
        })
    }

    /// Concatenate all compiler modules in correct order
    pub fn concatenate_sources(&self) -> String {
        vec![
            "// === Self-Hosted Sovereign Compiler ===\n\n",
            "// Phase 1: Standard Library Extensions\n",
            &self.stdlib_native,
            "\n\n// Phase 1b: AST Type Definitions\n",
            &self.stdlib_ast,
            "\n\n// Phase 2: Lexer\n",
            &self.lexer_self,
            "\n\n// Phase 3: Parser\n",
            &self.parser_self,
            "\n\n// Phase 4: C Code Generator\n",
            &self.codegen_self,
            "\n\n// Main Compiler Entry Point\n",
            &self.compiler_self,
        ]
        .concat()
    }

    /// Get compilation statistics
    pub fn statistics(&self) -> SelfHostingStats {
        SelfHostingStats {
            stdlib_lines: self.stdlib_native.lines().count(),
            ast_lines: self.stdlib_ast.lines().count(),
            lexer_lines: self.lexer_self.lines().count(),
            parser_lines: self.parser_self.lines().count(),
            codegen_lines: self.codegen_self.lines().count(),
            compiler_lines: self.compiler_self.lines().count(),
        }
    }

    /// Validate that all components compile without errors
    pub fn validate(&self, compiler: &crate::Compiler) -> Result<(), Vec<String>> {
        let combined = self.concatenate_sources();
        
        // Parse and compile each phase separately to catch errors
        let mut errors = Vec::new();

        // Parse and validate stdlib
        match compiler.compile_source(&self.stdlib_native, "stdlib_native") {
            Ok(_) => println!("✓ stdlib_native.sov compiles successfully"),
            Err(e) => errors.push(format!("stdlib_native.sov: {}", e)),
        }

        // Parse and validate AST definitions
        match compiler.compile_source(&self.stdlib_ast, "stdlib_ast") {
            Ok(_) => println!("✓ stdlib_ast.sov compiles successfully"),
            Err(e) => errors.push(format!("stdlib_ast.sov: {}", e)),
        }

        // Parse and validate lexer
        match compiler.compile_source(&self.lexer_self, "lexer_self") {
            Ok(_) => println!("✓ lexer_self.sov compiles successfully"),
            Err(e) => errors.push(format!("lexer_self.sov: {}", e)),
        }

        // Parse and validate parser
        match compiler.compile_source(&self.parser_self, "parser_self") {
            Ok(_) => println!("✓ parser_self.sov compiles successfully"),
            Err(e) => errors.push(format!("parser_self.sov: {}", e)),
        }

        // Parse and validate codegen
        match compiler.compile_source(&self.codegen_self, "codegen_self") {
            Ok(_) => println!("✓ codegen_self.sov compiles successfully"),
            Err(e) => errors.push(format!("codegen_self.sov: {}", e)),
        }

        // Parse and validate compiler
        match compiler.compile_source(&self.compiler_self, "compiler_self") {
            Ok(_) => println!("✓ compiler_self.sov compiles successfully"),
            Err(e) => errors.push(format!("compiler_self.sov: {}", e)),
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }

    /// Compile the self-hosted compiler to C code
    pub fn compile_to_c(&self, compiler: &crate::Compiler, output_path: &str) -> Result<(), String> {
        let combined = self.concatenate_sources();
        
        // Compile combined source to C
        let c_code = compiler.compile_to_c(&combined)?;
        
        // Write to output file
        fs::write(output_path, c_code)
            .map_err(|e| format!("Failed to write C output: {}", e))?;
        
        Ok(())
    }

    /// Compile the self-hosted compiler to LLVM IR
    pub fn compile_to_llvm(&self, compiler: &crate::Compiler, output_path: &str) -> Result<(), String> {
        let combined = self.concatenate_sources();
        
        // Compile combined source to LLVM IR
        let llvm_ir = compiler.compile_to_llvm(&combined)?;
        
        // Write to output file
        fs::write(output_path, llvm_ir)
            .map_err(|e| format!("Failed to write LLVM output: {}", e))?;
        
        Ok(())
    }

    /// Generate HTML documentation of the self-hosted compiler
    pub fn generate_docs(&self, output_dir: &str) -> Result<(), String> {
        fs::create_dir_all(output_dir)
            .map_err(|e| format!("Failed to create docs directory: {}", e))?;

        let stats = self.statistics();

        let html = format!(
            r#"<!DOCTYPE html>
<html>
<head>
    <title>Sovereign Self-Hosting Compiler Documentation</title>
    <style>
        body {{ font-family: monospace; margin: 20px; }}
        h1 {{ color: #333; }}
        .stats {{ background: #f5f5f5; padding: 10px; border-left: 4px solid #0066cc; }}
        .phase {{ margin: 20px 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #0066cc; color: white; }}
    </style>
</head>
<body>
    <h1>Sovereign Self-Hosting Compiler</h1>
    <p>Documentation for the self-hosted Sovereign compiler implementation.</p>
    
    <h2>Statistics</h2>
    <div class="stats">
        <table>
            <tr>
                <th>Component</th>
                <th>Lines of Code</th>
            </tr>
            <tr>
                <td>stdlib_native.sov</td>
                <td>{}</td>
            </tr>
            <tr>
                <td>stdlib_ast.sov</td>
                <td>{}</td>
            </tr>
            <tr>
                <td>lexer_self.sov</td>
                <td>{}</td>
            </tr>
            <tr>
                <td>parser_self.sov</td>
                <td>{}</td>
            </tr>
            <tr>
                <td>codegen_self.sov</td>
                <td>{}</td>
            </tr>
            <tr>
                <td>compiler_self.sov</td>
                <td>{}</td>
            </tr>
            <tr style="font-weight: bold;">
                <td>TOTAL</td>
                <td>{}</td>
            </tr>
        </table>
    </div>
    
    <h2>Components</h2>
    
    <div class="phase">
        <h3>Phase 1: Standard Library Extensions (stdlib_native.sov)</h3>
        <p>Extended standard library providing:</p>
        <ul>
            <li>Vec&lt;T&gt;: Generic dynamic arrays</li>
            <li>HashMap&lt;K,V&gt;: String-keyed hash tables</li>
            <li>String methods: split, join, find, replace, substring, etc.</li>
            <li>File I/O: open, read, write, close</li>
            <li>Binary utilities: byte manipulation and conversion</li>
        </ul>
    </div>
    
    <div class="phase">
        <h3>Phase 1b: AST Type Definitions (stdlib_ast.sov)</h3>
        <p>Data structures representing the Sovereign syntax tree:</p>
        <ul>
            <li>Token enum: All token types</li>
            <li>Expr enum: Expression variants</li>
            <li>Stmt enum: Statement variants</li>
            <li>Program struct: Root AST node</li>
        </ul>
    </div>
    
    <div class="phase">
        <h3>Phase 2: Lexer (lexer_self.sov)</h3>
        <p>Self-hosted tokenizer:</p>
        <ul>
            <li>Reads Sovereign source files</li>
            <li>Produces Vec&lt;Token&gt;</li>
            <li>Handles all keywords, operators, literals</li>
            <li>Tracks line/column information</li>
        </ul>
    </div>
    
    <div class="phase">
        <h3>Phase 3: Parser (parser_self.sov)</h3>
        <p>Recursive descent parser:</p>
        <ul>
            <li>Consumes Vec&lt;Token&gt;</li>
            <li>Produces Program AST</li>
            <li>Implements full Sovereign grammar</li>
            <li>Error recovery and diagnostics</li>
        </ul>
    </div>
    
    <div class="phase">
        <h3>Phase 4: C Code Generator (codegen_self.sov)</h3>
        <p>Emits C code from AST:</p>
        <ul>
            <li>Generates ANSI C output</li>
            <li>Preserves security semantics</li>
            <li>Compilable with gcc/clang</li>
            <li>Integrates with Sovereign runtime</li>
        </ul>
    </div>
</body>
</html>"#,
            stats.stdlib_lines,
            stats.ast_lines,
            stats.lexer_lines,
            stats.parser_lines,
            stats.codegen_lines,
            stats.compiler_lines,
            stats.total(),
        );

        fs::write(format!("{}/index.html", output_dir), html)
            .map_err(|e| format!("Failed to write HTML docs: {}", e))?;

        Ok(())
    }
}

pub struct SelfHostingStats {
    pub stdlib_lines: usize,
    pub ast_lines: usize,
    pub lexer_lines: usize,
    pub parser_lines: usize,
    pub codegen_lines: usize,
    pub compiler_lines: usize,
}

impl SelfHostingStats {
    pub fn total(&self) -> usize {
        self.stdlib_lines + self.ast_lines + self.lexer_lines + self.parser_lines + self.codegen_lines + self.compiler_lines
    }

    pub fn print_summary(&self) {
        println!("=== Self-Hosting Compiler Statistics ===");
        println!("stdlib_native.sov:  {:5} lines", self.stdlib_lines);
        println!("stdlib_ast.sov:     {:5} lines", self.ast_lines);
        println!("lexer_self.sov:     {:5} lines", self.lexer_lines);
        println!("parser_self.sov:    {:5} lines", self.parser_lines);
        println!("codegen_self.sov:   {:5} lines", self.codegen_lines);
        println!("compiler_self.sov:  {:5} lines", self.compiler_lines);
        println!("----------------------------------------");
        println!("TOTAL:              {:5} lines", self.total());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_self_hosting() {
        // This test loads all self-hosting components
        // In practice, run with: cargo test --lib self_hosting -- --ignored
        // (ignored by default to avoid file dependency in unit tests)
        let result = SelfHostingCompiler::load("src");
        assert!(result.is_ok(), "Should load all self-hosting components");
    }

    #[test]
    fn test_statistics_calculation() {
        let stats = SelfHostingStats {
            stdlib_lines: 100,
            ast_lines: 200,
            lexer_lines: 300,
            parser_lines: 400,
            codegen_lines: 500,
            compiler_lines: 100,
        };
        assert_eq!(stats.total(), 1600);
    }
}
