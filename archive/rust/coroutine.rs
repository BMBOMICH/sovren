use inkwell::builder::Builder;
/// LLVM Coroutine lowering for Sovereign async tasks.
///
/// LLVM coroutines work by splitting a function at every suspend point
/// (every `await` expression) into a state machine via these intrinsics:
///
///   llvm.coro.id     — marks the coroutine
///   llvm.coro.size   — returns allocation size for the frame
///   llvm.coro.begin  — initializes the coroutine frame
///   llvm.coro.suspend — yields execution (returns i8: 0=normal, 1=final, -1=destroy)
///   llvm.coro.resume — resumes a suspended coroutine
///   llvm.coro.destroy — frees the coroutine frame
///   llvm.coro.done   — checks if the coroutine finished
///   llvm.coro.end    — marks the end of the coroutine
///
/// Sovereign async task:
///
///   async task fetch(url: string) -> int {
///       set conn = connect(url)
///       await sleep(100)        ← suspend point 1
///       set data = read(conn)
///       await process(data)     ← suspend point 2
///       return data
///   }
///
/// Gets lowered to a state machine with 3 states:
///   State 0: entry → connect → suspend at sleep
///   State 1: after sleep → read → suspend at process
///   State 2: after process → return
///
/// The frame stores: current_state (i32) + all live variables at each suspend.
use inkwell::context::Context;
use inkwell::module::Module;
use inkwell::types::BasicTypeEnum;
use inkwell::values::{FunctionValue, PointerValue};

/// Names of all LLVM coroutine intrinsics we use
pub const CORO_ID: &str = "llvm.coro.id";
pub const CORO_SIZE: &str = "llvm.coro.size.i64";
pub const CORO_BEGIN: &str = "llvm.coro.begin";
pub const CORO_SUSPEND: &str = "llvm.coro.suspend";
pub const CORO_END: &str = "llvm.coro.end";
pub const CORO_FREE: &str = "llvm.coro.free";
pub const CORO_DONE: &str = "llvm.coro.done";
pub const CORO_RESUME: &str = "llvm.coro.resume";
pub const CORO_DESTROY: &str = "llvm.coro.destroy";
pub const CORO_PROMISE: &str = "llvm.coro.promise";

/// Declare all coroutine intrinsics in the module.
/// Must be called once before any async task is compiled.
pub fn declare_coro_intrinsics<'ctx>(context: &'ctx Context, module: &Module<'ctx>) {
    let i8_type = context.i8_type();
    let i32_type = context.i32_type();
    let i64_type = context.i64_type();
    let i1_type = context.bool_type();
    let ptr_type = context.ptr_type(inkwell::AddressSpace::default());
    let token_type = context.struct_type(&[], false); // token type approximation

    // llvm.coro.id(align i32, promise ptr, corofn ptr, prefetch ptr) -> token
    if module.get_function(CORO_ID).is_none() {
        let ty = token_type.fn_type(
            &[
                i32_type.into(),
                ptr_type.into(),
                ptr_type.into(),
                ptr_type.into(),
            ],
            false,
        );
        module.add_function(CORO_ID, ty, None);
    }

    // llvm.coro.size.i64() -> i64
    if module.get_function(CORO_SIZE).is_none() {
        let ty = i64_type.fn_type(&[], false);
        module.add_function(CORO_SIZE, ty, None);
    }

    // llvm.coro.begin(id token, mem ptr) -> ptr
    if module.get_function(CORO_BEGIN).is_none() {
        let ty = ptr_type.fn_type(&[ptr_type.into(), ptr_type.into()], false);
        module.add_function(CORO_BEGIN, ty, None);
    }

    // llvm.coro.suspend(save token, final i1) -> i8
    if module.get_function(CORO_SUSPEND).is_none() {
        let ty = i8_type.fn_type(&[ptr_type.into(), i1_type.into()], false);
        module.add_function(CORO_SUSPEND, ty, None);
    }

    // llvm.coro.end(handle ptr, unwind i1) -> i1
    if module.get_function(CORO_END).is_none() {
        let ty = i1_type.fn_type(&[ptr_type.into(), i1_type.into()], false);
        module.add_function(CORO_END, ty, None);
    }

    // llvm.coro.free(id token, handle ptr) -> ptr
    if module.get_function(CORO_FREE).is_none() {
        let ty = ptr_type.fn_type(&[ptr_type.into(), ptr_type.into()], false);
        module.add_function(CORO_FREE, ty, None);
    }

    // llvm.coro.done(handle ptr) -> i1
    if module.get_function(CORO_DONE).is_none() {
        let ty = i1_type.fn_type(&[ptr_type.into()], false);
        module.add_function(CORO_DONE, ty, None);
    }

    // llvm.coro.resume(handle ptr) -> void
    if module.get_function(CORO_RESUME).is_none() {
        let ty = context.void_type().fn_type(&[ptr_type.into()], false);
        module.add_function(CORO_RESUME, ty, None);
    }

    // llvm.coro.destroy(handle ptr) -> void
    if module.get_function(CORO_DESTROY).is_none() {
        let ty = context.void_type().fn_type(&[ptr_type.into()], false);
        module.add_function(CORO_DESTROY, ty, None);
    }
}

