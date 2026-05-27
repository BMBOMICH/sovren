use crate::ast::*;
use crate::token::Token;

pub struct Parser {
    tokens: Vec<Token>,
    spans: Vec<(usize, usize)>,
    pos: usize,
    source_lines: Vec<String>,
    errors: Vec<String>, // error recovery
}

impl Parser {
    pub fn new(tokens: Vec<Token>, spans: Vec<(usize, usize)>) -> Self {
        Parser {
            tokens,
            spans,
            pos: 0,
            source_lines: Vec::new(),
            errors: Vec::new(),
        }
    }

    pub fn with_source(mut self, source: &str) -> Self {
        self.source_lines = source.lines().map(|l| l.to_string()).collect();
        self
    }

    pub fn take_errors(&mut self) -> Vec<String> {
        std::mem::take(&mut self.errors)
    }

    fn error(&self, msg: &str) -> ! {
        let (l, c) = self.spans.get(self.pos).copied().unwrap_or((0, 0));
        eprintln!("[{}:{}] Error: {}", l, c, msg);
        if l > 0 && l <= self.source_lines.len() {
            let line = &self.source_lines[l - 1];
            eprintln!("  {}", line);
            eprintln!("  {}^", " ".repeat(c.saturating_sub(1)));
        }
        std::process::exit(1);
    }

    fn peek(&self) -> &Token {
        &self.tokens[self.pos]
    }

    fn advance(&mut self) -> Token {
        let t = self.tokens[self.pos].clone();
        self.pos += 1;
        t
    }

    fn is_at_end(&self) -> bool {
        matches!(self.peek(), Token::Eof)
    }

    fn skip_newlines(&mut self) {
        while matches!(self.peek(), Token::Newline) {
            self.advance();
        }
    }

    fn expect(&mut self, expected: Token) {
        let tok = self.advance();
        if tok != expected {
            self.error(&format!("expected {:?}, got {:?}", expected, tok));
        }
    }

    fn consume_identifier(&mut self) -> String {
        match self.advance() {
            Token::Identifier(n) => n,
            tok => self.error(&format!("expected identifier, got {:?}", tok)),
        }
    }

    fn peek_is_identifier(&self) -> bool {
        matches!(self.peek(), Token::Identifier(_))
    }
    fn peek_next(&self) -> Option<&Token> {
        self.tokens.get(self.pos + 1)
    }

    fn peek_next_is_assign(&self) -> bool {
        matches!(self.tokens.get(self.pos + 1), Some(Token::Assign))
            && !matches!(self.tokens.get(self.pos), Some(Token::Newline))
    }

    fn peek_next_is_compound_assign(&self) -> bool {
        matches!(
            self.tokens.get(self.pos + 1),
            Some(Token::PlusAssign)
                | Some(Token::MinusAssign)
                | Some(Token::StarAssign)
                | Some(Token::SlashAssign)
        )
    }

    fn peek_is_field_assign(&self) -> bool {
        self.peek_is_identifier()
            && matches!(self.tokens.get(self.pos + 1), Some(Token::Dot))
            && matches!(self.tokens.get(self.pos + 2), Some(Token::Identifier(_)))
            && matches!(self.tokens.get(self.pos + 3), Some(Token::Assign))
    }

    fn peek_is_index_assign(&self) -> bool {
        self.peek_is_identifier()
            && matches!(self.tokens.get(self.pos + 1), Some(Token::LeftBracket))
    }

    fn peek_is_expr_start(&self) -> bool {
        !matches!(self.peek(), Token::Newline | Token::RightBrace | Token::Eof)
    }

    fn peek_is_stmt_start(&self) -> bool {
        matches!(
            self.peek(),
            Token::Set
                | Token::Sensitive
                | Token::Const
                | Token::Type
                | Token::Task
                | Token::Inline
                | Token::Async
                | Token::Check
                | Token::Loop
                | Token::Override
                | Token::Purge
                | Token::Print
                | Token::PrintFmt
                | Token::Return
                | Token::Asm
                | Token::Import
                | Token::Break
                | Token::Continue
                | Token::Extern
                | Token::Struct
                | Token::Enum
                | Token::Free
                | Token::ConstantTime
                | Token::Match
                | Token::Spawn
                | Token::Defer
                | Token::Assert
                | Token::StaticAssert
                | Token::Test
                | Token::Namespace
                | Token::Use
        ) || (self.peek_is_identifier() && self.peek_next_is_assign())
            || (self.peek_is_identifier() && self.peek_next_is_compound_assign())
            || self.peek_is_field_assign()
    }

    pub fn parse_program(&mut self) -> Program {
        let mut stmts = Vec::new();
        while !self.is_at_end() {
            self.skip_newlines();
            if self.is_at_end() {
                break;
            }
            stmts.push(self.parse_stmt());
        }
        Program { statements: stmts }
    }

