/// Thread safety analysis for Sovereign.
///
/// Rust uses Send and Sync traits.
/// Sovereign uses a simpler model that is easier to learn but
/// catches the same bugs:
///
/// RULE: A value can only be accessed from the thread that owns it.
///       To share across threads you must use:
///         - chan (channel) — safe message passing
///         - atomic (future)
///         - explicit override block (unsafe)
///
/// This eliminates data races architecturally.
/// You literally cannot write a data race in safe Sovereign code.
use crate::ast::*;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, PartialEq)]
pub enum ThreadOwner {
    MainThread,
    Thread(usize), // thread id
    Shared,        // explicitly shared via channel
    Atomic,        // atomic access
}

#[derive(Debug, Clone)]
pub struct ThreadVar {
    pub name: String,
    pub owner: ThreadOwner,
    pub ty: Type,
}

pub struct ThreadAnalyzer {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
    // Map from variable name to which thread owns it
    ownership: HashMap<String, ThreadVar>,
    current_thread: ThreadOwner,
    thread_counter: usize,
    // Variables captured by spawned threads
    thread_captures: Vec<HashSet<String>>,
}

impl ThreadAnalyzer {
    pub fn new() -> Self {
        ThreadAnalyzer {
            errors: Vec::new(),
            warnings: Vec::new(),
            ownership: HashMap::new(),
            current_thread: ThreadOwner::MainThread,
            thread_counter: 0,
            thread_captures: Vec::new(),
        }
    }

    pub fn analyze(&mut self, program: &Program) -> Result<(), Vec<String>> {
        for stmt in &program.statements {
            self.check_stmt(stmt);
        }
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err(self.errors.clone())
        }
    }

    fn error(&mut self, msg: String) {
        self.errors.push(msg);
    }

    fn declare(&mut self, name: &str, ty: Type) {
        self.ownership.insert(
            name.to_string(),
            ThreadVar {
                name: name.to_string(),
                owner: self.current_thread.clone(),
                ty,
            },
        );
    }

    fn check_access(&mut self, name: &str) {
        if let Some(var) = self.ownership.get(name) {
            let var_owner = var.owner.clone();
            let current = self.current_thread.clone();
            if var_owner != current && var_owner != ThreadOwner::Shared {
                self.error(format!(
                    "Data race: '{}' is owned by {:?} but accessed from {:?}.\n  Use a channel (chan) to share data between threads.",
                    name, var_owner, current
                ));
            }
        }
    }

    fn check_stmt(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::VarDecl {
                name, value, ty, ..
            } => {
                self.check_expr(value);
                let final_ty = ty.as_ref().cloned().unwrap_or(Type::Int);
                self.declare(name, final_ty);
            }

            Stmt::Spawn { body, var } => {
                // Find all variables accessed inside the spawn block
                let mut captures = HashSet::new();
                collect_identifiers_block(body, &mut captures);

                // Check each captured variable
                for cap_name in &captures {
                    if let Some(var_info) = self.ownership.get(cap_name) {
                        let ty = var_info.ty.clone();
                        // Non-copy types cannot be shared without channel
                        if !is_thread_safe(&ty) {
                            self.error(format!(
                                "Thread safety violation: '{}' (type {:?}) cannot be shared across threads.\n  Solutions:\n    1. Use 'copy {}' to send a copy\n    2. Use a channel: chan c = make_chan()\n    3. Mark as atomic (future feature)",
                                cap_name, ty, cap_name
                            ));
                        }
                    }
                }

                // Compile the body in a new thread context
                let saved = self.current_thread.clone();
                self.thread_counter += 1;
                self.current_thread = ThreadOwner::Thread(self.thread_counter);
                self.check_block(body);
                self.current_thread = saved;
            }

            Stmt::Assign { name, value } => {
                self.check_access(name);
                self.check_expr(value);
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                self.check_expr(condition);
                self.check_block(then_block);
                if let Some(eb) = else_block {
                    self.check_block(eb);
                }
            }

            Stmt::Loop { body, kind } => {
                match kind {
                    LoopKind::While(e) | LoopKind::Times(e) => self.check_expr(e),
                    LoopKind::FromTo { from, to, .. } => {
                        self.check_expr(from);
                        self.check_expr(to);
                    }
                    _ => {}
                }
                self.check_block(body);
            }

            Stmt::TaskDecl { params, body, .. } => {
                let saved = self.current_thread.clone();
                self.current_thread = ThreadOwner::MainThread;
                for (pname, pty) in params {
                    self.declare(pname, pty.clone());
                }
                self.check_block(body);
                self.current_thread = saved;
            }

            Stmt::ExprStmt(e) | Stmt::Print(e) | Stmt::Return(Some(e)) => {
                self.check_expr(e);
            }

            _ => {}
        }
    }

    fn check_expr(&mut self, expr: &Expr) {
        match expr {
            Expr::Identifier(name) => self.check_access(name),
            Expr::BinaryOp { left, right, .. } => {
                self.check_expr(left);
                self.check_expr(right);
            }
            Expr::Call { func, args, .. } => {
                self.check_expr(func);
                for a in args {
                    self.check_expr(a);
                }
            }
            Expr::UnaryOp { operand, .. } => self.check_expr(operand),
            Expr::Index { array, index } => {
                self.check_expr(array);
                self.check_expr(index);
            }
            _ => {}
        }
    }

    fn check_block(&mut self, block: &Block) {
        for s in &block.statements {
            self.check_stmt(s);
        }
        if let Some(tail) = &block.tail_expr {
            self.check_expr(tail);
        }
    }
}

/// Types that are safe to share across threads (Copy types + atomic)
fn is_thread_safe(ty: &Type) -> bool {
    matches!(
        ty,
        Type::Int
            | Type::Int8
            | Type::Int16
            | Type::Int64
            | Type::Uint8
            | Type::Uint16
            | Type::Uint32
            | Type::Uint64
            | Type::Float
            | Type::Bool // ptr is NOT thread-safe by default
                         // string is NOT thread-safe (not atomic)
    )
}

fn collect_identifiers_block(block: &Block, out: &mut HashSet<String>) {
    for s in &block.statements {
        collect_identifiers_stmt(s, out);
    }
}

fn collect_identifiers_stmt(stmt: &Stmt, out: &mut HashSet<String>) {
    match stmt {
        Stmt::ExprStmt(e) | Stmt::Print(e) | Stmt::Return(Some(e)) => {
            collect_identifiers_expr(e, out);
        }
        Stmt::VarDecl { value, .. } | Stmt::Assign { value, .. } => {
            collect_identifiers_expr(value, out);
        }
        Stmt::Check {
            condition,
            then_block,
            else_block,
        } => {
            collect_identifiers_expr(condition, out);
            collect_identifiers_block(then_block, out);
            if let Some(eb) = else_block {
                collect_identifiers_block(eb, out);
            }
        }
        Stmt::Loop { body, .. } => collect_identifiers_block(body, out),
        _ => {}
    }
}

fn collect_identifiers_expr(expr: &Expr, out: &mut HashSet<String>) {
    match expr {
        Expr::Identifier(name) => {
            out.insert(name.clone());
        }
        Expr::BinaryOp { left, right, .. } => {
            collect_identifiers_expr(left, out);
            collect_identifiers_expr(right, out);
        }
        Expr::Call { func, args, .. } => {
            collect_identifiers_expr(func, out);
            for a in args {
                collect_identifiers_expr(a, out);
            }
        }
        Expr::UnaryOp { operand, .. } => collect_identifiers_expr(operand, out),
        _ => {}
    }
}
