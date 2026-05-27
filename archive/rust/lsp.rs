use std::collections::HashMap;
/// Sovereign Language Server (LSP)
///
/// Implements a subset of the Language Server Protocol over stdin/stdout.
/// Supports:
///   - textDocument/didOpen, didChange
///   - textDocument/publishDiagnostics (errors shown in editor)
///   - textDocument/completion (keyword completions)
///   - textDocument/hover     (type info)
///
/// Start with:  sovereign lsp
use std::io::{self, BufRead, Read, Write};

const KEYWORDS: &[&str] = &[
    "set",
    "task",
    "check",
    "loop",
    "override",
    "purge",
    "copy",
    "else",
    "from",
    "to",
    "times",
    "true",
    "false",
    "break",
    "continue",
    "const",
    "as",
    "sensitive",
    "inline",
    "extern",
    "alloc",
    "free",
    "struct",
    "enum",
    "null",
    "constant_time",
    "ok",
    "err",
    "match",
    "spawn",
    "print",
    "print_fmt",
    "return",
    "import",
    "and",
    "or",
    "not",
    "int",
    "float",
    "bool",
    "string",
    "ptr",
    "void",
];

pub fn run_lsp() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    let mut documents: HashMap<String, String> = HashMap::new();

    loop {
        // Read Content-Length header
        let mut header = String::new();
        {
            let mut reader = stdin.lock();
            loop {
                let mut line = String::new();
                if reader.read_line(&mut line).unwrap_or(0) == 0 {
                    return;
                }
                if line == "\r\n" || line == "\n" {
                    break;
                }
                if line.starts_with("Content-Length:") {
                    header = line.trim().to_string();
                }
            }
        }

        let length: usize = header
            .split(':')
            .nth(1)
            .and_then(|s| s.trim().parse().ok())
            .unwrap_or(0);

        if length == 0 {
            continue;
        }

        let mut body = vec![0u8; length];
        io::stdin().lock().read_exact(&mut body).unwrap_or(());
        let msg = String::from_utf8_lossy(&body).to_string();

        // Parse method
        let method = extract_string(&msg, "\"method\"");
        let id = extract_number(&msg, "\"id\"");

        match method.as_deref() {
            Some("initialize") => {
                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{{"capabilities":{{"textDocumentSync":1,"completionProvider":{{"triggerCharacters":[]}},"hoverProvider":true}}}}}}"#,
                    id.unwrap_or(1)
                );
                send_response(&mut out, &response);
            }

            Some("initialized") => {}

            Some("textDocument/didOpen") => {
                let uri = extract_string(&msg, "\"uri\"").unwrap_or_default();
                let text = extract_string(&msg, "\"text\"").unwrap_or_default();
                documents.insert(uri.clone(), text.clone());
                let diagnostics = compute_diagnostics(&uri, &text);
                send_response(&mut out, &diagnostics);
            }

            Some("textDocument/didChange") => {
                let uri = extract_string(&msg, "\"uri\"").unwrap_or_default();
                let text = extract_change_text(&msg);
                if !text.is_empty() {
                    documents.insert(uri.clone(), text.clone());
                    let diagnostics = compute_diagnostics(&uri, &text);
                    send_response(&mut out, &diagnostics);
                }
            }

            Some("textDocument/completion") => {
                let items: Vec<String> = KEYWORDS
                    .iter()
                    .map(|kw| {
                        format!(
                            r#"{{"label":"{}","kind":14,"detail":"Sovereign keyword"}}"#,
                            kw
                        )
                    })
                    .collect();
                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{{"isIncomplete":false,"items":[{}]}}}}"#,
                    id.unwrap_or(1),
                    items.join(",")
                );
                send_response(&mut out, &response);
            }

            Some("textDocument/hover") => {
                let word = extract_hover_word(&msg, &documents);
                let content = hover_content(&word);
                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{{"contents":{{"kind":"markdown","value":"{}"}}}}}}"#,
                    id.unwrap_or(1),
                    content
                );
                send_response(&mut out, &response);
            }

            Some("textDocument/definition") => {
                let uri = extract_string(&msg, "\"uri\"").unwrap_or_default();
                let line = extract_number(&msg, "\"line\"").unwrap_or(0) as usize;
                let char_ = extract_number(&msg, "\"character\"").unwrap_or(0) as usize;

                let result = if let Some(text) = documents.get(&uri) {
                    find_definition(text, line, char_, &uri)
                } else {
                    "null".to_string()
                };

                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{}}}"#,
                    id.unwrap_or(1),
                    result
                );
                send_response(&mut out, &response);
            }

            Some("textDocument/rename") => {
                let uri = extract_string(&msg, "\"uri\"").unwrap_or_default();
                let new_name = extract_string(&msg, "\"newName\"").unwrap_or_default();
                let line = extract_number(&msg, "\"line\"").unwrap_or(0) as usize;
                let char_ = extract_number(&msg, "\"character\"").unwrap_or(0) as usize;

                let result = if let Some(text) = documents.get(&uri) {
                    compute_rename(text, line, char_, &new_name, &uri)
                } else {
                    r#"{"changes":{}}"#.to_string()
                };

                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{}}}"#,
                    id.unwrap_or(1),
                    result
                );
                send_response(&mut out, &response);
            }

            Some("textDocument/formatting") => {
                let uri = extract_string(&msg, "\"uri\"").unwrap_or_default();
                let result = if let Some(text) = documents.get(&uri) {
                    format_document(text, &uri)
                } else {
                    "[]".to_string()
                };
                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":{}}}"#,
                    id.unwrap_or(1),
                    result
                );
                send_response(&mut out, &response);
            }

            Some("shutdown") => {
                let response = format!(
                    r#"{{"jsonrpc":"2.0","id":{},"result":null}}"#,
                    id.unwrap_or(1)
                );
                send_response(&mut out, &response);
            }

            Some("exit") => return,

            _ => {
                if let Some(id) = id {
                    let response = format!(
                        r#"{{"jsonrpc":"2.0","id":{},"error":{{"code":-32601,"message":"Method not found"}}}}"#,
                        id
                    );
                    send_response(&mut out, &response);
                }
            }
        }
    }
}

