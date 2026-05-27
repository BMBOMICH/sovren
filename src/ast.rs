#[derive(Debug, PartialEq, Clone)]
pub struct Program {
    pub statements: Vec<Stmt>,
}

#[derive(Debug, PartialEq, Clone)]
pub enum Stmt {
    VarDecl {
        name: String,
        ty: Option<Type>,
        value: Expr,
        sensitive: bool,
    },
    ConstDecl {
        name: String,
        value: Expr,
    },
    TypeAlias {
        name: String,
        ty: Type,
    },
    Assign {
        name: String,
        value: Expr,
    },
    CompoundAssign {
        name: String,
        op: BinOp,
        value: Expr,
    },
    MultiAssign {
        names: Vec<String>,
        values: Vec<Expr>,
    },
    Destructure {
        fields: Vec<String>,
        from_struct: Option<String>,
        value: Expr,
    },
    FieldAssign {
        object: String,
        field: String,
        value: Expr,
    },
    IndexAssign {
        array: String,
        index: Expr,
        value: Expr,
    },
    TaskDecl {
        name: String,
        type_params: Vec<String>,
        constraints: Vec<(String, Vec<String>)>, // (type_param, constraint_names)
        params: Vec<(String, Type)>,
        return_type: Type,
        body: Block,
        is_inline: bool,
        is_async: bool,
    },
    ExternDecl {
        name: String,
        params: Vec<Type>,
        return_type: Type,
        variadic: bool,
    },
    StructDecl {
        name: String,
        type_params: Vec<String>,
        fields: Vec<(String, Type)>,
    },
    EnumDecl {
        name: String,
        variants: Vec<EnumVariant>,
    },
    NamespaceDecl {
        name: String,
        body: Vec<Stmt>,
    },
    UseDecl {
        path: Vec<String>,
    },
    TestDecl {
        name: String,
        body: Block,
    },
    Check {
        condition: Expr,
        then_block: Block,
        else_block: Option<Block>,
    },
    Loop {
        kind: LoopKind,
        body: Block,
    },
    Match {
        value: Expr,
        arms: Vec<MatchArm>,
    },
    Override {
        body: Block,
    },
    ConstantTime {
        body: Block,
    },
    Spawn {
        var: Option<String>,
        body: Block,
    },
    Join {
        handle: Expr,
    },
    Defer {
        body: Block,
    },
    Assert {
        condition: Expr,
        message: Option<String>,
    },
    StaticAssert {
        condition: Expr,
        message: Option<String>,
    },
    Purge {
        variable: String,
    },
    Free {
        ptr: Expr,
    },
    Break,
    Continue,
    Print(Expr),
    PrintFmt {
        format: String,
        args: Vec<Expr>,
    },
    Return(Option<Expr>),
    Asm(String),
    Import(String),
    ExprStmt(Expr),
}

#[derive(Debug, PartialEq, Clone)]
pub struct EnumVariant {
    pub name: String,
    pub fields: Vec<Type>, // for enum variants with data: Some(int)
}

#[derive(Debug, PartialEq, Clone)]
pub struct MatchArm {
    pub pattern: Pattern,
    pub body: Block,
}

#[derive(Debug, PartialEq, Clone)]
pub enum Pattern {
    EnumVariant(String),
    EnumVariantCapture {
        variant: String,
        bindings: Vec<String>,
    },
    IntLiteral(i64),
    BoolLiteral(bool),
    StringLiteral(String),
    Range(i64, i64),
    Tuple(Vec<Pattern>),
    Wildcard,
}

#[derive(Debug, PartialEq, Clone)]
pub enum LoopKind {
    Infinite,
    Times(Expr),
    FromTo { var: String, from: Expr, to: Expr },
    Range { var: String, range: Expr },
    ForEach { var: String, iterable: Expr },
    While(Expr),
}

#[derive(Debug, PartialEq, Clone)]
pub struct Block {
    pub statements: Vec<Stmt>,
    pub tail_expr: Option<Expr>,
}

