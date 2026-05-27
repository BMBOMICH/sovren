use crate::ast::*;
use std::collections::HashMap;

type GenericDefs = HashMap<String, (Vec<String>, Vec<(String, Type)>, Type, Block, bool, bool)>;
type GenericStructs = HashMap<String, (Vec<String>, Vec<(String, Type)>)>;

pub fn monomorphize(program: &Program) -> Program {
    let mut generic_defs: GenericDefs = HashMap::new();
    let mut generic_structs: GenericStructs = HashMap::new();

    for stmt in &program.statements {
        match stmt {
            Stmt::TaskDecl {
                name,
                type_params,
                params,
                return_type,
                body,
                is_inline,
                is_async,
                ..
            } if !type_params.is_empty() => {
                generic_defs.insert(
                    name.clone(),
                    (
                        type_params.clone(),
                        params.clone(),
                        return_type.clone(),
                        body.clone(),
                        *is_inline,
                        *is_async,
                    ),
                );
            }
            Stmt::StructDecl {
                name,
                type_params,
                fields,
            } if !type_params.is_empty() => {
                generic_structs.insert(name.clone(), (type_params.clone(), fields.clone()));
            }
            _ => {}
        }
    }

    if generic_defs.is_empty() && generic_structs.is_empty() {
        return program.clone();
    }

    // Collect instantiations
    let mut task_inst: HashMap<String, Vec<Vec<Type>>> = HashMap::new();
    let mut struct_inst: HashMap<String, Vec<Vec<Type>>> = HashMap::new();

    for stmt in &program.statements {
        collect_instantiations_stmt(
            stmt,
            &generic_defs,
            &generic_structs,
            &mut task_inst,
            &mut struct_inst,
        );
    }

    // Build new program
    let mut new_stmts: Vec<Stmt> = Vec::new();

    // Keep non-generic stmts with rewritten calls
    for stmt in &program.statements {
        match stmt {
            Stmt::TaskDecl { type_params, .. } if !type_params.is_empty() => continue,
            Stmt::StructDecl { type_params, .. } if !type_params.is_empty() => continue,
            _ => new_stmts.push(rewrite_stmt(
                stmt,
                &generic_defs,
                &generic_structs,
                &task_inst,
                &struct_inst,
            )),
        }
    }

    // Add monomorphized struct versions
    for (struct_name, type_arg_sets) in &struct_inst {
        if let Some((type_params, fields)) = generic_structs.get(struct_name) {
            for type_args in type_arg_sets {
                let concrete_name = make_concrete_name(struct_name, type_args);
                let concrete_fields: Vec<(String, Type)> = fields
                    .iter()
                    .map(|(fname, ftype)| {
                        let mut t = ftype.clone();
                        for (param, arg) in type_params.iter().zip(type_args.iter()) {
                            t = t.substitute(param, arg);
                        }
                        (fname.clone(), t)
                    })
                    .collect();
                new_stmts.push(Stmt::StructDecl {
                    name: concrete_name,
                    type_params: Vec::new(),
                    fields: concrete_fields,
                });
            }
        }
    }

    // Add monomorphized task versions
    for (task_name, type_arg_sets) in &task_inst {
        if let Some((type_params, params, return_type, body, is_inline, is_async)) =
            generic_defs.get(task_name)
        {
            for type_args in type_arg_sets {
                let concrete_name = make_concrete_name(task_name, type_args);
                let concrete_params: Vec<(String, Type)> = params
                    .iter()
                    .map(|(pname, ptype)| {
                        let mut t = ptype.clone();
                        for (param, arg) in type_params.iter().zip(type_args.iter()) {
                            t = t.substitute(param, arg);
                        }
                        (pname.clone(), t)
                    })
                    .collect();
                let mut concrete_ret = return_type.clone();
                for (param, arg) in type_params.iter().zip(type_args.iter()) {
                    concrete_ret = concrete_ret.substitute(param, arg);
                }
                let concrete_body = substitute_block(body, type_params, type_args);
                new_stmts.push(Stmt::TaskDecl {
                    name: concrete_name,
                    type_params: Vec::new(),
                    constraints: Vec::new(),
                    params: concrete_params,
                    return_type: concrete_ret,
                    body: concrete_body,
                    is_inline: *is_inline,
                    is_async: *is_async,
                });
            }
        }
    }

    Program {
        statements: new_stmts,
    }
}

