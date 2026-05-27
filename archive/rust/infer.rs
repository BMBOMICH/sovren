/// Type inference for Sovereign.
///
/// When types are omitted, this pass fills them in before
/// semantic analysis and codegen.
///
/// This makes Sovereign as concise as Python for common cases:
///
///   task add(a, b) { return a + b }
///   add(3, 7)      ← infers a: int, b: int, returns int
///
///   x = "hello"   ← infers x: string
///   x = 3.14      ← infers x: float
///
/// Algorithm: Hindley-Milner style, simplified for Sovereign's
/// straightforward type system.
use crate::ast::*;
use std::collections::HashMap;

/// A type variable — represents an unknown type to be inferred
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct TypeVar(pub usize);

/// A type constraint: TypeVar must equal Type
#[derive(Debug, Clone)]
pub struct Constraint {
    pub var: TypeVar,
    pub ty: Type,
}

pub struct TypeInferencer {
    next_var: usize,
    // Map from variable name to its inferred type
    pub inferred: HashMap<String, Type>,
    // Map from task name to (param_types, return_type)
    pub task_types: HashMap<String, (Vec<Type>, Type)>,
    errors: Vec<String>,
}

impl TypeInferencer {
    pub fn new() -> Self {
        TypeInferencer {
            next_var: 0,
            inferred: HashMap::new(),
            task_types: HashMap::new(),
            errors: Vec::new(),
        }
    }

    pub fn infer_program(&mut self, program: &mut Program) {
        // Pass 1: collect all explicit types
        for stmt in &program.statements {
            self.collect_types(stmt);
        }

        // Pass 2: infer missing types
        for stmt in &mut program.statements {
            self.infer_stmt(stmt);
        }
    }

    fn fresh_var(&mut self) -> Type {
        let id = self.next_var;
        self.next_var += 1;
        Type::Generic(format!("_t{}", id))
    }

