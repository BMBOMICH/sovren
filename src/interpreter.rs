/// Sovereign interpreter for scripting mode.
///
/// sovereign run file.sov
///
/// Interprets the AST directly without compiling to machine code.
/// Slower than compiled mode but instant startup — useful for scripts.
/// Same language, same safety checks, just interpreted.
use crate::ast::*;
use std::collections::HashMap;
use std::fmt;

#[derive(Debug, Clone)]
pub enum Value {
    Int(i64),
    Float(f64),
    Bool(bool),
    Str(String),
    Array(Vec<Value>),
    Null,
    Void,
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Value::Int(n) => write!(f, "{}", n),
            Value::Float(v) => write!(f, "{}", v),
            Value::Bool(b) => write!(f, "{}", b),
            Value::Str(s) => write!(f, "{}", s),
            Value::Null => write!(f, "null"),
            Value::Void => write!(f, ""),
            Value::Array(a) => {
                let items: Vec<String> = a.iter().map(|v| format!("{}", v)).collect();
                write!(f, "[{}]", items.join(", "))
            }
        }
    }
}

pub struct Interpreter {
    scopes: Vec<HashMap<String, Value>>,
    tasks: HashMap<String, (Vec<(String, Type)>, Block)>,
    return_value: Option<Value>,
}

impl Interpreter {
    pub fn new() -> Self {
        Interpreter {
            scopes: vec![HashMap::new()],
            tasks: HashMap::new(),
            return_value: None,
        }
    }

    pub fn run(&mut self, program: &Program) {
        // Collect task declarations first
        for stmt in &program.statements {
            if let Stmt::TaskDecl {
                name, params, body, ..
            } = stmt
            {
                self.tasks
                    .insert(name.clone(), (params.clone(), body.clone()));
            }
        }
        // Execute top-level statements
        for stmt in &program.statements {
            if !matches!(stmt, Stmt::TaskDecl { .. }) {
                self.exec_stmt(stmt);
            }
        }
    }

    fn push_scope(&mut self) {
        self.scopes.push(HashMap::new());
    }
    fn pop_scope(&mut self) {
        self.scopes.pop();
    }

    fn set_var(&mut self, name: &str, val: Value) {
        // Update existing scope first
        for scope in self.scopes.iter_mut().rev() {
            if scope.contains_key(name) {
                scope.insert(name.to_string(), val);
                return;
            }
        }
        // Declare in current scope
        if let Some(scope) = self.scopes.last_mut() {
            scope.insert(name.to_string(), val);
        }
    }

    fn get_var(&self, name: &str) -> Value {
        for scope in self.scopes.iter().rev() {
            if let Some(v) = scope.get(name) {
                return v.clone();
            }
        }
        Value::Null
    }