fn make_concrete_name(name: &str, type_args: &[Type]) -> String {
    let suffix: Vec<String> = type_args.iter().map(type_to_suffix).collect();
    format!("{}_{}", name, suffix.join("_"))
}

fn type_to_suffix(t: &Type) -> String {
    match t {
        Type::Int => "int".into(),
        Type::Int8 => "i8".into(),
        Type::Int16 => "i16".into(),
        Type::Int64 => "i64".into(),
        Type::Float => "float".into(),
        Type::Bool => "bool".into(),
        Type::String => "string".into(),
        Type::Ptr => "ptr".into(),
        Type::Void => "void".into(),
        Type::Struct(n) => n.clone(),
        Type::Enum(n) => n.clone(),
        Type::Array(inner) => format!("arr_{}", type_to_suffix(inner)),
        Type::Generic(n) => n.clone(),
        _ => "t".into(),
    }
}

fn collect_instantiations_stmt(
    stmt: &Stmt,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &mut HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &mut HashMap<String, Vec<Vec<Type>>>,
) {
    match stmt {
        Stmt::VarDecl { value, .. } | Stmt::Assign { value, .. } => {
            collect_from_expr(value, defs, structs, task_inst, struct_inst);
        }
        Stmt::TaskDecl {
            type_params, body, ..
        } if type_params.is_empty() => {
            collect_from_block(body, defs, structs, task_inst, struct_inst);
        }
        Stmt::Check {
            condition,
            then_block,
            else_block,
        } => {
            collect_from_expr(condition, defs, structs, task_inst, struct_inst);
            collect_from_block(then_block, defs, structs, task_inst, struct_inst);
            if let Some(eb) = else_block {
                collect_from_block(eb, defs, structs, task_inst, struct_inst);
            }
        }
        Stmt::Loop { body, .. } => collect_from_block(body, defs, structs, task_inst, struct_inst),
        Stmt::ExprStmt(e) | Stmt::Print(e) | Stmt::Return(Some(e)) => {
            collect_from_expr(e, defs, structs, task_inst, struct_inst);
        }
        Stmt::PrintFmt { args, .. } => {
            for a in args {
                collect_from_expr(a, defs, structs, task_inst, struct_inst);
            }
        }
        _ => {}
    }
}

fn collect_from_block(
    block: &Block,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &mut HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &mut HashMap<String, Vec<Vec<Type>>>,
) {
    for s in &block.statements {
        collect_instantiations_stmt(s, defs, structs, task_inst, struct_inst);
    }
    if let Some(tail) = &block.tail_expr {
        collect_from_expr(tail, defs, structs, task_inst, struct_inst);
    }
}

fn collect_from_expr(
    expr: &Expr,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &mut HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &mut HashMap<String, Vec<Vec<Type>>>,
) {
    match expr {
        Expr::Call { func, args, .. } => {
            if let Expr::Identifier(name) = func.as_ref() {
                if let Some((type_params, params, _, _, _, _)) = defs.get(name) {
                    let inferred: Vec<Type> = type_params
                        .iter()
                        .map(|tp| {
                            for (i, (_, pt)) in params.iter().enumerate() {
                                if *pt == Type::Generic(tp.clone()) {
                                    if let Some(a) = args.get(i) {
                                        return infer_expr_type(a);
                                    }
                                }
                            }
                            Type::Int
                        })
                        .collect();
                    let entry = task_inst.entry(name.clone()).or_default();
                    if !entry.contains(&inferred) {
                        entry.push(inferred);
                    }
                }
            }
            for a in args {
                collect_from_expr(a, defs, structs, task_inst, struct_inst);
            }
        }
        Expr::StructLiteral { name, fields } => {
            if structs.contains_key(name) {
                // Try to infer type args from field values
                if let Some((type_params, struct_fields)) = structs.get(name) {
                    let inferred: Vec<Type> = type_params
                        .iter()
                        .map(|tp| {
                            for (sfield, stype) in struct_fields {
                                if *stype == Type::Generic(tp.clone()) {
                                    if let Some((_, fval)) =
                                        fields.iter().find(|(n, _)| n == sfield)
                                    {
                                        return infer_expr_type(fval);
                                    }
                                }
                            }
                            Type::Int
                        })
                        .collect();
                    let entry = struct_inst.entry(name.clone()).or_default();
                    if !entry.contains(&inferred) {
                        entry.push(inferred);
                    }
                }
            }
            for (_, fval) in fields {
                collect_from_expr(fval, defs, structs, task_inst, struct_inst);
            }
        }
        Expr::BinaryOp { left, right, .. } => {
            collect_from_expr(left, defs, structs, task_inst, struct_inst);
            collect_from_expr(right, defs, structs, task_inst, struct_inst);
        }
        Expr::UnaryOp { operand, .. } => {
            collect_from_expr(operand, defs, structs, task_inst, struct_inst)
        }
        _ => {}
    }
}