    fn parse_stmt(&mut self) -> Stmt {
        // Field assign: obj.field = val
        if self.peek_is_field_assign() {
            let object = self.consume_identifier();
            self.expect(Token::Dot);
            let field = self.consume_identifier();
            self.expect(Token::Assign);
            let value = self.parse_expr();
            self.skip_newlines();
            return Stmt::FieldAssign {
                object,
                field,
                value,
            };
        }

        // Index assign: arr[i] = val
        if self.peek_is_index_assign() {
            let save = self.pos;
            let array_name = self.consume_identifier();
            self.advance(); // [
            let idx = self.parse_expr();
            self.expect(Token::RightBracket);
            if matches!(self.peek(), Token::Assign) {
                self.advance();
                let value = self.parse_expr();
                self.skip_newlines();
                return Stmt::IndexAssign {
                    array: array_name,
                    index: idx,
                    value,
                };
            } else {
                self.pos = save;
            }
        }

        // Compound assign: x += 1
        if self.peek_is_identifier() && self.peek_next_is_compound_assign() {
            let name = self.consume_identifier();
            let op = match self.advance() {
                Token::PlusAssign => BinOp::Add,
                Token::MinusAssign => BinOp::Sub,
                Token::StarAssign => BinOp::Mul,
                Token::SlashAssign => BinOp::Div,
                _ => unreachable!(),
            };
            let value = self.parse_expr();
            self.skip_newlines();
            return Stmt::CompoundAssign { name, op, value };
        }

        match self.peek().clone() {
            Token::Set => {
                self.advance();
                let first_name = self.consume_identifier();

                // Optional type annotation: set x: int = 5
                let ty = if matches!(self.peek(), Token::Colon) {
                    self.advance();
                    Some(self.parse_type())
                } else {
                    None
                };

                // Multi-assign: set a, b = 1, 2
                if matches!(self.peek(), Token::Comma) {
                    let mut names = vec![first_name];
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        names.push(self.consume_identifier());
                    }
                    self.expect(Token::Assign);
                    let mut values = vec![self.parse_expr()];
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        values.push(self.parse_expr());
                    }
                    self.skip_newlines();
                    return Stmt::MultiAssign { names, values };
                }

                self.expect(Token::Assign);
                let value = self.parse_expr();
                self.skip_newlines();
                Stmt::VarDecl {
                    name: first_name,
                    ty,
                    value,
                    sensitive: false,
                }
            }

            Token::Sensitive => {
                self.advance();
                self.expect(Token::Set);
                let name = self.consume_identifier();
                let ty = if matches!(self.peek(), Token::Colon) {
                    self.advance();
                    Some(self.parse_type())
                } else {
                    None
                };
                self.expect(Token::Assign);
                let value = self.parse_expr();
                self.skip_newlines();
                Stmt::VarDecl {
                    name,
                    ty,
                    value,
                    sensitive: true,
                }
            }

            Token::Const => {
                self.advance();
                let name = self.consume_identifier();
                self.expect(Token::Assign);
                let value = self.parse_expr();
                self.skip_newlines();
                Stmt::ConstDecl { name, value }
            }

            Token::Type => {
                self.advance();
                let name = self.consume_identifier();
                self.expect(Token::Assign);
                let ty = self.parse_type();
                self.skip_newlines();
                Stmt::TypeAlias { name, ty }
            }