    fn exec_stmt(&mut self, stmt: &Stmt) {
        if self.return_value.is_some() {
            return;
        }

        match stmt {
            Stmt::VarDecl { name, value, .. } | Stmt::ConstDecl { name, value } => {
                let val = self.eval_expr(value);
                self.set_var(name, val);
            }

            Stmt::Assign { name, value } => {
                let val = self.eval_expr(value);
                self.set_var(name, val);
            }

            Stmt::CompoundAssign { name, op, value } => {
                let current = self.get_var(name);
                let rhs = self.eval_expr(value);
                let result = self.apply_binop(&current, op, &rhs);
                self.set_var(name, result);
            }

            Stmt::Print(expr) => {
                let val = self.eval_expr(expr);
                println!("{}", val);
            }

            Stmt::PrintFmt { format, args } => {
                let mut result = format.clone();
                let compiled: Vec<Value> = args.iter().map(|a| self.eval_expr(a)).collect();
                for val in &compiled {
                    if let Some(pos) = result
                        .find("%d")
                        .or_else(|| result.find("%s"))
                        .or_else(|| result.find("%f"))
                    {
                        let end = pos + 2;
                        result = format!("{}{}{}", &result[..pos], val, &result[end..]);
                    }
                }
                print!("{}", result);
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                let cond = self.eval_expr(condition);
                if is_truthy(&cond) {
                    self.push_scope();
                    self.exec_block(then_block);
                    self.pop_scope();
                } else if let Some(eb) = else_block {
                    self.push_scope();
                    self.exec_block(eb);
                    self.pop_scope();
                }
            }

            Stmt::Loop { kind, body } => match kind {
                LoopKind::FromTo { var, from, to } => {
                    let from_val = match self.eval_expr(from) {
                        Value::Int(n) => n,
                        _ => 0,
                    };
                    let to_val = match self.eval_expr(to) {
                        Value::Int(n) => n,
                        _ => 0,
                    };
                    let mut i = from_val;
                    while i <= to_val {
                        self.push_scope();
                        self.set_var(var, Value::Int(i));
                        self.exec_block(body);
                        self.pop_scope();
                        if self.return_value.is_some() {
                            break;
                        }
                        i += 1;
                    }
                }
                LoopKind::Times(count) => {
                    let n = match self.eval_expr(count) {
                        Value::Int(n) => n,
                        _ => 0,
                    };
                    for _ in 0..n {
                        self.push_scope();
                        self.exec_block(body);
                        self.pop_scope();
                        if self.return_value.is_some() {
                            break;
                        }
                    }
                }
                LoopKind::While(cond) => loop {
                    let c = self.eval_expr(cond);
                    if !is_truthy(&c) {
                        break;
                    }
                    self.push_scope();
                    self.exec_block(body);
                    self.pop_scope();
                    if self.return_value.is_some() {
                        break;
                    }
                },
                LoopKind::ForEach { var, iterable } => {
                    let arr = self.eval_expr(iterable);
                    if let Value::Array(items) = arr {
                        for item in items {
                            self.push_scope();
                            self.set_var(var, item);
                            self.exec_block(body);
                            self.pop_scope();
                            if self.return_value.is_some() {
                                break;
                            }
                        }
                    }
                }
                LoopKind::Infinite => loop {
                    self.push_scope();
                    self.exec_block(body);
                    self.pop_scope();
                    if self.return_value.is_some() {
                        break;
                    }
                },
                _ => {}
            },

            Stmt::Return(expr) => {
                let val = expr
                    .as_ref()
                    .map(|e| self.eval_expr(e))
                    .unwrap_or(Value::Void);
                self.return_value = Some(val);
            }

            Stmt::Assert { condition, message } => {
                let cond = self.eval_expr(condition);
                if !is_truthy(&cond) {
                    let msg = message.as_deref().unwrap_or("Assertion failed");
                    eprintln!("ASSERTION FAILED: {}", msg);
                    std::process::exit(1);
                }
            }

            Stmt::ExprStmt(expr) => {
                self.eval_expr(expr);
            }

            Stmt::StructDecl { .. }
            | Stmt::EnumDecl { .. }
            | Stmt::TaskDecl { .. }
            | Stmt::Import(_) => {}

            _ => {}
        }
    }

    fn exec_block(&mut self, block: &Block) {
        for stmt in &block.statements {
            if self.return_value.is_some() {
                break;
            }
            self.exec_stmt(stmt);
        }
        if let Some(tail) = &block.tail_expr {
            if self.return_value.is_none() {
                self.eval_expr(tail);
            }
        }
    }