fn infer_expr_type(expr: &Expr) -> Type {
    match expr {
        Expr::Integer(_) => Type::Int,
        Expr::Float(_) => Type::Float,
        Expr::Boolean(_) => Type::Bool,
        Expr::StringLiteral(_) => Type::String,
        Expr::Null => Type::Ptr,
        _ => Type::Int,
    }
}

// Rewriting functions (same as before but updated for new AST)
fn rewrite_stmt(
    stmt: &Stmt,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &HashMap<String, Vec<Vec<Type>>>,
) -> Stmt {
    match stmt {
        Stmt::ExprStmt(e) => Stmt::ExprStmt(rewrite_expr(e, defs, structs, task_inst, struct_inst)),
        Stmt::Print(e) => Stmt::Print(rewrite_expr(e, defs, structs, task_inst, struct_inst)),
        Stmt::Return(Some(e)) => {
            Stmt::Return(Some(rewrite_expr(e, defs, structs, task_inst, struct_inst)))
        }
        Stmt::VarDecl {
            name,
            ty,
            value,
            sensitive,
        } => Stmt::VarDecl {
            name: name.clone(),
            ty: ty.clone(),
            value: rewrite_expr(value, defs, structs, task_inst, struct_inst),
            sensitive: *sensitive,
        },
        Stmt::Assign { name, value } => Stmt::Assign {
            name: name.clone(),
            value: rewrite_expr(value, defs, structs, task_inst, struct_inst),
        },
        Stmt::Check {
            condition,
            then_block,
            else_block,
        } => Stmt::Check {
            condition: rewrite_expr(condition, defs, structs, task_inst, struct_inst),
            then_block: rewrite_block(then_block, defs, structs, task_inst, struct_inst),
            else_block: else_block
                .as_ref()
                .map(|b| rewrite_block(b, defs, structs, task_inst, struct_inst)),
        },
        Stmt::Loop { kind, body } => {
            let new_kind = match kind {
                LoopKind::Times(e) => {
                    LoopKind::Times(rewrite_expr(e, defs, structs, task_inst, struct_inst))
                }
                LoopKind::While(e) => {
                    LoopKind::While(rewrite_expr(e, defs, structs, task_inst, struct_inst))
                }
                LoopKind::FromTo { var, from, to } => LoopKind::FromTo {
                    var: var.clone(),
                    from: rewrite_expr(from, defs, structs, task_inst, struct_inst),
                    to: rewrite_expr(to, defs, structs, task_inst, struct_inst),
                },
                LoopKind::ForEach { var, iterable } => LoopKind::ForEach {
                    var: var.clone(),
                    iterable: rewrite_expr(iterable, defs, structs, task_inst, struct_inst),
                },
                LoopKind::Range { var, range } => LoopKind::Range {
                    var: var.clone(),
                    range: rewrite_expr(range, defs, structs, task_inst, struct_inst),
                },
                other => other.clone(),
            };
            Stmt::Loop {
                kind: new_kind,
                body: rewrite_block(body, defs, structs, task_inst, struct_inst),
            }
        }
        Stmt::TaskDecl {
            name,
            type_params,
            constraints,
            params,
            return_type,
            body,
            is_inline,
            is_async,
        } if type_params.is_empty() => Stmt::TaskDecl {
            name: name.clone(),
            type_params: Vec::new(),
            constraints: constraints.clone(),
            params: params.clone(),
            return_type: return_type.clone(),
            body: rewrite_block(body, defs, structs, task_inst, struct_inst),
            is_inline: *is_inline,
            is_async: *is_async,
        },
        other => other.clone(),
    }
}