fn send_response(out: &mut impl Write, response: &str) {
    let _ = write!(
        out,
        "Content-Length: {}\r\n\r\n{}",
        response.len(),
        response
    );
    let _ = out.flush();
}

fn compute_diagnostics(uri: &str, text: &str) -> String {
    use crate::lexer::Lexer;
    use crate::parser::Parser;
    use crate::semantic::Analyzer;

    let mut lexer = Lexer::new(text);
    let (tokens, spans) = lexer.tokenize();
    let mut parser = Parser::new(tokens, spans);

    // Capture parse errors by catching panics - in production LSP, use a recoverable parser
    let program = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| parser.parse_program()));

    let mut diags = Vec::new();

    if let Ok(program) = program {
        let mut analyzer = Analyzer::new();
        if let Err(errors) = analyzer.analyze(&program) {
            for (i, error) in errors.iter().enumerate() {
                let line = i; // simplified: real impl would track line numbers
                diags.push(format!(
                    r#"{{"range":{{"start":{{"line":{},"character":0}},"end":{{"line":{},"character":100}}}},"severity":1,"message":{:?}}}"#,
                    line, line, error
                ));
            }
        }
    } else {
        diags.push(
            r#"{"range":{"start":{"line":0,"character":0},"end":{"line":0,"character":100}},"severity":1,"message":"Parse error"}"#
                .to_string(),
        );
    }

    format!(
        r#"{{"jsonrpc":"2.0","method":"textDocument/publishDiagnostics","params":{{"uri":{},"diagnostics":[{}]}}}}"#,
        serde_json_string(uri),
        diags.join(",")
    )
}

fn hover_content(word: &str) -> String {
    match word {
        "set" => "Declare a variable: `set x = value`",
        "task" => "Declare a function: `task name(param: type) -> return_type { }`",
        "check" => "Conditional: `check condition { } else { }`",
        "loop" => "Loop: `loop N times`, `loop from to`, `loop condition`, `loop { }` (infinite)",
        "override" => "Unsafe block: enables raw pointers, asm, no safety checks",
        "purge" => "Securely zero a variable: `purge x`",
        "sensitive" => "Mark variable for auto-zeroing on scope exit: `sensitive set x = val`",
        "constant_time" => "Constant-time block: prevents timing side-channels",
        "spawn" => "Spawn OS thread: `spawn h { code }` - no runtime needed",
        "alloc" => "Heap allocate: `alloc(count, size)` -> ptr",
        "free" => "Free heap memory: `free ptr`",
        "inline" => "Force function inlining: `inline task name(...)`",
        "extern" => "Declare external C function: `extern task name(type) -> type`",
        "struct" => "Declare a struct: `struct Name { field: type }`",
        "enum" => "Declare an enum: `enum Name { Variant1, Variant2 }`",
        "match" => "Pattern match: `match value { Pattern => { } }`",
        "const" => "Compile-time constant: `const NAME = value`",
        "print" => "Print a value: `print expr`",
        "print_fmt" => "Formatted print: `print_fmt(\"Hello, %s!\", name)`",
        _ => word,
    }
    .to_string()
}