    fn eval_expr(&mut self, expr: &Expr) -> Value {
        match expr {
            Expr::Integer(n) => Value::Int(*n),
            Expr::Float(f) => Value::Float(*f),
            Expr::Boolean(b) => Value::Bool(*b),
            Expr::StringLiteral(s) => Value::Str(s.clone()),
            Expr::Null => Value::Null,

            Expr::InterpolatedString(parts) => {
                let mut result = String::new();
                for part in parts {
                    match part {
                        StringPart::Literal(s) => result.push_str(s),
                        StringPart::Interpolated(e) => {
                            result.push_str(&format!("{}", self.eval_expr(e)));
                        }
                    }
                }
                Value::Str(result)
            }

            Expr::Identifier(name) => self.get_var(name),

            Expr::BinaryOp { left, op, right } => {
                let l = self.eval_expr(left);
                let r = self.eval_expr(right);
                self.apply_binop(&l, op, &r)
            }

            Expr::UnaryOp { op, operand } => {
                let val = self.eval_expr(operand);
                match op {
                    UnaryOp::Neg => match val {
                        Value::Int(n) => Value::Int(-n),
                        Value::Float(f) => Value::Float(-f),
                        _ => Value::Int(0),
                    },
                    UnaryOp::Not => Value::Bool(!is_truthy(&val)),
                    UnaryOp::BitNot => match val {
                        Value::Int(n) => Value::Int(!n),
                        _ => Value::Int(0),
                    },
                }
            }

            Expr::Call { func, args, .. } => {
                if let Expr::Identifier(name) = func.as_ref() {
                    // Built-in functions
                    match name.as_str() {
                        "puts" | "print" => {
                            let val = args
                                .first()
                                .map(|a| self.eval_expr(a))
                                .unwrap_or(Value::Null);
                            println!("{}", val);
                            return Value::Int(0);
                        }
                        "strlen" | "str_len" => {
                            if let Some(a) = args.first() {
                                if let Value::Str(s) = self.eval_expr(a) {
                                    return Value::Int(s.len() as i64);
                                }
                            }
                            return Value::Int(0);
                        }
                        "sqrt" => {
                            if let Some(a) = args.first() {
                                if let Value::Float(f) = self.eval_expr(a) {
                                    return Value::Float(f.sqrt());
                                }
                            }
                        }
                        "abs" => {
                            if let Some(a) = args.first() {
                                match self.eval_expr(a) {
                                    Value::Int(n) => return Value::Int(n.abs()),
                                    Value::Float(f) => return Value::Float(f.abs()),
                                    _ => {}
                                }
                            }
                        }
                        "min" => {
                            if args.len() >= 2 {
                                let a = self.eval_expr(&args[0]);
                                let b = self.eval_expr(&args[1]);
                                return match (a, b) {
                                    (Value::Int(x), Value::Int(y)) => Value::Int(x.min(y)),
                                    (Value::Float(x), Value::Float(y)) => Value::Float(x.min(y)),
                                    _ => Value::Int(0),
                                };
                            }
                        }
                        "max" => {
                            if args.len() >= 2 {
                                let a = self.eval_expr(&args[0]);
                                let b = self.eval_expr(&args[1]);
                                return match (a, b) {
                                    (Value::Int(x), Value::Int(y)) => Value::Int(x.max(y)),
                                    (Value::Float(x), Value::Float(y)) => Value::Float(x.max(y)),
                                    _ => Value::Int(0),
                                };
                            }
                        }
                        "exit" => {
                            let code = args
                                .first()
                                .map(|a| match self.eval_expr(a) {
                                    Value::Int(n) => n as i32,
                                    _ => 0,
                                })
                                .unwrap_or(0);
                            std::process::exit(code);
                        }
                        _ => {
                            // User-defined task
                            if let Some((params, body)) = self.tasks.get(name).cloned() {
                                let compiled_args: Vec<Value> =
                                    args.iter().map(|a| self.eval_expr(a)).collect();
                                self.push_scope();
                                for (i, (pname, _)) in params.iter().enumerate() {
                                    let val = compiled_args.get(i).cloned().unwrap_or(Value::Null);
                                    self.set_var(pname, val);
                                }
                                self.exec_block(&body);
                                self.pop_scope();
                                let ret = self.return_value.take().unwrap_or(Value::Void);
                                return ret;
                            }
                        }
                    }
                }
                Value::Void
            }

            Expr::Array(elems) => {
                let vals: Vec<Value> = elems.iter().map(|e| self.eval_expr(e)).collect();
                Value::Array(vals)
            }

            Expr::Index { array, index } => {
                let arr = self.eval_expr(array);
                let idx = match self.eval_expr(index) {
                    Value::Int(n) => n as usize,
                    _ => 0,
                };
                match arr {
                    Value::Array(items) => {
                        if idx < items.len() {
                            items[idx].clone()
                        } else {
                            eprintln!(
                                "Error: array index {} out of bounds (len {})",
                                idx,
                                items.len()
                            );
                            std::process::exit(1);
                        }
                    }
                    Value::Str(s) => {
                        let chars: Vec<char> = s.chars().collect();
                        if idx < chars.len() {
                            Value::Int(chars[idx] as i64)
                        } else {
                            Value::Null
                        }
                    }
                    _ => Value::Null,
                }
            }

            Expr::Cast { expr, to } => {
                let val = self.eval_expr(expr);
                match (val, to) {
                    (Value::Int(n), Type::Float) => Value::Float(n as f64),
                    (Value::Float(f), Type::Int) => Value::Int(f as i64),
                    (Value::Int(n), Type::Bool) => Value::Bool(n != 0),
                    (Value::Bool(b), Type::Int) => Value::Int(b as i64),
                    (v, _) => v,
                }
            }

            Expr::StrLen(inner) => match self.eval_expr(inner) {
                Value::Str(s) => Value::Int(s.len() as i64),
                _ => Value::Int(0),
            },

            Expr::StrConcat(a, b) => {
                let sa = match self.eval_expr(a) {
                    Value::Str(s) => s,
                    v => format!("{}", v),
                };
                let sb = match self.eval_expr(b) {
                    Value::Str(s) => s,
                    v => format!("{}", v),
                };
                Value::Str(sa + &sb)
            }

            Expr::Min(a, b) => {
                let va = self.eval_expr(a);
                let vb = self.eval_expr(b);
                match (va, vb) {
                    (Value::Int(x), Value::Int(y)) => Value::Int(x.min(y)),
                    (Value::Float(x), Value::Float(y)) => Value::Float(x.min(y)),
                    _ => Value::Null,
                }
            }

            Expr::Max(a, b) => {
                let va = self.eval_expr(a);
                let vb = self.eval_expr(b);
                match (va, vb) {
                    (Value::Int(x), Value::Int(y)) => Value::Int(x.max(y)),
                    (Value::Float(x), Value::Float(y)) => Value::Float(x.max(y)),
                    _ => Value::Null,
                }
            }

            Expr::Abs(inner) => match self.eval_expr(inner) {
                Value::Int(n) => Value::Int(n.abs()),
                Value::Float(f) => Value::Float(f.abs()),
                v => v,
            },

            _ => Value::Void,
        }
    }