/// Information about a compiled coroutine
pub struct CoroInfo<'ctx> {
    /// The coroutine function itself (takes no args, returns ptr = handle)
    pub coro_fn: FunctionValue<'ctx>,
    /// The handle pointer type
    pub handle_ty: BasicTypeEnum<'ctx>,
}

/// Count the number of await expressions in a block (= number of suspend points)
pub fn count_await_points(block: &crate::ast::Block) -> usize {
    let mut count = 0;
    for stmt in &block.statements {
        count += count_await_in_stmt(stmt);
    }
    if let Some(tail) = &block.tail_expr {
        count += count_await_in_expr(tail);
    }
    count
}

fn count_await_in_stmt(stmt: &crate::ast::Stmt) -> usize {
    use crate::ast::Stmt;
    match stmt {
        Stmt::VarDecl { value, .. } | Stmt::Assign { value, .. } => count_await_in_expr(value),
        Stmt::ExprStmt(e) | Stmt::Print(e) | Stmt::Return(Some(e)) => count_await_in_expr(e),
        Stmt::Check {
            condition,
            then_block,
            else_block,
        } => {
            count_await_in_expr(condition)
                + count_await_points(then_block)
                + else_block.as_ref().map_or(0, count_await_points)
        }
        Stmt::Loop { body, .. } => count_await_points(body),
        _ => 0,
    }
}

fn count_await_in_expr(expr: &crate::ast::Expr) -> usize {
    use crate::ast::Expr;
    match expr {
        Expr::Await(_) => 1,
        Expr::BinaryOp { left, right, .. } => {
            count_await_in_expr(left) + count_await_in_expr(right)
        }
        Expr::Call { args, .. } => args.iter().map(count_await_in_expr).sum(),
        Expr::UnaryOp { operand, .. } => count_await_in_expr(operand),
        _ => 0,
    }
}

/// Emit the coroutine prologue (id, size, alloc, begin).
/// Returns (coro_handle, coro_id_token).
pub fn emit_coro_prologue<'ctx>(
    context: &'ctx Context,
    module: &Module<'ctx>,
    builder: &Builder<'ctx>,
    function: FunctionValue<'ctx>,
) -> (PointerValue<'ctx>, inkwell::values::BasicValueEnum<'ctx>) {
    let ptr_type = context.ptr_type(inkwell::AddressSpace::default());
    let i32_type = context.i32_type();
    let i64_type = context.i64_type();
    let i1_false = context.bool_type().const_int(0, false);

    let null_ptr = ptr_type.const_null();
    let align_4 = i32_type.const_int(4, false);

    // %id = call token @llvm.coro.id(i32 4, ptr null, ptr null, ptr null)
    let coro_id_fn = module.get_function(CORO_ID).unwrap();
    let coro_id = builder
        .build_call(
            coro_id_fn,
            &[
                align_4.into(),
                null_ptr.into(),
                null_ptr.into(),
                null_ptr.into(),
            ],
            "coro.id",
        )
        .unwrap()
        .try_as_basic_value()
        .left()
        .unwrap();

    // %size = call i64 @llvm.coro.size.i64()
    let coro_size_fn = module.get_function(CORO_SIZE).unwrap();
    let coro_size = builder
        .build_call(coro_size_fn, &[], "coro.size")
        .unwrap()
        .try_as_basic_value()
        .left()
        .unwrap()
        .into_int_value();

    // %mem = call ptr @malloc(i64 %size)
    let malloc_fn = module.get_function("malloc").unwrap();
    let mem = builder
        .build_call(malloc_fn, &[coro_size.into()], "coro.mem")
        .unwrap()
        .try_as_basic_value()
        .left()
        .unwrap();

    // %hdl = call ptr @llvm.coro.begin(token %id, ptr %mem)
    let coro_begin_fn = module.get_function(CORO_BEGIN).unwrap();
    let hdl = builder
        .build_call(coro_begin_fn, &[coro_id.into(), mem.into()], "coro.hdl")
        .unwrap()
        .try_as_basic_value()
        .left()
        .unwrap()
        .into_pointer_value();

    (hdl, coro_id)
}