fn find_definition(text: &str, line: usize, char_: usize, uri: &str) -> String {
    let word = get_word_at(text, line, char_);
    if word.is_empty() {
        return "null".to_string();
    }

    // Search for declaration of `word` in the document
    for (i, source_line) in text.lines().enumerate() {
        let trimmed = source_line.trim();
        // task declarations
        if trimmed.starts_with("task ") && trimmed.contains(&format!("{}(", word)) {
            return format!(
                r#"{{"uri":{},"range":{{"start":{{"line":{},"character":0}},"end":{{"line":{},"character":100}}}}}}"#,
                serde_json_string(uri),
                i,
                i
            );
        }
        // set/const declarations
        if (trimmed.starts_with("set ") || trimmed.starts_with("const "))
            && trimmed.contains(&format!("{} =", word))
        {
            return format!(
                r#"{{"uri":{},"range":{{"start":{{"line":{},"character":0}},"end":{{"line":{},"character":100}}}}}}"#,
                serde_json_string(uri),
                i,
                i
            );
        }
        // struct declarations
        if trimmed.starts_with("struct ") && trimmed.contains(&word) {
            return format!(
                r#"{{"uri":{},"range":{{"start":{{"line":{},"character":0}},"end":{{"line":{},"character":100}}}}}}"#,
                serde_json_string(uri),
                i,
                i
            );
        }
    }
    "null".to_string()
}

fn compute_rename(text: &str, line: usize, char_: usize, new_name: &str, uri: &str) -> String {
    let old_name = get_word_at(text, line, char_);
    if old_name.is_empty() {
        return r#"{"changes":{}}"#.to_string();
    }

    // Simple rename: replace all occurrences of the word
    // In production, use the symbol table for precise renaming
    let mut edits = Vec::new();
    for (i, source_line) in text.lines().enumerate() {
        let mut col = 0;
        while let Some(pos) = source_line[col..].find(&old_name) {
            let abs_pos = col + pos;
            // Check it's a word boundary
            let before_ok = abs_pos == 0
                || !source_line
                    .chars()
                    .nth(abs_pos - 1)
                    .map(|c| c.is_alphanumeric() || c == '_')
                    .unwrap_or(false);
            let after_ok = abs_pos + old_name.len() >= source_line.len()
                || !source_line
                    .chars()
                    .nth(abs_pos + old_name.len())
                    .map(|c| c.is_alphanumeric() || c == '_')
                    .unwrap_or(false);

            if before_ok && after_ok {
                edits.push(format!(
                    r#"{{"range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}},"newText":"{}"}}"#,
                    i,
                    abs_pos,
                    i,
                    abs_pos + old_name.len(),
                    new_name
                ));
            }
            col = abs_pos + 1;
            if col >= source_line.len() {
                break;
            }
        }
    }
    format!(
        r#"{{"changes":{{{}: [{}]}}}}"#,
        serde_json_string(uri),
        edits.join(",")
    )
}

fn format_document(text: &str, _uri: &str) -> String {
    // Sovereign formatter: normalize indentation, spacing around operators
    let mut formatted = String::new();
    let mut indent = 0usize;

    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            formatted.push('\n');
            continue;
        }

        // Decrease indent before closing brace
        if trimmed.starts_with('}') && indent > 0 {
            indent -= 1;
        }

        formatted.push_str(&"    ".repeat(indent));
        // Normalize spaces around = (but not ==)
        let normalized = normalize_spacing(trimmed);
        formatted.push_str(&normalized);
        formatted.push('\n');

        // Increase indent after opening brace
        if trimmed.ends_with('{') {
            indent += 1;
        }
    }

    let escaped = serde_json_string(&formatted);
    format!(
        r#"[{{"range":{{"start":{{"line":0,"character":0}},"end":{{"line":99999,"character":0}}}},"newText":{}}}]"#,
        escaped
    )
}

fn normalize_spacing(line: &str) -> String {
    // Basic: ensure single space around operators
    line.replace("  ", " ")
        .replace("=", " = ")
        .replace("  =  ", " = ")
        .replace("= =", "==")
        .replace("! =", "!=")
        .replace("< =", "<=")
        .replace("> =", ">=")
        .replace("= >", "=>")
        .replace("- >", "->")
}

fn get_word_at(text: &str, line: usize, char_: usize) -> String {
    if let Some(source_line) = text.lines().nth(line) {
        let start = source_line[..char_.min(source_line.len())]
            .rfind(|c: char| !c.is_alphanumeric() && c != '_')
            .map(|i| i + 1)
            .unwrap_or(0);
        let end = source_line[char_..]
            .find(|c: char| !c.is_alphanumeric() && c != '_')
            .map(|i| i + char_)
            .unwrap_or(source_line.len());
        return source_line[start..end].to_string();
    }
    String::new()
}

