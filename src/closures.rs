/// Closure capture analysis and environment struct generation.
///
/// When a closure captures variables from its enclosing scope,
/// we need to:
/// 1. Collect all free variables (used but not declared inside the closure)
/// 2. Generate an environment struct containing pointers to those variables
/// 3. Pass the environment as a hidden first argument to the closure function
/// 4. Rewrite variable accesses inside the closure to load from the environment
///
/// Example:
///   set x = 10
///   set f = |y| x + y   ← x is captured
///
/// Becomes internally:
///   struct __env_0 { x: ptr }
///   task __closure_0(env: __env_0, y: int) -> int {
///       return *env.x + y
///   }
///   set __env = __env_0 { x: &x }
///   set f = __closure_0  (called as f(__env, y))
use crate::ast::*;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone)]
pub struct ClosureInfo {
    /// Name of the generated closure function
    pub fn_name: String,
    /// Name of the generated environment struct
    pub env_struct_name: String,
    /// Captured variable names and their types
    pub captures: Vec<(String, Type)>,
}

/// Analyze a closure expression and return its capture info.
pub fn analyze_closure(
    params: &[String],
    body: &Expr,
    enclosing_scope: &HashMap<String, Type>,
) -> ClosureInfo {
    let mut free_vars: HashSet<String> = HashSet::new();
    let param_set: HashSet<String> = params.iter().cloned().collect();

    collect_free_vars_expr(body, &param_set, &mut free_vars);

    let captures: Vec<(String, Type)> = free_vars
        .iter()
        .filter_map(|name| {
            enclosing_scope
                .get(name)
                .map(|ty| (name.clone(), ty.clone()))
        })
        .collect();

    static COUNTER: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let id = COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

    ClosureInfo {
        fn_name: format!("__closure_{}", id),
        env_struct_name: format!("__env_{}", id),
        captures,
    }
}

fn collect_free_vars_expr(expr: &Expr, bound: &HashSet<String>, free: &mut HashSet<String>) {
    match expr {
        Expr::Identifier(name) => {
            if !bound.contains(name) {
                free.insert(name.clone());
            }
        }
        Expr::BinaryOp { left, right, .. } => {
            collect_free_vars_expr(left, bound, free);
            collect_free_vars_expr(right, bound, free);
        }
        Expr::UnaryOp { operand, .. } => collect_free_vars_expr(operand, bound, free),
        Expr::Call { func, args } => {
            collect_free_vars_expr(func, bound, free);
            for a in args {
                collect_free_vars_expr(a, bound, free);
            }
        }
        Expr::Closure { params, body } => {
            let mut inner_bound = bound.clone();
            for p in params {
                inner_bound.insert(p.clone());
            }
            collect_free_vars_expr(body, &inner_bound, free);
        }
        Expr::Index { array, index } => {
            collect_free_vars_expr(array, bound, free);
            collect_free_vars_expr(index, bound, free);
        }
        Expr::FieldAccess { object, .. } => collect_free_vars_expr(object, bound, free),
        _ => {}
    }
}

/// Rewrite a closure body to load captured variables from the environment struct.
pub fn rewrite_closure_body(expr: &Expr, captures: &[(String, Type)], env_param: &str) -> Expr {
    let captured_names: HashSet<String> = captures.iter().map(|(n, _)| n.clone()).collect();
    rewrite_expr_captures(expr, &captured_names, env_param)
}

fn rewrite_expr_captures(expr: &Expr, captures: &HashSet<String>, env_param: &str) -> Expr {
    match expr {
        Expr::Identifier(name) if captures.contains(name) => {
            // Replace x with (*env.x) — load from environment
            Expr::Deref(Box::new(Expr::FieldAccess {
                object: Box::new(Expr::Identifier(env_param.to_string())),
                field: name.clone(),
            }))
        }
        Expr::BinaryOp { left, op, right } => Expr::BinaryOp {
            left: Box::new(rewrite_expr_captures(left, captures, env_param)),
            op: op.clone(),
            right: Box::new(rewrite_expr_captures(right, captures, env_param)),
        },
        Expr::UnaryOp { op, operand } => Expr::UnaryOp {
            op: op.clone(),
            operand: Box::new(rewrite_expr_captures(operand, captures, env_param)),
        },
        Expr::Call { func, args } => Expr::Call {
            func: Box::new(rewrite_expr_captures(func, captures, env_param)),
            args: args
                .iter()
                .map(|a| rewrite_expr_captures(a, captures, env_param))
                .collect(),
        },
        other => other.clone(),
    }
}

/// Generate the struct declaration and task declaration for a capturing closure.
/// Returns (StructDecl, TaskDecl) to be inserted into the program.
pub fn generate_closure_stmts(info: &ClosureInfo, params: &[String], body: &Expr) -> Vec<Stmt> {
    let mut stmts = Vec::new();

    // struct __env_N { captured_var1: ptr, captured_var2: ptr, ... }
    if !info.captures.is_empty() {
        let fields: Vec<(String, Type)> = info
            .captures
            .iter()
            .map(|(name, _)| (name.clone(), Type::Ptr))
            .collect();
        stmts.push(Stmt::StructDecl {
            name: info.env_struct_name.clone(),
            type_params: Vec::new(),
            fields,
        });
    }

    // task __closure_N(env: __env_N, param1: int, ...) -> int { rewritten_body }
    let captured_names: HashSet<String> = info.captures.iter().map(|(n, _)| n.clone()).collect();
    let rewritten_body = rewrite_expr_captures(body, &captured_names, "__env");

    let mut task_params: Vec<(String, Type)> = Vec::new();
    if !info.captures.is_empty() {
        task_params.push((
            "__env".to_string(),
            Type::Struct(info.env_struct_name.clone()),
        ));
    }
    for p in params {
        task_params.push((p.clone(), Type::Int)); // default param type
    }

    stmts.push(Stmt::TaskDecl {
        name: info.fn_name.clone(),
        type_params: Vec::new(),
        params: task_params,
        return_type: Type::Int,
        body: Block {
            statements: Vec::new(),
            tail_expr: Some(rewritten_body),
        },
        is_inline: true,
        is_async: false,
    });

    stmts
}
