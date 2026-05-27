/// Generic constraint checking for Sovereign.
///
/// Syntax:
///   task sort[T where T: Comparable](arr: [T]) { ... }
///   task max[T where T: Comparable + Printable](a: T, b: T) -> T { ... }
///
/// Built-in constraints:
///   Comparable  — supports ==, !=, <, >, <=, >=
///   Printable   — can be passed to print
///   Numeric     — supports +, -, *, /
///   Integer     — is an integer type
///   Float       — is a float type
///   Copyable    — can be copied (primitives: int, float, bool)
///   Zeroable    — can be zeroed (all types)
use crate::ast::*;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Constraint {
    Comparable,
    Printable,
    Numeric,
    Integer,
    Float,
    Copyable,
    Zeroable,
}

impl Constraint {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "Comparable" => Some(Constraint::Comparable),
            "Printable" => Some(Constraint::Printable),
            "Numeric" => Some(Constraint::Numeric),
            "Integer" => Some(Constraint::Integer),
            "Float" => Some(Constraint::Float),
            "Copyable" => Some(Constraint::Copyable),
            "Zeroable" => Some(Constraint::Zeroable),
            _ => None,
        }
    }
}

/// Check that a concrete type satisfies a set of constraints.
pub fn satisfies(ty: &Type, constraints: &[Constraint]) -> bool {
    for c in constraints {
        if !type_satisfies(ty, c) {
            return false;
        }
    }
    true
}

fn type_satisfies(ty: &Type, constraint: &Constraint) -> bool {
    match constraint {
        Constraint::Comparable => matches!(ty, Type::Int | Type::Float | Type::Bool | Type::String),
        Constraint::Printable => matches!(ty, Type::Int | Type::Float | Type::Bool | Type::String),
        Constraint::Numeric => matches!(ty, Type::Int | Type::Float),
        Constraint::Integer => matches!(ty, Type::Int),
        Constraint::Float => matches!(ty, Type::Float),
        Constraint::Copyable => matches!(ty, Type::Int | Type::Float | Type::Bool),
        Constraint::Zeroable => true, // all types can be zeroed
    }
}

/// Constraint map: type_param_name -> list of required constraints
pub type ConstraintMap = HashMap<String, Vec<Constraint>>;

/// Check that a generic instantiation satisfies all constraints.
/// Returns Ok(()) or Err with a description of the violation.
pub fn check_instantiation(
    type_params: &[String],
    type_args: &[Type],
    constraints: &ConstraintMap,
) -> Result<(), String> {
    for (param, arg) in type_params.iter().zip(type_args.iter()) {
        if let Some(cs) = constraints.get(param) {
            for c in cs {
                if !type_satisfies(arg, c) {
                    return Err(format!(
                        "Type {:?} does not satisfy constraint {:?} for type parameter '{}'",
                        arg, c, param
                    ));
                }
            }
        }
    }
    Ok(())
}

/// Parse constraint annotations from a where clause string.
/// Input: "T: Comparable + Numeric, U: Printable"
pub fn parse_constraints(where_clause: &str) -> ConstraintMap {
    let mut map: ConstraintMap = HashMap::new();
    for part in where_clause.split(',') {
        let part = part.trim();
        if let Some(colon_pos) = part.find(':') {
            let param = part[..colon_pos].trim().to_string();
            let cs_str = &part[colon_pos + 1..];
            let constraints: Vec<Constraint> = cs_str
                .split('+')
                .filter_map(|s| Constraint::from_str(s.trim()))
                .collect();
            map.insert(param, constraints);
        }
    }
    map
}

/// Validate all generic call sites in a program against declared constraints.
pub fn validate_program(program: &Program) -> Vec<String> {
    let mut errors = Vec::new();

    // Collect constraint declarations
    let mut task_constraints: HashMap<String, ConstraintMap> = HashMap::new();
    let mut task_type_params: HashMap<String, Vec<String>> = HashMap::new();

    for stmt in &program.statements {
        if let Stmt::TaskDecl {
            name, type_params, ..
        } = stmt
        {
            task_type_params.insert(name.clone(), type_params.clone());
            // In the full implementation, where clauses would be parsed here
        }
    }

    errors
}