fn rewrite_block(
    block: &Block,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &HashMap<String, Vec<Vec<Type>>>,
) -> Block {
    Block {
        statements: block
            .statements
            .iter()
            .map(|s| rewrite_stmt(s, defs, structs, task_inst, struct_inst))
            .collect(),
        tail_expr: block
            .tail_expr
            .as_ref()
            .map(|e| rewrite_expr(e, defs, structs, task_inst, struct_inst)),
    }
}

fn rewrite_expr(
    expr: &Expr,
    defs: &GenericDefs,
    structs: &GenericStructs,
    task_inst: &HashMap<String, Vec<Vec<Type>>>,
    struct_inst: &HashMap<String, Vec<Vec<Type>>>,
) -> Expr {
    match expr {
        Expr::Call { func, args, named } => {
            if let Expr::Identifier(name) = func.as_ref() {
                if defs.contains_key(name) {
                    if let Some(type_arg_sets) = task_inst.get(name) {
                        let d = defs.get(name).unwrap();
                        let inferred: Vec<Type> =
                            d.0.iter()
                                .enumerate()
                                .map(|(_, tp)| {
                                    for (j, (_, pt)) in d.1.iter().enumerate() {
                                        if *pt == Type::Generic(tp.clone()) {
                                            if let Some(a) = args.get(j) {
                                                return infer_expr_type(a);
                                            }
                                        }
                                    }
                                    Type::Int
                                })
                                .collect();
                        if type_arg_sets.contains(&inferred) {
                            let concrete_name = make_concrete_name(name, &inferred);
                            let new_args = args
                                .iter()
                                .map(|a| rewrite_expr(a, defs, structs, task_inst, struct_inst))
                                .collect();
                            return Expr::Call {
                                func: Box::new(Expr::Identifier(concrete_name)),
                                args: new_args,
                                named: named.clone(),
                            };
                        }
                    }
                }
            }
            Expr::Call {
                func: func.clone(),
                args: args
                    .iter()
                    .map(|a| rewrite_expr(a, defs, structs, task_inst, struct_inst))
                    .collect(),
                named: named.clone(),
            }
        }
        Expr::StructLiteral { name, fields } => {
            // Rewrite generic struct literal to concrete name
            if structs.contains_key(name) {
                if let Some(type_arg_sets) = struct_inst.get(name) {
                    if let Some(type_args) = type_arg_sets.first() {
                        let concrete_name = make_concrete_name(name, type_args);
                        let new_fields = fields
                            .iter()
                            .map(|(fn_, fv)| {
                                (
                                    fn_.clone(),
                                    rewrite_expr(fv, defs, structs, task_inst, struct_inst),
                                )
                            })
                            .collect();
                        return Expr::StructLiteral {
                            name: concrete_name,
                            fields: new_fields,
                        };
                    }
                }
            }
            let new_fields = fields
                .iter()
                .map(|(fn_, fv)| {
                    (
                        fn_.clone(),
                        rewrite_expr(fv, defs, structs, task_inst, struct_inst),
                    )
                })
                .collect();
            Expr::StructLiteral {
                name: name.clone(),
                fields: new_fields,
            }
        }
        Expr::BinaryOp { left, op, right } => Expr::BinaryOp {
            left: Box::new(rewrite_expr(left, defs, structs, task_inst, struct_inst)),
            op: op.clone(),
            right: Box::new(rewrite_expr(right, defs, structs, task_inst, struct_inst)),
        },
        Expr::UnaryOp { op, operand } => Expr::UnaryOp {
            op: op.clone(),
            operand: Box::new(rewrite_expr(operand, defs, structs, task_inst, struct_inst)),
        },
        other => other.clone(),
    }
}

