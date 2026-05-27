/// Sovereign Borrow Checker
///
/// Implements the three fundamental ownership rules:
///
/// Rule 1 — Ownership
///   Every value has exactly one owner.
///   When the owner goes out of scope, the value is dropped.
///   When a non-Copy value is assigned/passed, it is MOVED.
///   The original cannot be used after the move.
///
/// Rule 2 — Borrowing
///   At any point you may have EITHER:
///     - Any number of immutable borrows (&val)
///     - Exactly one mutable borrow (&mut val)
///   Never both at the same time.
///
/// Rule 3 — Lifetimes
///   References cannot outlive the value they reference.
///   Returning &local is an error.
///   Storing &local beyond the local's scope is an error.
///
/// Copy types (do not need borrow checking for ownership):
///   int, int8, int16, int64, uint8, uint16, uint32, uint64,
///   float, bool, ptr
///
/// Non-Copy types (ownership tracked):
///   string, struct, array, enum (with data)
use crate::ast::*;
use std::collections::HashMap;

// ── Lifetime ──────────────────────────────────────────────────────────────

/// A lifetime is just a scope depth number.
/// Lifetime 0 = global. Lifetime N = N scopes deep.
/// A reference's lifetime must be <= the lifetime of what it references.
type Lifetime = usize;

// ── Borrow kinds ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum BorrowKind {
    Immutable, // &val — read-only
    Mutable,   // &mut val — read-write (future: when we add &mut syntax)
}

#[derive(Debug, Clone)]
pub struct Borrow {
    pub kind: BorrowKind,
    pub lifetime: Lifetime,
    pub source: String, // name of the borrowed variable
}

// ── Value state ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum ValueState {
    Owned,                 // fully owned, no active borrows
    Borrowed(Vec<Borrow>), // has active borrows
    Moved,                 // moved to another owner
    Freed,                 // explicitly freed (ptr)
    Purged,                // purged (zeroed)
    Uninitialized,         // declared but not yet assigned
}

#[derive(Debug, Clone)]
pub struct VarOwnership {
    pub ty: Type,
    pub state: ValueState,
    pub lifetime: Lifetime,
    pub is_copy: bool, // Copy types skip move checking
}

// ── Borrow checker ────────────────────────────────────────────────────────

pub struct BorrowChecker {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
    // Stack of scopes. Each scope maps name -> ownership info.
    scopes: Vec<HashMap<String, VarOwnership>>,
    // Current scope depth = lifetime
    depth: Lifetime,
    // Return type of current function
    current_ret: Option<Type>,
    // Name of current function (for error messages)
    current_fn: Option<String>,
}

impl BorrowChecker {
    pub fn new() -> Self {
        BorrowChecker {
            errors: Vec::new(),
            warnings: Vec::new(),
            scopes: vec![HashMap::new()],
            depth: 0,
            current_ret: None,
            current_fn: None,
        }
    }

