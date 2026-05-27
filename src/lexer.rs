use crate::token::Token;

pub struct Lexer {
    source: Vec<char>,
    pos: usize,
    line: usize,
    col: usize,
}

impl Lexer {
    pub fn new(source: &str) -> Self {
        Lexer {
            source: source.chars().collect(),
            pos: 0,
            line: 1,
            col: 1,
        }
    }

    pub fn tokenize(&mut self) -> (Vec<Token>, Vec<(usize, usize)>) {
        let mut tokens = Vec::new();
        let mut spans = Vec::new();

        while self.pos < self.source.len() {
            let sl = self.line;
            let sc = self.col;

            match self.current_char() {
                ' ' | '\t' | '\r' => self.advance(),
                '\n' => {
                    tokens.push(Token::Newline);
                    spans.push((sl, sc));
                    self.advance_newline();
                }
                '/' if self.peek() == Some('/') => self.skip_line_comment(),
                '/' if self.peek() == Some('*') => self.skip_block_comment(),
                '"' => {
                    let t = self.read_string();
                    spans.push((sl, sc));
                    tokens.push(t);
                }
                '0' if self.peek() == Some('x') || self.peek() == Some('X') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_hex());
                }
                '0' if self.peek() == Some('b') || self.peek() == Some('B') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_binary());
                }
                '0' if self.peek() == Some('o') || self.peek() == Some('O') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_octal());
                }
                c if c.is_ascii_digit() => {
                    spans.push((sl, sc));
                    tokens.push(self.read_number());
                }
                c if c.is_alphabetic() || c == '_' => {
                    spans.push((sl, sc));
                    tokens.push(self.read_identifier_or_keyword());
                }
                '+' if self.peek() == Some('=') => {
                    tokens.push(Token::PlusAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '+' => {
                    tokens.push(Token::Plus);
                    spans.push((sl, sc));
                    self.advance();
                }
                '-' if self.peek() == Some('>') => {
                    tokens.push(Token::Arrow);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '-' if self.peek() == Some('=') => {
                    tokens.push(Token::MinusAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '-' => {
                    tokens.push(Token::Minus);
                    spans.push((sl, sc));
                    self.advance();
                }
                '*' if self.peek() == Some('=') => {
                    tokens.push(Token::StarAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '*' => {
                    tokens.push(Token::Star);
                    spans.push((sl, sc));
                    self.advance();
                }
                '/' if self.peek() == Some('=') => {
                    tokens.push(Token::SlashAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '/' => {
                    tokens.push(Token::Slash);
                    spans.push((sl, sc));
                    self.advance();
                }
                '%' => {
                    tokens.push(Token::Percent);
                    spans.push((sl, sc));
                    self.advance();
                }
                '|' if self.peek() == Some('|') => {
                    tokens.push(Token::Pipe2);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '|' => {
                    tokens.push(Token::Pipe);
                    spans.push((sl, sc));
                    self.advance();
                }
                '^' => {
                    tokens.push(Token::Caret);
                    spans.push((sl, sc));
                    self.advance();
                }
                '~' => {
                    tokens.push(Token::Tilde);
                    spans.push((sl, sc));
                    self.advance();
                }
                '<' if self.peek() == Some('<') => {
                    tokens.push(Token::LessLess);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '>' if self.peek() == Some('>') => {
                    tokens.push(Token::GreaterGreater);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' if self.peek() == Some('=') => {
                    tokens.push(Token::EqualEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' if self.peek() == Some('>') => {
                    tokens.push(Token::FatArrow);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' => {
                    tokens.push(Token::Assign);
                    spans.push((sl, sc));
                    self.advance();
                }
                '!' if self.peek() == Some('=') => {
                    tokens.push(Token::NotEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '!' => {
                    tokens.push(Token::Bang);
                    spans.push((sl, sc));
                    self.advance();
                }
                '<' if self.peek() == Some('=') => {
                    tokens.push(Token::LessEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '<' => {
                    tokens.push(Token::Less);
                    spans.push((sl, sc));
                    self.advance();
                }
                '>' if self.peek() == Some('=') => {
                    tokens.push(Token::GreaterEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '>' => {
                    tokens.push(Token::Greater);
                    spans.push((sl, sc));
                    self.advance();
                }
                '&' => {
                    tokens.push(Token::Ampersand);
                    spans.push((sl, sc));
                    self.advance();
                }
                '(' => {
                    tokens.push(Token::LeftParen);
                    spans.push((sl, sc));
                    self.advance();
                }
                ')' => {
                    tokens.push(Token::RightParen);
                    spans.push((sl, sc));
                    self.advance();
                }
                '{' => {
                    tokens.push(Token::LeftBrace);
                    spans.push((sl, sc));
                    self.advance();
                }
                '}' => {
                    tokens.push(Token::RightBrace);
                    spans.push((sl, sc));
                    self.advance();
                }
                '[' => {
                    tokens.push(Token::LeftBracket);
                    spans.push((sl, sc));
                    self.advance();
                }
                ']' => {
                    tokens.push(Token::RightBracket);
                    spans.push((sl, sc));
                    self.advance();
                }
                ',' => {
                    tokens.push(Token::Comma);
                    spans.push((sl, sc));
                    self.advance();
                }
                '.' if self.peek() == Some('.') && self.peek2() == Some('=') => {
                    tokens.push(Token::DotDotEq);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                    self.advance();
                }
                '.' if self.peek() == Some('.') => {
                    tokens.push(Token::DotDot);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '.' => {
                    tokens.push(Token::Dot);
                    spans.push((sl, sc));
                    self.advance();
                }
                ':' if self.peek() == Some(':') => {
                    tokens.push(Token::DoubleColon);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                ':' => {
                    tokens.push(Token::Colon);
                    spans.push((sl, sc));
                    self.advance();
                }
                '?' => {
                    tokens.push(Token::Question);
                    spans.push((sl, sc));
                    self.advance();
                }
                c => {
                    eprintln!(
                        "Error at {}:{}: unexpected character '{}'",
                        self.line, self.col, c
                    );
                    std::process::exit(1);
                }
            }
        }
        tokens.push(Token::Eof);
        spans.push((self.line, self.col));
        (tokens, spans)
    }

    fn current_char(&self) -> char {
        self.source[self.pos]
    }
    fn advance(&mut self) {
        if self.pos < self.source.len() {
            self.col += 1;
            self.pos += 1;
        }
    }
    fn advance_newline(&mut self) {
        self.pos += 1;
        self.line += 1;
        self.col = 1;
    }
    fn peek(&self) -> Option<char> {
        self.source.get(self.pos + 1).copied()
    }
    fn peek2(&self) -> Option<char> {
        self.source.get(self.pos + 2).copied()
    }

    fn skip_line_comment(&mut self) {
        while self.pos < self.source.len() && self.current_char() != '\n' {
            self.advance();
        }
    }

    fn skip_block_comment(&mut self) {
        self.advance();
        self.advance();
        while self.pos + 1 < self.source.len() {
            if self.current_char() == '*' && self.peek() == Some('/') {
                self.advance();
                self.advance();
                return;
            }
            if self.current_char() == '\n' {
                self.line += 1;
                self.col = 0;
            }
            self.advance();
        }
        eprintln!("Error: unterminated block comment");
        std::process::exit(1);
    }

    fn read_string(&mut self) -> Token {
        let sl = self.line;
        let sc = self.col;
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len() && self.current_char() != '"' {
            if self.current_char() == '\\' {
                self.advance();
                if self.pos >= self.source.len() {
                    break;
                }
                match self.current_char() {
                    'n' => s.push('\n'),
                    't' => s.push('\t'),
                    'r' => s.push('\r'),
                    '0' => s.push('\0'),
                    '"' => s.push('"'),
                    '\\' => s.push('\\'),
                    '{' => s.push('{'),
                    '}' => s.push('}'),
                    'u' => {
                        // Unicode: \u{1F600}
                        if self.peek() == Some('{') {
                            self.advance();
                            self.advance();
                            let mut hex = String::new();
                            while self.pos < self.source.len() && self.current_char() != '}' {
                                hex.push(self.current_char());
                                self.advance();
                            }
                            if let Ok(code) = u32::from_str_radix(&hex, 16) {
                                if let Some(c) = char::from_u32(code) {
                                    s.push(c);
                                }
                            }
                        }
                    }
                    c => {
                        eprintln!(
                            "Error at {}:{}: unknown escape '\\{}'",
                            self.line, self.col, c
                        );
                        std::process::exit(1);
                    }
                }
            } else {
                s.push(self.current_char());
            }
            self.advance();
        }
        if self.pos >= self.source.len() {
            eprintln!("Error: unterminated string at {}:{}", sl, sc);
            std::process::exit(1);
        }
        self.advance();
        Token::StringLiteral(s)
    }

    fn read_number(&mut self) -> Token {
        let mut s = String::new();
        let mut is_float = false;
        while self.pos < self.source.len()
            && (self.current_char().is_ascii_digit()
                || self.current_char() == '.'
                || self.current_char() == '_')
        {
            if self.current_char() == '_' {
                self.advance();
                continue;
            } // numeric separator: 1_000_000
            if self.current_char() == '.' {
                if self.peek() == Some('.') {
                    break;
                } // range operator
                if is_float {
                    eprintln!("Error: extra '.' in number");
                    std::process::exit(1);
                }
                is_float = true;
            }
            s.push(self.current_char());
            self.advance();
        }
        if is_float {
            Token::Float(s.parse().unwrap())
        } else {
            Token::Integer(s.parse().unwrap())
        }
    }

    fn read_binary(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut val: i64 = 0;
        while self.pos < self.source.len() {
            match self.current_char() {
                '0' => {
                    val = val * 2;
                    self.advance();
                }
                '1' => {
                    val = val * 2 + 1;
                    self.advance();
                }
                '_' => {
                    self.advance();
                } // separator
                _ => break,
            }
        }
        Token::Integer(val)
    }

    fn read_hex(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len() {
            match self.current_char() {
                '_' => {
                    self.advance();
                }
                c if c.is_ascii_hexdigit() => {
                    s.push(c);
                    self.advance();
                }
                _ => break,
            }
        }
        Token::Integer(i64::from_str_radix(&s, 16).unwrap_or(0))
    }

    fn read_octal(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len()
            && self.current_char() >= '0'
            && self.current_char() <= '7'
        {
            s.push(self.current_char());
            self.advance();
        }
        Token::Integer(i64::from_str_radix(&s, 8).unwrap_or(0))
    }

    fn read_identifier_or_keyword(&mut self) -> Token {
        let mut s = String::new();
        while self.pos < self.source.len()
            && (self.current_char().is_alphanumeric() || self.current_char() == '_')
        {
            s.push(self.current_char());
            self.advance();
        }
        match s.as_str() {
            "set" => Token::Set,
            "task" => Token::Task,
            "check" => Token::Check,
            "loop" => Token::Loop,
            "override" => Token::Override,
            "purge" => Token::Purge,
            "copy" => Token::Copy,
            "print" => Token::Print,
            "print_fmt" => Token::PrintFmt,
            "return" => Token::Return,
            "asm" => Token::Asm,
            "import" => Token::Import,
            "else" => Token::Else,
            "from" => Token::From,
            "to" => Token::To,
            "times" => Token::Times,
            "in" => Token::In,
            "true" => Token::True,
            "false" => Token::False,
            "and" => Token::And,
            "or" => Token::Or,
            "not" => Token::Not,
            "break" => Token::Break,
            "continue" => Token::Continue,
            "const" => Token::Const,
            "as" => Token::As,
            "sensitive" => Token::Sensitive,
            "inline" => Token::Inline,
            "extern" => Token::Extern,
            "alloc" => Token::Alloc,
            "free" => Token::Free,
            "struct" => Token::Struct,
            "enum" => Token::Enum,
            "null" => Token::Null,
            "constant_time" => Token::ConstantTime,
            "ok" => Token::Ok,
            "err" => Token::Err,
            "match" => Token::Match,
            "spawn" => Token::Spawn,
            "async" => Token::Async,
            "await" => Token::Await,
            "chan" => Token::Chan,
            "where" => Token::Where,
            "test" => Token::Test,
            "assert" => Token::Assert,
            "static_assert" => Token::StaticAssert,
            "defer" => Token::Defer,
            "type" => Token::Type,
            "comptime" => Token::Comptime,
            "namespace" => Token::Namespace,
            "use" => Token::Use,
            "int8" => Token::Int8,
            "int16" => Token::Int16,
            "int64" => Token::Int64,
            "uint8" => Token::Uint8,
            "uint16" => Token::Uint16,
            "make_chan" => Token::MakeChan,
            "uint32" => Token::Uint32,
            "uint64" => Token::Uint64,
            _ => Token::Identifier(s),
        }
    }

    /// Recognizes keyword aliases for familiar syntax from other languages.
    /// This allows users to use `fn`, `let`, `if`, `for`, `while`, `unsafe`, `None`, `nil`, `switch`
    /// as aliases for Sovereign's native keywords.
    fn keyword_or_identifier_with_aliases(&mut self, s: &str) -> Token {
        match s {
            // Sovereign native keywords
            "set" => Token::Set,
            "task" => Token::Task,
            "check" => Token::Check,
            "loop" => Token::Loop,
            "override" => Token::Override,
            "purge" => Token::Purge,
            "copy" => Token::Copy,
            "print" => Token::Print,
            "print_fmt" => Token::PrintFmt,
            "return" => Token::Return,
            "asm" => Token::Asm,
            "import" => Token::Import,
            "else" => Token::Else,
            "from" => Token::From,
            "to" => Token::To,
            "times" => Token::Times,
            "in" => Token::In,
            "true" => Token::True,
            "false" => Token::False,
            "and" => Token::And,
            "or" => Token::Or,
            "not" => Token::Not,
            "break" => Token::Break,
            "continue" => Token::Continue,
            "const" => Token::Const,
            "as" => Token::As,
            "sensitive" => Token::Sensitive,
            "inline" => Token::Inline,
            "extern" => Token::Extern,
            "alloc" => Token::Alloc,
            "free" => Token::Free,
            "struct" => Token::Struct,
            "enum" => Token::Enum,
            "null" => Token::Null,
            "constant_time" => Token::ConstantTime,
            "ok" => Token::Ok,
            "err" => Token::Err,
            "match" => Token::Match,
            "spawn" => Token::Spawn,
            "async" => Token::Async,
            "await" => Token::Await,
            "chan" => Token::Chan,
            "where" => Token::Where,
            "test" => Token::Test,
            "assert" => Token::Assert,
            "static_assert" => Token::StaticAssert,
            "defer" => Token::Defer,
            "type" => Token::Type,
            "comptime" => Token::Comptime,
            "namespace" => Token::Namespace,
            "use" => Token::Use,
            "make_chan" => Token::MakeChan,
            // Type keywords
            "int8" => Token::Int8,
            "int16" => Token::Int16,
            "int64" => Token::Int64,
            "uint8" => Token::Uint8,
            "uint16" => Token::Uint16,
            "uint32" => Token::Uint32,
            "uint64" => Token::Uint64,
            // Aliases for familiar syntax from other languages
            "fn" => Token::Fn,          // Rust-style function
            "def" => Token::Task,       // Python-style function
            "func" => Token::Task,      // Go-style function
            "let" => Token::Set,        // Rust-style variable
            "var" => Token::Set,        // Go/JS-style variable
            "if" => Token::Check,       // Universal conditional
            "for" => Token::Loop,       // Universal loop
            "while" => Token::Loop,     // C-style loop
            "unsafe" => Token::Override, // Rust-style unsafe block
            "None" => Token::Null,      // Python-style null
            "nil" => Token::Null,       // Go-style null
            "switch" => Token::Match,   // C/Go-style match
            _ => Token::Identifier(s.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_tokens() {
        let mut lexer = Lexer::new("set x = 42");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Set));
        assert!(matches!(&tokens[1], Token::Identifier(s) if s == "x"));
        assert!(matches!(tokens[2], Token::Assign));
        assert!(matches!(tokens[3], Token::Integer(42)));
    }

    #[test]
    fn test_string_literal() {
        let mut lexer = Lexer::new("\"hello world\"");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(&tokens[0], Token::StringLiteral(s) if s == "hello world"));
    }

    #[test]
    fn test_operators() {
        let mut lexer = Lexer::new("+ - * / == != <= >= -> =>");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Plus));
        assert!(matches!(tokens[1], Token::Minus));
        assert!(matches!(tokens[2], Token::Star));
        assert!(matches!(tokens[3], Token::Slash));
        assert!(matches!(tokens[4], Token::EqualEqual));
        assert!(matches!(tokens[5], Token::NotEqual));
        assert!(matches!(tokens[6], Token::LessEqual));
        assert!(matches!(tokens[7], Token::GreaterEqual));
        assert!(matches!(tokens[8], Token::Arrow));
        assert!(matches!(tokens[9], Token::FatArrow));
    }

    #[test]
    fn test_hex_binary_octal() {
        let mut lexer = Lexer::new("0xFF 0b1010 0o17");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Integer(255)));
        assert!(matches!(tokens[1], Token::Integer(10)));
        assert!(matches!(tokens[2], Token::Integer(15)));
    }

    #[test]
    fn test_float() {
        let mut lexer = Lexer::new("3.14159");
        let (tokens, _) = lexer.tokenize();
        if let Token::Float(f) = tokens[0] {
            assert!((f - 3.14159).abs() < 0.0001);
        } else {
            panic!("Expected float token");
        }
    }

    #[test]
    fn test_keywords_vs_identifiers() {
        let mut lexer = Lexer::new("task my_task set my_var");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Task));
        assert!(matches!(&tokens[1], Token::Identifier(s) if s == "my_task"));
        assert!(matches!(tokens[2], Token::Set));
        assert!(matches!(&tokens[3], Token::Identifier(s) if s == "my_var"));
    }

    #[test]
    fn test_aliases() {
        let mut lexer = Lexer::new("fn let if for while unsafe None nil switch");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Fn));
        assert!(matches!(tokens[1], Token::Set));
        assert!(matches!(tokens[2], Token::Check));
        assert!(matches!(tokens[3], Token::Loop));
        assert!(matches!(tokens[4], Token::Loop));
        assert!(matches!(tokens[5], Token::Override));
        assert!(matches!(tokens[6], Token::Null));
        assert!(matches!(tokens[7], Token::Null));
        assert!(matches!(tokens[8], Token::Match));
    }

    #[test]
    fn test_numeric_separators() {
        let mut lexer = Lexer::new("1_000_000");
        let (tokens, _) = lexer.tokenize();
        assert!(matches!(tokens[0], Token::Integer(1_000_000)));
    }
} => self.skip_block_comment(),
                '"' => {
                    let t = self.read_string();
                    spans.push((sl, sc));
                    tokens.push(t);
                }
                '0' if self.peek() == Some('x') || self.peek() == Some('X') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_hex());
                }
                '0' if self.peek() == Some('b') || self.peek() == Some('B') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_binary());
                }
                '0' if self.peek() == Some('o') || self.peek() == Some('O') => {
                    spans.push((sl, sc));
                    tokens.push(self.read_octal());
                }
                c if c.is_ascii_digit() => {
                    spans.push((sl, sc));
                    tokens.push(self.read_number());
                }
                c if c.is_alphabetic() || c == '_' => {
                    spans.push((sl, sc));
                    tokens.push(self.read_identifier_or_keyword());
                }
                '+' if self.peek() == Some('=') => {
                    tokens.push(Token::PlusAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '+' => {
                    tokens.push(Token::Plus);
                    spans.push((sl, sc));
                    self.advance();
                }
                '-' if self.peek() == Some('>') => {
                    tokens.push(Token::Arrow);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '-' if self.peek() == Some('=') => {
                    tokens.push(Token::MinusAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '-' => {
                    tokens.push(Token::Minus);
                    spans.push((sl, sc));
                    self.advance();
                }
                '*' if self.peek() == Some('=') => {
                    tokens.push(Token::StarAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '*' => {
                    tokens.push(Token::Star);
                    spans.push((sl, sc));
                    self.advance();
                }
                '/' if self.peek() == Some('=') => {
                    tokens.push(Token::SlashAssign);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '/' => {
                    tokens.push(Token::Slash);
                    spans.push((sl, sc));
                    self.advance();
                }
                '%' => {
                    tokens.push(Token::Percent);
                    spans.push((sl, sc));
                    self.advance();
                }
                '|' if self.peek() == Some('|') => {
                    tokens.push(Token::Pipe2);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '|' => {
                    tokens.push(Token::Pipe);
                    spans.push((sl, sc));
                    self.advance();
                }
                '^' => {
                    tokens.push(Token::Caret);
                    spans.push((sl, sc));
                    self.advance();
                }
                '~' => {
                    tokens.push(Token::Tilde);
                    spans.push((sl, sc));
                    self.advance();
                }
                '<' if self.peek() == Some('<') => {
                    tokens.push(Token::LessLess);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '>' if self.peek() == Some('>') => {
                    tokens.push(Token::GreaterGreater);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' if self.peek() == Some('=') => {
                    tokens.push(Token::EqualEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' if self.peek() == Some('>') => {
                    tokens.push(Token::FatArrow);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '=' => {
                    tokens.push(Token::Assign);
                    spans.push((sl, sc));
                    self.advance();
                }
                '!' if self.peek() == Some('=') => {
                    tokens.push(Token::NotEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '!' => {
                    tokens.push(Token::Bang);
                    spans.push((sl, sc));
                    self.advance();
                }
                '<' if self.peek() == Some('=') => {
                    tokens.push(Token::LessEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '<' => {
                    tokens.push(Token::Less);
                    spans.push((sl, sc));
                    self.advance();
                }
                '>' if self.peek() == Some('=') => {
                    tokens.push(Token::GreaterEqual);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '>' => {
                    tokens.push(Token::Greater);
                    spans.push((sl, sc));
                    self.advance();
                }
                '&' => {
                    tokens.push(Token::Ampersand);
                    spans.push((sl, sc));
                    self.advance();
                }
                '(' => {
                    tokens.push(Token::LeftParen);
                    spans.push((sl, sc));
                    self.advance();
                }
                ')' => {
                    tokens.push(Token::RightParen);
                    spans.push((sl, sc));
                    self.advance();
                }
                '{' => {
                    tokens.push(Token::LeftBrace);
                    spans.push((sl, sc));
                    self.advance();
                }
                '}' => {
                    tokens.push(Token::RightBrace);
                    spans.push((sl, sc));
                    self.advance();
                }
                '[' => {
                    tokens.push(Token::LeftBracket);
                    spans.push((sl, sc));
                    self.advance();
                }
                ']' => {
                    tokens.push(Token::RightBracket);
                    spans.push((sl, sc));
                    self.advance();
                }
                ',' => {
                    tokens.push(Token::Comma);
                    spans.push((sl, sc));
                    self.advance();
                }
                '.' if self.peek() == Some('.') && self.peek2() == Some('=') => {
                    tokens.push(Token::DotDotEq);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                    self.advance();
                }
                '.' if self.peek() == Some('.') => {
                    tokens.push(Token::DotDot);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                '.' => {
                    tokens.push(Token::Dot);
                    spans.push((sl, sc));
                    self.advance();
                }
                ':' if self.peek() == Some(':') => {
                    tokens.push(Token::DoubleColon);
                    spans.push((sl, sc));
                    self.advance();
                    self.advance();
                }
                ':' => {
                    tokens.push(Token::Colon);
                    spans.push((sl, sc));
                    self.advance();
                }
                '?' => {
                    tokens.push(Token::Question);
                    spans.push((sl, sc));
                    self.advance();
                }
                c => {
                    eprintln!(
                        "Error at {}:{}: unexpected character '{}'",
                        self.line, self.col, c
                    );
                    std::process::exit(1);
                }
            }
        }
        tokens.push(Token::Eof);
        spans.push((self.line, self.col));
        (tokens, spans)
    }

    fn current_char(&self) -> char {
        self.source[self.pos]
    }
    fn advance(&mut self) {
        if self.pos < self.source.len() {
            self.col += 1;
            self.pos += 1;
        }
    }
    fn advance_newline(&mut self) {
        self.pos += 1;
        self.line += 1;
        self.col = 1;
    }
    fn peek(&self) -> Option<char> {
        self.source.get(self.pos + 1).copied()
    }
    fn peek2(&self) -> Option<char> {
        self.source.get(self.pos + 2).copied()
    }

    fn skip_line_comment(&mut self) {
        while self.pos < self.source.len() && self.current_char() != '\n' {
            self.advance();
        }
    }

    fn skip_block_comment(&mut self) {
        self.advance();
        self.advance();
        while self.pos + 1 < self.source.len() {
            if self.current_char() == '*' && self.peek() == Some('/') {
                self.advance();
                self.advance();
                return;
            }
            if self.current_char() == '\n' {
                self.line += 1;
                self.col = 0;
            }
            self.advance();
        }
        eprintln!("Error: unterminated block comment");
        std::process::exit(1);
    }

    fn read_string(&mut self) -> Token {
        let sl = self.line;
        let sc = self.col;
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len() && self.current_char() != '"' {
            if self.current_char() == '\\' {
                self.advance();
                if self.pos >= self.source.len() {
                    break;
                }
                match self.current_char() {
                    'n' => s.push('\n'),
                    't' => s.push('\t'),
                    'r' => s.push('\r'),
                    '0' => s.push('\0'),
                    '"' => s.push('"'),
                    '\\' => s.push('\\'),
                    '{' => s.push('{'),
                    '}' => s.push('}'),
                    'u' => {
                        if self.peek() == Some('{') {
                            self.advance();
                            self.advance();
                            let mut hex = String::new();
                            while self.pos < self.source.len() && self.current_char() != '}' {
                                hex.push(self.current_char());
                                self.advance();
                            }
                            if let Ok(code) = u32::from_str_radix(&hex, 16) {
                                if let Some(c) = char::from_u32(code) {
                                    s.push(c);
                                }
                            }
                        }
                    }
                    c => {
                        eprintln!(
                            "Error at {}:{}: unknown escape '\\{}'",
                            self.line, self.col, c
                        );
                        std::process::exit(1);
                    }
                }
            } else {
                s.push(self.current_char());
            }
            self.advance();
        }
        if self.pos >= self.source.len() {
            eprintln!("Error: unterminated string at {}:{}", sl, sc);
            std::process::exit(1);
        }
        self.advance();
        Token::StringLiteral(s)
    }

    fn read_number(&mut self) -> Token {
        let mut s = String::new();
        let mut is_float = false;
        while self.pos < self.source.len()
            && (self.current_char().is_ascii_digit()
                || self.current_char() == '.'
                || self.current_char() == '_')
        {
            if self.current_char() == '_' {
                self.advance();
                continue;
            }
            if self.current_char() == '.' {
                if self.peek() == Some('.') {
                    break;
                }
                if is_float {
                    eprintln!("Error: extra '.' in number");
                    std::process::exit(1);
                }
                is_float = true;
            }
            s.push(self.current_char());
            self.advance();
        }
        if is_float {
            Token::Float(s.parse().unwrap())
        } else {
            Token::Integer(s.parse().unwrap())
        }
    }

    fn read_binary(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut val: i64 = 0;
        while self.pos < self.source.len() {
            match self.current_char() {
                '0' => {
                    val *= 2;
                    self.advance();
                }
                '1' => {
                    val = val * 2 + 1;
                    self.advance();
                }
                '_' => {
                    self.advance();
                }
                _ => break,
            }
        }
        Token::Integer(val)
    }

    fn read_hex(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len() {
            match self.current_char() {
                '_' => {
                    self.advance();
                }
                c if c.is_ascii_hexdigit() => {
                    s.push(c);
                    self.advance();
                }
                _ => break,
            }
        }
        Token::Integer(i64::from_str_radix(&s, 16).unwrap_or(0))
    }

    fn read_octal(&mut self) -> Token {
        self.advance();
        self.advance();
        let mut s = String::new();
        while self.pos < self.source.len()
            && self.current_char() >= '0'
            && self.current_char() <= '7'
        {
            s.push(self.current_char());
            self.advance();
        }
        Token::Integer(i64::from_str_radix(&s, 8).unwrap_or(0))
    }

    fn read_identifier_or_keyword(&mut self) -> Token {
        let mut s = String::new();
        while self.pos < self.source.len()
            && (self.current_char().is_alphanumeric() || self.current_char() == '_')
        {
            s.push(self.current_char());
            self.advance();
        }
        match s.as_str() {
            "set" => Token::Set,
            "task" => Token::Task,
            "fn" => Token::Fn,     // alias for task
            "def" => Token::Task,  // Python-familiar alias
            "func" => Token::Task, // Go-familiar alias
            "let" => Token::Set,   // Rust-familiar alias
            "var" => Token::Set,   // Go-familiar alias
            "check" => Token::Check,
            "if" => Token::Check, // Universal alias
            "else" => Token::Else,
            "loop" => Token::Loop,
            "for" => Token::Loop,   // Universal alias
            "while" => Token::Loop, // Universal alias
            "override" => Token::Override,
            "unsafe" => Token::Override, // Rust-familiar alias
            "purge" => Token::Purge,
            "copy" => Token::Copy,
            "print" => Token::Print,
            "return" => Token::Return,
            "asm" => Token::Asm,
            "import" => Token::Import,
            "from" => Token::From,
            "to" => Token::To,
            "in" => Token::In,
            "times" => Token::Times,
            "true" => Token::True,
            "false" => Token::False,
            "and" => Token::And,
            "or" => Token::Or,
            "not" => Token::Not,
            "break" => Token::Break,
            "continue" => Token::Continue,
            "const" => Token::Const,
            "as" => Token::As,
            "sensitive" => Token::Sensitive,
            "inline" => Token::Inline,
            "extern" => Token::Extern,
            "alloc" => Token::Alloc,
            "free" => Token::Free,
            "struct" => Token::Struct,
            "enum" => Token::Enum,
            "null" => Token::Null,
            "None" => Token::Null, // Python-familiar alias
            "nil" => Token::Null,  // Go-familiar alias
            "constant_time" => Token::ConstantTime,
            "ok" => Token::Ok,
            "err" => Token::Err,
            "match" => Token::Match,
            "switch" => Token::Match, // C/Go-familiar alias
            "spawn" => Token::Spawn,
            "async" => Token::Async,
            "await" => Token::Await,
            "chan" => Token::Chan,
            "where" => Token::Where,
            "test" => Token::Test,
            "assert" => Token::Assert,
            "static_assert" => Token::StaticAssert,
            "defer" => Token::Defer,
            "type" => Token::Type,
            "comptime" => Token::Comptime,
            "namespace" => Token::Namespace,
            "use" => Token::Use,
            "int8" => Token::Int8,
            "int16" => Token::Int16,
            "int64" => Token::Int64,
            "uint8" => Token::Uint8,
            "uint16" => Token::Uint16,
            "uint32" => Token::Uint32,
            "uint64" => Token::Uint64,
            _ => Token::Identifier(s),
        }
    }

    fn run_repl() {
        use interpreter::Interpreter;
        use std::io::{self, BufRead, Write};

        println!("Sovereign v1.0.0 REPL");
        println!("Type Sovereign code. Press Ctrl+C to exit.");
        println!();

        let mut interp = Interpreter::new();
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

            // Parse and interpret the single line
            let mut lexer = Lexer::new(trimmed);
            let (tokens, spans) = lexer.tokenize();
            let mut parser = Parser::new(tokens, spans).with_source(trimmed);
            let program = parser.parse_program();
            let program = generics::monomorphize(&program);

            interp.run(&program);
        }
    }
}