/// Emit a suspend point. Returns the switch value (i8).
/// After this call, the builder is positioned in the "resume" block.
pub fn emit_suspend_point<'ctx>(
    context: &'ctx Context,
    module: &Module<'ctx>,
    builder: &Builder<'ctx>,
    function: FunctionValue<'ctx>,
    coro_hdl: PointerValue<'ctx>,
    is_final: bool,
) -> inkwell::values::IntValue<'ctx> {
    let i8_type = context.i8_type();
    let i1_type = context.bool_type();
    let ptr_type = context.ptr_type(inkwell::AddressSpace::default());

    let is_final_val = i1_type.const_int(is_final as u64, false);
    let null_token = ptr_type.const_null();

    // %sv = call i8 @llvm.coro.suspend(token none, i1 false)
    let suspend_fn = module.get_function(CORO_SUSPEND).unwrap();
    let sv = builder
        .build_call(
            suspend_fn,
            &[null_token.into(), is_final_val.into()],
            "coro.suspend",
        )
        .unwrap()
        .try_as_basic_value()
        .left()
        .unwrap()
        .into_int_value();

    // switch i8 %sv:
    //   0  → resume_bb   (normal resume)
    //   1  → cleanup_bb  (final suspend, coroutine done)
    //  -1  → unwind_bb   (destroy without resume)
    let resume_bb = context.append_basic_block(function, "coro.resume");
    let cleanup_bb = context.append_basic_block(function, "coro.cleanup");
    let unwind_bb = context.append_basic_block(function, "coro.unwind");

    let switch = builder.build_switch(sv, unwind_bb, 2).unwrap();
    switch.add_case(i8_type.const_int(0, false), resume_bb);
    switch.add_case(i8_type.const_int(1, false), cleanup_bb);

    // cleanup_bb: free the frame and return
    builder.position_at_end(cleanup_bb);
    emit_coro_cleanup(context, module, builder, function, coro_hdl);

    // unwind_bb: same as cleanup
    builder.position_at_end(unwind_bb);
    emit_coro_cleanup(context, module, builder, function, coro_hdl);

    // Continue compilation in resume_bb
    builder.position_at_end(resume_bb);

    sv
}

fn emit_coro_cleanup<'ctx>(
    context: &'ctx Context,
    module: &Module<'ctx>,
    builder: &Builder<'ctx>,
    function: FunctionValue<'ctx>,
    coro_hdl: PointerValue<'ctx>,
) {
    let i1_false = context.bool_type().const_int(0, false);

    // %mem = call ptr @llvm.coro.free(token %id, ptr %hdl)
    if let Some(free_fn) = module.get_function(CORO_FREE) {
        let null = context
            .ptr_type(inkwell::AddressSpace::default())
            .const_null();
        let mem = builder
            .build_call(free_fn, &[null.into(), coro_hdl.into()], "coro.free.mem")
            .unwrap()
            .try_as_basic_value()
            .left()
            .unwrap();
        // free(mem)
        if let Some(libc_free) = module.get_function("free") {
            let _ = builder.build_call(libc_free, &[mem.into()], "");
        }
    }

    // call void @llvm.coro.end(ptr %hdl, i1 false)
    if let Some(end_fn) = module.get_function(CORO_END) {
        let _ = builder.build_call(end_fn, &[coro_hdl.into(), i1_false.into()], "");
    }

    let _ = builder.build_return(Some(&coro_hdl));
}

/// Emit a final return for a coroutine (replaces normal return).
pub fn emit_coro_final_return<'ctx>(
    context: &'ctx Context,
    module: &Module<'ctx>,
    builder: &Builder<'ctx>,
    function: FunctionValue<'ctx>,
    coro_hdl: PointerValue<'ctx>,
) {
    // Final suspend point — tells LLVM this coroutine is done
    emit_suspend_point(context, module, builder, function, coro_hdl, true);
    // After final suspend, return the handle (caller can .destroy() it)
    if !builder
        .get_insert_block()
        .unwrap()
        .get_terminator()
        .is_some()
    {
        let _ = builder.build_return(Some(&coro_hdl));
    }
}