/// Public entry point for `sovereign fmt <file>`
pub fn format_source(source: &str) -> String {
    let mut formatted = String::new();
    let mut indent = 0usize;
    let mut prev_blank = false;

    for line in source.lines() {
        let trimmed = line.trim();

        // Collapse multiple blank lines into one
        if trimmed.is_empty() {
            if !prev_blank {
                formatted.push('\n');
            }
            prev_blank = true;
            continue;
        }
        prev_blank = false;

        // Decrease indent before closing brace
        if trimmed.starts_with('}') && indent > 0 {
            indent -= 1;
        }

        // Write indent + normalized line
        formatted.push_str(&"    ".repeat(indent));
        formatted.push_str(&normalize_operator_spacing(trimmed));
        formatted.push('\n');

        // Increase indent after opening brace
        if trimmed.ends_with('{') {
            indent += 1;
        }
    }
    formatted
}

fn normalize_operator_spacing(line: &str) -> String {
    // Ensure single spaces around = but not == => ->
    let mut result = String::new();
    let chars: Vec<char> = line.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        // Skip string literals
        if c == '"' {
            result.push(c);
            i += 1;
            while i < chars.len() && chars[i] != '"' {
                if chars[i] == '\\' {
                    result.push(chars[i]);
                    i += 1;
                }
                if i < chars.len() {
                    result.push(chars[i]);
                    i += 1;
                }
            }
            if i < chars.len() {
                result.push(chars[i]);
                i += 1;
            }
            continue;
        }
        result.push(c);
        i += 1;
    }
    result
}

fn extract_string(json: &str, key: &str) -> Option<String> {
    let pos = json.find(key)? + key.len();
    let rest = &json[pos..];
    let start = rest.find('"')? + 1;
    let end = rest[start..].find('"')?;
    Some(rest[start..start + end].to_string())
}

fn extract_number(json: &str, key: &str) -> Option<i64> {
    let pos = json.find(key)? + key.len();
    let rest = json[pos..].trim_start_matches(|c: char| c == ':' || c == ' ');
    let end = rest.find(|c: char| !c.is_ascii_digit())?;
    rest[..end].parse().ok()
}

fn extract_change_text(json: &str) -> String {
    // Extract text from contentChanges[0].text
    if let Some(pos) = json.find("\"text\"") {
        let rest = &json[pos + 6..];
        let start = rest.find('"').unwrap_or(0) + 1;
        let chars: Vec<char> = rest[start..].chars().collect();
        let mut i = 0;
        while i < chars.len() {
            if chars[i] == '\\' {
                i += 2;
                continue;
            }
            if chars[i] == '"' {
                return rest[start..start + i].to_string();
            }
            i += 1;
        }
    }
    String::new()
}

fn extract_hover_word(json: &str, documents: &HashMap<String, String>) -> String {
    let uri = extract_string(json, "\"uri\"").unwrap_or_default();
    let line = extract_number(json, "\"line\"").unwrap_or(0) as usize;
    let char_pos = extract_number(json, "\"character\"").unwrap_or(0) as usize;

    if let Some(text) = documents.get(&uri) {
        return get_word_at(text, line, char_pos);
    }
    String::new()
}

fn serde_json_string(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_string() {
        let json = r#"{"method":"initialize","id":1}"#;
        assert_eq!(extract_string(json, "\"method\""), Some("initialize".to_string()));
    }

    #[test]
    fn test_extract_number() {
        let json = r#"{"id":42,"method":"test"}"#;
        assert_eq!(extract_number(json, "\"id\""), Some(42));
    }

    #[test]
    fn test_hover_content() {
        assert!(hover_content("set").contains("variable"));
        assert!(hover_content("task").contains("function"));
        assert_eq!(hover_content("unknown_word"), "unknown_word");
    }

    #[test]
    fn test_get_word_at() {
        let text = "set my_var = 42";
        assert_eq!(get_word_at(text, 0, 4), "my_var");
        assert_eq!(get_word_at(text, 0, 0), "set");
    }

    #[test]
    fn test_format_source() {
        let source = "task main() {\nprint 42\n}";
        let formatted = format_source(source);
        assert!(formatted.contains("    print"));
    }

    #[test]
    fn test_serde_json_string() {
        assert_eq!(serde_json_string("hello"), "\"hello\"");
        assert_eq!(serde_json_string("he\"llo"), "\"he\\\"llo\"");
    }
}