    fn apply_binop(&self, left: &Value, op: &BinOp, right: &Value) -> Value {
        match (left, right) {
            (Value::Int(a), Value::Int(b)) => match op {
                BinOp::Add => Value::Int(a.wrapping_add(*b)),
                BinOp::Sub => Value::Int(a.wrapping_sub(*b)),
                BinOp::Mul => Value::Int(a.wrapping_mul(*b)),
                BinOp::Div => {
                    if *b == 0 {
                        eprintln!("Error: division by zero");
                        std::process::exit(1);
                    } else {
                        Value::Int(a / b)
                    }
                }
                BinOp::Mod => Value::Int(a % b),
                BinOp::Eq => Value::Bool(a == b),
                BinOp::Neq => Value::Bool(a != b),
                BinOp::Lt => Value::Bool(a < b),
                BinOp::Gt => Value::Bool(a > b),
                BinOp::Le => Value::Bool(a <= b),
                BinOp::Ge => Value::Bool(a >= b),
                BinOp::BitAnd => Value::Int(a & b),
                BinOp::BitOr => Value::Int(a | b),
                BinOp::BitXor => Value::Int(a ^ b),
                BinOp::Shl => Value::Int(a << b),
                BinOp::Shr => Value::Int(a >> b),
                _ => Value::Int(0),
            },
            (Value::Float(a), Value::Float(b)) => match op {
                BinOp::Add => Value::Float(a + b),
                BinOp::Sub => Value::Float(a - b),
                BinOp::Mul => Value::Float(a * b),
                BinOp::Div => Value::Float(a / b),
                BinOp::Eq => Value::Bool((a - b).abs() < f64::EPSILON),
                BinOp::Neq => Value::Bool((a - b).abs() >= f64::EPSILON),
                BinOp::Lt => Value::Bool(a < b),
                BinOp::Gt => Value::Bool(a > b),
                BinOp::Le => Value::Bool(a <= b),
                BinOp::Ge => Value::Bool(a >= b),
                _ => Value::Float(0.0),
            },
            (Value::Int(a), Value::Float(b)) => {
                self.apply_binop(&Value::Float(*a as f64), op, right)
            }
            (Value::Float(_), Value::Int(b)) => {
                self.apply_binop(left, op, &Value::Float(*b as f64))
            }
            (Value::Str(a), Value::Str(b)) => match op {
                BinOp::Add => Value::Str(a.clone() + b),
                BinOp::Eq => Value::Bool(a == b),
                BinOp::Neq => Value::Bool(a != b),
                BinOp::Lt => Value::Bool(a < b),
                BinOp::Gt => Value::Bool(a > b),
                _ => Value::Bool(false),
            },
            (Value::Bool(a), Value::Bool(b)) => match op {
                BinOp::And | BinOp::BitAnd => Value::Bool(*a && *b),
                BinOp::Or | BinOp::BitOr => Value::Bool(*a || *b),
                BinOp::Eq => Value::Bool(a == b),
                BinOp::Neq => Value::Bool(a != b),
                _ => Value::Bool(false),
            },
            _ => Value::Null,
        }
    }
}

fn is_truthy(val: &Value) -> bool {
    match val {
        Value::Bool(b) => *b,
        Value::Int(n) => *n != 0,
        Value::Float(f) => *f != 0.0,
        Value::Str(s) => !s.is_empty(),
        Value::Null => false,
        Value::Array(a) => !a.is_empty(),
        Value::Void => false,
    }
}