fn substitute_block(block: &Block, type_params: &[String], type_args: &[Type]) -> Block {
    Block {
        statements: block
            .statements
            .iter()
            .map(|s| substitute_stmt(s, type_params, type_args))
            .collect(),
        tail_expr: block
            .tail_expr
            .as_ref()
            .map(|e| substitute_expr(e, type_params, type_args)),
    }
}

fn substitute_stmt(stmt: &Stmt, tp: &[String], ta: &[Type]) -> Stmt {
    match stmt {
        Stmt::VarDecl {
            name,
            ty,
            value,
            sensitive,
        } => Stmt::VarDecl {
            name: name.clone(),
            ty: ty.as_ref().map(|t| {
                let mut r = t.clone();
                for (p, a) in tp.iter().zip(ta.iter()) {
                    r = r.substitute(p, a);
                }
                r
            }),
            value: substitute_expr(value, tp, ta),
            sensitive: *sensitive,
        },
        Stmt::Return(Some(e)) => Stmt::Return(Some(substitute_expr(e, tp, ta))),
        Stmt::ExprStmt(e) => Stmt::ExprStmt(substitute_expr(e, tp, ta)),
        Stmt::Print(e) => Stmt::Print(substitute_expr(e, tp, ta)),
        Stmt::Assign { name, value } => Stmt::Assign {
            name: name.clone(),
            value: substitute_expr(value, tp, ta),
        },
        Stmt::Check {
            condition,
            then_block,
            else_block,
        } => Stmt::Check {
            condition: substitute_expr(condition, tp, ta),
            then_block: substitute_block(then_block, tp, ta),
            else_block: else_block.as_ref().map(|b| substitute_block(b, tp, ta)),
        },
        Stmt::Loop { kind, body } => {
            let new_kind = match kind {
                LoopKind::Times(e) => LoopKind::Times(substitute_expr(e, tp, ta)),
                LoopKind::While(e) => LoopKind::While(substitute_expr(e, tp, ta)),
                LoopKind::FromTo { var, from, to } => LoopKind::FromTo {
                    var: var.clone(),
                    from: substitute_expr(from, tp, ta),
                    to: substitute_expr(to, tp, ta),
                },
                other => other.clone(),
            };
            Stmt::Loop {
                kind: new_kind,
                body: substitute_block(body, tp, ta),
            }
        }
        other => other.clone(),
    }
}

fn substitute_expr(expr: &Expr, tp: &[String], ta: &[Type]) -> Expr {
    match expr {
        Expr::Cast { expr, to } => {
            let mut new_to = to.clone();
            for (p, a) in tp.iter().zip(ta.iter()) {
                new_to = new_to.substitute(p, a);
            }
            Expr::Cast {
                expr: Box::new(substitute_expr(expr, tp, ta)),
                to: new_to,
            }
        }
        Expr::BinaryOp { left, op, right } => Expr::BinaryOp {
            left: Box::new(substitute_expr(left, tp, ta)),
            op: op.clone(),
            right: Box::new(substitute_expr(right, tp, ta)),
        },
        Expr::UnaryOp { op, operand } => Expr::UnaryOp {
            op: op.clone(),
            operand: Box::new(substitute_expr(operand, tp, ta)),
        },
        Expr::Call { func, args, named } => Expr::Call {
            func: func.clone(),
            args: args.iter().map(|a| substitute_expr(a, tp, ta)).collect(),
            named: named.clone(),
        },
        Expr::Index { array, index } => Expr::Index {
            array: Box::new(substitute_expr(array, tp, ta)),
            index: Box::new(substitute_expr(index, tp, ta)),
        },
        Expr::StructLiteral { name, fields } => Expr::StructLiteral {
            name: name.clone(),
            fields: fields
                .iter()
                .map(|(n, v)| (n.clone(), substitute_expr(v, tp, ta)))
                .collect(),
        },
        other => other.clone(),
    }
}