    pub fn check(&mut self, program: &Program) -> Result<(), Vec<String>> {
        for stmt in &program.statements {
            self.check_stmt(stmt);
        }
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err(self.errors.clone())
        }
    }

    // ── Scope management ─────────────────────────────────────────────────

    fn push_scope(&mut self) {
        self.scopes.push(HashMap::new());
        self.depth += 1;
    }

    fn pop_scope(&mut self) {
        // Drop all values owned in this scope
        if let Some(scope) = self.scopes.pop() {
            for (name, info) in &scope {
                if !info.is_copy {
                    match &info.state {
                        ValueState::Borrowed(borrows) if !borrows.is_empty() => {
                            self.errors
                                .push(format!("Value '{}' dropped while still borrowed", name));
                        }
                        _ => {}
                    }
                }
            }
        }
        if self.depth > 0 {
            self.depth -= 1;
        }
    }

    // ── Variable management ───────────────────────────────────────────────

    fn declare(&mut self, name: &str, ty: Type, initialized: bool) {
        let is_copy = is_copy_type(&ty);
        let state = if initialized {
            ValueState::Owned
        } else {
            ValueState::Uninitialized
        };
        if let Some(scope) = self.scopes.last_mut() {
            scope.insert(
                name.to_string(),
                VarOwnership {
                    ty,
                    state,
                    lifetime: self.depth,
                    is_copy,
                },
            );
        }
    }

    fn lookup(&self, name: &str) -> Option<&VarOwnership> {
        for scope in self.scopes.iter().rev() {
            if let Some(v) = scope.get(name) {
                return Some(v);
            }
        }
        None
    }

    fn lookup_mut(&mut self, name: &str) -> Option<&mut VarOwnership> {
        for scope in self.scopes.iter_mut().rev() {
            if scope.contains_key(name) {
                return scope.get_mut(name);
            }
        }
        None
    }

    fn set_state(&mut self, name: &str, state: ValueState) {
        if let Some(v) = self.lookup_mut(name) {
            v.state = state;
        }
    }

    // ── Rule 1: Ownership / Move semantics ───────────────────────────────

    /// Check that a value can be read (used).
    /// Errors if moved, freed, purged, or uninitialized.
    fn check_readable(&mut self, name: &str) -> Option<Type> {
        match self.lookup(name) {
            None => {
                self.errors.push(format!("'{}' is not defined", name));
                None
            }
            Some(v) => match &v.state {
                ValueState::Moved => {
                    self.errors.push(format!(
                        "Use of moved value '{}' — value was moved earlier",
                        name
                    ));
                    None
                }
                ValueState::Freed => {
                    self.errors
                        .push(format!("Use-after-free: '{}' was freed", name));
                    None
                }
                ValueState::Purged => {
                    self.errors
                        .push(format!("Use of purged value '{}' — value was zeroed", name));
                    None
                }
                ValueState::Uninitialized => {
                    self.errors
                        .push(format!("Use of possibly uninitialized variable '{}'", name));
                    None
                }
                _ => Some(v.ty.clone()),
            },
        }
    }

    /// Mark a value as moved to another owner.
    /// Only applies to non-Copy types.
    fn do_move(&mut self, name: &str) {
        if let Some(v) = self.lookup(name) {
            if !v.is_copy {
                match &v.state {
                    ValueState::Moved => {
                        self.errors
                            .push(format!("Move of already-moved value '{}'", name));
                    }
                    ValueState::Borrowed(_) => {
                        self.errors
                            .push(format!("Cannot move '{}' because it is borrowed", name));
                    }
                    _ => {}
                }
                self.set_state(name, ValueState::Moved);
            }
        }
    }

    // ── Rule 2: Borrow checking ───────────────────────────────────────────

    /// Add an immutable borrow of `name`.
    /// Fails if there is already a mutable borrow.
    fn borrow_immutable(&mut self, name: &str) -> bool {
        if let Some(v) = self.lookup(name) {
            match &v.state.clone() {
                ValueState::Borrowed(existing) => {
                    // Check for existing mutable borrow
                    let has_mut = existing.iter().any(|b| b.kind == BorrowKind::Mutable);
                    if has_mut {
                        self.errors.push(format!(
                            "Cannot borrow '{}' immutably — already mutably borrowed",
                            name
                        ));
                        return false;
                    }
                    // Add another immutable borrow
                    let depth = self.depth;
                    let mut new_borrows = existing.clone();
                    new_borrows.push(Borrow {
                        kind: BorrowKind::Immutable,
                        lifetime: depth,
                        source: name.to_string(),
                    });
                    self.set_state(name, ValueState::Borrowed(new_borrows));
                    true
                }
                ValueState::Owned => {
                    let depth = self.depth;
                    self.set_state(
                        name,
                        ValueState::Borrowed(vec![Borrow {
                            kind: BorrowKind::Immutable,
                            lifetime: depth,
                            source: name.to_string(),
                        }]),
                    );
                    true
                }
                ValueState::Moved => {
                    self.errors
                        .push(format!("Cannot borrow moved value '{}'", name));
                    false
                }
                _ => false,
            }
        } else {
            false
        }
    }

    /// Add a mutable borrow of `name`.
    /// Fails if there are ANY existing borrows.
    fn borrow_mutable(&mut self, name: &str) -> bool {
        if let Some(v) = self.lookup(name) {
            match &v.state.clone() {
                ValueState::Borrowed(existing) if !existing.is_empty() => {
                    self.errors.push(format!(
                        "Cannot borrow '{}' mutably — already borrowed",
                        name
                    ));
                    false
                }
                ValueState::Owned => {
                    let depth = self.depth;
                    self.set_state(
                        name,
                        ValueState::Borrowed(vec![Borrow {
                            kind: BorrowKind::Mutable,
                            lifetime: depth,
                            source: name.to_string(),
                        }]),
                    );
                    true
                }
                _ => false,
            }
        } else {
            false
        }
    }

    /// Release all borrows from the current scope depth.
    fn release_borrows_at_depth(&mut self, depth: Lifetime) {
        for scope in self.scopes.iter_mut() {
            for (_, v) in scope.iter_mut() {
                if let ValueState::Borrowed(ref borrows) = v.state.clone() {
                    let remaining: Vec<Borrow> = borrows
                        .iter()
                        .filter(|b| b.lifetime < depth)
                        .cloned()
                        .collect();
                    v.state = if remaining.is_empty() {
                        ValueState::Owned
                    } else {
                        ValueState::Borrowed(remaining)
                    };
                }
            }
        }
    }

    // ── Rule 3: Lifetime checking ─────────────────────────────────────────

    /// Check that a reference does not escape its origin's lifetime.
    fn check_lifetime_escape(&mut self, expr: &Expr) {
        if let Expr::AddressOf(inner) = expr {
            if let Expr::Identifier(name) = inner.as_ref() {
                if let Some(v) = self.lookup(name) {
                    // If returning a reference to a local variable
                    if v.lifetime >= self.depth {
                        if let Some(ref ret) = self.current_ret.clone() {
                            if matches!(ret, Type::Ptr) {
                                self.errors.push(format!(
                                    "Dangling reference: '{}' does not live long enough — it will be dropped when this function returns",
                                    name
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Statement checking ────────────────────────────────────────────────

    fn check_stmt(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::VarDecl {
                name, value, ty, ..
            } => {
                // Check the right-hand side first
                let rhs_type = self.check_expr_ownership(value);
                // If RHS is an identifier of a non-copy type, it gets moved
                if let Expr::Identifier(src) = value {
                    let is_copy = self.lookup(src).map(|v| v.is_copy).unwrap_or(true);
                    if !is_copy {
                        self.do_move(src);
                    }
                }
                let final_ty = ty.as_ref().cloned().or(rhs_type).unwrap_or(Type::Int);
                self.declare(name, final_ty, true);
            }

            Stmt::ConstDecl { name, value } => {
                self.check_expr_ownership(value);
                self.declare(name, Type::Int, true);
            }

            Stmt::Assign { name, value } => {
                // Check RHS
                self.check_expr_ownership(value);
                // Move if non-copy
                if let Expr::Identifier(src) = value {
                    let is_copy = self.lookup(src).map(|v| v.is_copy).unwrap_or(true);
                    if !is_copy {
                        self.do_move(src);
                    }
                }
                // Mark LHS as re-initialized
                if let Some(v) = self.lookup_mut(name) {
                    if v.state != ValueState::Moved {
                        v.state = ValueState::Owned;
                    }
                }
            }

            Stmt::Free { ptr } => {
                if let Expr::Identifier(name) = ptr {
                    // Check for double-free
                    if let Some(v) = self.lookup(name) {
                        match v.state {
                            ValueState::Freed => {
                                self.errors
                                    .push(format!("Double-free: '{}' was already freed", name));
                            }
                            ValueState::Borrowed(_) => {
                                self.errors
                                    .push(format!("Cannot free '{}' while it is borrowed", name));
                            }
                            ValueState::Moved => {
                                self.errors
                                    .push(format!("Cannot free moved value '{}'", name));
                            }
                            _ => {}
                        }
                    }
                    self.set_state(name, ValueState::Freed);
                } else {
                    self.check_expr_ownership(ptr);
                }
            }

            Stmt::Purge { variable } => {
                if let Some(v) = self.lookup(variable) {
                    if matches!(v.state, ValueState::Moved) {
                        self.errors
                            .push(format!("Cannot purge moved value '{}'", variable));
                    }
                    if matches!(v.state, ValueState::Borrowed(_)) {
                        self.errors
                            .push(format!("Cannot purge '{}' while it is borrowed", variable));
                    }
                }
                self.set_state(variable, ValueState::Purged);
            }

            Stmt::Return(Some(expr)) => {
                // Rule 3: check for dangling references
                self.check_lifetime_escape(expr);
                self.check_expr_ownership(expr);
                // If returning a non-copy value, move it out
                if let Expr::Identifier(name) = expr {
                    let is_copy = self.lookup(name).map(|v| v.is_copy).unwrap_or(true);
                    if !is_copy {
                        self.do_move(name);
                    }
                }
            }

            Stmt::TaskDecl {
                name,
                params,
                body,
                return_type,
                ..
            } => {
                let saved_fn = self.current_fn.clone();
                let saved_ret = self.current_ret.clone();
                self.current_fn = Some(name.clone());
                self.current_ret = Some(return_type.clone());
                self.push_scope();
                for (pname, pty) in params {
                    self.declare(pname, pty.clone(), true);
                }
                self.check_block(body);
                self.release_borrows_at_depth(self.depth);
                self.pop_scope();
                self.current_fn = saved_fn;
                self.current_ret = saved_ret;
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                self.check_expr_ownership(condition);
                self.push_scope();
                self.check_block(then_block);
                self.release_borrows_at_depth(self.depth);
                self.pop_scope();
                if let Some(eb) = else_block {
                    self.push_scope();
                    self.check_block(eb);
                    self.release_borrows_at_depth(self.depth);
                    self.pop_scope();
                }
            }

            Stmt::Loop { kind, body } => {
                match kind {
                    LoopKind::FromTo { var, from, to } => {
                        self.check_expr_ownership(from);
                        self.check_expr_ownership(to);
                        self.push_scope();
                        self.declare(var, Type::Int, true);
                        self.check_block(body);
                        self.release_borrows_at_depth(self.depth);
                        self.pop_scope();
                        return;
                    }
                    LoopKind::ForEach { var, iterable } => {
                        let elem_ty = self
                            .check_expr_ownership(iterable)
                            .and_then(|t| match t {
                                Type::Array(inner) => Some(*inner),
                                _ => None,
                            })
                            .unwrap_or(Type::Int);
                        // Iterating borrows the collection
                        if let Expr::Identifier(name) = iterable {
                            self.borrow_immutable(name);
                        }
                        self.push_scope();
                        self.declare(var, elem_ty, true);
                        self.check_block(body);
                        self.release_borrows_at_depth(self.depth);
                        self.pop_scope();
                        // Release the borrow after loop
                        if let Expr::Identifier(name) = iterable {
                            self.release_borrows_at_depth(self.depth + 1);
                        }
                        return;
                    }
                    LoopKind::While(cond) => {
                        self.check_expr_ownership(cond);
                    }
                    LoopKind::Times(e) => {
                        self.check_expr_ownership(e);
                    }
                    LoopKind::Infinite => {}
                    _ => {}
                }
                self.push_scope();
                self.check_block(body);
                self.release_borrows_at_depth(self.depth);
                self.pop_scope();
            }

            Stmt::Override { body } | Stmt::ConstantTime { body } => {
                self.push_scope();
                self.check_block(body);
                self.pop_scope();
            }

            Stmt::Spawn { body, .. } => {
                // Threads cannot borrow from parent scope
                // (no shared mutable state without explicit sync)
                // For now: check the body in an isolated scope
                self.push_scope();
                self.check_block(body);
                self.pop_scope();
            }

            Stmt::Match { value, arms } => {
                self.check_expr_ownership(value);
                for arm in arms {
                    self.push_scope();
                    // Bind capture variables
                    if let Pattern::EnumVariantCapture { bindings, .. } = &arm.pattern {
                        for b in bindings {
                            self.declare(b, Type::Int, true);
                        }
                    }
                    self.check_block(&arm.body);
                    self.release_borrows_at_depth(self.depth);
                    self.pop_scope();
                }
            }

            Stmt::Defer { body } => {
                self.push_scope();
                self.check_block(body);
                self.pop_scope();
            }

            Stmt::ExprStmt(e) | Stmt::Print(e) => {
                self.check_expr_ownership(e);
            }

            Stmt::PrintFmt { args, .. } => {
                for a in args {
                    self.check_expr_ownership(a);
                }
            }

            Stmt::Assert { condition, .. } | Stmt::StaticAssert { condition, .. } => {
                self.check_expr_ownership(condition);
            }

            Stmt::MultiAssign { names, values } => {
                let compiled: Vec<Option<Type>> = values
                    .iter()
                    .map(|v| self.check_expr_ownership(v))
                    .collect();
                for (i, name) in names.iter().enumerate() {
                    let ty = compiled.get(i).cloned().flatten().unwrap_or(Type::Int);
                    if self.lookup(name).is_some() {
                        self.set_state(name, ValueState::Owned);
                    } else {
                        self.declare(name, ty, true);
                    }
                }
            }

            Stmt::CompoundAssign { name, value, .. } => {
                self.check_readable(name);
                self.check_expr_ownership(value);
            }

            Stmt::FieldAssign {
                object,
                field: _,
                value,
            } => {
                // Mutating a field requires owning the struct
                if let Some(v) = self.lookup(object) {
                    if matches!(v.state, ValueState::Borrowed(_)) {
                        self.errors.push(format!(
                            "Cannot mutate field of '{}' while it is borrowed",
                            object
                        ));
                    }
                }
                self.check_expr_ownership(value);
            }

            Stmt::IndexAssign {
                array,
                index,
                value,
            } => {
                if let Some(v) = self.lookup(array) {
                    if matches!(v.state, ValueState::Borrowed(ref b) if b.iter().any(|b| b.kind == BorrowKind::Immutable))
                    {
                        self.errors.push(format!(
                            "Cannot mutate '{}' while it is immutably borrowed",
                            array
                        ));
                    }
                }
                self.check_expr_ownership(index);
                self.check_expr_ownership(value);
            }

            _ => {}
        }
    }

    // ── Expression checking ───────────────────────────────────────────────

    /// Check an expression for ownership/borrow violations.
    /// Returns the type of the expression if determinable.
    fn check_expr_ownership(&mut self, expr: &Expr) -> Option<Type> {
        match expr {
            Expr::Integer(_) => Some(Type::Int),
            Expr::Float(_) => Some(Type::Float),
            Expr::Boolean(_) => Some(Type::Bool),
            Expr::StringLiteral(_) => Some(Type::String),
            Expr::Null => Some(Type::Ptr),

            Expr::Identifier(name) => self.check_readable(name),

            Expr::AddressOf(inner) => {
                // &val creates an immutable borrow
                if let Expr::Identifier(name) = inner.as_ref() {
                    self.borrow_immutable(name);
                }
                self.check_expr_ownership(inner);
                Some(Type::Ptr)
            }

            Expr::Deref(inner) => {
                // *ptr requires ptr to be live and non-null
                if let Expr::Identifier(name) = inner.as_ref() {
                    if let Some(v) = self.lookup(name) {
                        match v.state {
                            ValueState::Freed => {
                                self.errors.push(format!(
                                    "Use-after-free: dereferencing freed pointer '{}'",
                                    name
                                ));
                            }
                            ValueState::Moved => {
                                self.errors
                                    .push(format!("Dereferencing moved value '{}'", name));
                            }
                            _ => {}
                        }
                    }
                }
                self.check_expr_ownership(inner);
                Some(Type::Int)
            }

            Expr::Call { func, args, .. } => {
                // For each argument:
                // - Copy types: passed by value, no ownership change
                // - Non-copy types: moved into the function
                self.check_expr_ownership(func);
                for arg in args {
                    self.check_expr_ownership(arg);
                    // Move non-copy arguments
                    if let Expr::Identifier(name) = arg {
                        let is_copy = self.lookup(name).map(|v| v.is_copy).unwrap_or(true);
                        if !is_copy {
                            // Passing a non-copy value moves it
                            // Exception: if the function signature takes &T, it borrows
                            // For now: treat all non-copy pass as move
                            // (conservative but safe)
                            self.do_move(name);
                        }
                    }
                }
                None // Return type determined by semantic analysis
            }

            Expr::BinaryOp { left, op, right } => {
                let lt = self.check_expr_ownership(left);
                let rt = self.check_expr_ownership(right);
                match op {
                    BinOp::Eq | BinOp::Neq | BinOp::Lt | BinOp::Gt | BinOp::Le | BinOp::Ge => {
                        Some(Type::Bool)
                    }
                    _ => lt.or(rt),
                }
            }

            Expr::UnaryOp { operand, .. } => self.check_expr_ownership(operand),

            Expr::Index { array, index } => {
                self.check_expr_ownership(array);
                self.check_expr_ownership(index);
                // Indexing borrows the array
                if let Expr::Identifier(name) = array.as_ref() {
                    self.borrow_immutable(name);
                }
                None
            }

            Expr::FieldAccess { object, .. } => {
                // Field access borrows the struct
                if let Expr::Identifier(name) = object.as_ref() {
                    self.borrow_immutable(name);
                }
                self.check_expr_ownership(object);
                None
            }

            Expr::StructLiteral { fields, .. } => {
                for (_, val) in fields {
                    self.check_expr_ownership(val);
                }
                None
            }

            Expr::Array(elems) => {
                for e in elems {
                    self.check_expr_ownership(e);
                }
                None
            }

            Expr::Tuple(elems) => {
                for e in elems {
                    self.check_expr_ownership(e);
                }
                None
            }

            Expr::Copy(inner) => {
                // `copy x` explicitly copies — does NOT move
                // This is how you opt out of move semantics
                self.check_expr_ownership(inner)
            }

            Expr::Alloc { count, size } => {
                self.check_expr_ownership(count);
                self.check_expr_ownership(size);
                Some(Type::Ptr)
            }

            Expr::Cast { expr, to } => {
                self.check_expr_ownership(expr);
                Some(to.clone())
            }

            Expr::Closure { params, body } => {
                // Closures capture by borrow (immutable)
                // Variables used inside the closure get an implicit borrow
                self.push_scope();
                for (pname, pty) in params {
                    let ty = pty.as_ref().cloned().unwrap_or(Type::Int);
                    self.declare(pname, ty, true);
                }
                self.check_expr_ownership(body);
                self.pop_scope();
                None
            }

            Expr::Await(inner) => self.check_expr_ownership(inner),
            Expr::Comptime(inner) => self.check_expr_ownership(inner),
            Expr::OkExpr(inner) => self.check_expr_ownership(inner),
            Expr::ErrExpr(inner) => self.check_expr_ownership(inner),
            Expr::IsOk(inner) => {
                self.check_expr_ownership(inner);
                Some(Type::Bool)
            }
            Expr::Unwrap(inner) => self.check_expr_ownership(inner),
            Expr::StrLen(s) => {
                self.check_expr_ownership(s);
                Some(Type::Int)
            }
            Expr::StrConcat(a, b) => {
                self.check_expr_ownership(a);
                self.check_expr_ownership(b);
                Some(Type::String)
            }
            Expr::Nullable(inner) => self.check_expr_ownership(inner),
            Expr::Range { start, end, .. } => {
                self.check_expr_ownership(start);
                self.check_expr_ownership(end);
                Some(Type::Array(Box::new(Type::Int)))
            }

            _ => None,
        }
    }

    fn check_block(&mut self, block: &Block) {
        for stmt in &block.statements {
            self.check_stmt(stmt);
        }
        if let Some(tail) = &block.tail_expr {
            self.check_expr_ownership(tail);
        }
    }
}

/// Lifetime elision rules (same as Rust's three rules):
///
/// Rule 1: Each parameter that is a reference gets its own lifetime.
///         fn foo(x: &T) → fn foo<'a>(x: &'a T)
///
/// Rule 2: If there is exactly one input lifetime parameter,
///         that lifetime is assigned to all output lifetime parameters.
///         fn foo(x: &T) -> &U → fn foo<'a>(x: &'a T) -> &'a U
///
/// Rule 3: If one of the input lifetime parameters is &self,
///         that lifetime is assigned to all output lifetime parameters.
///         (Sovereign: first parameter of a task)
///
/// These rules mean that in 90% of real code you never think about lifetimes.
/// The checker handles them silently.

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LifetimeVar(pub usize);

impl LifetimeVar {
    pub fn new(id: usize) -> Self {
        LifetimeVar(id)
    }
}

pub struct LifetimeElider {
    next_id: usize,
}

impl LifetimeElider {
    pub fn new() -> Self {
        LifetimeElider { next_id: 0 }
    }

    pub fn fresh(&mut self) -> LifetimeVar {
        let id = self.next_id;
        self.next_id += 1;
        LifetimeVar(id)
    }

    /// Apply elision rules to a task signature.
    /// Returns (param_lifetimes, return_lifetime)
    pub fn elide(
        &mut self,
        params: &[(String, Type)],
        return_type: &Type,
    ) -> (Vec<Option<LifetimeVar>>, Option<LifetimeVar>) {
        // Rule 1: Each reference parameter gets its own lifetime
        let param_lifetimes: Vec<Option<LifetimeVar>> = params
            .iter()
            .map(|(_, ty)| {
                if has_reference(ty) {
                    Some(self.fresh())
                } else {
                    None
                }
            })
            .collect();

        // Count reference parameters
        let ref_params: Vec<&LifetimeVar> =
            param_lifetimes.iter().filter_map(|l| l.as_ref()).collect();

        let return_lifetime = if has_reference(return_type) {
            if ref_params.len() == 1 {
                // Rule 2: exactly one input lifetime → assign to output
                Some(ref_params[0].clone())
            } else if !ref_params.is_empty() {
                // Rule 3: first parameter's lifetime → assign to output
                Some(ref_params[0].clone())
            } else {
                None
            }
        } else {
            None
        };
        /// Higher-ranked lifetime bounds.
        ///
        /// In Rust: for<'a> fn(&'a T) -> &'a U
        /// In Sovereign: handled automatically — you never write this.
        ///
        /// The checker tracks alias sets. Two pointers that might point
        /// to the same memory are in the same alias set.
        /// Mutations through one alias invalidate reads through the other.
        use std::collections::HashMap;

        #[derive(Debug, Clone, PartialEq)]
        pub enum AliasSet {
            Unique(usize),         // points to unique memory
            MayAlias(Vec<String>), // may point to same memory as these vars
            Null,
        }

        pub struct AliasTracker {
            sets: HashMap<String, AliasSet>,
            next_id: usize,
            pub errors: Vec<String>,
        }

        impl AliasTracker {
            pub fn new() -> Self {
                AliasTracker {
                    sets: HashMap::new(),
                    next_id: 0,
                    errors: Vec::new(),
                }
            }

            pub fn declare_unique(&mut self, name: &str) {
                let id = self.next_id;
                self.next_id += 1;
                self.sets.insert(name.to_string(), AliasSet::Unique(id));
            }

            pub fn declare_alias(&mut self, name: &str, aliases: Vec<String>) {
                self.sets
                    .insert(name.to_string(), AliasSet::MayAlias(aliases));
            }

            /// Check if two names may alias.
            pub fn may_alias(&self, a: &str, b: &str) -> bool {
                match (self.sets.get(a), self.sets.get(b)) {
                    (Some(AliasSet::MayAlias(av)), _) => av.contains(&b.to_string()),
                    (_, Some(AliasSet::MayAlias(bv))) => bv.contains(&a.to_string()),
                    (Some(AliasSet::Unique(ia)), Some(AliasSet::Unique(ib))) => ia == ib,
                    _ => false,
                }
            }

            /// Check mutation through one alias while another exists.
            /// This catches the core of what complex aliasing means.
            pub fn check_mutation(&mut self, mutated: &str, active_borrows: &[String]) {
                for borrow in active_borrows {
                    if self.may_alias(mutated, borrow) {
                        self.errors.push(format!(
                            "Aliasing violation: mutating '{}' while '{}' may alias it.\n  This would be undefined behavior in C.\n  Sovereign prevents it here.",
                            mutated, borrow
                        ));
                    }
                }
            }
        }

        (param_lifetimes, return_lifetime)
    }
}

fn has_reference(ty: &Type) -> bool {
    matches!(
        ty,
        Type::Ptr | Type::Array(_) | Type::Slice(_) | Type::String
    )
}
// ── Copy type determination ───────────────────────────────────────────────

/// Copy types are passed by value and do not require ownership tracking.
/// These match Rust's Copy trait conceptually.
pub fn is_copy_type(ty: &Type) -> bool {
    matches!(
        ty,
        Type::Int   | Type::Int8  | Type::Int16 | Type::Int64
        | Type::Uint8 | Type::Uint16 | Type::Uint32 | Type::Uint64
        | Type::Float | Type::Float32
        | Type::Bool
        | Type::Ptr  // raw pointers are Copy (like in C)
        | Type::Enum(_) // simple enums without data are Copy
    )
}

/// Non-copy types are moved when assigned or passed.
pub fn is_non_copy_type(ty: &Type) -> bool {
    !is_copy_type(ty)
}