            Token::Namespace => {
                self.advance();
                let name = self.consume_identifier();
                self.skip_newlines();
                self.expect(Token::LeftBrace);
                let mut body = Vec::new();
                self.skip_newlines();
                while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
                    body.push(self.parse_stmt());
                    self.skip_newlines();
                }
                self.expect(Token::RightBrace);
                self.skip_newlines();
                Stmt::NamespaceDecl { name, body }
            }

            Token::Use => {
                self.advance();
                let mut path = vec![self.consume_identifier()];
                while matches!(self.peek(), Token::DoubleColon) {
                    self.advance();
                    path.push(self.consume_identifier());
                }
                self.skip_newlines();
                Stmt::UseDecl { path }
            }

            Token::Extern => {
                self.advance();
                self.expect(Token::Task);
                let name = self.consume_identifier();
                self.expect(Token::LeftParen);
                let mut params: Vec<Type> = Vec::new();
                let mut variadic = false;
                if !matches!(self.peek(), Token::RightParen) {
                    if matches!(self.peek(), Token::DotDot) {
                        self.advance();
                        variadic = true;
                    } else {
                        params.push(self.parse_type());
                        while matches!(self.peek(), Token::Comma) {
                            self.advance();
                            if matches!(self.peek(), Token::DotDot) {
                                self.advance();
                                variadic = true;
                                break;
                            }
                            params.push(self.parse_type());
                        }
                    }
                }
                self.expect(Token::RightParen);
                let return_type = if matches!(self.peek(), Token::Arrow) {
                    self.advance();
                    self.parse_type()
                } else {
                    Type::Void
                };
                self.skip_newlines();
                Stmt::ExternDecl {
                    name,
                    params,
                    return_type,
                    variadic,
                }
            }

            Token::Struct => {
                self.advance();
                let name = self.consume_identifier();
                let mut type_params: Vec<String> = Vec::new();
                if matches!(self.peek(), Token::LeftBracket) {
                    self.advance();
                    type_params.push(self.consume_identifier());
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        type_params.push(self.consume_identifier());
                    }
                    self.expect(Token::RightBracket);
                }
                self.skip_newlines();
                self.expect(Token::LeftBrace);
                let mut fields: Vec<(String, Type)> = Vec::new();
                self.skip_newlines();
                while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
                    let fname = self.consume_identifier();
                    self.expect(Token::Colon);
                    let ftype = self.parse_type();
                    fields.push((fname, ftype));
                    self.skip_newlines();
                }
                self.expect(Token::RightBrace);
                self.skip_newlines();
                Stmt::StructDecl {
                    name,
                    type_params,
                    fields,
                }
            }

            Token::Enum => {
                self.advance();
                let name = self.consume_identifier();
                self.skip_newlines();
                self.expect(Token::LeftBrace);
                let mut variants: Vec<EnumVariant> = Vec::new();
                self.skip_newlines();
                while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
                    let vname = self.consume_identifier();
                    // Enum variant with fields: Some(int) or None
                    let fields = if matches!(self.peek(), Token::LeftParen) {
                        self.advance();
                        let mut ftypes = Vec::new();
                        if !matches!(self.peek(), Token::RightParen) {
                            ftypes.push(self.parse_type());
                            while matches!(self.peek(), Token::Comma) {
                                self.advance();
                                ftypes.push(self.parse_type());
                            }
                        }
                        self.expect(Token::RightParen);
                        ftypes
                    } else {
                        Vec::new()
                    };
                    variants.push(EnumVariant {
                        name: vname,
                        fields,
                    });
                    if matches!(self.peek(), Token::Comma) {
                        self.advance();
                    }
                    self.skip_newlines();
                }
                self.expect(Token::RightBrace);
                self.skip_newlines();
                Stmt::EnumDecl { name, variants }
            }

            Token::Test => {
                self.advance();
                let name = match self.peek().clone() {
                    Token::StringLiteral(s) => {
                        self.advance();
                        s
                    }
                    Token::Identifier(s) => {
                        self.advance();
                        s
                    }
                    _ => self.error("expected test name"),
                };
                let body = self.parse_block();
                Stmt::TestDecl { name, body }
            }

            Token::Assert => {
                self.advance();
                self.expect(Token::LeftParen);
                let condition = self.parse_expr();
                let message = if matches!(self.peek(), Token::Comma) {
                    self.advance();
                    Some(match self.advance() {
                        Token::StringLiteral(s) => s,
                        _ => self.error("expected string message"),
                    })
                } else {
                    None
                };
                self.expect(Token::RightParen);
                self.skip_newlines();
                Stmt::Assert { condition, message }
            }

            Token::StaticAssert => {
                self.advance();
                self.expect(Token::LeftParen);
                let condition = self.parse_expr();
                let message = if matches!(self.peek(), Token::Comma) {
                    self.advance();
                    Some(match self.advance() {
                        Token::StringLiteral(s) => s,
                        _ => self.error("expected string"),
                    })
                } else {
                    None
                };
                self.expect(Token::RightParen);
                self.skip_newlines();
                Stmt::StaticAssert { condition, message }
            }

            Token::Defer => {
                self.advance();
                let body = self.parse_block();
                Stmt::Defer { body }
            }

            Token::Inline => {
                self.advance();
                let is_async = matches!(self.peek(), Token::Async);
                if is_async {
                    self.advance();
                }
                self.expect(Token::Task);
                self.parse_task_body(true, is_async)
            }

            Token::Async => {
                self.advance();
                self.expect(Token::Task);
                self.parse_task_body(false, true)
            }

            Token::Task => {
                self.advance();
                self.parse_task_body(false, false)
            }

            Token::Check => {
                self.advance();
                let condition = self.parse_expr();
                let then_block = self.parse_block();
                self.skip_newlines();
                let else_block = if matches!(self.peek(), Token::Else) {
                    self.advance();
                    Some(self.parse_block())
                } else {
                    None
                };
                Stmt::Check {
                    condition,
                    then_block,
                    else_block,
                }
            }

            Token::Loop => {
                self.advance();
                let kind = self.parse_loop_kind();
                let body = self.parse_block();
                Stmt::Loop { kind, body }
            }

            Token::Match => {
                self.advance();
                let value = self.parse_expr();
                self.skip_newlines();
                self.expect(Token::LeftBrace);
                let mut arms: Vec<MatchArm> = Vec::new();
                self.skip_newlines();
                while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
                    let pattern = self.parse_pattern();
                    self.expect(Token::FatArrow);
                    let body = self.parse_block();
                    arms.push(MatchArm { pattern, body });
                    self.skip_newlines();
                }
                self.expect(Token::RightBrace);
                self.skip_newlines();
                Stmt::Match { value, arms }
            }

            Token::Spawn => {
                self.advance();
                let var = if self.peek_is_identifier() {
                    Some(self.consume_identifier())
                } else {
                    None
                };
                let body = self.parse_block();
                Stmt::Spawn { var, body }
            }

            Token::Override => {
                self.advance();
                Stmt::Override {
                    body: self.parse_block(),
                }
            }
            Token::ConstantTime => {
                self.advance();
                Stmt::ConstantTime {
                    body: self.parse_block(),
                }
            }

            Token::Purge => {
                self.advance();
                let var = self.consume_identifier();
                self.skip_newlines();
                Stmt::Purge { variable: var }
            }

            Token::Free => {
                self.advance();
                let ptr = self.parse_expr();
                self.skip_newlines();
                Stmt::Free { ptr }
            }

            Token::Break => {
                self.advance();
                self.skip_newlines();
                Stmt::Break
            }
            Token::Continue => {
                self.advance();
                self.skip_newlines();
                Stmt::Continue
            }

            Token::Print => {
                self.advance();
                let expr = self.parse_expr();
                self.skip_newlines();
                Stmt::Print(expr)
            }

            Token::PrintFmt => {
                self.advance();
                self.expect(Token::LeftParen);
                let fmt = match self.advance() {
                    Token::StringLiteral(s) => s,
                    _ => self.error("print_fmt expects a format string"),
                };
                let mut args = Vec::new();
                while matches!(self.peek(), Token::Comma) {
                    self.advance();
                    args.push(self.parse_expr());
                }
                self.expect(Token::RightParen);
                self.skip_newlines();
                Stmt::PrintFmt { format: fmt, args }
            }

            Token::Return => {
                self.advance();
                let expr = if self.peek_is_expr_start() {
                    Some(self.parse_expr())
                } else {
                    None
                };
                self.skip_newlines();
                Stmt::Return(expr)
            }

            Token::Asm => {
                self.advance();
                self.expect(Token::LeftParen);
                let code = match self.advance() {
                    Token::StringLiteral(s) => s,
                    _ => self.error("expected assembly string"),
                };
                self.expect(Token::RightParen);
                self.skip_newlines();
                Stmt::Asm(code)
            }

            Token::Import => {
                self.advance();
                let path = match self.advance() {
                    Token::StringLiteral(s) => s,
                    _ => self.error("expected import path"),
                };
                self.skip_newlines();
                Stmt::Import(path)
            }

            _ if self.peek_is_identifier() && self.peek_next_is_assign() => {
                let name = self.consume_identifier();
                self.expect(Token::Assign);
                let value = self.parse_expr();
                self.skip_newlines();
                Stmt::Assign { name, value }
            }

            _ => {
                let expr = self.parse_expr();
                self.skip_newlines();
                Stmt::ExprStmt(expr)
            }
        }
    }

    fn parse_pattern(&mut self) -> Pattern {
        match self.peek().clone() {
            Token::Identifier(name) => {
                self.advance();
                if name == "_" {
                    return Pattern::Wildcard;
                }
                // Check for enum variant with capture: Some(x)
                if matches!(self.peek(), Token::LeftParen) {
                    self.advance();
                    let mut bindings = Vec::new();
                    if !matches!(self.peek(), Token::RightParen) {
                        bindings.push(self.consume_identifier());
                        while matches!(self.peek(), Token::Comma) {
                            self.advance();
                            bindings.push(self.consume_identifier());
                        }
                    }
                    self.expect(Token::RightParen);
                    return Pattern::EnumVariantCapture {
                        variant: name,
                        bindings,
                    };
                }
                // Namespaced: Enum::Variant
                if matches!(self.peek(), Token::DoubleColon) {
                    self.advance();
                    let variant = self.consume_identifier();
                    return Pattern::EnumVariant(variant);
                }
                Pattern::EnumVariant(name)
            }
            Token::Integer(n) => {
                let n = n;
                self.advance();
                if matches!(self.peek(), Token::DotDot) {
                    self.advance();
                    if let Token::Integer(end) = self.advance() {
                        return Pattern::Range(n, end);
                    }
                }
                Pattern::IntLiteral(n)
            }
            Token::True => {
                self.advance();
                Pattern::BoolLiteral(true)
            }
            Token::False => {
                self.advance();
                Pattern::BoolLiteral(false)
            }
            Token::StringLiteral(s) => {
                let s = s;
                self.advance();
                Pattern::StringLiteral(s)
            }
            _ => {
                self.advance();
                Pattern::Wildcard
            }
        }
    }

    fn parse_loop_kind(&mut self) -> LoopKind {
        if matches!(self.peek(), Token::LeftBrace) {
            return LoopKind::Infinite;
        }

        // FromTo: loop i from 0 to 10
        if self.peek_is_identifier() && self.peek_next() == Some(&Token::From) {
            let var = self.consume_identifier();
            self.expect(Token::From);
            let from = self.parse_expr();
            if matches!(self.peek(), Token::DotDot) {
                self.advance();
                let to = self.parse_expr();
                return LoopKind::FromTo { var, from, to };
            }
            self.expect(Token::To);
            let to = self.parse_expr();
            return LoopKind::FromTo { var, from, to };
        }

        // ForEach: loop item in collection
        if self.peek_is_identifier() && matches!(self.tokens.get(self.pos + 1), Some(Token::In)) {
            let var = self.consume_identifier();
            self.advance(); // in
            let iterable = self.parse_expr();
            return LoopKind::ForEach { var, iterable };
        }

        // Range: loop i in 0..10
        if self.peek_is_identifier() {
            // Look ahead for 'in' after identifier
        }

        let expr = self.parse_expr();
        if matches!(self.peek(), Token::Times) {
            self.advance();
            LoopKind::Times(expr)
        } else {
            LoopKind::While(expr)
        }
    }

    fn parse_task_body(&mut self, is_inline: bool, is_async: bool) -> Stmt {
        let name = self.consume_identifier();

        // Generic type params: task sort[T]
        let mut type_params: Vec<String> = Vec::new();
        if matches!(self.peek(), Token::LeftBracket) {
            self.advance();
            type_params.push(self.consume_identifier());
            while matches!(self.peek(), Token::Comma) {
                self.advance();
                type_params.push(self.consume_identifier());
            }
            self.expect(Token::RightBracket);
        }

        // Constraints: where T: Comparable + Numeric
        let mut constraints: Vec<(String, Vec<String>)> = Vec::new();
        if matches!(self.peek(), Token::Where) {
            self.advance();
            loop {
                let tp = self.consume_identifier();
                self.expect(Token::Colon);
                let mut cs = vec![self.consume_identifier()];
                while matches!(self.peek(), Token::Plus) {
                    self.advance();
                    cs.push(self.consume_identifier());
                }
                constraints.push((tp, cs));
                if !matches!(self.peek(), Token::Comma) {
                    break;
                }
                self.advance();
            }
        }

        self.expect(Token::LeftParen);
        let mut params: Vec<(String, Type)> = Vec::new();
        if !matches!(self.peek(), Token::RightParen) {
            let pn = self.consume_identifier();
            self.expect(Token::Colon);
            let pt = self.parse_type();
            params.push((pn, pt));
            while matches!(self.peek(), Token::Comma) {
                self.advance();
                let pn = self.consume_identifier();
                self.expect(Token::Colon);
                let pt = self.parse_type();
                params.push((pn, pt));
            }
        }
        self.expect(Token::RightParen);

        let return_type = if matches!(self.peek(), Token::Arrow) {
            self.advance();
            self.parse_type()
        } else {
            Type::Void
        };

        let body = self.parse_block();
        Stmt::TaskDecl {
            name,
            type_params,
            constraints,
            params,
            return_type,
            body,
            is_inline,
            is_async,
        }
    }

    fn parse_block(&mut self) -> Block {
        self.skip_newlines();
        self.expect(Token::LeftBrace);
        let mut stmts = Vec::new();
        let mut tail = None;
        self.skip_newlines();
        while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
            if self.peek_is_stmt_start() {
                stmts.push(self.parse_stmt());
                self.skip_newlines();
            } else {
                let expr = self.parse_expr();
                self.skip_newlines();
                if matches!(self.peek(), Token::RightBrace) {
                    tail = Some(expr);
                    break;
                } else {
                    stmts.push(Stmt::ExprStmt(expr));
                    self.skip_newlines();
                }
            }
        }
        self.expect(Token::RightBrace);
        self.skip_newlines();
        Block {
            statements: stmts,
            tail_expr: tail,
        }
    }

    fn parse_type(&mut self) -> Type {
        // Closure type: |int| -> int
        if matches!(self.peek(), Token::Pipe | Token::Pipe2) {
            let is_empty = matches!(self.peek(), Token::Pipe2);
            let mut params = Vec::new();
            if is_empty {
                self.advance();
            } else {
                self.advance();
                if !matches!(self.peek(), Token::Pipe) {
                    params.push(self.parse_type());
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        params.push(self.parse_type());
                    }
                }
                self.expect(Token::Pipe);
            }
            let ret = if matches!(self.peek(), Token::Arrow) {
                self.advance();
                self.parse_type()
            } else {
                Type::Void
            };
            return Type::Fn(params, Box::new(ret));
        }

        // Tuple: (int, float, bool)
        if matches!(self.peek(), Token::LeftParen) {
            self.advance();
            let mut types = Vec::new();
            if !matches!(self.peek(), Token::RightParen) {
                types.push(self.parse_type());
                while matches!(self.peek(), Token::Comma) {
                    self.advance();
                    types.push(self.parse_type());
                }
            }
            self.expect(Token::RightParen);
            return if types.len() == 1 {
                types.remove(0)
            } else {
                Type::Tuple(types)
            };
        }

        let base = match self.advance() {
            Token::Identifier(s) => match s.as_str() {
                "int" => Type::Int,
                "float" => Type::Float,
                "bool" => Type::Bool,
                "string" => Type::String,
                "ptr" => Type::Ptr,
                "void" => Type::Void,
                name if name.len() == 1
                    && name.chars().next().map_or(false, |c| c.is_uppercase()) =>
                {
                    Type::Generic(name.to_string())
                }
                name => Type::Struct(name.to_string()),
            },
            Token::Int8 => Type::Int8,
            Token::Int16 => Type::Int16,
            Token::Int64 => Type::Int64,
            Token::Uint8 => Type::Uint8,
            Token::Uint16 => Type::Uint16,
            Token::Uint32 => Type::Uint32,
            Token::Uint64 => Type::Uint64,
            Token::LeftBracket => {
                // Slice: [int] or [int; 10] (future)
                let inner = self.parse_type();
                self.expect(Token::RightBracket);
                Type::Array(Box::new(inner))
            }
            tok => self.error(&format!("expected type, got {:?}", tok)),
        };

        // Nullable: int?
        if matches!(self.peek(), Token::Question) {
            self.advance();
            return Type::Nullable(Box::new(base));
        }

        base
    }

    // ── Expression tower ─────────────────────────────────────────────────────

    fn parse_expr(&mut self) -> Expr {
        self.parse_or()
    }

    fn parse_or(&mut self) -> Expr {
        let mut l = self.parse_and();
        while matches!(self.peek(), Token::Or) {
            self.advance();
            let r = self.parse_and();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op: BinOp::Or,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_and(&mut self) -> Expr {
        let mut l = self.parse_bitor();
        while matches!(self.peek(), Token::And) {
            self.advance();
            let r = self.parse_bitor();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op: BinOp::And,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_bitor(&mut self) -> Expr {
        let mut l = self.parse_bitxor();
        while matches!(self.peek(), Token::Pipe) {
            self.advance();
            let r = self.parse_bitxor();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op: BinOp::BitOr,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_bitxor(&mut self) -> Expr {
        let mut l = self.parse_bitand();
        while matches!(self.peek(), Token::Caret) {
            self.advance();
            let r = self.parse_bitand();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op: BinOp::BitXor,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_bitand(&mut self) -> Expr {
        let mut l = self.parse_comparison();
        while matches!(self.peek(), Token::Ampersand) {
            self.advance();
            let r = self.parse_comparison();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op: BinOp::BitAnd,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_comparison(&mut self) -> Expr {
        let mut l = self.parse_shift();
        loop {
            let op = match self.peek() {
                Token::EqualEqual => BinOp::Eq,
                Token::NotEqual => BinOp::Neq,
                Token::Less => BinOp::Lt,
                Token::Greater => BinOp::Gt,
                Token::LessEqual => BinOp::Le,
                Token::GreaterEqual => BinOp::Ge,
                _ => break,
            };
            self.advance();
            let r = self.parse_shift();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_shift(&mut self) -> Expr {
        let mut l = self.parse_term();
        loop {
            let op = match self.peek() {
                Token::LessLess => BinOp::Shl,
                Token::GreaterGreater => BinOp::Shr,
                _ => break,
            };
            self.advance();
            let r = self.parse_term();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_term(&mut self) -> Expr {
        let mut l = self.parse_factor();
        loop {
            let op = match self.peek() {
                Token::Plus => BinOp::Add,
                Token::Minus => BinOp::Sub,
                _ => break,
            };
            self.advance();
            let r = self.parse_factor();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_factor(&mut self) -> Expr {
        let mut l = self.parse_unary();
        loop {
            let op = match self.peek() {
                Token::Star => BinOp::Mul,
                Token::Slash => BinOp::Div,
                Token::Percent => BinOp::Mod,
                _ => break,
            };
            self.advance();
            let r = self.parse_unary();
            l = Expr::BinaryOp {
                left: Box::new(l),
                op,
                right: Box::new(r),
            };
        }
        l
    }

    fn parse_unary(&mut self) -> Expr {
        match self.peek() {
            Token::Minus => {
                self.advance();
                Expr::UnaryOp {
                    op: UnaryOp::Neg,
                    operand: Box::new(self.parse_unary()),
                }
            }
            Token::Not => {
                self.advance();
                Expr::UnaryOp {
                    op: UnaryOp::Not,
                    operand: Box::new(self.parse_unary()),
                }
            }
            Token::Tilde => {
                self.advance();
                Expr::UnaryOp {
                    op: UnaryOp::BitNot,
                    operand: Box::new(self.parse_unary()),
                }
            }
            Token::Ampersand => {
                self.advance();
                Expr::AddressOf(Box::new(self.parse_unary()))
            }
            Token::Star => {
                self.advance();
                Expr::Deref(Box::new(self.parse_unary()))
            }
            Token::Comptime => {
                self.advance();
                Expr::Comptime(Box::new(self.parse_primary()))
            }
            Token::Await => {
                self.advance();
                Expr::Await(Box::new(self.parse_primary()))
            }
            _ => self.parse_postfix(),
        }
    }

    fn parse_postfix(&mut self) -> Expr {
        let mut expr = self.parse_primary();
        loop {
            match self.peek() {
                Token::LeftParen => {
                    self.advance();
                    let mut args = Vec::new();
                    let mut named = Vec::new();
                    if !matches!(self.peek(), Token::RightParen) {
                        // Check for named argument: name: value
                        if self.peek_is_identifier()
                            && matches!(self.tokens.get(self.pos + 1), Some(Token::Colon))
                        {
                            let aname = self.consume_identifier();
                            self.advance(); // :
                            let aval = self.parse_expr();
                            named.push((aname, aval));
                        } else {
                            args.push(self.parse_expr());
                        }
                        while matches!(self.peek(), Token::Comma) {
                            self.advance();
                            if self.peek_is_identifier()
                                && matches!(self.tokens.get(self.pos + 1), Some(Token::Colon))
                            {
                                let aname = self.consume_identifier();
                                self.advance();
                                named.push((aname, self.parse_expr()));
                            } else {
                                args.push(self.parse_expr());
                            }
                        }
                    }
                    self.expect(Token::RightParen);
                    expr = Expr::Call {
                        func: Box::new(expr),
                        args,
                        named,
                    };
                }
                Token::LeftBracket => {
                    self.advance();
                    let index = self.parse_expr();
                    self.expect(Token::RightBracket);
                    expr = Expr::Index {
                        array: Box::new(expr),
                        index: Box::new(index),
                    };
                }
                Token::As => {
                    self.advance();
                    let to = self.parse_type();
                    expr = Expr::Cast {
                        expr: Box::new(expr),
                        to,
                    };
                }
                Token::Dot => {
                    self.advance();
                    if matches!(self.peek(), Token::Await) {
                        self.advance();
                        expr = Expr::Await(Box::new(expr));
                    } else if let Token::Integer(n) = self.peek().clone() {
                        // Tuple index: tuple.0
                        let n = n;
                        self.advance();
                        expr = Expr::TupleIndex {
                            tuple: Box::new(expr),
                            index: n as usize,
                        };
                    } else {
                        let field = self.consume_identifier();
                        expr = Expr::FieldAccess {
                            object: Box::new(expr),
                            field,
                        };
                    }
                }
                Token::Question => {
                    self.advance();
                    expr = Expr::PropagateErr(Box::new(expr));
                }
                _ => break,
            }
        }
        // Range: expr..expr or expr..=expr
        if matches!(self.peek(), Token::DotDot | Token::DotDotEq) {
            let inclusive = matches!(self.peek(), Token::DotDotEq);
            self.advance();
            let end = self.parse_primary();
            return Expr::Range {
                start: Box::new(expr),
                end: Box::new(end),
                inclusive,
            };
        }
        expr
    }

    fn parse_primary(&mut self) -> Expr {
        // Closure: |x, y| expr  or  || expr
        if matches!(self.peek(), Token::Pipe | Token::Pipe2) {
            let is_empty = matches!(self.peek(), Token::Pipe2);
            let mut params: Vec<(String, Option<Type>)> = Vec::new();
            if is_empty {
                self.advance();
            } else {
                self.advance();
                if !matches!(self.peek(), Token::Pipe) {
                    let pname = self.consume_identifier();
                    let pty = if matches!(self.peek(), Token::Colon) {
                        self.advance();
                        Some(self.parse_type())
                    } else {
                        None
                    };
                    params.push((pname, pty));
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        let pn = self.consume_identifier();
                        let pt = if matches!(self.peek(), Token::Colon) {
                            self.advance();
                            Some(self.parse_type())
                        } else {
                            None
                        };
                        params.push((pn, pt));
                    }
                }
                self.expect(Token::Pipe);
            }
            let body = self.parse_expr();
            return Expr::Closure {
                params,
                body: Box::new(body),
            };
        }

        if matches!(self.peek(), Token::Alloc) {
            self.advance();
            self.expect(Token::LeftParen);
            let count = self.parse_expr();
            self.expect(Token::Comma);
            let size = self.parse_expr();
            self.expect(Token::RightParen);
            return Expr::Alloc {
                count: Box::new(count),
                size: Box::new(size),
            };
        }
        if matches!(self.peek(), Token::Ok) {
            self.advance();
            self.expect(Token::LeftParen);
            let inner = self.parse_expr();
            self.expect(Token::RightParen);
            return Expr::OkExpr(Box::new(inner));
        }
        if matches!(self.peek(), Token::Err) {
            self.advance();
            self.expect(Token::LeftParen);
            let inner = self.parse_expr();
            self.expect(Token::RightParen);
            return Expr::ErrExpr(Box::new(inner));
        }

        match self.advance() {
            Token::Integer(n) => Expr::Integer(n),
            Token::Float(f) => Expr::Float(f),
            Token::True => Expr::Boolean(true),
            Token::False => Expr::Boolean(false),
            Token::Null => Expr::Null,
            Token::StringLiteral(s) => {
                if s.contains('{') && s.contains('}') {
                    self.parse_interpolated_string(s)
                } else {
                    Expr::StringLiteral(s)
                }
            }
            Token::Identifier(name) => {
                // Struct literal: Name { ... }
                if matches!(self.peek(), Token::LeftBrace) {
                    self.advance();
                    let mut fields = Vec::new();
                    self.skip_newlines();
                    while !matches!(self.peek(), Token::RightBrace) && !self.is_at_end() {
                        let fname = self.consume_identifier();
                        self.expect(Token::Colon);
                        let fval = self.parse_expr();
                        fields.push((fname, fval));
                        if matches!(self.peek(), Token::Comma) {
                            self.advance();
                        }
                        self.skip_newlines();
                    }
                    self.expect(Token::RightBrace);
                    Expr::StructLiteral { name, fields }
                } else {
                    Expr::Identifier(name)
                }
            }
            Token::LeftParen => {
                // Tuple or parenthesized expr
                let first = self.parse_expr();
                if matches!(self.peek(), Token::Comma) {
                    let mut elems = vec![first];
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        if matches!(self.peek(), Token::RightParen) {
                            break;
                        }
                        elems.push(self.parse_expr());
                    }
                    self.expect(Token::RightParen);
                    Expr::Tuple(elems)
                } else {
                    self.expect(Token::RightParen);
                    first
                }
            }
            Token::LeftBracket => {
                let mut elems = Vec::new();
                if !matches!(self.peek(), Token::RightBracket) {
                    elems.push(self.parse_expr());
                    while matches!(self.peek(), Token::Comma) {
                        self.advance();
                        elems.push(self.parse_expr());
                    }
                }
                self.expect(Token::RightBracket);
                Expr::Array(elems)
            }
            Token::Copy => Expr::Copy(Box::new(self.parse_primary())),
            tok => self.error(&format!("unexpected token: {:?}", tok)),
        }
    }

    fn parse_interpolated_string(&self, s: String) -> Expr {
        let mut parts: Vec<StringPart> = Vec::new();
        let mut current = String::new();
        let chars: Vec<char> = s.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            if chars[i] == '{' && i + 1 < chars.len() && chars[i + 1] != '{' {
                if !current.is_empty() {
                    parts.push(StringPart::Literal(current.clone()));
                    current.clear();
                }
                i += 1;
                let mut expr_str = String::new();
                while i < chars.len() && chars[i] != '}' {
                    expr_str.push(chars[i]);
                    i += 1;
                }
                i += 1;
                parts.push(StringPart::Interpolated(Expr::Identifier(
                    expr_str.trim().to_string(),
                )));
            } else if chars[i] == '{' && i + 1 < chars.len() && chars[i + 1] == '{' {
                current.push('{');
                i += 2;
            } else if chars[i] == '}' && i + 1 < chars.len() && chars[i + 1] == '}' {
                current.push('}');
                i += 2;
            } else {
                current.push(chars[i]);
                i += 1;
            }
            // In parse_stmt, handle bare assignment without `set`:
            // x = 10  works the same as  set x = 10
            // The parser tries assignment if it sees identifier = expression

            // In parse_type, all type annotations are optional
            // set x = 10        → x inferred as int
            // task add(a, b)    → params inferred from usage
            // task add(a, b) -> { return a + b }  → return type inferred

            fn parse_stmt(&mut self) -> Stmt {
                // Bare assignment: x = 10 (no set keyword needed)
                // This is the Python-style shorthand
                if self.peek_is_identifier() {
                    // Look ahead: if next is = (not ==), treat as declaration/assignment
                    if self.peek_next_is_assign() {
                        let name = self.consume_identifier();
                        self.expect(Token::Assign);
                        let value = self.parse_expr();
                        self.skip_newlines();
                        fn parse_task_body(&mut self, is_inline: bool, is_async: bool) -> Stmt {
                            let name = self.consume_identifier();
                            // ... type params and constraints ...
                            self.expect(Token::LeftParen);
                            let mut params: Vec<(String, Type)> = Vec::new();
                            if !matches!(self.peek(), Token::RightParen) {
                                let pn = self.consume_identifier();
                                // Type annotation is now OPTIONAL
                                let pt = if matches!(self.peek(), Token::Colon) {
                                    self.advance();
                                    self.parse_type()
                                } else {
                                    Type::Generic("_infer".to_string()) // mark for inference
                                };
                                params.push((pn, pt));
                                while matches!(self.peek(), Token::Comma) {
                                    self.advance();
                                    let pn = self.consume_identifier();
                                    let pt = if matches!(self.peek(), Token::Colon) {
                                        self.advance();
                                        self.parse_type()
                                    } else {
                                        Type::Generic("_infer".to_string())
                                    };
                                    params.push((pn, pt));
                                }
                                fn parse_block(&mut self) -> Block {
                                    self.skip_newlines();

                                    // Optional braces — if next token is not {, parse a single statement
                                    if !matches!(self.peek(), Token::LeftBrace) {
                                        // Single-line block: if condition: statement
                                        let stmt = self.parse_stmt();
                                        return Block {
                                            statements: vec![stmt],
                                            tail_expr: None,
                                        };
                                        // Multiple return values
                                        // task divmod(a: int, b: int) -> (int, int) {
                                        //     return (a / b, a % b)
                                        // }
                                        // set q, r = divmod(10, 3)

                                        // Error recovery — collect ALL errors, not just first
                                        // Add errors: Vec<String> to Parser struct
                                        // In parse_stmt, catch errors and continue:

                                        impl Parser {
                                            // Add to existing impl:

                                            fn try_parse_stmt(&mut self) -> Result<Stmt, String> {
                                                // Wraps parse_stmt with error recovery
                                                // On error: skip to next newline and continue
                                                // This lets us report ALL errors at once
                                                let save = self.pos;
                                                // ... parse attempt
                                                // on failure: restore pos, skip to next statement boundary
                                                Ok(Stmt::ExprStmt(Expr::In
                                                    Token::Return => {
                                                        self.advance();
                                                        let has_paren = matches!(self.peek(), Token::LeftParen);
                                                        if has_paren { self.advance(); }
                                                        let expr = if self.peek_is_expr_start() {
                                                            Some(self.parse_expr())
                                                        } else {
                                                            None
                                                        };
                                                        if has_paren {
                                                            if matches!(self.peek(), Token::RightParen) { self.advance(); }
                                                        }
                                                        self.skip_newlines();
                                                        Stmt::Return(expr)
                                                    }teger(0))) // placeholder
                                            }
                                            Token::Assert => {
                                                self.advance();
                                                // Both forms work:
                                                //   assert(x > 0, "message")
                                                //   assert x > 0
                                                let has_paren = matches!(self.peek(), Token::LeftParen);
                                                if has_paren { self.advance(); }
                                                let condition = self.parse_expr();
                                                let message = if matches!(self.peek(), Token::Comma) {
                                                    self.advance();
                                                    Some(match self.advance() {
                                                        Token::StringLiteral(s) => s,
                                                        _ => self.error("expected string message"),
                                                    })
                                                } else { None };
                                                if has_paren {
                                                    if matches!(self.peek(), Token::RightParen) { self.advance(); }
                                                }
                                                self.skip_newlines();
                                                Stmt::Assert { condition, message }
                                            }
                                            // Allow print("Hello") with parentheses
                                            // so Python muscle memory works perfectly
                                            Token::Print => {
                                            Token::Print => {
                                                self.advance();
                                                // Accept both: print "hello"  AND  print("hello")
                                                // So Python muscle memory works perfectly
                                                let has_paren = matches!(self.peek(), Token::LeftParen);
                                                if has_paren { self.advance(); }
                                                let expr = self.parse_expr();
                                                if has_paren {
                                                    // Only consume ) if we consumed (
                                                    if matches!(self.peek(), Token::RightParen) {
                                                        self.advance();
                                                    }
                                                }
                                                self.skip_newlines();
                                                Stmt::Print(expr)
                                            }
                                                self.advance();
                                                // Accept optional parentheses
                                                let has_paren = matches!(self.peek(), Token::LeftParen);
                                                if has_paren { self.advance(); }
                                                let expr = self.parse_expr();
                                                if has_paren { self.expect(Token::RightParen); }
                                                self.skip_newlines();
                                                Stmt::Print(expr)
                                            }

                                            fn sync_to_next_statement(&mut self) {
                                                // Skip tokens until we reach something that looks like
                                                // the start of a new statement
                                                while !self.is_at_end() {
                                                    if matches!(self.peek(), Token::Newline) {
                                                        self.advance();
                                                        // Check if next token is a statement start
                                                        if self.peek_is_stmt_start() { return; }
                                                    } else {
                                                        self.advance();
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    // Normal brace block
                                    self.expect(Token::LeftBrace);
                                    // ... rest unchanged
                            }
                            self.expect(Token::RightParen);
                            // Return type is optional
                            let return_type = if matches!(self.peek(), Token::Arrow) {
                                self.advance(); self.parse_type()
                            } else {
                                Type::Void // inferred
                            };
                            let body = self.parse_block();
                            Stmt::TaskDecl { name, type_params: vec![], constraints: vec![], params, return_type, body, is_inline, is_async }
                        }
                        // Declare if new, assign if exists
                        return Stmt::VarDecl {
                            name,
                            ty: None,      // always infer
                            value,
                            sensitive: false,
                        };
                    }
                }

                // All existing parse_stmt logic follows...
                // (unchanged from previous version)
        }
        if !current.is_empty() {
            parts.push(StringPart::Literal(current));
        }
        if parts.len() == 1 {
            if let StringPart::Literal(ref l) = parts[0] {
                return Expr::StringLiteral(l.clone());
            }
        }
        Expr::InterpolatedString(parts)
    }
}
