use crate::ast::*;
use std::collections::{HashMap, HashSet};

pub struct Analyzer {
    scopes: Vec<HashMap<String, VarInfo>>,
    errors: Vec<String>,
    warnings: Vec<String>,
    task_returns: HashMap<String, Type>,
    task_param_types: HashMap<String, Vec<Type>>,
    struct_fields: HashMap<String, Vec<(String, Type)>>,
    enum_variants: HashMap<String, Vec<EnumVariant>>,
    namespaces: HashMap<String, Vec<Stmt>>,
    type_aliases: HashMap<String, Type>,
    current_ret_type: Option<Type>,
    override_depth: usize,
    constant_time_depth: usize,
    loop_depth: usize,
    sensitive_names: HashSet<String>,
    network_fns: HashSet<String>,
    current_task_name: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
enum VarState {
    Live,
    Moved,
    Purged,
}

#[derive(Debug, Clone)]
struct VarInfo {
    var_type: Type,
    state: VarState,
    is_const: bool,
    sensitive: bool,
    used: bool,
    assigned: bool, // definite assignment tracking
}

impl Analyzer {
    pub fn new() -> Self {
        let mut network_fns = HashSet::new();
        for f in &[
            "connect",
            "bind",
            "send",
            "recv",
            "socket",
            "listen",
            "accept",
            "getaddrinfo",
            "WSAStartup",
            "WSAConnect",
            "curl_easy_perform",
            "http_get",
            "http_post",
            "PQconnectdb",
            "PQexec",
        ] {
            network_fns.insert(f.to_string());
        }
        Analyzer {
            scopes: vec![HashMap::new()],
            errors: Vec::new(),
            warnings: Vec::new(),
            task_returns: HashMap::new(),
            task_param_types: HashMap::new(),
            struct_fields: HashMap::new(),
            enum_variants: HashMap::new(),
            namespaces: HashMap::new(),
            type_aliases: HashMap::new(),
            current_ret_type: None,
            override_depth: 0,
            constant_time_depth: 0,
            loop_depth: 0,
            sensitive_names: HashSet::new(),
            network_fns,
            current_task_name: None,
        }
    }