    fn collect_types(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::TaskDecl {
                name,
                params,
                return_type,
                ..
            } => {
                let ptypes: Vec<Type> = params.iter().map(|(_, t)| t.clone()).collect();
                self.task_types
                    .insert(name.clone(), (ptypes, return_type.clone()));
            }
            _ => {}
        }
    }

    fn infer_stmt(&mut self, stmt: &mut Stmt) {
        match stmt {
            Stmt::VarDecl {
                name, ty, value, ..
            } => {
                let inferred = self.infer_expr_type(value);
                if ty.is_none() || matches!(ty, Some(Type::Generic(s)) if s.starts_with("_")) {
                    *ty = Some(inferred.clone());
                    self.inferred.insert(name.clone(), inferred);
                }
            }

            Stmt::TaskDecl {
                name,
                params,
                return_type,
                body,
                ..
            } => {
                // Infer parameter types from usage in body
                for (pname, pty) in params.iter_mut() {
                    if matches!(pty, Type::Generic(s) if s == "_infer") {
                        // Look at how the parameter is used in the body
                        let inferred = self.infer_param_type(pname, body);
                        *pty = inferred;
                    }
                }

                // Infer return type from return statements
                if *return_type == Type::Void {
                    let inferred_ret = self.infer_return_type(body);
                    if inferred_ret != Type::Void {
                        *return_type = inferred_ret;
                    }
                }

                // Update task type info
                let ptypes: Vec<Type> = params.iter().map(|(_, t)| t.clone()).collect();
                self.task_types
                    .insert(name.clone(), (ptypes, return_type.clone()));

                // Infer types in body
                for s in body.statements.iter_mut() {
                    self.infer_stmt(s);
                }
            }

            Stmt::Assign { name, value } => {
                let inferred = self.infer_expr_type(value);
                self.inferred.insert(name.clone(), inferred);
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                for s in then_block.statements.iter_mut() {
                    self.infer_stmt(s);
                }
                if let Some(eb) = else_block {
                    for s in eb.statements.iter_mut() {
                        self.infer_stmt(s);
                    }
                }
            }

            Stmt::Loop { body, .. } => {
                for s in body.statements.iter_mut() {
                    self.infer_stmt(s);
                }
            }

            _ => {}
        }
    }

    fn infer_expr_type(&self, expr: &Expr) -> Type {
        match expr {
            Expr::Integer(_) => Type::Int,
            Expr::Float(_) => Type::Float,
            Expr::Boolean(_) => Type::Bool,
            Expr::StringLiteral(_) => Type::String,
            Expr::Null => Type::Ptr,
            Expr::Identifier(name) => self.inferred.get(name).cloned().unwrap_or(Type::Int),
            Expr::BinaryOp { left, op, right } => {
                let lt = self.infer_expr_type(left);
                let rt = self.infer_expr_type(right);
                match op {
                    BinOp::Eq
                    | BinOp::Neq
                    | BinOp::Lt
                    | BinOp::Gt
                    | BinOp::Le
                    | BinOp::Ge
                    | BinOp::And
                    | BinOp::Or => Type::Bool,
                    _ => {
                        if lt == Type::Float || rt == Type::Float {
                            Type::Float
                        } else {
                            lt
                        }
                    }
                }
            }
            Expr::Call { func, .. } => {
                if let Expr::Identifier(name) = func.as_ref() {
                    self.task_types
                        .get(name)
                        .map(|(_, ret)| ret.clone())
                        .unwrap_or(Type::Int)
                } else {
                    Type::Int
                }
            }
            Expr::Array(elems) => {
                let elem_ty = elems
                    .first()
                    .map(|e| self.infer_expr_type(e))
                    .unwrap_or(Type::Int);
                Type::Array(Box::new(elem_ty))
            }
            Expr::StructLiteral { name, .. } => Type::Struct(name.clone()),
            Expr::Cast { to, .. } => to.clone(),
            Expr::StrLen(_) => Type::Int,
            Expr::StrConcat(_, _) => Type::String,
            _ => Type::Int,
        }
    }

    fn infer_param_type(&self, param_name: &str, body: &Block) -> Type {
        // Look at how the parameter is used
        // If added to an int → int
        // If compared with string → string
        // Default to int
        for stmt in &body.statements {
            if let Some(ty) = self.infer_param_usage(param_name, stmt) {
                return ty;
            }
        }
        Type::Int // safe default
    }

    fn infer_param_usage(&self, name: &str, stmt: &Stmt) -> Option<Type> {
        match stmt {
            Stmt::Return(Some(expr)) => self.infer_param_in_expr(name, expr),
            Stmt::ExprStmt(expr) | Stmt::Print(expr) => self.infer_param_in_expr(name, expr),
            Stmt::VarDecl { value, .. } => self.infer_param_in_expr(name, value),
            _ => None,
        }
    }

    fn infer_param_in_expr(&self, name: &str, expr: &Expr) -> Option<Type> {
        match expr {
            Expr::BinaryOp { left, op, right } => {
                if let Expr::Identifier(n) = left.as_ref() {
                    if n == name {
                        let other_ty = self.infer_expr_type(right);
                        return Some(other_ty);
                    }
                }
                if let Expr::Identifier(n) = right.as_ref() {
                    if n == name {
                        let other_ty = self.infer_expr_type(left);
                        return Some(other_ty);
                    }
                }
                self.infer_param_in_expr(name, left)
                    .or_else(|| self.infer_param_in_expr(name, right))
            }
            Expr::Call { args, .. } => {
                for arg in args {
                    if let Some(ty) = self.infer_param_in_expr(name, arg) {
                        return Some(ty);
                    }
                }
                None
            }
            _ => None,
        }
    }

    fn infer_return_type(&self, body: &Block) -> Type {
        for stmt in &body.statements {
            if let Stmt::Return(Some(expr)) = stmt {
                return self.infer_expr_type(expr);
            }
        }
        if let Some(tail) = &body.tail_expr {
            return self.infer_expr_type(tail);
        }
        Type::Void
    }
}

/// Apply type inference to a program, filling in missing types.
pub fn infer(program: &mut Program) {
    let mut inferencer = TypeInferencer::new();
    inferencer.infer_program(program);
}