#[derive(Debug, PartialEq, Clone)]
pub enum Expr {
    // Literals
    Integer(i64),
    Float(f64),
    Boolean(bool),
    StringLiteral(String),
    InterpolatedString(Vec<StringPart>),
    Null,
    // Collections
    Tuple(Vec<Expr>),
    Array(Vec<Expr>),
    // Variables & access
    Identifier(String),
    NamespacedIdent {
        namespace: String,
        name: String,
    },
    EnumVariant {
        enum_name: String,
        variant: String,
    },
    FieldAccess {
        object: Box<Expr>,
        field: String,
    },
    TupleIndex {
        tuple: Box<Expr>,
        index: usize,
    },
    StructLiteral {
        name: String,
        fields: Vec<(String, Expr)>,
    },
    // Operations
    BinaryOp {
        left: Box<Expr>,
        op: BinOp,
        right: Box<Expr>,
    },
    UnaryOp {
        op: UnaryOp,
        operand: Box<Expr>,
    },
    Cast {
        expr: Box<Expr>,
        to: Type,
    },
    // String operations (built-in)
    StrLen(Box<Expr>),
    StrConcat(Box<Expr>, Box<Expr>),
    StrSlice {
        s: Box<Expr>,
        start: Box<Expr>,
        end: Box<Expr>,
    },
    StrContains {
        s: Box<Expr>,
        needle: Box<Expr>,
    },
    StrToInt(Box<Expr>),
    IntToStr(Box<Expr>),
    // Error handling
    OkExpr(Box<Expr>),
    ErrExpr(Box<Expr>),
    IsOk(Box<Expr>),
    Unwrap(Box<Expr>),
    PropagateErr(Box<Expr>), // expr? — propagate error
    // Closures & async
    Closure {
        params: Vec<(String, Option<Type>)>,
        body: Box<Expr>,
    },
    Await(Box<Expr>),
    // Comptime
    Comptime(Box<Expr>),
    // Memory
    Nullable(Box<Expr>),
    Range {
        start: Box<Expr>,
        end: Box<Expr>,
        inclusive: bool,
    },
    Call {
        func: Box<Expr>,
        args: Vec<Expr>,
        named: Vec<(String, Expr)>,
    },
    Alloc {
        count: Box<Expr>,
        size: Box<Expr>,
    },
    Index {
        array: Box<Expr>,
        index: Box<Expr>,
    },
    Copy(Box<Expr>),
    AddressOf(Box<Expr>),
    Deref(Box<Expr>),
    // Min/max/abs built-ins
    Min(Box<Expr>, Box<Expr>),
    Max(Box<Expr>, Box<Expr>),
    Abs(Box<Expr>),
}

#[derive(Debug, PartialEq, Clone)]
pub enum StringPart {
    Literal(String),
    Interpolated(Expr),
}

#[derive(Debug, PartialEq, Clone)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Eq,
    Neq,
    Lt,
    Gt,
    Le,
    Ge,
    And,
    Or,
    BitAnd,
    BitOr,
    BitXor,
    Shl,
    Shr,
}

#[derive(Debug, PartialEq, Clone)]
pub enum UnaryOp {
    Neg,
    Not,
    BitNot,
}

#[derive(Debug, PartialEq, Clone)]
pub enum Type {
    // Primitive
    Int,
    Int8,
    Int16,
    Int64,
    Uint8,
    Uint16,
    Uint32,
    Uint64,
    Float,
    Float32,
    Bool,
    // String as owned type (not just ptr)
    String,
    // Collections
    Array(Box<Type>),
    Slice(Box<Type>), // &[T] — view into array
    Tuple(Vec<Type>),
    // Pointer
    Ptr,
    // User-defined
    Struct(String),
    Enum(String),
    // Error handling
    Result(Box<Type>),
    Nullable(Box<Type>),
    // Generics
    Generic(String),
    // Function type
    Fn(Vec<Type>, Box<Type>),
    // Async
    Async(Box<Type>),
    Void,
}

impl Type {
    pub fn substitute(&self, param: &str, concrete: &Type) -> Type {
        match self {
            Type::Generic(name) if name == param => concrete.clone(),
            Type::Array(inner) => Type::Array(Box::new(inner.substitute(param, concrete))),
            Type::Slice(inner) => Type::Slice(Box::new(inner.substitute(param, concrete))),
            Type::Tuple(types) => Type::Tuple(
                types
                    .iter()
                    .map(|t| t.substitute(param, concrete))
                    .collect(),
            ),
            Type::Result(inner) => Type::Result(Box::new(inner.substitute(param, concrete))),
            Type::Nullable(inner) => Type::Nullable(Box::new(inner.substitute(param, concrete))),
            Type::Async(inner) => Type::Async(Box::new(inner.substitute(param, concrete))),
            other => other.clone(),
        }
    }
    // Add to Type enum:
    Chan(Box<Type>),  // channel for sending T between threads

    // Add to Expr enum:
    MakeChan(Box<Type>),            // make_chan() -> chan T
    ChanSend { chan: Box<Expr>, value: Box<Expr> }, // send(chan, val)
    ChanRecv(Box<Expr>),            // recv(chan) -> T

    // Add to Stmt enum:
    ChanDecl { name: String, ty: Type },

    pub fn bit_width(&self) -> u32 {
        match self {
            Type::Int8 | Type::Uint8 => 8,
            Type::Int16 | Type::Uint16 => 16,
            Type::Int | Type::Uint32 => 32,
            Type::Int64 | Type::Uint64 => 64,
            _ => 32,
        }
    }

    pub fn is_signed(&self) -> bool {
        matches!(self, Type::Int | Type::Int8 | Type::Int16 | Type::Int64)
    }
}