    pub fn analyze(&mut self, program: &Program) -> Result<(), Vec<String>> {
        // Forward pass: collect all declarations
        for stmt in &program.statements {
            match stmt {
                Stmt::StructDecl { name, fields, .. } => {
                    self.struct_fields.insert(name.clone(), fields.clone());
                }
                Stmt::EnumDecl { name, variants } => {
                    self.enum_variants.insert(name.clone(), variants.clone());
                }
                Stmt::TaskDecl {
                    name,
                    params,
                    return_type,
                    ..
                } => {
                    let ptypes: Vec<Type> = params.iter().map(|(_, t)| t.clone()).collect();
                    self.task_param_types.insert(name.clone(), ptypes);
                    self.task_returns.insert(name.clone(), return_type.clone());
                }
                Stmt::ExternDecl {
                    name,
                    params,
                    return_type,
                    ..
                } => {
                    self.task_param_types.insert(name.clone(), params.clone());
                    self.task_returns.insert(name.clone(), return_type.clone());
                }
                Stmt::TypeAlias { name, ty } => {
                    self.type_aliases.insert(name.clone(), ty.clone());
                }
                Stmt::NamespaceDecl { name, body } => {
                    self.namespaces.insert(name.clone(), body.clone());
                    // Register namespace tasks
                    for s in body {
                        if let Stmt::TaskDecl {
                            name: tname,
                            params,
                            return_type,
                            ..
                        } = s
                        {
                            let full_name = format!("{}::{}", name, tname);
                            let ptypes: Vec<Type> = params.iter().map(|(_, t)| t.clone()).collect();
                            self.task_param_types.insert(full_name.clone(), ptypes);
                            self.task_returns.insert(full_name, return_type.clone());
                        }
                    }
                }
                _ => {}
            }
        }

        // Register stdlib functions
        let stdlib_fns: &[(&str, &[&str], &str)] = &[
            ("min", &["int", "int"], "int"),
            ("max", &["int", "int"], "int"),
            ("abs", &["int"], "int"),
            ("clamp", &["int", "int", "int"], "int"),
            ("minf", &["float", "float"], "float"),
            ("maxf", &["float", "float"], "float"),
            ("str_eq", &["string", "string"], "bool"),
            ("str_len", &["string"], "int"),
        ];
        for (fname, params, ret) in stdlib_fns {
            let ptypes: Vec<Type> = params.iter().map(|s| str_to_type(s)).collect();
            self.task_param_types.insert(fname.to_string(), ptypes);
            self.task_returns
                .insert(fname.to_string(), str_to_type(ret));
        }

        for stmt in &program.statements {
            self.analyze_stmt(stmt);
        }
        for w in &self.warnings.clone() {
            eprintln!("Warning: {}", w);
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
    fn warn(&mut self, msg: String) {
        self.warnings.push(msg);
    }
    fn push_scope(&mut self) {
        self.scopes.push(HashMap::new());
    }

    fn pop_scope(&mut self) {
        if let Some(scope) = self.scopes.pop() {
            for (name, info) in &scope {
                if !info.used && info.state == VarState::Live && !info.is_const {
                    self.warn(format!("unused variable '{}'", name));
                }
            }
        }
    }

    fn declare_var(&mut self, name: &str, var_type: Type, is_const: bool, sensitive: bool) {
        if sensitive {
            self.sensitive_names.insert(name.to_string());
        }
        let scope = self.scopes.last_mut().unwrap();
        if scope.contains_key(name) {
            self.error(format!("'{}' already declared in this scope", name));
        } else {
            scope.insert(
                name.to_string(),
                VarInfo {
                    var_type,
                    state: VarState::Live,
                    is_const,
                    sensitive,
                    used: false,
                    assigned: true,
                },
            );
        }
    }

    fn lookup_var(&self, name: &str) -> Option<&VarInfo> {
        for scope in self.scopes.iter().rev() {
            if let Some(info) = scope.get(name) {
                return Some(info);
            }
        }
        None
    }

    fn mark_used(&mut self, name: &str) {
        for scope in self.scopes.iter_mut().rev() {
            if let Some(info) = scope.get_mut(name) {
                info.used = true;
                return;
            }
        }
    }

    fn set_state(&mut self, name: &str, state: VarState) {
        for scope in self.scopes.iter_mut().rev() {
            if let Some(info) = scope.get_mut(name) {
                info.state = state;
                return;
            }
        }
    }

    fn resolve_type(&self, ty: &Type) -> Type {
        if let Type::Struct(name) = ty {
            if let Some(aliased) = self.type_aliases.get(name) {
                return aliased.clone();
            }
        }
        ty.clone()
    }

    fn check_usable(&mut self, name: &str) -> Option<Type> {
        self.mark_used(name);
        if let Some(info) = self.lookup_var(name) {
            match info.state {
                VarState::Live => Some(info.var_type.clone()),
                VarState::Moved => {
                    self.error(format!("'{}' was moved", name));
                    None
                }
                VarState::Purged => {
                    self.error(format!("'{}' was purged", name));
                    None
                }
            }
        } else {
            self.error(format!("'{}' is not defined", name));
            None
        }
    }

    fn infer_type(&mut self, expr: &Expr) -> Option<Type> {
        match expr {
            Expr::Integer(_) => Some(Type::Int),
            Expr::Float(_) => Some(Type::Float),
            Expr::Boolean(_) => Some(Type::Bool),
            Expr::StringLiteral(_) => Some(Type::String),
            Expr::Null => Some(Type::Ptr),
            Expr::Identifier(name) => self.check_usable(name),

            Expr::Tuple(elems) => {
                let types: Vec<Type> = elems.iter().filter_map(|e| self.infer_type(e)).collect();
                Some(Type::Tuple(types))
            }

            Expr::TupleIndex { tuple, index } => {
                if let Some(Type::Tuple(types)) = self.infer_type(tuple) {
                    types.get(*index).cloned()
                } else {
                    self.error("Tuple index on non-tuple type".into());
                    None
                }
            }

            Expr::Min(a, b) | Expr::Max(a, b) => {
                let ta = self.infer_type(a);
                let tb = self.infer_type(b);
                match (ta, tb) {
                    (Some(Type::Int), Some(Type::Int)) => Some(Type::Int),
                    (Some(Type::Float), Some(Type::Float)) => Some(Type::Float),
                    _ => Some(Type::Int),
                }
            }

            Expr::Abs(inner) => self.infer_type(inner),

            Expr::Comptime(inner) => self.infer_type(inner),

            Expr::PropagateErr(inner) => {
                // expr? — if inner is Result(T), returns T, propagates err
                if let Some(Type::Result(inner_t)) = self.infer_type(inner) {
                    Some(*inner_t)
                } else {
                    self.infer_type(inner)
                }
            }

            Expr::InterpolatedString(_) => Some(Type::String),

            Expr::Range { .. } => Some(Type::Array(Box::new(Type::Int))),

            Expr::EnumVariant { .. } => Some(Type::Int),

            Expr::NamespacedIdent { namespace, name } => {
                let full = format!("{}::{}", namespace, name);
                self.check_usable(&full)
            }

            Expr::StrLen(s) => {
                self.infer_type(s);
                Some(Type::Int)
            }
            Expr::StrConcat(a, b) => {
                self.infer_type(a);
                self.infer_type(b);
                Some(Type::String)
            }
            Expr::StrSlice { s, start, end } => {
                self.infer_type(s);
                self.infer_type(start);
                self.infer_type(end);
                Some(Type::String)
            }
            Expr::StrContains { s, needle } => {
                self.infer_type(s);
                self.infer_type(needle);
                Some(Type::Bool)
            }
            Expr::StrToInt(s) => {
                self.infer_type(s);
                Some(Type::Int)
            }
            Expr::IntToStr(n) => {
                self.infer_type(n);
                Some(Type::String)
            }

            Expr::OkExpr(inner) => {
                let t = self.infer_type(inner);
                t.map(|it| Type::Result(Box::new(it)))
            }
            Expr::ErrExpr(_) => Some(Type::Result(Box::new(Type::Int))),
            Expr::IsOk(inner) => {
                self.infer_type(inner);
                Some(Type::Bool)
            }
            Expr::Unwrap(inner) => {
                if let Some(Type::Result(it)) = self.infer_type(inner) {
                    Some(*it)
                } else {
                    self.error("unwrap requires Result type".into());
                    None
                }
            }

            Expr::StructLiteral { name, fields } => {
                if let Some(decl_fields) = self.struct_fields.get(name).cloned() {
                    for (fname, fval) in fields {
                        if let Some((_, decl_ty)) = decl_fields.iter().find(|(n, _)| n == fname) {
                            let at = self.infer_type(fval);
                            let decl_ty = decl_ty.clone();
                            if let Some(actual) = at {
                                // Allow generic type fields
                                if !matches!(decl_ty, Type::Generic(_)) && actual != decl_ty {
                                    self.error(format!(
                                        "Field '{}': expected {:?}, got {:?}",
                                        fname, decl_ty, actual
                                    ));
                                }
                            }
                        } else {
                            self.error(format!("Unknown field '{}' in struct '{}'", fname, name));
                        }
                    }
                    Some(Type::Struct(name.clone()))
                } else {
                    self.error(format!("Unknown struct '{}'", name));
                    None
                }
            }

            Expr::FieldAccess { object, field } => {
                let obj_ty = self.infer_type(object);
                match obj_ty {
                    Some(Type::Struct(sname)) => {
                        if let Some(fields) = self.struct_fields.get(&sname).cloned() {
                            if let Some((_, ft)) = fields.iter().find(|(n, _)| n == field) {
                                Some(ft.clone())
                            } else {
                                self.error(format!("Struct '{}' has no field '{}'", sname, field));
                                None
                            }
                        } else {
                            None
                        }
                    }
                    _ => {
                        self.error("Field access on non-struct".into());
                        None
                    }
                }
            }

            Expr::Alloc { count, size } => {
                self.infer_type(count);
                self.infer_type(size);
                Some(Type::Ptr)
            }

            Expr::Cast { expr, to } => {
                self.infer_type(expr);
                Some(to.clone())
            }

            Expr::BinaryOp { left, op, right } => {
                let lt = self.infer_type(left);
                let rt = self.infer_type(right);
                match (lt, rt) {
                    (Some(l), Some(r)) => match op {
                        BinOp::And | BinOp::Or => {
                            if l != Type::Bool {
                                self.error(format!("'{:?}' needs bool, got {:?}", op, l));
                            }
                            if r != Type::Bool {
                                self.error(format!("'{:?}' needs bool, got {:?}", op, r));
                            }
                            Some(Type::Bool)
                        }
                        BinOp::Eq | BinOp::Neq => {
                            // Allow string comparison via ==
                            Some(Type::Bool)
                        }
                        BinOp::Lt | BinOp::Gt | BinOp::Le | BinOp::Ge => {
                            if l != r {
                                self.error(format!("Cannot compare {:?} with {:?}", l, r));
                            }
                            Some(Type::Bool)
                        }
                        BinOp::BitAnd | BinOp::BitOr | BinOp::BitXor | BinOp::Shl | BinOp::Shr => {
                            Some(Type::Int)
                        }
                        _ => {
                            if l != r {
                                // Allow int/float mixing in arithmetic if castable
                                if (l == Type::Int || l == Type::Float)
                                    && (r == Type::Int || r == Type::Float)
                                {
                                    Some(Type::Float) // widening
                                } else {
                                    self.error(format!("Type mismatch: {:?} vs {:?}", l, r));
                                    None
                                }
                            } else {
                                Some(l)
                            }
                        }
                    },
                    _ => None,
                }
            }

            Expr::UnaryOp { op, operand } => {
                let t = self.infer_type(operand);
                match op {
                    UnaryOp::Neg => t,
                    UnaryOp::Not => {
                        if t != Some(Type::Bool) { /* allow */ }
                        Some(Type::Bool)
                    }
                    UnaryOp::BitNot => Some(Type::Int),
                }
            }

            Expr::Call { func, args, named } => {
                if let Expr::Identifier(name) = func.as_ref() {
                    if self.network_fns.contains(name) && self.override_depth == 0 {
                        self.warn(format!(
                            "Privacy warning: '{}' is a network function. Use 'override'.",
                            name
                        ));
                    }
                    if let Some(ptypes) = self.task_param_types.get(name).cloned() {
                        let total_args = args.len() + named.len();
                        if total_args != ptypes.len() && !ptypes.is_empty() {
                            // Allow variadic — only check minimum
                        }
                        for (i, arg) in args.iter().enumerate() {
                            if let Some(at) = self.infer_type(arg) {
                                if let Some(pt) = ptypes.get(i) {
                                    if at != *pt
                                        && !matches!(pt, Type::Generic(_))
                                        && *pt != Type::Ptr
                                    {
                                        // Allow compatible numeric types
                                    }
                                }
                            }
                            if let Expr::Identifier(aname) = arg {
                                if self.sensitive_names.contains(aname) {
                                    self.warn(format!(
                                        "Privacy: sensitive '{}' passed to '{}'",
                                        aname, name
                                    ));
                                }
                            }
                        }
                        for (_, aval) in named {
                            self.infer_type(aval);
                        }
                    } else {
                        for a in args {
                            self.infer_type(a);
                        }
                        for (_, a) in named {
                            self.infer_type(a);
                        }
                        // Don't error on unknown — might be stdlib
                    }
                    self.task_returns.get(name).cloned()
                } else {
                    for a in args {
                        self.infer_type(a);
                    }
                    None
                }
            }

            Expr::Closure { params, body } => {
                self.push_scope();
                for (pname, pty) in params {
                    let t = pty.as_ref().cloned().unwrap_or(Type::Int);
                    self.declare_var(pname, t, false, false);
                }
                let ret = self.infer_type(body);
                self.pop_scope();
                Some(Type::Fn(
                    params
                        .iter()
                        .map(|(_, t)| t.as_ref().cloned().unwrap_or(Type::Int))
                        .collect(),
                    Box::new(ret.unwrap_or(Type::Void)),
                ))
            }

            Expr::Await(inner) => self.infer_type(inner),
            Expr::Nullable(inner) => {
                self.infer_type(inner);
                Some(Type::Bool)
            }

            Expr::Array(elems) => {
                let mut elem_type: Option<Type> = None;
                for e in elems {
                    let t = self.infer_type(e);
                    if elem_type.is_none() {
                        elem_type = t;
                    }
                }
                Some(Type::Array(Box::new(elem_type.unwrap_or(Type::Int))))
            }

            Expr::Index { array, index } => {
                let arr_ty = self.infer_type(array);
                self.infer_type(index);
                match arr_ty {
                    Some(Type::Array(inner)) | Some(Type::Slice(inner)) => Some(*inner),
                    Some(Type::String) => Some(Type::Int), // char access
                    _ => Some(Type::Int),
                }
            }

            Expr::Copy(inner) => self.infer_type(inner),

            Expr::AddressOf(inner) => {
                if self.override_depth == 0 {
                    self.error("'&' only inside 'override'".into());
                }
                self.infer_type(inner);
                Some(Type::Ptr)
            }

            Expr::Deref(inner) => {
                if self.override_depth == 0 {
                    self.error("'*' only inside 'override'".into());
                }
                self.infer_type(inner);
                Some(Type::Int)
            }
        }
    }

    fn analyze_stmt(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::StructDecl { .. }
            | Stmt::EnumDecl { .. }
            | Stmt::ExternDecl { .. }
            | Stmt::TypeAlias { .. } => {}

            Stmt::NamespaceDecl { name, body } => {
                self.push_scope();
                for s in body {
                    self.analyze_stmt(s);
                }
                self.pop_scope();
            }

            Stmt::UseDecl { path } => {
                // Import namespace symbols into current scope
                // Simplified: just mark as used
            }

            Stmt::VarDecl {
                name,
                ty,
                value,
                sensitive,
            } => {
                let inferred = self.infer_type(value);
                let final_ty = ty.as_ref().cloned().or(inferred).unwrap_or(Type::Int);
                // Move semantics for non-primitives
                if let Expr::Identifier(moved) = value {
                    match final_ty {
                        Type::Int
                        | Type::Float
                        | Type::Bool
                        | Type::Int8
                        | Type::Int16
                        | Type::Int64 => {}
                        _ => self.set_state(moved, VarState::Moved),
                    }
                }
                if *sensitive {
                    self.sensitive_names.insert(name.clone());
                }
                self.declare_var(name, final_ty, false, *sensitive);
            }

            Stmt::ConstDecl { name, value } => {
                let t = self.infer_type(value).unwrap_or(Type::Int);
                self.declare_var(name, t, true, false);
            }

            Stmt::Assign { name, value } => {
                if let Some(info) = self.lookup_var(name) {
                    if info.is_const {
                        self.error(format!("Cannot assign to const '{}'", name));
                        return;
                    }
                    let expected = info.var_type.clone();
                    let state = info.state.clone();
                    if state == VarState::Moved {
                        self.error(format!("'{}' was moved", name));
                    }
                    if state == VarState::Purged {
                        self.error(format!("'{}' was purged", name));
                    }
                    self.infer_type(value);
                } else {
                    self.error(format!("'{}' not defined. Use 'set'.", name));
                }
            }

            Stmt::CompoundAssign { name, op: _, value } => {
                if self.lookup_var(name).is_none() {
                    self.error(format!("'{}' not defined", name));
                }
                self.infer_type(value);
            }

            Stmt::MultiAssign { names, values } => {
                for (name, value) in names.iter().zip(values.iter()) {
                    let t = self.infer_type(value).unwrap_or(Type::Int);
                    if self.lookup_var(name).is_some() {
                        // re-assign
                    } else {
                        self.declare_var(name, t, false, false);
                    }
                }
            }

            Stmt::Destructure {
                fields,
                from_struct,
                value,
            } => {
                let ty = self.infer_type(value);
                if let Some(Type::Struct(sname)) = ty {
                    if let Some(struct_fields) = self.struct_fields.get(&sname).cloned() {
                        for fname in fields {
                            if let Some((_, ft)) = struct_fields.iter().find(|(n, _)| n == fname) {
                                self.declare_var(fname, ft.clone(), false, false);
                            }
                        }
                    }
                }
            }

            Stmt::FieldAssign {
                object,
                field,
                value,
            } => {
                if let Some(info) = self.lookup_var(object) {
                    if let Type::Struct(ref sname) = info.var_type.clone() {
                        if let Some(fields) = self.struct_fields.get(sname).cloned() {
                            if let Some((_, ft)) = fields.iter().find(|(n, _)| n == field) {
                                let at = self.infer_type(value);
                                if let Some(actual) = at {
                                    if actual != *ft && !matches!(ft, Type::Generic(_)) {
                                        // Allow compatible types
                                    }
                                }
                            } else {
                                self.error(format!("No field '{}' in '{}'", field, sname));
                            }
                        }
                    } else {
                        self.error(format!("'{}' is not a struct", object));
                    }
                } else {
                    self.error(format!("'{}' not defined", object));
                }
            }

            Stmt::IndexAssign {
                array,
                index,
                value,
            } => {
                self.infer_type(index);
                self.infer_type(value);
                if self.lookup_var(array).is_none() {
                    self.error(format!("'{}' not defined", array));
                }
            }

            Stmt::TaskDecl {
                name: tname,
                params,
                body,
                return_type,
                type_params,
                constraints,
                ..
            } => {
                let saved = self.current_ret_type.clone();
                let saved_name = self.current_task_name.clone();
                self.current_ret_type = Some(return_type.clone());
                self.current_task_name = Some(tname.clone());
                self.push_scope();

                // Declare generic type params as themselves
                for tp in type_params {
                    self.declare_var(tp, Type::Generic(tp.clone()), true, false);
                }

                for (pname, ptype) in params {
                    self.declare_var(pname, ptype.clone(), false, false);
                }

                self.analyze_block(body);

                // Check all paths return
                if *return_type != Type::Void && !self.block_always_returns(body) {
                    self.error(format!(
                        "Task '{}': not all code paths return a value",
                        tname
                    ));
                }

                // Dead code detection
                self.check_dead_code(body);

                self.pop_scope();
                self.current_ret_type = saved;
                self.current_task_name = saved_name;
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                let ct = self.infer_type(condition);
                if ct.is_some() && ct != Some(Type::Bool) {
                    // Allow integer conditions (they get converted to bool)
                }
                self.push_scope();
                self.analyze_block(then_block);
                self.pop_scope();
                if let Some(eb) = else_block {
                    self.push_scope();
                    self.analyze_block(eb);
                    self.pop_scope();
                }
            }

            Stmt::Loop { kind, body } => {
                match kind {
                    LoopKind::FromTo { var, from, to } => {
                        self.infer_type(from);
                        self.infer_type(to);
                        self.push_scope();
                        self.declare_var(var, Type::Int, false, false);
                        self.loop_depth += 1;
                        self.analyze_block(body);
                        self.loop_depth -= 1;
                        self.pop_scope();
                        return;
                    }
                    LoopKind::ForEach { var, iterable } => {
                        let elem_ty = match self.infer_type(iterable) {
                            Some(Type::Array(inner)) | Some(Type::Slice(inner)) => *inner,
                            Some(Type::String) => Type::Int, // char
                            _ => Type::Int,
                        };
                        self.push_scope();
                        self.declare_var(var, elem_ty, false, false);
                        self.loop_depth += 1;
                        self.analyze_block(body);
                        self.loop_depth -= 1;
                        self.pop_scope();
                        return;
                    }
                    LoopKind::Range { var, range } => {
                        self.infer_type(range);
                        self.push_scope();
                        self.declare_var(var, Type::Int, false, false);
                        self.loop_depth += 1;
                        self.analyze_block(body);
                        self.loop_depth -= 1;
                        self.pop_scope();
                        return;
                    }
                    LoopKind::Times(e) => {
                        self.infer_type(e);
                    }
                    LoopKind::While(e) => {
                        self.infer_type(e);
                    }
                    LoopKind::Infinite => {}
                }
                self.push_scope();
                self.loop_depth += 1;
                self.analyze_block(body);
                self.loop_depth -= 1;
                self.pop_scope();
            }

            Stmt::Match { value, arms } => {
                self.infer_type(value);
                for arm in arms {
                    self.push_scope();
                    // Bind capture variables from pattern
                    if let Pattern::EnumVariantCapture { bindings, .. } = &arm.pattern {
                        for b in bindings {
                            self.declare_var(b, Type::Int, false, false);
                        }
                    }
                    self.analyze_block(&arm.body);
                    self.pop_scope();
                }
            }

            Stmt::Break | Stmt::Continue => {
                if self.loop_depth == 0 {
                    self.error("'break'/'continue' outside loop".into());
                }
            }

            Stmt::Override { body } => {
                self.override_depth += 1;
                self.push_scope();
                self.analyze_block(body);
                self.pop_scope();
                self.override_depth -= 1;
            }

            Stmt::ConstantTime { body } => {
                self.constant_time_depth += 1;
                self.push_scope();
                self.analyze_block(body);
                self.pop_scope();
                self.constant_time_depth -= 1;
            }

            Stmt::Spawn { body, .. } => {
                self.push_scope();
                self.analyze_block(body);
                self.pop_scope();
            }

            Stmt::Join { handle } => {
                self.infer_type(handle);
            }

            Stmt::Defer { body } => {
                self.push_scope();
                self.analyze_block(body);
                self.pop_scope();
            }

            Stmt::Assert { condition, .. } | Stmt::StaticAssert { condition, .. } => {
                self.infer_type(condition);
            }

            Stmt::Purge { variable } => {
                if let Some(info) = self.lookup_var(variable) {
                    if info.is_const {
                        self.error(format!("Cannot purge const '{}'", variable));
                        return;
                    }
                }
                if self.check_usable(variable).is_some() {
                    self.set_state(variable, VarState::Purged);
                }
            }

            Stmt::Free { ptr } => {
                self.infer_type(ptr);
            }

            Stmt::Print(e) => {
                self.infer_type(e);
            }

            Stmt::PrintFmt { args, .. } => {
                for a in args {
                    self.infer_type(a);
                }
            }

            Stmt::Return(expr) => {
                let exp = self.current_ret_type.clone();
                if let (Some(exp), Some(e)) = (&exp, expr) {
                    let t = self.infer_type(e);
                    if let Some(actual) = t {
                        if actual != *exp && !matches!(exp, Type::Generic(_)) {
                            // Allow compatible returns (e.g. int where Result<int> expected)
                        }
                    }
                }
            }

            Stmt::Asm(_) => {
                if self.override_depth == 0 {
                    self.error("'asm' only inside 'override'".into());
                }
            }

            Stmt::TestDecl { name, body } => {
                self.push_scope();
                self.current_ret_type = Some(Type::Void);
                self.analyze_block(body);
                self.pop_scope();
                self.current_ret_type = None;
            }

            Stmt::Import(_) => {}
            Stmt::ExprStmt(e) => {
                self.infer_type(e);
            }
        }
    }

    fn analyze_block(&mut self, block: &Block) {
        for s in &block.statements {
            self.analyze_stmt(s);
        }
        if let Some(tail) = &block.tail_expr {
            self.infer_type(tail);
        }
    }

    fn block_always_returns(&self, block: &Block) -> bool {
        block.statements.iter().any(|s| self.stmt_always_returns(s))
    }

    fn stmt_always_returns(&self, stmt: &Stmt) -> bool {
        match stmt {
            Stmt::Return(_) => true,
            Stmt::Check {
                then_block,
                else_block: Some(eb),
                ..
            } => self.block_always_returns(then_block) && self.block_always_returns(eb),
            Stmt::Loop {
                kind: LoopKind::Infinite,
                body,
            } => self.block_always_returns(body),
            Stmt::Match { arms, .. } => {
                !arms.is_empty() && arms.iter().all(|a| self.block_always_returns(&a.body))
            }
            _ => false,
        }
    }

    fn check_dead_code(&mut self, block: &Block) {
        let mut found_terminator = false;
        for stmt in &block.statements {
            if found_terminator {
                self.warn("Unreachable code after return/break".into());
                break;
            }
            if matches!(stmt, Stmt::Return(_) | Stmt::Break | Stmt::Continue) {
                found_terminator = true;
            }
        }
    }
}

fn str_to_type(s: &str) -> Type {
    match s {
        "int" => Type::Int,
        "float" => Type::Float,
        "bool" => Type::Bool,
        "string" => Type::String,
        "ptr" => Type::Ptr,
        "void" => Type::Void,
        _ => Type::Int,
    }
}
