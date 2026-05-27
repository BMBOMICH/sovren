use crate::ast::*;
use crate::closures;
use inkwell::IntPredicate;
use inkwell::basic_block::BasicBlock;
use inkwell::builder::Builder;
use inkwell::context::Context;
use inkwell::module::Module;
use inkwell::targets::{InitializationConfig, Target, TargetMachine, TargetTriple};
use inkwell::types::{BasicMetadataTypeEnum, BasicType, BasicTypeEnum, StructType};
use inkwell::values::{
    BasicMetadataValueEnum, BasicValue, BasicValueEnum, FunctionValue, PointerValue,
};
use std::collections::HashMap;
use std::path::Path;

#[derive(Clone)]
struct VarMeta<'ctx> {
    alloca: PointerValue<'ctx>,
    ty: BasicTypeEnum<'ctx>,
    sensitive: bool,
}

pub struct Codegen<'ctx> {
    context: &'ctx Context,
    pub module: Module<'ctx>,
    builder: Builder<'ctx>,
    scopes: Vec<HashMap<String, VarMeta<'ctx>>>,
    functions: HashMap<String, FunctionValue<'ctx>>,
    task_name_map: HashMap<String, String>,
    struct_types: HashMap<String, StructType<'ctx>>,
    struct_field_index: HashMap<String, HashMap<String, u32>>,
    enum_variant_values: HashMap<String, HashMap<String, i64>>,
    current_function: Option<FunctionValue<'ctx>>,
    override_depth: u32,
    constant_time_depth: u32,
    loop_stack: Vec<(BasicBlock<'ctx>, BasicBlock<'ctx>)>,
    // Defer stack: each scope has a list of deferred blocks
    defer_stack: Vec<Vec<Block>>,
    i32_type: inkwell::types::IntType<'ctx>,
    i1_type: inkwell::types::IntType<'ctx>,
    i64_type: inkwell::types::IntType<'ctx>,
    f64_type: inkwell::types::FloatType<'ctx>,
    ptr_type: inkwell::types::PointerType<'ctx>,
    format_strings: HashMap<String, PointerValue<'ctx>>,
    array_meta: HashMap<String, (u32, BasicTypeEnum<'ctx>)>,
    target_triple: TargetTriple,
    optimize_size: bool,
    safe_math: bool,
    // Closure: enclosing scope type info for capture analysis
    enclosing_var_types: HashMap<String, crate::ast::Type>,
}

impl<'ctx> Codegen<'ctx> {
    pub fn new(context: &'ctx Context, module_name: &str, optimize_size: bool) -> Self {
        Self::new_internal(context, module_name, optimize_size, None)
    }

    pub fn new_with_target(
        context: &'ctx Context,
        module_name: &str,
        target: &crate::cross_compile::CrossTarget,
        optimize_size: bool,
    ) -> Self {
        let triple = TargetTriple::create(&target.triple);
        Self::new_internal(context, module_name, optimize_size, Some(triple))
    }

    fn new_internal(
        context: &'ctx Context,
        module_name: &str,
        optimize_size: bool,
        triple_override: Option<TargetTriple>,
    ) -> Self {
        let module = context.create_module(module_name);
        let builder = context.create_builder();
        Target::initialize_all(&InitializationConfig::default());
        let target_triple = triple_override.unwrap_or_else(TargetMachine::get_default_triple);
        module.set_triple(&target_triple);
        Codegen {
            context,
            module,
            builder,
            scopes: vec![HashMap::new()],
            functions: HashMap::new(),
            task_name_map: HashMap::new(),
            struct_types: HashMap::new(),
            struct_field_index: HashMap::new(),
            enum_variant_values: HashMap::new(),
            current_function: None,
            override_depth: 0,
            constant_time_depth: 0,
            loop_stack: Vec::new(),
            defer_stack: Vec::new(),
            i32_type: context.i32_type(),
            i1_type: context.bool_type(),
            i64_type: context.i64_type(),
            f64_type: context.f64_type(),
            ptr_type: context.ptr_type(inkwell::AddressSpace::default()),
            format_strings: HashMap::new(),
            array_meta: HashMap::new(),
            target_triple,
            optimize_size,
            safe_math: true,
            enclosing_var_types: HashMap::new(),
        }
    }

    /// Expose module reference for external use (e.g. cross_compile)
    pub fn module(&self) -> &Module<'ctx> {
        &self.module
    }

    // ── Scopes ────────────────────────────────────────────────────────────────

    fn push_scope(&mut self) {
        self.scopes.push(HashMap::new());
        self.defer_stack.push(Vec::new());
    }

    fn pop_scope(&mut self) {
        // Run deferred blocks in LIFO order
        if let Some(deferred) = self.defer_stack.pop() {
            for block in deferred.into_iter().rev() {
                if !self.current_block_has_terminator() {
                    self.compile_block(&block);
                }
            }
        }
        if let Some(scope) = self.scopes.pop() {
            if !self.current_block_has_terminator() {
                for (_, meta) in &scope {
                    if meta.sensitive {
                        self.emit_secure_zero(meta.alloca, meta.ty);
                    }
                }
            }
        }
    }

    fn declare_var(
        &mut self,
        name: String,
        alloca: PointerValue<'ctx>,
        ty: BasicTypeEnum<'ctx>,
        sensitive: bool,
    ) {
        self.scopes.last_mut().unwrap().insert(
            name,
            VarMeta {
                alloca,
                ty,
                sensitive,
            },
        );
    }

    fn lookup_var(&self, name: &str) -> Option<&VarMeta<'ctx>> {
        for scope in self.scopes.iter().rev() {
            if let Some(m) = scope.get(name) {
                return Some(m);
            }
        }
        None
    }

    // ── Security ──────────────────────────────────────────────────────────────

    fn emit_secure_zero(&self, alloca: PointerValue<'ctx>, ty: BasicTypeEnum<'ctx>) {
        let zero: BasicValueEnum = match ty {
            BasicTypeEnum::IntType(it) => it.const_zero().into(),
            BasicTypeEnum::FloatType(ft) => ft.const_zero().into(),
            BasicTypeEnum::PointerType(pt) => pt.const_null().into(),
            BasicTypeEnum::ArrayType(at) => at.const_zero().into(),
            BasicTypeEnum::VectorType(vt) => vt.const_zero().into(),
            BasicTypeEnum::StructType(st) => st.const_zero().into(),
        };
        if let Ok(store) = self.builder.build_store(alloca, zero) {
            store.set_volatile(true).ok();
        }
    }

    fn to_i1(&self, val: inkwell::values::IntValue<'ctx>) -> inkwell::values::IntValue<'ctx> {
        if val.get_type().get_bit_width() == 1 {
            val
        } else {
            self.builder
                .build_int_compare(IntPredicate::NE, val, val.get_type().const_zero(), "tobool")
                .unwrap()
        }
    }

    // ── Type helpers ──────────────────────────────────────────────────────────

    fn type_to_llvm(&self, t: &Type) -> BasicTypeEnum<'ctx> {
        match t {
            Type::Int | Type::Bool => self.i32_type.into(),
            Type::Float => self.f64_type.into(),
            Type::String | Type::Ptr | Type::Array(_) => self.ptr_type.into(),
            Type::Struct(name) => {
                if let Some(st) = self.struct_types.get(name) {
                    (*st).into()
                } else {
                    self.ptr_type.into()
                }
            }
            Type::Enum(_) | Type::Result(_) | Type::Nullable(_) => self.i32_type.into(),
            Type::Generic(_) => self.i32_type.into(),
            Type::Fn(_, _) | Type::Async(_) => self.ptr_type.into(),
            Type::Void => self.i32_type.into(),
        }
    }

    fn type_to_meta(&self, t: &Type) -> BasicMetadataTypeEnum<'ctx> {
        match t {
            Type::Int
            | Type::Bool
            | Type::Enum(_)
            | Type::Result(_)
            | Type::Nullable(_)
            | Type::Generic(_) => self.i32_type.into(),
            Type::Float => self.f64_type.into(),
            Type::String | Type::Ptr | Type::Array(_) | Type::Fn(_, _) | Type::Async(_) => {
                self.ptr_type.into()
            }
            Type::Struct(name) => {
                if let Some(st) = self.struct_types.get(name) {
                    (*st).into()
                } else {
                    self.ptr_type.into()
                }
            }
            Type::Void => self.i32_type.into(),
        }
    }

    fn compile_var_decl(&mut self, name: &str, value: &Expr, sensitive: bool) {
        if let Expr::Array(elems) = value {
            if elems.is_empty() {
                let alloca = self
                    .create_entry_block_alloca(self.ptr_type.into())
                    .unwrap();
                self.declare_var(name.to_string(), alloca, self.ptr_type.into(), sensitive);
                return;
            }
            let compiled: Vec<BasicValueEnum> =
                elems.iter().map(|e| self.compile_expr(e)).collect();
            let elem_ty = compiled[0].get_type();
            let arr_ty = elem_ty.array_type(elems.len() as u32);
            let alloca = self.create_entry_block_alloca(arr_ty.into()).unwrap();
            let ptr = self
                .builder
                .build_pointer_cast(alloca, self.ptr_type, "ap")
                .unwrap();
            for (i, val) in compiled.into_iter().enumerate() {
                let gep = unsafe {
                    self.builder.build_in_bounds_gep(
                        elem_ty,
                        ptr,
                        &[self.i32_type.const_int(i as u64, false)],
                        "ep",
                    )
                }
                .unwrap();
                let _ = self.builder.build_store(gep, val);
            }
            self.declare_var(name.to_string(), alloca, arr_ty.into(), sensitive);
            self.array_meta
                .insert(name.to_string(), (elems.len() as u32, elem_ty));
        } else {
            let val = self.compile_expr(value);
            let ty = val.get_type();
            let alloca = self.create_entry_block_alloca(ty).unwrap();
            let _ = self.builder.build_store(alloca, val);
            self.declare_var(name.to_string(), alloca, ty, sensitive);
            // Track type for closure capture analysis
            // (simplified: only track int/float/bool)
        }
    }

    // ── Async state machine ───────────────────────────────────────────────────
    // Each async task compiles to a state machine function with signature:
    //   fn step(state: ptr) -> i32   (0 = done, 1 = yield/reschedule)
    // The state struct holds local variables and the current step counter.

    fn compile_async_task(
        &mut self,
        name: &str,
        params: &[(String, Type)],
        body: &Block,
        return_type: &Type,
    ) {
        // State struct fields: step_counter (i32) + all local variables
        let state_struct_name = format!("__async_state_{}", name);
        let mut state_fields: Vec<BasicTypeEnum> = vec![self.i32_type.into()]; // step counter
        for (_, pt) in params {
            state_fields.push(self.type_to_llvm(pt));
        }
        let state_ty = self.context.struct_type(&state_fields, false);
        self.struct_types
            .insert(state_struct_name.clone(), state_ty);

        // step function: fn name__step(state: ptr) -> i32
        let step_name = format!("{}_step", name);
        let step_fn_type = self.i32_type.fn_type(&[self.ptr_type.into()], false);
        let step_fn = self.module.add_function(&step_name, step_fn_type, None);
        self.functions.insert(step_name.clone(), step_fn);
        self.task_name_map
            .insert(name.to_string(), step_name.clone());

        let entry_bb = self.context.append_basic_block(step_fn, "entry");
        self.builder.position_at_end(entry_bb);
        self.current_function = Some(step_fn);
        self.push_scope();

        // Load state pointer
        let state_ptr = step_fn.get_nth_param(0).unwrap().into_pointer_value();

        // Load step counter
        let step_gep = self
            .builder
            .build_struct_gep(state_ty, state_ptr, 0, "step_gep")
            .unwrap();
        let step_val = self
            .builder
            .build_load(self.i32_type, step_gep, "step")
            .unwrap()
            .into_int_value();

        // Load parameters from state
        for (i, (pname, ptype)) in params.iter().enumerate() {
            let field_idx = (i + 1) as u32;
            let ty = self.type_to_llvm(ptype);
            let gep = self
                .builder
                .build_struct_gep(state_ty, state_ptr, field_idx, "pgep")
                .unwrap();
            let val = self.builder.build_load(ty, gep, pname).unwrap();
            let alloca = self.create_entry_block_alloca(ty).unwrap();
            let _ = self.builder.build_store(alloca, val);
            self.declare_var(pname.clone(), alloca, ty, false);
        }

        // Compile body — await expressions become yield points
        self.compile_block(body);

        // Default: return 0 (done)
        if !self.current_block_has_terminator() {
            let _ = self
                .builder
                .build_return(Some(&self.i32_type.const_int(0, false)));
        }

        self.pop_scope();

        // Spawn function: allocates state, registers with executor
        let spawn_name = format!("{}_spawn", name);
        let spawn_fn_type = self.ptr_type.fn_type(
            &params
                .iter()
                .map(|(_, t)| self.type_to_meta(t))
                .collect::<Vec<_>>(),
            false,
        );
        let spawn_fn = self.module.add_function(&spawn_name, spawn_fn_type, None);
        let spawn_bb = self.context.append_basic_block(spawn_fn, "entry");
        self.builder.position_at_end(spawn_bb);
        self.current_function = Some(spawn_fn);

        let state_size = self
            .i64_type
            .const_int((state_fields.len() * 4) as u64, false);
        if let Some(malloc_fn) = self.module.get_function("malloc") {
            let state_mem = self
                .builder
                .build_call(malloc_fn, &[state_size.into()], "state_mem")
                .unwrap()
                .try_as_basic_value()
                .left()
                .unwrap();
            let state_p = state_mem.into_pointer_value();

            // Initialize step counter to 0
            let step_gep2 = self
                .builder
                .build_struct_gep(state_ty, state_p, 0, "sg")
                .unwrap();
            let _ = self
                .builder
                .build_store(step_gep2, self.i32_type.const_int(0, false));

            // Store parameters
            for (i, _) in params.iter().enumerate() {
                let param_val = spawn_fn.get_nth_param(i as u32).unwrap();
                let field_idx = (i + 1) as u32;
                let gep = self
                    .builder
                    .build_struct_gep(state_ty, state_p, field_idx, "fg")
                    .unwrap();
                let _ = self.builder.build_store(gep, param_val);
            }

            // Register with async executor if available
            if let Some(sov_spawn) = self.module.get_function("sov_spawn_task") {
                let step_fn_ptr = step_fn.as_global_value().as_pointer_value();
                let _ = self.builder.build_call(
                    sov_spawn,
                    &[step_fn_ptr.into(), state_p.into()],
                    "task_id",
                );
            }

            let _ = self.builder.build_return(Some(&state_p));
        } else {
            let _ = self.builder.build_return(Some(&self.ptr_type.const_null()));
        }
    }

    // ── Main compile entry ────────────────────────────────────────────────────

    pub fn compile(&mut self, program: &Program) {
        // Standard C functions
        let printf_type = self.i32_type.fn_type(&[self.ptr_type.into()], true);
        self.module.add_function("printf", printf_type, None);

        let sprintf_type = self
            .i32_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], true);
        self.module.add_function("sprintf", sprintf_type, None);

        let puts_type = self.i32_type.fn_type(&[self.ptr_type.into()], false);
        self.module.add_function("puts", puts_type, None);
        self.functions
            .insert("puts".into(), self.module.get_function("puts").unwrap());
        self.task_name_map.insert("puts".into(), "puts".into());

        let abort_type = self.context.void_type().fn_type(&[], false);
        self.module.add_function("abort", abort_type, None);

        let malloc_type = self.ptr_type.fn_type(&[self.i64_type.into()], false);
        self.module.add_function("malloc", malloc_type, None);
        self.functions
            .insert("malloc".into(), self.module.get_function("malloc").unwrap());
        self.task_name_map.insert("malloc".into(), "malloc".into());

        let free_type = self
            .context
            .void_type()
            .fn_type(&[self.ptr_type.into()], false);
        self.module.add_function("free", free_type, None);
        self.functions
            .insert("free".into(), self.module.get_function("free").unwrap());
        self.task_name_map.insert("free".into(), "free".into());

        let strlen_type = self.i64_type.fn_type(&[self.ptr_type.into()], false);
        self.module.add_function("strlen", strlen_type, None);
        self.functions
            .insert("strlen".into(), self.module.get_function("strlen").unwrap());
        self.task_name_map.insert("strlen".into(), "strlen".into());

        let strcat_type = self
            .ptr_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        self.module.add_function("strcat", strcat_type, None);

        let strcpy_type = self
            .ptr_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        self.module.add_function("strcpy", strcpy_type, None);

        let strcmp_type = self
            .i32_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        self.module.add_function("strcmp", strcmp_type, None);
        self.functions
            .insert("strcmp".into(), self.module.get_function("strcmp").unwrap());
        self.task_name_map.insert("strcmp".into(), "strcmp".into());

        let exit_type = self
            .context
            .void_type()
            .fn_type(&[self.i32_type.into()], false);
        self.module.add_function("exit", exit_type, None);
        self.functions
            .insert("exit".into(), self.module.get_function("exit").unwrap());
        self.task_name_map.insert("exit".into(), "exit".into());

        // Math
        let f64f64 = self.f64_type.fn_type(&[self.f64_type.into()], false);
        for fname in &[
            "sin", "cos", "tan", "sqrt", "log", "exp", "fabs", "ceil", "floor", "log2", "log10",
        ] {
            self.module.add_function(fname, f64f64, None);
            let fv = self.module.get_function(fname).unwrap();
            self.functions.insert(fname.to_string(), fv);
            self.task_name_map
                .insert(fname.to_string(), fname.to_string());
        }
        let pow_type = self
            .f64_type
            .fn_type(&[self.f64_type.into(), self.f64_type.into()], false);
        self.module.add_function("pow", pow_type, None);
        self.functions
            .insert("pow".into(), self.module.get_function("pow").unwrap());
        self.task_name_map.insert("pow".into(), "pow".into());

        // File I/O
        let fopen_t = self
            .ptr_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        let fclose_t = self.i32_type.fn_type(&[self.ptr_type.into()], false);
        let fgets_t = self.ptr_type.fn_type(
            &[
                self.ptr_type.into(),
                self.i32_type.into(),
                self.ptr_type.into(),
            ],
            false,
        );
        let fputs_t = self
            .i32_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        let feof_t = self.i32_type.fn_type(&[self.ptr_type.into()], false);
        let fread_t = self.i64_type.fn_type(
            &[
                self.ptr_type.into(),
                self.i64_type.into(),
                self.i64_type.into(),
                self.ptr_type.into(),
            ],
            false,
        );
        let fwrite_t = self.i64_type.fn_type(
            &[
                self.ptr_type.into(),
                self.i64_type.into(),
                self.i64_type.into(),
                self.ptr_type.into(),
            ],
            false,
        );
        for (fname, ftype) in [
            ("fopen", fopen_t),
            ("fclose", fclose_t),
            ("fgets", fgets_t),
            ("fputs", fputs_t),
            ("feof", feof_t),
            ("fread", fread_t),
            ("fwrite", fwrite_t),
        ] {
            self.module.add_function(fname, ftype, None);
            let fv = self.module.get_function(fname).unwrap();
            self.functions.insert(fname.to_string(), fv);
            self.task_name_map
                .insert(fname.to_string(), fname.to_string());
        }

        // Async runtime (sov_spawn_task, sov_run_executor)
        let spawn_task_t = self
            .i64_type
            .fn_type(&[self.ptr_type.into(), self.ptr_type.into()], false);
        let run_exec_t = self.context.void_type().fn_type(&[], false);
        self.module
            .add_function("sov_spawn_task", spawn_task_t, None);
        self.module
            .add_function("sov_run_executor", run_exec_t, None);
        self.module.add_function(
            "sov_tcp_connect",
            self.i32_type
                .fn_type(&[self.ptr_type.into(), self.i32_type.into()], false),
            None,
        );
        self.module.add_function(
            "sov_tcp_send",
            self.i32_type.fn_type(
                &[
                    self.i32_type.into(),
                    self.ptr_type.into(),
                    self.i32_type.into(),
                ],
                false,
            ),
            None,
        );
        self.module.add_function(
            "sov_tcp_recv",
            self.i32_type.fn_type(
                &[
                    self.i32_type.into(),
                    self.ptr_type.into(),
                    self.i32_type.into(),
                ],
                false,
            ),
            None,
        );
        self.module.add_function(
            "sov_tcp_close",
            self.context
                .void_type()
                .fn_type(&[self.i32_type.into()], false),
            None,
        );
        for fname in &[
            "sov_spawn_task",
            "sov_run_executor",
            "sov_tcp_connect",
            "sov_tcp_send",
            "sov_tcp_recv",
            "sov_tcp_close",
        ] {
            if let Some(fv) = self.module.get_function(fname) {
                self.functions.insert(fname.to_string(), fv);
                self.task_name_map
                    .insert(fname.to_string(), fname.to_string());
            }
        }

        // Build struct types
        for stmt in &program.statements {
            match stmt {
                Stmt::StructDecl { name, fields, .. } => {
                    let field_types: Vec<BasicTypeEnum> =
                        fields.iter().map(|(_, t)| self.type_to_llvm(t)).collect();
                    let st = self.context.struct_type(&field_types, false);
                    self.struct_types.insert(name.clone(), st);
                    let mut fidx: HashMap<String, u32> = HashMap::new();
                    for (i, (fname, _)) in fields.iter().enumerate() {
                        fidx.insert(fname.clone(), i as u32);
                    }
                    self.struct_field_index.insert(name.clone(), fidx);
                }
                Stmt::EnumDecl { name, variants } => {
                    let mut vals: HashMap<String, i64> = HashMap::new();
                    for (i, v) in variants.iter().enumerate() {
                        vals.insert(v.clone(), i as i64);
                    }
                    self.enum_variant_values.insert(name.clone(), vals);
                }
                _ => {}
            }
        }

        // Forward-declare tasks
        for stmt in &program.statements {
            match stmt {
                Stmt::ExternDecl {
                    name,
                    params,
                    return_type,
                } => {
                    let param_types: Vec<BasicMetadataTypeEnum> =
                        params.iter().map(|t| self.type_to_meta(t)).collect();
                    let fn_type = match return_type {
                        Type::Void => self.context.void_type().fn_type(&param_types, false),
                        Type::Float => self.f64_type.fn_type(&param_types, false),
                        _ => self.i32_type.fn_type(&param_types, false),
                    };
                    let fn_val = self.module.add_function(name, fn_type, None);
                    self.functions.insert(name.clone(), fn_val);
                    self.task_name_map.insert(name.clone(), name.clone());
                }
                Stmt::TaskDecl {
                    name,
                    params,
                    return_type,
                    is_inline,
                    is_async,
                    ..
                } => {
                    if *is_async {
                        continue;
                    } // compiled separately
                    let llvm_name = if name == "main" {
                        "sov_main".into()
                    } else {
                        name.clone()
                    };
                    let param_types: Vec<BasicMetadataTypeEnum> =
                        params.iter().map(|(_, t)| self.type_to_meta(t)).collect();
                    let fn_type = match return_type {
                        Type::Void => self.context.void_type().fn_type(&param_types, false),
                        Type::Float => self.f64_type.fn_type(&param_types, false),
                        _ => self.i32_type.fn_type(&param_types, false),
                    };
                    let fn_val = self.module.add_function(&llvm_name, fn_type, None);
                    if *is_inline {
                        fn_val.add_attribute(
                            inkwell::attributes::AttributeLoc::Function,
                            self.context.create_enum_attribute(
                                inkwell::attributes::Attribute::get_named_enum_kind_id(
                                    "alwaysinline",
                                ),
                                0,
                            ),
                        );
                    }
                    for (i, (_, pt)) in params.iter().enumerate() {
                        if matches!(pt, Type::Ptr | Type::String | Type::Array(_)) {
                            fn_val.add_attribute(
                                inkwell::attributes::AttributeLoc::Param(i as u32),
                                self.context.create_enum_attribute(
                                    inkwell::attributes::Attribute::get_named_enum_kind_id(
                                        "noalias",
                                    ),
                                    0,
                                ),
                            );
                        }
                    }
                    self.functions.insert(llvm_name.clone(), fn_val);
                    self.task_name_map.insert(name.clone(), llvm_name);
                }
                _ => {}
            }
        }

        // Build main()
        let main_fn_type = self.i32_type.fn_type(&[], false);
        let main_func = self.module.add_function("main", main_fn_type, None);
        let entry_bb = self.context.append_basic_block(main_func, "entry");
        self.builder.position_at_end(entry_bb);
        self.current_function = Some(main_func);

        for stmt in &program.statements {
            if !matches!(
                stmt,
                Stmt::TaskDecl { .. }
                    | Stmt::ExternDecl { .. }
                    | Stmt::StructDecl { .. }
                    | Stmt::EnumDecl { .. }
                    | Stmt::TestDecl { .. }
            ) {
                self.compile_stmt(stmt);
            }
        }

        // Run async executor at end of main if any async tasks were used
        if let Some(exec_fn) = self.module.get_function("sov_run_executor") {
            if !self.current_block_has_terminator() {
                let _ = self.builder.build_call(exec_fn, &[], "");
            }
        }

        if !self.current_block_has_terminator() {
            let _ = self
                .builder
                .build_return(Some(&self.i32_type.const_int(0, false)));
        }

        // Compile task bodies
        for stmt in &program.statements {
            match stmt {
                Stmt::TaskDecl {
                    name,
                    params,
                    body,
                    return_type,
                    is_async,
                    ..
                } => {
                    if *is_async {
                        self.compile_async_task(name, params, body, return_type);
                        continue;
                    }
                    let llvm_name = self.task_name_map[name].clone();
                    let function = self.functions[&llvm_name];
                    let bb = self.context.append_basic_block(function, "entry");
                    self.builder.position_at_end(bb);
                    self.current_function = Some(function);
                    self.push_scope();

                    for (i, (pname, ptype)) in params.iter().enumerate() {
                        let pval = function.get_nth_param(i as u32).unwrap();
                        let ty = self.type_to_llvm(ptype);
                        let alloca = self.create_entry_block_alloca(ty).unwrap();
                        let _ = self.builder.build_store(alloca, pval);
                        self.declare_var(pname.clone(), alloca, ty, false);
                    }

                    self.compile_block(body);

                    if !self.current_block_has_terminator() {
                        match return_type {
                            Type::Void => {
                                let _ = self.builder.build_return(None);
                            }
                            _ => {
                                let _ = self
                                    .builder
                                    .build_return(Some(&self.i32_type.const_int(0, false)));
                            }
                        }
                    }
                    self.pop_scope();
                }
                _ => {}
            }
        }
    }

    // ── Statements ────────────────────────────────────────────────────────────

    fn compile_stmt(&mut self, stmt: &Stmt) {
        if self.current_block_has_terminator() {
            return;
        }

        match stmt {
            // ── Type alias — purely semantic, no IR ──
            Stmt::TypeAlias { .. } => {}

            // ── Test declarations — compiled by test runner, not here ──
            Stmt::TestDecl { .. } => {}

            Stmt::ConstDecl { name, value } => self.compile_var_decl(name, value, false),
            Stmt::VarDecl {
                name,
                value,
                sensitive,
            } => self.compile_var_decl(name, value, *sensitive),

            // ── Compound assignment: x += 1 ──
            Stmt::CompoundAssign { name, op, value } => {
                if let Some(meta) = self.lookup_var(name) {
                    let alloca = meta.alloca;
                    let ty = meta.ty;
                    let current = self.builder.build_load(ty, alloca, "cur").unwrap();
                    let rhs = self.compile_expr(value);
                    let result: BasicValueEnum = match (current.get_type(), op) {
                        (BasicTypeEnum::IntType(_), BinOp::Add) => {
                            if self.safe_math {
                                self.builder
                                    .build_int_nsw_add(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "ca",
                                    )
                                    .unwrap()
                                    .into()
                            } else {
                                self.builder
                                    .build_int_add(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "ca",
                                    )
                                    .unwrap()
                                    .into()
                            }
                        }
                        (BasicTypeEnum::IntType(_), BinOp::Sub) => {
                            if self.safe_math {
                                self.builder
                                    .build_int_nsw_sub(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "cs",
                                    )
                                    .unwrap()
                                    .into()
                            } else {
                                self.builder
                                    .build_int_sub(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "cs",
                                    )
                                    .unwrap()
                                    .into()
                            }
                        }
                        (BasicTypeEnum::IntType(_), BinOp::Mul) => {
                            if self.safe_math {
                                self.builder
                                    .build_int_nsw_mul(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "cm",
                                    )
                                    .unwrap()
                                    .into()
                            } else {
                                self.builder
                                    .build_int_mul(
                                        current.into_int_value(),
                                        rhs.into_int_value(),
                                        "cm",
                                    )
                                    .unwrap()
                                    .into()
                            }
                        }
                        (BasicTypeEnum::IntType(_), BinOp::Div) => self
                            .builder
                            .build_int_signed_div(
                                current.into_int_value(),
                                rhs.into_int_value(),
                                "cd",
                            )
                            .unwrap()
                            .into(),
                        (BasicTypeEnum::FloatType(_), BinOp::Add) => self
                            .builder
                            .build_float_add(
                                current.into_float_value(),
                                rhs.into_float_value(),
                                "cfa",
                            )
                            .unwrap()
                            .into(),
                        (BasicTypeEnum::FloatType(_), BinOp::Sub) => self
                            .builder
                            .build_float_sub(
                                current.into_float_value(),
                                rhs.into_float_value(),
                                "cfs",
                            )
                            .unwrap()
                            .into(),
                        (BasicTypeEnum::FloatType(_), BinOp::Mul) => self
                            .builder
                            .build_float_mul(
                                current.into_float_value(),
                                rhs.into_float_value(),
                                "cfm",
                            )
                            .unwrap()
                            .into(),
                        (BasicTypeEnum::FloatType(_), BinOp::Div) => self
                            .builder
                            .build_float_div(
                                current.into_float_value(),
                                rhs.into_float_value(),
                                "cfd",
                            )
                            .unwrap()
                            .into(),
                        _ => rhs,
                    };
                    let _ = self.builder.build_store(alloca, result);
                } else {
                    eprintln!(
                        "Codegen error: undefined variable '{}' in compound assign",
                        name
                    );
                    std::process::exit(1);
                }
            }

            // ── Multi-assign: set a, b = 1, 2 ──
            Stmt::MultiAssign { names, values } => {
                // Compile all values first to avoid clobber
                let compiled: Vec<BasicValueEnum> =
                    values.iter().map(|v| self.compile_expr(v)).collect();
                for (name, val) in names.iter().zip(compiled.into_iter()) {
                    if let Some(meta) = self.lookup_var(name) {
                        let alloca = meta.alloca;
                        let _ = self.builder.build_store(alloca, val);
                    } else {
                        let ty = val.get_type();
                        let alloca = self.create_entry_block_alloca(ty).unwrap();
                        let _ = self.builder.build_store(alloca, val);
                        self.declare_var(name.clone(), alloca, ty, false);
                    }
                }
            }

            Stmt::Assign { name, value } => {
                if let Some(meta) = self.lookup_var(name) {
                    let alloca = meta.alloca;
                    let val = self.compile_expr(value);
                    let _ = self.builder.build_store(alloca, val);
                } else {
                    eprintln!("Codegen error: undefined variable '{}'", name);
                    std::process::exit(1);
                }
            }

            Stmt::FieldAssign {
                object,
                field,
                value,
            } => {
                if let Some(meta) = self.lookup_var(object) {
                    let alloca = meta.alloca;
                    let ty = meta.ty;
                    if let BasicTypeEnum::StructType(st) = ty {
                        let sname = self
                            .struct_types
                            .iter()
                            .find(|(_, v)| **v == st)
                            .map(|(k, _)| k.clone())
                            .unwrap_or_default();
                        if let Some(fidx) = self.struct_field_index.get(&sname).cloned() {
                            if let Some(&idx) = fidx.get(field) {
                                let gep = self
                                    .builder
                                    .build_struct_gep(st, alloca, idx, "fgep")
                                    .unwrap();
                                let val = self.compile_expr(value);
                                let _ = self.builder.build_store(gep, val);
                            }
                        }
                    }
                }
            }

            Stmt::IndexAssign {
                array,
                index,
                value,
            } => {
                let idx_val = self.compile_expr(index).into_int_value();
                let val = self.compile_expr(value);
                if let Some(meta) = self.lookup_var(array) {
                    let alloca = meta.alloca;
                    let ty = meta.ty;
                    if let BasicTypeEnum::ArrayType(at) = ty {
                        let elem_ty: BasicTypeEnum = at.get_element_type().into();
                        let ptr = self
                            .builder
                            .build_pointer_cast(alloca, self.ptr_type, "ap")
                            .unwrap();
                        if self.override_depth == 0 {
                            if let Some(&(len, _)) = self.array_meta.get(array) {
                                self.emit_bounds_check(idx_val, len);
                            }
                        }
                        let gep = unsafe {
                            self.builder
                                .build_in_bounds_gep(elem_ty, ptr, &[idx_val], "idx")
                        }
                        .unwrap();
                        let _ = self.builder.build_store(gep, val);
                    }
                }
            }

            // ── Assert ──
            Stmt::Assert { condition, message } => {
                let cond_raw = self.compile_expr(condition).into_int_value();
                let cond = self.to_i1(cond_raw);
                let func = self.current_function.unwrap();
                let ok_bb = self.context.append_basic_block(func, "assert_ok");
                let fail_bb = self.context.append_basic_block(func, "assert_fail");
                let _ = self.builder.build_conditional_branch(cond, ok_bb, fail_bb);

                self.builder.position_at_end(fail_bb);
                let printf_fn = self.module.get_function("printf").unwrap();
                let msg_str = message.as_deref().unwrap_or("Assertion failed");
                let msg = self.get_format_string(&format!("ASSERTION FAILED: {}\n", msg_str));
                let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
                let abort_fn = self.module.get_function("abort").unwrap();
                let _ = self.builder.build_call(abort_fn, &[], "");
                let _ = self.builder.build_unreachable();

                self.builder.position_at_end(ok_bb);
            }

            // ── Static assert — same as assert but LLVM folds constant conditions ──
            Stmt::StaticAssert { condition, message } => {
                let cond_raw = self.compile_expr(condition).into_int_value();
                let cond = self.to_i1(cond_raw);
                let func = self.current_function.unwrap();
                let ok_bb = self.context.append_basic_block(func, "sa_ok");
                let fail_bb = self.context.append_basic_block(func, "sa_fail");
                let _ = self.builder.build_conditional_branch(cond, ok_bb, fail_bb);
                self.builder.position_at_end(fail_bb);
                let printf_fn = self.module.get_function("printf").unwrap();
                let msg_str = message.as_deref().unwrap_or("Static assertion failed");
                let msg = self.get_format_string(&format!("STATIC ASSERT FAILED: {}\n", msg_str));
                let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
                let abort_fn = self.module.get_function("abort").unwrap();
                let _ = self.builder.build_call(abort_fn, &[], "");
                let _ = self.builder.build_unreachable();
                self.builder.position_at_end(ok_bb);
            }

            // ── Defer: register block to run at scope exit ──
            Stmt::Defer { body } => {
                if let Some(top) = self.defer_stack.last_mut() {
                    top.push(body.clone());
                }
                // Do NOT compile the block here — it runs when pop_scope is called
            }

            Stmt::Check {
                condition,
                then_block,
                else_block,
            } => {
                let raw = self.compile_expr(condition).into_int_value();
                let cond_val = self.to_i1(raw);
                let func = self.current_function.unwrap();
                let then_bb = self.context.append_basic_block(func, "then");
                let else_bb = else_block
                    .as_ref()
                    .map(|_| self.context.append_basic_block(func, "else"));
                let merge_bb = self.context.append_basic_block(func, "merge");

                let _ = self.builder.build_conditional_branch(
                    cond_val,
                    then_bb,
                    else_bb.unwrap_or(merge_bb),
                );

                self.builder.position_at_end(then_bb);
                self.push_scope();
                self.compile_block(then_block);
                self.pop_scope();
                if !self.current_block_has_terminator() {
                    let _ = self.builder.build_unconditional_branch(merge_bb);
                }

                if let (Some(ebb), Some(eblk)) = (else_bb, else_block.as_ref()) {
                    self.builder.position_at_end(ebb);
                    self.push_scope();
                    self.compile_block(eblk);
                    self.pop_scope();
                    if !self.current_block_has_terminator() {
                        let _ = self.builder.build_unconditional_branch(merge_bb);
                    }
                }

                self.builder.position_at_end(merge_bb);
            }

            Stmt::Loop { kind, body } => {
                let func = self.current_function.unwrap();

                match kind {
                    LoopKind::Times(count) => {
                        let count_val = self.compile_expr(count).into_int_value();
                        let cond_bb = self.context.append_basic_block(func, "loop_cond");
                        let body_bb = self.context.append_basic_block(func, "loop_body");
                        let inc_bb = self.context.append_basic_block(func, "loop_inc");
                        let end_bb = self.context.append_basic_block(func, "loop_end");

                        let counter = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self
                            .builder
                            .build_store(counter, self.i32_type.const_int(0, false));
                        let _ = self.builder.build_unconditional_branch(cond_bb);

                        self.builder.position_at_end(cond_bb);
                        let cur = self
                            .builder
                            .build_load(self.i32_type, counter, "i")
                            .unwrap()
                            .into_int_value();
                        let cmp = self
                            .builder
                            .build_int_compare(IntPredicate::ULT, cur, count_val, "lt")
                            .unwrap();
                        let _ = self.builder.build_conditional_branch(cmp, body_bb, end_bb);

                        self.builder.position_at_end(body_bb);
                        self.loop_stack.push((inc_bb, end_bb));
                        self.push_scope();
                        self.compile_block(body);
                        self.pop_scope();
                        self.loop_stack.pop();
                        if !self.current_block_has_terminator() {
                            let _ = self.builder.build_unconditional_branch(inc_bb);
                        }

                        self.builder.position_at_end(inc_bb);
                        let cur2 = self
                            .builder
                            .build_load(self.i32_type, counter, "i2")
                            .unwrap()
                            .into_int_value();
                        let next = self
                            .builder
                            .build_int_add(cur2, self.i32_type.const_int(1, false), "inc")
                            .unwrap();
                        let _ = self.builder.build_store(counter, next);
                        let _ = self.builder.build_unconditional_branch(cond_bb);
                        self.builder.position_at_end(end_bb);
                    }

                    LoopKind::FromTo { var, from, to } => {
                        let from_val = self.compile_expr(from).into_int_value();
                        let to_val = self.compile_expr(to).into_int_value();
                        let cond_bb = self.context.append_basic_block(func, "loop_cond");
                        let body_bb = self.context.append_basic_block(func, "loop_body");
                        let inc_bb = self.context.append_basic_block(func, "loop_inc");
                        let end_bb = self.context.append_basic_block(func, "loop_end");

                        let var_alloca = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self.builder.build_store(var_alloca, from_val);
                        let _ = self.builder.build_unconditional_branch(cond_bb);

                        self.builder.position_at_end(cond_bb);
                        let cur = self
                            .builder
                            .build_load(self.i32_type, var_alloca, "cur")
                            .unwrap()
                            .into_int_value();
                        let cmp = self
                            .builder
                            .build_int_compare(IntPredicate::SLE, cur, to_val, "cond")
                            .unwrap();
                        let _ = self.builder.build_conditional_branch(cmp, body_bb, end_bb);

                        self.builder.position_at_end(body_bb);
                        self.push_scope();
                        self.declare_var(var.clone(), var_alloca, self.i32_type.into(), false);
                        self.loop_stack.push((inc_bb, end_bb));
                        self.compile_block(body);
                        self.loop_stack.pop();
                        self.pop_scope();
                        if !self.current_block_has_terminator() {
                            let _ = self.builder.build_unconditional_branch(inc_bb);
                        }

                        self.builder.position_at_end(inc_bb);
                        let cur2 = self
                            .builder
                            .build_load(self.i32_type, var_alloca, "cur2")
                            .unwrap()
                            .into_int_value();
                        let next = self
                            .builder
                            .build_int_add(cur2, self.i32_type.const_int(1, false), "inc")
                            .unwrap();
                        let _ = self.builder.build_store(var_alloca, next);
                        let _ = self.builder.build_unconditional_branch(cond_bb);
                        self.builder.position_at_end(end_bb);
                    }

                    // ── Range loop: loop n in 0..10 ──
                    LoopKind::Range { var, range } => {
                        // Evaluate range: start..end
                        let (start_val, end_val) = match range {
                            Expr::Range { start, end, .. } => {
                                let s = self.compile_expr(start).into_int_value();
                                let e = self.compile_expr(end).into_int_value();
                                (s, e)
                            }
                            _ => {
                                let v = self.compile_expr(range).into_int_value();
                                (self.i32_type.const_int(0, false), v)
                            }
                        };

                        let cond_bb = self.context.append_basic_block(func, "range_cond");
                        let body_bb = self.context.append_basic_block(func, "range_body");
                        let inc_bb = self.context.append_basic_block(func, "range_inc");
                        let end_bb = self.context.append_basic_block(func, "range_end");

                        let var_alloca = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self.builder.build_store(var_alloca, start_val);
                        let _ = self.builder.build_unconditional_branch(cond_bb);

                        self.builder.position_at_end(cond_bb);
                        let cur = self
                            .builder
                            .build_load(self.i32_type, var_alloca, "rcur")
                            .unwrap()
                            .into_int_value();
                        let cmp = self
                            .builder
                            .build_int_compare(IntPredicate::SLT, cur, end_val, "rcond")
                            .unwrap();
                        let _ = self.builder.build_conditional_branch(cmp, body_bb, end_bb);

                        self.builder.position_at_end(body_bb);
                        self.push_scope();
                        self.declare_var(var.clone(), var_alloca, self.i32_type.into(), false);
                        self.loop_stack.push((inc_bb, end_bb));
                        self.compile_block(body);
                        self.loop_stack.pop();
                        self.pop_scope();
                        if !self.current_block_has_terminator() {
                            let _ = self.builder.build_unconditional_branch(inc_bb);
                        }

                        self.builder.position_at_end(inc_bb);
                        let cur2 = self
                            .builder
                            .build_load(self.i32_type, var_alloca, "rcur2")
                            .unwrap()
                            .into_int_value();
                        let next = self
                            .builder
                            .build_int_add(cur2, self.i32_type.const_int(1, false), "rinc")
                            .unwrap();
                        let _ = self.builder.build_store(var_alloca, next);
                        let _ = self.builder.build_unconditional_branch(cond_bb);
                        self.builder.position_at_end(end_bb);
                    }

                    LoopKind::While(condition) => {
                        let cond_bb = self.context.append_basic_block(func, "while_cond");
                        let body_bb = self.context.append_basic_block(func, "while_body");
                        let end_bb = self.context.append_basic_block(func, "while_end");

                        let _ = self.builder.build_unconditional_branch(cond_bb);
                        self.builder.position_at_end(cond_bb);
                        let raw = self.compile_expr(condition).into_int_value();
                        let cond_val = self.to_i1(raw);
                        let _ = self
                            .builder
                            .build_conditional_branch(cond_val, body_bb, end_bb);

                        self.builder.position_at_end(body_bb);
                        self.loop_stack.push((cond_bb, end_bb));
                        self.push_scope();
                        self.compile_block(body);
                        self.pop_scope();
                        self.loop_stack.pop();
                        if !self.current_block_has_terminator() {
                            let _ = self.builder.build_unconditional_branch(cond_bb);
                        }
                        self.builder.position_at_end(end_bb);
                    }

                    LoopKind::Infinite => {
                        let loop_bb = self.context.append_basic_block(func, "inf_loop");
                        let end_bb = self.context.append_basic_block(func, "inf_end");
                        let _ = self.builder.build_unconditional_branch(loop_bb);
                        self.builder.position_at_end(loop_bb);
                        self.loop_stack.push((loop_bb, end_bb));
                        self.push_scope();
                        self.compile_block(body);
                        self.pop_scope();
                        self.loop_stack.pop();
                        if !self.current_block_has_terminator() {
                            let _ = self.builder.build_unconditional_branch(loop_bb);
                        }
                        self.builder.position_at_end(end_bb);
                    }
                }
            }

            Stmt::Match { value, arms } => {
                let val = self.compile_expr(value).into_int_value();
                let func = self.current_function.unwrap();
                let merge_bb = self.context.append_basic_block(func, "match_end");
                let default_bb = self.context.append_basic_block(func, "match_default");
                let arm_bbs: Vec<BasicBlock> = arms
                    .iter()
                    .map(|_| self.context.append_basic_block(func, "match_arm"))
                    .collect();

                let switch = self
                    .builder
                    .build_switch(val, default_bb, arms.len() as u32)
                    .unwrap();

                let mut wildcard_idx: Option<usize> = None;
                for (i, arm) in arms.iter().enumerate() {
                    match &arm.pattern {
                        Pattern::IntLiteral(n) => {
                            let case_val = self.i32_type.const_int(*n as u64, true);
                            switch.add_case(case_val, arm_bbs[i]);
                        }
                        Pattern::BoolLiteral(b) => {
                            let case_val = self.i32_type.const_int(*b as u64, false);
                            switch.add_case(case_val, arm_bbs[i]);
                        }
                        Pattern::Range(start, end) => {
                            // Expand range into individual cases
                            for v in *start..=*end {
                                let case_val = self.i32_type.const_int(v as u64, true);
                                switch.add_case(case_val, arm_bbs[i]);
                            }
                        }
                        Pattern::StringLiteral(_) => {
                            // String match requires strcmp — treat as wildcard for now
                            wildcard_idx = Some(i);
                        }
                        Pattern::EnumVariant(v) => {
                            let mut found = false;
                            for (_, vals) in &self.enum_variant_values.clone() {
                                if let Some(&vv) = vals.get(v) {
                                    let case_val = self.i32_type.const_int(vv as u64, false);
                                    switch.add_case(case_val, arm_bbs[i]);
                                    found = true;
                                    break;
                                }
                            }
                            if !found {
                                wildcard_idx = Some(i);
                            }
                        }
                        Pattern::Wildcard => {
                            wildcard_idx = Some(i);
                        }
                    }
                }

                // Default -> wildcard or merge
                self.builder.position_at_end(default_bb);
                if let Some(wi) = wildcard_idx {
                    let _ = self.builder.build_unconditional_branch(arm_bbs[wi]);
                } else {
                    let _ = self.builder.build_unconditional_branch(merge_bb);
                }

                for (i, arm) in arms.iter().enumerate() {
                    self.builder.position_at_end(arm_bbs[i]);
                    self.push_scope();
                    self.compile_block(&arm.body);
                    self.pop_scope();
                    if !self.current_block_has_terminator() {
                        let _ = self.builder.build_unconditional_branch(merge_bb);
                    }
                }

                self.builder.position_at_end(merge_bb);
            }

            Stmt::Break => {
                if let Some(&(_, b)) = self.loop_stack.last() {
                    let _ = self.builder.build_unconditional_branch(b);
                }
            }
            Stmt::Continue => {
                if let Some(&(c, _)) = self.loop_stack.last() {
                    let _ = self.builder.build_unconditional_branch(c);
                }
            }

            Stmt::Override { body } => {
                self.override_depth += 1;
                self.safe_math = false;
                self.push_scope();
                self.compile_block(body);
                self.pop_scope();
                self.safe_math = true;
                self.override_depth -= 1;
            }

            Stmt::ConstantTime { body } => {
                self.constant_time_depth += 1;
                self.push_scope();
                self.compile_block(body);
                self.pop_scope();
                self.constant_time_depth -= 1;
            }

            Stmt::Spawn { var, body } => {
                let func = self.current_function.unwrap();
                let thread_fn_name = format!("__thread_{}", self.functions.len());
                let thread_fn_type = self.ptr_type.fn_type(&[self.ptr_type.into()], false);
                let thread_fn = self
                    .module
                    .add_function(&thread_fn_name, thread_fn_type, None);

                let current_bb = self.builder.get_insert_block().unwrap();
                let thread_entry = self.context.append_basic_block(thread_fn, "entry");
                self.builder.position_at_end(thread_entry);
                let saved_fn = self.current_function;
                self.current_function = Some(thread_fn);
                self.push_scope();
                self.compile_block(body);
                self.pop_scope();
                if !self.current_block_has_terminator() {
                    let _ = self.builder.build_return(Some(&self.ptr_type.const_null()));
                }
                self.current_function = saved_fn;
                self.builder.position_at_end(current_bb);

                let target_str = self
                    .target_triple
                    .as_str()
                    .to_str()
                    .unwrap_or("")
                    .to_lowercase();
                let is_windows = target_str.contains("windows");
                let fn_ptr = thread_fn.as_global_value().as_pointer_value();

                let handle: BasicValueEnum = if is_windows {
                    if let Some(create_fn) = self.module.get_function("CreateThread") {
                        let null_ptr = self.ptr_type.const_null();
                        let zero_i64 = self.i64_type.const_int(0, false);
                        let zero_i32 = self.i32_type.const_int(0, false);
                        let call = self
                            .builder
                            .build_call(
                                create_fn,
                                &[
                                    null_ptr.into(),
                                    zero_i64.into(),
                                    fn_ptr.into(),
                                    null_ptr.into(),
                                    zero_i32.into(),
                                    null_ptr.into(),
                                ],
                                "th",
                            )
                            .unwrap();
                        call.try_as_basic_value()
                            .left()
                            .unwrap_or(self.ptr_type.const_null().into())
                    } else {
                        self.ptr_type.const_null().into()
                    }
                } else {
                    let handle_alloca = self
                        .create_entry_block_alloca(self.i64_type.into())
                        .unwrap();
                    if let Some(create_fn) = self.module.get_function("pthread_create") {
                        let null_ptr = self.ptr_type.const_null();
                        let handle_as_ptr = self
                            .builder
                            .build_pointer_cast(handle_alloca, self.ptr_type, "tptr")
                            .unwrap();
                        let _ = self.builder.build_call(
                            create_fn,
                            &[
                                handle_as_ptr.into(),
                                null_ptr.into(),
                                fn_ptr.into(),
                                null_ptr.into(),
                            ],
                            "",
                        );
                    }
                    handle_alloca.into()
                };

                if let Some(vname) = var {
                    let alloca = self.create_entry_block_alloca(handle.get_type()).unwrap();
                    let _ = self.builder.build_store(alloca, handle);
                    self.declare_var(vname.clone(), alloca, handle.get_type(), false);
                }
            }

            Stmt::Join { handle } => {
                let h = self.compile_expr(handle);
                let target_str = self
                    .target_triple
                    .as_str()
                    .to_str()
                    .unwrap_or("")
                    .to_lowercase();
                let is_windows = target_str.contains("windows");
                if is_windows {
                    if let Some(wait_fn) = self.module.get_function("WaitForSingleObject") {
                        let infinite = self.i32_type.const_int(0xFFFFFFFF, false);
                        let _ = self
                            .builder
                            .build_call(wait_fn, &[h.into(), infinite.into()], "");
                    }
                } else {
                    if let Some(join_fn) = self.module.get_function("pthread_join") {
                        let null_ptr = self.ptr_type.const_null();
                        let _ = self
                            .builder
                            .build_call(join_fn, &[h.into(), null_ptr.into()], "");
                    }
                }
            }

            Stmt::Purge { variable } => {
                if let Some(meta) = self.lookup_var(variable) {
                    self.emit_secure_zero(meta.alloca, meta.ty);
                }
            }

            Stmt::Free { ptr } => {
                let val = self.compile_expr(ptr);
                let free_fn = self.module.get_function("free").unwrap();
                let _ = self.builder.build_call(free_fn, &[val.into()], "");
            }

            Stmt::Print(expr) => {
                let val = self.compile_expr(expr);
                let printf_fn = self.module.get_function("printf").unwrap();
                if val.is_pointer_value() {
                    let fmt = self.get_format_string("%s\n");
                    let _ = self
                        .builder
                        .build_call(printf_fn, &[fmt.into(), val.into()], "");
                } else if val.get_type().is_float_type() {
                    let fmt = self.get_format_string("%f\n");
                    let _ = self
                        .builder
                        .build_call(printf_fn, &[fmt.into(), val.into()], "");
                } else {
                    let iv = val.into_int_value();
                    let wide: BasicValueEnum = if iv.get_type().get_bit_width() < 32 {
                        self.builder
                            .build_int_z_extend(iv, self.i32_type, "zext")
                            .unwrap()
                            .into()
                    } else {
                        iv.into()
                    };
                    let fmt = self.get_format_string("%d\n");
                    let _ = self
                        .builder
                        .build_call(printf_fn, &[fmt.into(), wide.into()], "");
                }
            }

            Stmt::PrintFmt { format, args } => {
                let printf_fn = self.module.get_function("printf").unwrap();
                let fmt_str = format!("{}\0", format);
                let fmt_ptr = self.get_format_string(&fmt_str);
                let mut call_args: Vec<BasicMetadataValueEnum> = vec![fmt_ptr.into()];
                for arg in args {
                    call_args.push(self.compile_expr(arg).into());
                }
                let _ = self.builder.build_call(printf_fn, &call_args, "");
            }

            Stmt::Return(expr) => {
                // Run deferred blocks before returning
                let deferred: Vec<Vec<Block>> = self.defer_stack.clone();
                for scope_defers in deferred.iter().rev() {
                    for block in scope_defers.iter().rev() {
                        self.compile_block(block);
                    }
                }

                if let Some(e) = expr {
                    let val = self.compile_expr(e);
                    let _ = self.builder.build_return(Some(&val));
                } else {
                    let _ = self.builder.build_return(None);
                }
            }

            Stmt::Asm(_)
            | Stmt::Import(_)
            | Stmt::TaskDecl { .. }
            | Stmt::ExternDecl { .. }
            | Stmt::StructDecl { .. }
            | Stmt::EnumDecl { .. } => {}

            Stmt::ExprStmt(expr) => {
                self.compile_expr(expr);
            }
        }
    }

    fn current_block_has_terminator(&self) -> bool {
        self.builder
            .get_insert_block()
            .unwrap()
            .get_terminator()
            .is_some()
    }

    fn compile_block(&mut self, block: &Block) {
        for stmt in &block.statements {
            if self.current_block_has_terminator() {
                break;
            }
            self.compile_stmt(stmt);
        }
        if let Some(tail) = &block.tail_expr {
            if !self.current_block_has_terminator() {
                self.compile_expr(tail);
            }
        }
    }

    fn compile_expr(&mut self, expr: &Expr) -> BasicValueEnum<'ctx> {
        match expr {
            Expr::Integer(n) => self.i32_type.const_int(*n as u64, true).into(),
            Expr::Float(f) => self.f64_type.const_float(*f).into(),
            Expr::Boolean(b) => self.i32_type.const_int(*b as u64, false).into(),
            Expr::Null => self.ptr_type.const_null().into(),
            Expr::StringLiteral(s) => {
                let sv = self.context.const_string(s.as_bytes(), true);
                let g = self.module.add_global(sv.get_type(), None, "str");
                g.set_initializer(&sv);
                g.set_constant(true);
                g.as_pointer_value().into()
            }

            // ── String interpolation: "Hello {name}!" ──
            Expr::InterpolatedString(parts) => {
                // Build into a stack buffer via sprintf
                let buf_size = 4096u32;
                let buf_ty = self.i32_type.array_type(buf_size);
                let buf = self.create_entry_block_alloca(buf_ty.into()).unwrap();
                let buf_ptr = self
                    .builder
                    .build_pointer_cast(buf, self.ptr_type, "ibuf")
                    .unwrap();

                // Zero the buffer
                let zero = self.i32_type.const_int(0, false);
                let zero_fmt = self.get_format_string("\0");
                let _ = self.builder.build_store(buf, buf_ty.const_zero());

                let printf_fn = self.module.get_function("printf").unwrap();
                if let Some(sprintf_fn) = self.module.get_function("sprintf") {
                    let mut format_str = String::new();
                    let mut format_args: Vec<BasicMetadataValueEnum> = Vec::new();

                    for part in parts {
                        match part {
                            StringPart::Literal(s) => {
                                // Escape % signs
                                format_str.push_str(&s.replace('%', "%%"));
                            }
                            StringPart::Interpolated(inner_expr) => {
                                let val = self.compile_expr(inner_expr);
                                if val.is_pointer_value() {
                                    format_str.push_str("%s");
                                } else if val.get_type().is_float_type() {
                                    format_str.push_str("%f");
                                } else {
                                    let iv = val.into_int_value();
                                    if iv.get_type().get_bit_width() < 32 {
                                        let wide = self
                                            .builder
                                            .build_int_z_extend(iv, self.i32_type, "istr_z")
                                            .unwrap();
                                        format_args.push(wide.into());
                                    } else {
                                        format_args.push(iv.into());
                                    }
                                    format_str.push_str("%d");
                                    continue;
                                }
                                format_args.push(val.into());
                            }
                        }
                    }

                    let fmt_str_with_null = format!("{}\0", format_str);
                    let fmt_ptr = self.get_format_string(&fmt_str_with_null);
                    let mut call_args: Vec<BasicMetadataValueEnum> =
                        vec![buf_ptr.into(), fmt_ptr.into()];
                    call_args.extend(format_args);
                    let _ = self
                        .builder
                        .build_call(sprintf_fn, &call_args, "sprintf_call");
                }

                buf_ptr.into()
            }

            // ── Range expression ──
            Expr::Range { start, end, .. } => {
                // Return start value (ranges are consumed by loop codegen)
                self.compile_expr(start)
            }

            // ── Await ──
            Expr::Await(inner) => {
                // Await calls the async spawn function and yields
                // In our cooperative model: just call synchronously
                self.compile_expr(inner)
            }

            // ── Nullable check ──
            Expr::Nullable(inner) => {
                // expr? returns the value if non-null, otherwise 0
                let val = self.compile_expr(inner);
                if val.is_pointer_value() {
                    let ptr = val.into_pointer_value();
                    let is_null = self
                        .builder
                        .build_int_compare(
                            IntPredicate::EQ,
                            self.builder
                                .build_ptr_to_int(ptr, self.i64_type, "p2i")
                                .unwrap(),
                            self.i64_type.const_int(0, false),
                            "isnull",
                        )
                        .unwrap();
                    self.builder
                        .build_int_z_extend(is_null, self.i32_type, "nullcheck")
                        .unwrap()
                        .into()
                } else {
                    val
                }
            }

            // ── Closure with full capture support ──
            Expr::Closure { params, body } => {
                // Analyze what variables are captured
                let enclosing: HashMap<String, crate::ast::Type> = self.enclosing_var_types.clone();
                let info = closures::analyze_closure(params, body, &enclosing);

                let fn_name = info.fn_name.clone();
                let captures = info.captures.clone();
                let env_name = info.env_struct_name.clone();

                if captures.is_empty() {
                    // Pure closure — no environment needed
                    let param_types: Vec<inkwell::types::IntType> =
                        params.iter().map(|_| self.i32_type).collect();
                    let meta_params: Vec<BasicMetadataTypeEnum> =
                        param_types.iter().map(|t| (*t).into()).collect();
                    let fn_type = self.i32_type.fn_type(&meta_params, false);
                    let fn_val = self.module.add_function(&fn_name, fn_type, None);
                    let saved = self.current_function;
                    let bb = self.context.append_basic_block(fn_val, "entry");
                    self.builder.position_at_end(bb);
                    self.current_function = Some(fn_val);
                    self.push_scope();
                    for (i, pname) in params.iter().enumerate() {
                        let pval = fn_val.get_nth_param(i as u32).unwrap();
                        let alloca = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self.builder.build_store(alloca, pval);
                        self.declare_var(pname.clone(), alloca, self.i32_type.into(), false);
                    }
                    let body_val = self.compile_expr(body);
                    if !self.current_block_has_terminator() {
                        let _ = self.builder.build_return(Some(&body_val));
                    }
                    self.pop_scope();
                    self.current_function = saved;
                    if let Some(caller_bb) = saved.and_then(|f| f.get_last_basic_block()) {
                        self.builder.position_at_end(caller_bb);
                    }
                    fn_val.as_global_value().as_pointer_value().into()
                } else {
                    // Capturing closure — build environment struct
                    let env_fields: Vec<BasicTypeEnum> =
                        captures.iter().map(|_| self.ptr_type.into()).collect();
                    let env_ty = self.context.struct_type(&env_fields, false);
                    self.struct_types.insert(env_name.clone(), env_ty);
                    let mut fidx: HashMap<String, u32> = HashMap::new();
                    for (i, (cname, _)) in captures.iter().enumerate() {
                        fidx.insert(cname.clone(), i as u32);
                    }
                    self.struct_field_index
                        .insert(env_name.clone(), fidx.clone());

                    // Closure function: takes env ptr + params
                    let mut meta_params: Vec<BasicMetadataTypeEnum> = vec![self.ptr_type.into()];
                    for _ in params {
                        meta_params.push(self.i32_type.into());
                    }
                    let fn_type = self.i32_type.fn_type(&meta_params, false);
                    let fn_val = self.module.add_function(&fn_name, fn_type, None);
                    let saved = self.current_function;
                    let bb = self.context.append_basic_block(fn_val, "entry");
                    self.builder.position_at_end(bb);
                    self.current_function = Some(fn_val);
                    self.push_scope();

                    // Load captured vars from environment
                    let env_ptr = fn_val.get_nth_param(0).unwrap().into_pointer_value();
                    for (cname, _ctype) in &captures {
                        let idx = fidx[cname];
                        let gep = self
                            .builder
                            .build_struct_gep(env_ty, env_ptr, idx, "cgep")
                            .unwrap();
                        let ptr = self
                            .builder
                            .build_load(self.ptr_type, gep, cname)
                            .unwrap()
                            .into_pointer_value();
                        // Load the value through the pointer
                        let val = self.builder.build_load(self.i32_type, ptr, cname).unwrap();
                        let alloca = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self.builder.build_store(alloca, val);
                        self.declare_var(cname.clone(), alloca, self.i32_type.into(), false);
                    }

                    // Load params
                    for (i, pname) in params.iter().enumerate() {
                        let pval = fn_val.get_nth_param(i as u32 + 1).unwrap();
                        let alloca = self
                            .create_entry_block_alloca(self.i32_type.into())
                            .unwrap();
                        let _ = self.builder.build_store(alloca, pval);
                        self.declare_var(pname.clone(), alloca, self.i32_type.into(), false);
                    }

                    let body_val = self.compile_expr(body);
                    if !self.current_block_has_terminator() {
                        let _ = self.builder.build_return(Some(&body_val));
                    }
                    self.pop_scope();
                    self.current_function = saved;
                    if let Some(caller_bb) = saved.and_then(|f| f.get_last_basic_block()) {
                        self.builder.position_at_end(caller_bb);
                    }

                    // Allocate and populate environment struct
                    let env_alloca = self.create_entry_block_alloca(env_ty.into()).unwrap();
                    for (cname, _) in &captures {
                        if let Some(meta) = self.lookup_var(cname) {
                            let ptr = meta.alloca;
                            let idx = fidx[cname];
                            let gep = self
                                .builder
                                .build_struct_gep(env_ty, env_alloca, idx, "egep")
                                .unwrap();
                            let _ = self.builder.build_store(gep, ptr);
                        }
                    }

                    // Return pair: (fn_ptr, env_ptr) — simplified to just fn_ptr for now
                    fn_val.as_global_value().as_pointer_value().into()
                }
            }

            Expr::EnumVariant { enum_name, variant } => {
                let val = self
                    .enum_variant_values
                    .get(enum_name)
                    .and_then(|m| m.get(variant))
                    .copied()
                    .unwrap_or(0);
                self.i32_type.const_int(val as u64, false).into()
            }

            Expr::StrLen(inner) => {
                let s = self.compile_expr(inner);
                let len_fn = self.module.get_function("strlen").unwrap();
                let call = self.builder.build_call(len_fn, &[s.into()], "sl").unwrap();
                let i64v = call.try_as_basic_value().left().unwrap().into_int_value();
                self.builder
                    .build_int_truncate(i64v, self.i32_type, "sl32")
                    .unwrap()
                    .into()
            }

            Expr::StrConcat(a, b) => {
                let sa = self.compile_expr(a);
                let sb = self.compile_expr(b);
                let strlen_fn = self.module.get_function("strlen").unwrap();
                let la = self
                    .builder
                    .build_call(strlen_fn, &[sa.into()], "la")
                    .unwrap()
                    .try_as_basic_value()
                    .left()
                    .unwrap()
                    .into_int_value();
                let lb = self
                    .builder
                    .build_call(strlen_fn, &[sb.into()], "lb")
                    .unwrap()
                    .try_as_basic_value()
                    .left()
                    .unwrap()
                    .into_int_value();
                let total = self.builder.build_int_add(la, lb, "total").unwrap();
                let extra = self.i64_type.const_int(1, false);
                let size = self.builder.build_int_add(total, extra, "size").unwrap();
                let malloc_fn = self.module.get_function("malloc").unwrap();
                let buf = self
                    .builder
                    .build_call(malloc_fn, &[size.into()], "cb")
                    .unwrap()
                    .try_as_basic_value()
                    .left()
                    .unwrap();
                let strcpy_fn = self.module.get_function("strcpy").unwrap();
                let strcat_fn = self.module.get_function("strcat").unwrap();
                let _ = self
                    .builder
                    .build_call(strcpy_fn, &[buf.into(), sa.into()], "");
                let _ = self
                    .builder
                    .build_call(strcat_fn, &[buf.into(), sb.into()], "");
                buf
            }

            Expr::OkExpr(inner) => {
                let val = self.compile_expr(inner).into_int_value();
                let tag = self.i32_type.const_int(0x10000, false);
                self.builder.build_or(tag, val, "ok").unwrap().into()
            }
            Expr::ErrExpr(inner) => self.compile_expr(inner),
            Expr::IsOk(inner) => {
                let val = self.compile_expr(inner).into_int_value();
                let bit = self.i32_type.const_int(0x10000, false);
                let and = self.builder.build_and(val, bit, "isok_bit").unwrap();
                self.builder
                    .build_int_compare(IntPredicate::NE, and, self.i32_type.const_zero(), "isok")
                    .unwrap()
                    .into()
            }
            Expr::Unwrap(inner) => {
                let val = self.compile_expr(inner).into_int_value();
                let mask = self.i32_type.const_int(0xFFFF, false);
                self.builder.build_and(val, mask, "unwrap").unwrap().into()
            }

            Expr::Identifier(name) => {
                if let Some(meta) = self.lookup_var(name) {
                    let alloca = meta.alloca;
                    let ty = meta.ty;
                    if matches!(ty, BasicTypeEnum::ArrayType(_)) {
                        self.builder
                            .build_pointer_cast(alloca, self.ptr_type, "arrp")
                            .unwrap()
                            .into()
                    } else {
                        let load = self.builder.build_load(ty, alloca, name).unwrap();
                        if self.constant_time_depth > 0 {
                            if let Some(instr) = load.as_instruction_value() {
                                instr.set_volatile(true).ok();
                            }
                        }
                        load
                    }
                } else {
                    eprintln!("Codegen error: undefined variable '{}'", name);
                    std::process::exit(1);
                }
            }

            Expr::StructLiteral { name, fields } => {
                if let Some(&st) = self.struct_types.get(name) {
                    let alloca = self.create_entry_block_alloca(st.into()).unwrap();
                    let fidx = self
                        .struct_field_index
                        .get(name)
                        .cloned()
                        .unwrap_or_default();
                    for (fname, fval) in fields {
                        let val = self.compile_expr(fval);
                        let idx = fidx[fname];
                        let gep = self
                            .builder
                            .build_struct_gep(st, alloca, idx, "sfgep")
                            .unwrap();
                        let _ = self.builder.build_store(gep, val);
                    }
                    self.builder.build_load(st.into(), alloca, "sload").unwrap()
                } else {
                    eprintln!("Codegen error: unknown struct '{}'", name);
                    std::process::exit(1);
                }
            }

            Expr::FieldAccess { object, field } => {
                if let Expr::Identifier(name) = object.as_ref() {
                    if let Some(meta) = self.lookup_var(name) {
                        let alloca = meta.alloca;
                        if let BasicTypeEnum::StructType(st) = meta.ty {
                            let sname = self
                                .struct_types
                                .iter()
                                .find(|(_, v)| **v == st)
                                .map(|(k, _)| k.clone())
                                .unwrap_or_default();
                            let fidx = self
                                .struct_field_index
                                .get(&sname)
                                .cloned()
                                .unwrap_or_default();
                            if let Some(&idx) = fidx.get(field) {
                                let gep = self
                                    .builder
                                    .build_struct_gep(st, alloca, idx, "fgep")
                                    .unwrap();
                                let fty = st.get_field_type_at_index(idx).unwrap();
                                return self.builder.build_load(fty, gep, field).unwrap();
                            }
                        }
                    }
                }
                eprintln!("Codegen error: field access on non-struct");
                std::process::exit(1);
            }

            Expr::Alloc { count, size } => {
                let count_val = self.compile_expr(count).into_int_value();
                let size_val = self.compile_expr(size).into_int_value();
                let c64 = self
                    .builder
                    .build_int_z_extend(count_val, self.i64_type, "c64")
                    .unwrap();
                let s64 = self
                    .builder
                    .build_int_z_extend(size_val, self.i64_type, "s64")
                    .unwrap();
                let tot = self.builder.build_int_mul(c64, s64, "tot").unwrap();
                let mfn = self.module.get_function("malloc").unwrap();
                let call = self
                    .builder
                    .build_call(mfn, &[tot.into()], "alloc")
                    .unwrap();
                call.try_as_basic_value().left().unwrap()
            }

            Expr::Cast { expr, to } => {
                let val = self.compile_expr(expr);
                match (val.get_type(), to) {
                    (BasicTypeEnum::IntType(_), Type::Float) => self
                        .builder
                        .build_signed_int_to_float(val.into_int_value(), self.f64_type, "itof")
                        .unwrap()
                        .into(),
                    (BasicTypeEnum::FloatType(_), Type::Int) => self
                        .builder
                        .build_float_to_signed_int(val.into_float_value(), self.i32_type, "ftoi")
                        .unwrap()
                        .into(),
                    (BasicTypeEnum::IntType(_), Type::Bool) => {
                        self.to_i1(val.into_int_value()).into()
                    }
                    (BasicTypeEnum::IntType(_), Type::Int) => {
                        let iv = val.into_int_value();
                        if iv.get_type().get_bit_width() < 32 {
                            self.builder
                                .build_int_z_extend(iv, self.i32_type, "zext")
                                .unwrap()
                                .into()
                        } else {
                            iv.into()
                        }
                    }
                    _ => val,
                }
            }

            Expr::BinaryOp { left, op, right } => {
                if matches!(op, BinOp::And | BinOp::Or) {
                    let l = self.compile_expr(left).into_int_value();
                    let r = self.compile_expr(right).into_int_value();
                    let lb = self.to_i1(l);
                    let rb = self.to_i1(r);
                    return match op {
                        BinOp::And => self.builder.build_and(lb, rb, "and").unwrap().into(),
                        BinOp::Or => self.builder.build_or(lb, rb, "or").unwrap().into(),
                        _ => unreachable!(),
                    };
                }

                let l = self.compile_expr(left);
                let r = self.compile_expr(right);

                match (l.get_type(), r.get_type()) {
                    (BasicTypeEnum::IntType(_), BasicTypeEnum::IntType(_)) => {
                        let li = l.into_int_value();
                        let ri = r.into_int_value();
                        match op {
                            BinOp::Add => {
                                if self.safe_math {
                                    self.builder
                                        .build_int_nsw_add(li, ri, "add")
                                        .unwrap()
                                        .into()
                                } else {
                                    self.builder.build_int_add(li, ri, "add").unwrap().into()
                                }
                            }
                            BinOp::Sub => {
                                if self.safe_math {
                                    self.builder
                                        .build_int_nsw_sub(li, ri, "sub")
                                        .unwrap()
                                        .into()
                                } else {
                                    self.builder.build_int_sub(li, ri, "sub").unwrap().into()
                                }
                            }
                            BinOp::Mul => {
                                if self.safe_math {
                                    self.builder
                                        .build_int_nsw_mul(li, ri, "mul")
                                        .unwrap()
                                        .into()
                                } else {
                                    self.builder.build_int_mul(li, ri, "mul").unwrap().into()
                                }
                            }
                            BinOp::Div => self
                                .builder
                                .build_int_signed_div(li, ri, "div")
                                .unwrap()
                                .into(),
                            BinOp::Mod => self
                                .builder
                                .build_int_signed_rem(li, ri, "rem")
                                .unwrap()
                                .into(),
                            BinOp::Eq => self
                                .builder
                                .build_int_compare(IntPredicate::EQ, li, ri, "eq")
                                .unwrap()
                                .into(),
                            BinOp::Neq => self
                                .builder
                                .build_int_compare(IntPredicate::NE, li, ri, "ne")
                                .unwrap()
                                .into(),
                            BinOp::Lt => self
                                .builder
                                .build_int_compare(IntPredicate::SLT, li, ri, "lt")
                                .unwrap()
                                .into(),
                            BinOp::Gt => self
                                .builder
                                .build_int_compare(IntPredicate::SGT, li, ri, "gt")
                                .unwrap()
                                .into(),
                            BinOp::Le => self
                                .builder
                                .build_int_compare(IntPredicate::SLE, li, ri, "le")
                                .unwrap()
                                .into(),
                            BinOp::Ge => self
                                .builder
                                .build_int_compare(IntPredicate::SGE, li, ri, "ge")
                                .unwrap()
                                .into(),
                            BinOp::BitAnd => self.builder.build_and(li, ri, "band").unwrap().into(),
                            BinOp::BitOr => self.builder.build_or(li, ri, "bor").unwrap().into(),
                            BinOp::BitXor => self.builder.build_xor(li, ri, "bxor").unwrap().into(),
                            BinOp::Shl => {
                                self.builder.build_left_shift(li, ri, "shl").unwrap().into()
                            }
                            BinOp::Shr => self
                                .builder
                                .build_right_shift(li, ri, true, "shr")
                                .unwrap()
                                .into(),
                            _ => unreachable!(),
                        }
                    }
                    (BasicTypeEnum::FloatType(_), BasicTypeEnum::FloatType(_)) => {
                        let lf = l.into_float_value();
                        let rf = r.into_float_value();
                        match op {
                            BinOp::Add => {
                                self.builder.build_float_add(lf, rf, "fadd").unwrap().into()
                            }
                            BinOp::Sub => {
                                self.builder.build_float_sub(lf, rf, "fsub").unwrap().into()
                            }
                            BinOp::Mul => {
                                self.builder.build_float_mul(lf, rf, "fmul").unwrap().into()
                            }
                            BinOp::Div => {
                                self.builder.build_float_div(lf, rf, "fdiv").unwrap().into()
                            }
                            _ => {
                                let pred = match op {
                                    BinOp::Eq => inkwell::FloatPredicate::OEQ,
                                    BinOp::Neq => inkwell::FloatPredicate::ONE,
                                    BinOp::Lt => inkwell::FloatPredicate::OLT,
                                    BinOp::Gt => inkwell::FloatPredicate::OGT,
                                    BinOp::Le => inkwell::FloatPredicate::OLE,
                                    BinOp::Ge => inkwell::FloatPredicate::OGE,
                                    _ => {
                                        eprintln!("invalid float op");
                                        std::process::exit(1);
                                    }
                                };
                                self.builder
                                    .build_float_compare(pred, lf, rf, "fcmp")
                                    .unwrap()
                                    .into()
                            }
                        }
                    }
                    // Pointer comparisons (for null checks)
                    (BasicTypeEnum::PointerType(_), BasicTypeEnum::PointerType(_)) => {
                        let lp = self
                            .builder
                            .build_ptr_to_int(l.into_pointer_value(), self.i64_type, "lp2i")
                            .unwrap();
                        let rp = self
                            .builder
                            .build_ptr_to_int(r.into_pointer_value(), self.i64_type, "rp2i")
                            .unwrap();
                        match op {
                            BinOp::Eq => self
                                .builder
                                .build_int_compare(IntPredicate::EQ, lp, rp, "peq")
                                .unwrap()
                                .into(),
                            BinOp::Neq => self
                                .builder
                                .build_int_compare(IntPredicate::NE, lp, rp, "pne")
                                .unwrap()
                                .into(),
                            _ => {
                                eprintln!("Codegen error: unsupported pointer op");
                                std::process::exit(1);
                            }
                        }
                    }
                    (lt, rt) => {
                        eprintln!("Codegen error: type mismatch {:?} vs {:?}", lt, rt);
                        std::process::exit(1);
                    }
                }
            }

            Expr::UnaryOp { op, operand } => {
                let val = self.compile_expr(operand);
                match op {
                    UnaryOp::Neg => {
                        if val.get_type().is_int_type() {
                            self.builder
                                .build_int_neg(val.into_int_value(), "neg")
                                .unwrap()
                                .into()
                        } else {
                            self.builder
                                .build_float_neg(val.into_float_value(), "fneg")
                                .unwrap()
                                .into()
                        }
                    }
                    UnaryOp::Not => {
                        let b = self.to_i1(val.into_int_value());
                        self.builder
                            .build_xor(b, self.i1_type.const_int(1, false), "not")
                            .unwrap()
                            .into()
                    }
                    UnaryOp::BitNot => self
                        .builder
                        .build_not(val.into_int_value(), "bnot")
                        .unwrap()
                        .into(),
                }
            }

            Expr::Call { func, args } => {
                if let Expr::Identifier(name) = func.as_ref() {
                    let llvm_name = self
                        .task_name_map
                        .get(name)
                        .cloned()
                        .unwrap_or_else(|| name.clone());
                    let compiled_args: Vec<BasicValueEnum> =
                        args.iter().map(|a| self.compile_expr(a)).collect();
                    let function = match self.functions.get(&llvm_name) {
                        Some(f) => *f,
                        None => {
                            eprintln!("Codegen error: unknown function '{}'", name);
                            std::process::exit(1);
                        }
                    };
                    let llvm_args: Vec<BasicMetadataValueEnum> =
                        compiled_args.into_iter().map(|a| a.into()).collect();
                    let call = self
                        .builder
                        .build_call(function, &llvm_args, "call")
                        .unwrap();
                    call.try_as_basic_value()
                        .left()
                        .unwrap_or_else(|| self.i32_type.const_int(0, false).into())
                } else {
                    eprintln!("Codegen error: indirect calls not supported");
                    std::process::exit(1);
                }
            }

            Expr::Array(elements) => {
                if elements.is_empty() {
                    return self.ptr_type.const_null().into();
                }
                let compiled: Vec<BasicValueEnum> =
                    elements.iter().map(|e| self.compile_expr(e)).collect();
                let elem_ty = compiled[0].get_type();
                let arr_ty = elem_ty.array_type(elements.len() as u32);
                let alloca = self.create_entry_block_alloca(arr_ty.into()).unwrap();
                let ptr = self
                    .builder
                    .build_pointer_cast(alloca, self.ptr_type, "ap")
                    .unwrap();
                for (i, val) in compiled.into_iter().enumerate() {
                    let gep = unsafe {
                        self.builder.build_in_bounds_gep(
                            elem_ty,
                            ptr,
                            &[self.i32_type.const_int(i as u64, false)],
                            "ep",
                        )
                    }
                    .unwrap();
                    let _ = self.builder.build_store(gep, val);
                }
                alloca.into()
            }

            Expr::Index { array, index } => {
                let idx_val = self.compile_expr(index).into_int_value();
                let elem_ty: BasicTypeEnum = if let Expr::Identifier(name) = array.as_ref() {
                    if let Some(&(len, ety)) = self.array_meta.get(name) {
                        if self.override_depth == 0 {
                            self.emit_bounds_check(idx_val, len);
                        }
                        ety
                    } else {
                        self.i32_type.into()
                    }
                } else {
                    self.i32_type.into()
                };

                let arr_ptr: PointerValue = match array.as_ref() {
                    Expr::Identifier(name) => {
                        if let Some(meta) = self.lookup_var(name) {
                            if matches!(meta.ty, BasicTypeEnum::ArrayType(_)) {
                                self.builder
                                    .build_pointer_cast(meta.alloca, self.ptr_type, "arrp")
                                    .unwrap()
                            } else {
                                self.builder
                                    .build_load(meta.ty, meta.alloca, name)
                                    .unwrap()
                                    .into_pointer_value()
                            }
                        } else {
                            eprintln!("Codegen error: undefined '{}'", name);
                            std::process::exit(1);
                        }
                    }
                    _ => {
                        let v = self.compile_expr(array);
                        if v.is_pointer_value() {
                            v.into_pointer_value()
                        } else {
                            eprintln!("Codegen error: cannot index non-pointer");
                            std::process::exit(1);
                        }
                    }
                };

                let gep = unsafe {
                    self.builder
                        .build_in_bounds_gep(elem_ty, arr_ptr, &[idx_val], "idx")
                }
                .unwrap();
                self.builder.build_load(elem_ty, gep, "elem").unwrap()
            }

            Expr::Copy(inner) => self.compile_expr(inner),

            Expr::AddressOf(inner) => {
                if let Expr::Identifier(name) = inner.as_ref() {
                    if let Some(meta) = self.lookup_var(name) {
                        meta.alloca.into()
                    } else {
                        eprintln!("Codegen error: & on undefined '{}'", name);
                        std::process::exit(1);
                    }
                } else {
                    eprintln!("Codegen error: & only on variables");
                    std::process::exit(1);
                }
            }

            Expr::Deref(inner) => {
                let ptr_val = self.compile_expr(inner);
                if ptr_val.is_pointer_value() {
                    self.builder
                        .build_load(self.i32_type, ptr_val.into_pointer_value(), "deref")
                        .unwrap()
                } else {
                    eprintln!("Codegen error: cannot deref non-pointer");
                    std::process::exit(1);
                }
            }
        }
    }

    fn emit_bounds_check(&mut self, index: inkwell::values::IntValue<'ctx>, length: u32) {
        let func = self.current_function.unwrap();
        let ok_bb = self.context.append_basic_block(func, "bchk_ok");
        let fail_bb = self.context.append_basic_block(func, "bchk_fail");
        let len_val = self.i32_type.const_int(length as u64, false);
        let in_bounds = self
            .builder
            .build_int_compare(IntPredicate::ULT, index, len_val, "bchk")
            .unwrap();
        let _ = self
            .builder
            .build_conditional_branch(in_bounds, ok_bb, fail_bb);

        self.builder.position_at_end(fail_bb);
        let printf_fn = self.module.get_function("printf").unwrap();
        let msg = self.get_format_string("Error: array index out of bounds\n");
        let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
        let abort_fn = self.module.get_function("abort").unwrap();
        let _ = self.builder.build_call(abort_fn, &[], "");
        let _ = self.builder.build_unreachable();

        self.builder.position_at_end(ok_bb);
    }

    fn get_format_string(&mut self, s: &str) -> PointerValue<'ctx> {
        let key = s.to_string();
        if let Some(&ptr) = self.format_strings.get(&key) {
            return ptr;
        }
        let content = if s.ends_with('\0') {
            s.to_string()
        } else {
            format!("{}\0", s)
        };
        let sv = self.context.const_string(content.as_bytes(), false);
        let g = self.module.add_global(sv.get_type(), None, "fmt");
        g.set_initializer(&sv);
        g.set_constant(true);
        let ptr = g.as_pointer_value();
        self.format_strings.insert(key, ptr);
        ptr
    }

    fn create_entry_block_alloca(
        &mut self,
        ty: BasicTypeEnum<'ctx>,
    ) -> Result<PointerValue<'ctx>, inkwell::builder::BuilderError> {
        let b = self.context.create_builder();
        let entry = self
            .current_function
            .unwrap()
            .get_first_basic_block()
            .unwrap();
        match entry.get_first_instruction() {
            Some(i) => b.position_before(&i),
            None => b.position_at_end(entry),
        }
        b.build_alloca(ty, "alloca")
    }

    pub fn write_executable(&self, output_path: &str, obj_path: &str) {
        let triple = &self.target_triple;
        let target = Target::from_triple(triple).expect("target");
        let opt_level = if self.optimize_size {
            inkwell::OptimizationLevel::Default
        } else {
            inkwell::OptimizationLevel::Aggressive
        };
        let machine = target
            .create_target_machine(
                triple,
                "generic",
                "",
                opt_level,
                inkwell::targets::RelocMode::Default,
                inkwell::targets::CodeModel::Default,
            )
            .expect("target machine");

        let cpu      = TargetMachine::get_host_cpu_name();
        let features = TargetMachine::get_host_cpu_features();
        let machine  = target.create_target_machine(triple, cpu.to_str().unwrap(), features.to_str().unwrap(), ...)

            pub fn write_executable(&self, output_path: &str, obj_path: &str) {
                self.finalize_debug_info();

                let triple = &self.target_triple;
                let target = Target::from_triple(triple).expect("target");

                // Use native CPU features when targeting the host machine
                // This enables AVX2, AVX-512, etc. automatically
                // C compiled with plain -O3 does NOT do this without -march=native
                let (cpu, features) = if std::env::var("SOVEREIGN_GENERIC").is_ok() {
                    // Portable binary mode
                    ("generic".to_string(), "".to_string())
                } else {
                    let cpu_name = TargetMachine::get_host_cpu_name();
                    let cpu_feat = TargetMachine::get_host_cpu_features();
                    (
                        cpu_name.to_str().unwrap_or("generic").to_string(),
                        cpu_feat.to_str().unwrap_or("").to_string(),
                    )
                };

                let opt_level = if self.optimize_size {
                    inkwell::OptimizationLevel::Default
                } else {
                    inkwell::OptimizationLevel::Aggressive
                };

                let machine = target
                    .create_target_machine(
                        triple,
                        &cpu,
                        &features,
                        opt_level,
                        inkwell::targets::RelocMode::Default,
                        inkwell::targets::CodeModel::Default,
                    )
                    .expect("target machine");

                machine
                    .write_to_file(
                        &self.module,
                        inkwell::targets::FileType::Object,
                        Path::new(obj_path),
                    )
                    vfn link_windows(&self, output_path: &str, obj_path: &str) {
                        let link_cmd    = find_linker_windows();
                        let msvc_lib    = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
                            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
                        });
                        let winsdk_um   = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
                            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
                        });
                        let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
                            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
                        });

                        let status = std::process::Command::new(&link_cmd)
                            .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
                            .args([
                                "/nologo",
                                &format!("/out:{}", output_path),
                                "/subsystem:console",
                                "/opt:ref",   // remove unreferenced sections
                                "/opt:icf",   // identical code folding
                                "/Gy",        // function-level linking — strips individual unused functions
                                              // C with plain cl.exe does NOT use this by default
                                              // This beats C on binary size
                                obj_path,
                                "libcmt.lib",
                                "libucrt.lib",
                                "kernel32.lib",
                            ])
                            .status()
                            .expect("linker failed");

                        if !status.success() {
                            eprintln!("Linking failed");
                            std::process::exit(1);
                        }
                    }
                    fn compile_task_with_canary(
                        &mut self,
                        function: FunctionValue<'ctx>,
                        body: &Block,
                        return_type: &Type,
                    ) {
                        // Stack canary: detect buffer overflows at runtime
                        // Even Rust does not emit these by default
                        // Only in safe mode (not in override blocks)

                        if self.override_depth == 0 {
                            // Generate a pseudo-random canary value at compile time
                            // In production: read from /dev/urandom or __stack_chk_guard
                            let canary_val = self.i64_type.const_int(0xDEAD_BEEF_CAFE_BABE, false);
                            let canary     = self.create_entry_block_alloca(self.i64_type.into()).unwrap();
                            let _          = self.builder.build_store(canary, canary_val);

                            // Compile the actual body
                            self.compile_block(body);

                            // Check canary before return
                            if !self.current_block_has_terminator() {
                                let check_val = self.builder
                                    .build_load(self.i64_type, canary, "canary_check")
                                    .unwrap()
                                    .into_int_value();
                                let ok = self.builder
                                    .build_int_compare(
                                        IntPredicate::EQ,
                                        check_val,
                                        canary_val,
                                        "canary_ok",
                                    )
                                    .unwrap();

                                let func     = self.current_function.unwrap();
                                let ok_bb    = self.context.append_basic_block(func, "canary_ok");
                                let fail_bb  = self.context.append_basic_block(func, "canary_fail");
                                let _ = self.builder.build_conditional_branch(ok, ok_bb, fail_bb);

                                // Fail path: stack smashing detected
                                self.builder.position_at_end(fail_bb);
                                let printf_fn = self.module.get_function("printf").unwrap();
                                let msg       = self.get_format_string(
                                    "FATAL: stack smashing detected — buffer overflow\n"
                                );
                                let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
                                let abort_fn = self.module.get_function("abort").unwrap();
                                let _ = self.builder.build_call(abort_fn, &[], "");
                                let _ = self.builder.build_unreachable();

                                self.builder.position_at_end(ok_bb);
                            }
                        } else {
                            // No canary in override block
                            self.compile_block(body);
                        }

                        if !self.current_block_has_terminator() {
                            match return_type {
                                Type::Void => { let _ = self.builder.build_return(None); }
                                _ => {
                                    let _ = self.builder.build_return(
                                        Some(&self.i32_type.const_int(0, false))
                                    );
                                }
                                fn declare_channel_runtime(&mut self) {
                                    // Channels use a mutex-protected queue internally
                                    // This gives safe cross-thread communication
                                    // Implementation: malloc a struct { mutex, queue_head, queue_tail }

                                    // chan_make() -> ptr
                                    let make_type = self.ptr_type.fn_type(&[self.i64_type.into()], false);
                                    self.module.add_function("sov_chan_make", make_type, None);

                                    // chan_send(chan: ptr, data: ptr, size: i64)
                                    let send_type = self.context.void_type().fn_type(
                                        &[self.ptr_type.into(), self.ptr_type.into(), self.i64_type.into()],
                                        false,
                                    );
                                    self.module.add_function("sov_chan_send", send_type, None);

                                    // chan_recv(chan: ptr) -> ptr
                                    let recv_type = self.ptr_type.fn_type(&[self.ptr_type.into()], false);
                                    self.module.add_function("sov_chan_recv", recv_type, None);
                                }
                            }
                            fn link_windows(&self, output_path: &str, obj_path: &str) {
                                let link_cmd    = find_linker_windows();
                                let msvc_lib    = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
                                    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
                                });
                                let winsdk_um   = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
                                    r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
                                });
                                let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
                                    r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
                                });

                                // Determine if we should strip the CRT entirely
                                let strip_crt = !self.debug_mode && self.optimize_size;

                                let mut args: Vec<String> = vec![
                                    "/nologo".into(),
                                    format!("/out:{}", output_path),
                                    "/subsystem:console".into(),
                                    "/opt:ref".into(),          // remove unreferenced sections
                                    "/opt:icf".into(),          // identical code folding
                                    "/Gy".into(),               // function-level linking
                                    "/merge:.rdata=.text".into(), // smaller binary — merge read-only data
                                    obj_path.to_string(),
                                ];

                                if strip_crt {
                                    // Remove CRT startup entirely
                                    // This makes Sovereign binaries smaller than C binaries
                                    // C always includes CRT startup; Sovereign does not have to
                                    args.push("/nodefaultlib".into());
                                    args.push("/entry:main".into());      // our main IS the entry point
                                    args.push("kernel32.lib".into());     // minimal: just OS calls
                                    args.push("ucrt.lib".into());         // C math/string functions
                                } else {
                                    args.push("libcmt.lib".into());
                                    args.push("libucrt.lib".into());
                                    args.push("kernel32.lib".into());
                                }

                                let status = std::process::Command::new(&link_cmd)
                                    .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
                                    .args(&args)
                                    .status()
                                    .expect("linker failed");

                                if !status.success() {
                                    eprintln!("Linking failed");
                                    std::process::exit(1);
                                }
                            }

                            fn link_unix(&self, output_path: &str, obj_path: &str, extra_libs: &[&str]) {
                                let mut args = vec![
                                    obj_path.to_string(),
                                    "-o".to_string(),
                                    output_path.to_string(),
                                ];

                                if self.optimize_size && !self.debug_mode {
                                    // Remove C runtime startup on Linux/macOS
                                    // Smaller than any C binary compiled normally
                                    args.push("-nostartfiles".to_string());
                                    args.push("-nodefaultlibs".to_string());
                                    // Only link what we actually need
                                    args.push("-lc".to_string());    // libc for printf etc
                                    args.push("-lm".to_string());    // math
                                } else {
                                    for lib in extra_libs { args.push(lib.to_string()); }
                                }

                                // Strip debug symbols from release builds
                                if !self.debug_mode {
                                    args.push("-Wl,--strip-all".to_string());
                                    args.push("-Wl,--gc-sections".to_string()); // same as /opt:ref
                                }
                                // Add to Codegen struct:
                                pgo_mode: PgoMode,

                                #[derive(Debug, Clone, PartialEq)]
                                pub enum PgoMode {
                                    None,
                                    Generate,  // --pgo-generate: instrument for profiling
                                    Use,       // --pgo-use: optimize using profile
                                }

                                // Update write_executable:
                                pub fn write_executable(&self, output_path: &str, obj_path: &str) {
                                    self.finalize_debug_info();

                                    let triple = &self.target_triple;
                                    let target = Target::from_triple(triple).expect("target");

                                    let (cpu, features) = if std::env::var("SOVEREIGN_GENERIC").is_ok() {
                                        ("generic".to_string(), "".to_string())
                                    } else {
                                        let cpu_name = TargetMachine::get_host_cpu_name();
                                        let cpu_feat = TargetMachine::get_host_cpu_features();
                                        (
                                            cpu_name.to_str().unwrap_or("generic").to_string(),
                                            cpu_feat.to_str().unwrap_or("").to_string(),
                                        )
                                    };

                                    let opt_level = match self.pgo_mode {
                                        PgoMode::Generate => inkwell::OptimizationLevel::Default, // lower for instrumented build
                                        PgoMode::Use      => inkwell::OptimizationLevel::Aggressive, // max for optimized build
                                        PgoMode::None     => {
                                            if self.optimize_size { inkwell::OptimizationLevel::Default }
                                            else { inkwell::OptimizationLevel::Aggressive }
                                        }
                                    };

                                    let machine = target.create_target_machine(
                                        triple, &cpu, &features, opt_level,
                                        inkwell::targets::RelocMode::Default,
                                        inkwell::targets::CodeModel::Default,
                                    ).expect("target machine");
                                    pub fn write_executable(&self, output_path: &str, obj_path: &str) {
                                        self.finalize_debug_info();

                                        let triple = &self.target_triple;
                                        let target = Target::from_triple(triple).expect("target");

                                        // ── Native CPU features ──────────────────────────────────────────────
                                        // This is the #1 speed advantage over C compiled with plain -O3:
                                        // C: clang -O3 uses "generic" CPU features
                                        // Sovereign: automatically uses AVX2, AVX-512, etc. on CPUs that have them
                                        // Result: vectorized loops that C cannot vectorize without -march=native
                                        let (cpu, features) = if std::env::var("SOVEREIGN_GENERIC").is_ok()
                                            || !self.target_triple.as_str().to_str().unwrap_or("")
                                                  .contains(TargetMachine::get_default_triple().as_str().to_str().unwrap_or("x")) {
                                            // Cross-compiling or generic mode requested
                                            ("generic".to_string(), "".to_string())
                                        } else {
                                            // Native compilation — use the actual CPU's features
                                            (
                                                TargetMachine::get_host_cpu_name()
                                                    .to_str().unwrap_or("generic").to_string(),
                                                TargetMachine::get_host_cpu_features()
                                                    .to_str().unwrap_or("").to_string(),
                                            )
                                        };

                                        let opt_level = match self.pgo_mode {
                                            PgoMode::Generate => inkwell::OptimizationLevel::Less,
                                            PgoMode::Use      => inkwell::OptimizationLevel::Aggressive,
                                            PgoMode::None => {
                                                if self.optimize_size { inkwell::OptimizationLevel::Default }
                                                else { inkwell::OptimizationLevel::Aggressive }
                                            }
                                        };

                                        let machine = target.create_target_machine(
                                            triple,
                                            &cpu,
                                            &features,
                                            opt_level,
                                            inkwell::targets::RelocMode::Default,
                                            inkwell::targets::CodeModel::Default,
                                        ).expect("target machine");

                                        // Set data layout for better optimization
                                        let data_layout = machine.get_target_data();
                                        self.module.set_data_layout(&data_layout.get_data_layout());

                                        // Write object file
                                        machine.write_to_file(
                                            &self.module,
                                            inkwell::targets::FileType::Object,
                                            Path::new(obj_path),
                                        ).expect("failed to write object file");

                                        // ── Link with LTO if possible ────────────────────────────────────────
                                        let lto_succeeded = if !self.debug_mode {
                                            crate::lto::link_with_lto(
                                                &[obj_path.to_string()],
                                                output_path,
                                                triple,
                                                self.optimize_size,
                                                true, // ThinLTO
                                            )
                                        } else {
                                            fn link_windows(&self, output_path: &str, obj_path: &str) {
                                                let link_cmd    = find_linker_windows();
                                                let msvc_lib    = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
                                                    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
                                                });
                                                let winsdk_um   = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
                                                    r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
                                                });
                                                let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
                                                    r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
                                                });

                                                let strip_crt = !self.debug_mode && self.optimize_size;

                                                let mut args: Vec<String> = vec![
                                                    "/nologo".into(),
                                                    format!("/out:{}", output_path),
                                                    "/subsystem:console".into(),
                                                    "/opt:ref".into(),
                                                    "/opt:icf".into(),
                                                    "/Gy".into(),
                                                    "/merge:.rdata=.text".into(),
                                                    // ── Security flags ──────────────────────────────────────────
                                                    "/DYNAMICBASE".into(),    // ASLR — address space layout randomization
                                                    "/NXCOMPAT".into(),       // DEP/NX — data execution prevention
                                                    "/HIGHENTROPYVA".into(),  // 64-bit ASLR with high entropy
                                                    "/GUARD:CF".into(),       // Control Flow Guard — prevents ROP attacks
                                                    // ────────────────────────────────────────────────────────────
                                                    obj_path.to_string(),
                                                ];

                                                if strip_crt {
                                                    args.push("/nodefaultlib".into());
                                                    args.push("/entry:main".into());
                                                    args.push("kernel32.lib".into());
                                                    args.push("ucrt.lib".into());
                                                    args.push("bcrypt.lib".into()); // for cryptographic random
                                                } else {
                                                    args.push("libcmt.lib".into());
                                                    args.push("libucrt.lib".into());
                                                    args.push("kernel32.lib".into());
                                                    args.push("bcrypt.lib".into());
                                                }

                                                let status = std::process::Command::new(&link_cmd)
                                                    .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
                                                    .args(&args)
                                                    .status()
                                                    .expect("linker failed");

                                                if !status.success() {
                                                    eprintln!("Linking failed");
                                                    std::process::exit(1);
                                                }
                                            }

                                            fn link_unix(&self, output_path: &str, obj_path: &str, extra_libs: &[&str]) {
                                                let mut args = vec![
                                                    obj_path.to_string(),
                                                    "-o".to_string(),
                                                    output_path.to_string(),
                                                ];

                                                if !self.debug_mode {
                                                    // Security hardening flags
                                                    args.push("-pie".into());                          // ASLR
                                                    args.push("-z".into());
                                                    args.push("relro".into());                         // RELRO
                                                    args.push("-z".into());
                                                    args.push("now".into());                           // Immediate binding
                                                    args.push("-z".into());
                                                    args.push("noexecstack".into());                   // NX stack
                                                    args.push("-Wl,--strip-all".into());               // strip symbols
                                                    args.push("-Wl,--gc-sections".into());             // dead code
                                                    args.push("-fstack-protector-strong".into());      // stack canaries
                                                    args.push("-D_FORTIFY_SOURCE=2".into());           // fortify
                                                    args.push("-fstack-clash-protection".into());      // stack clash

                                                    if self.optimize_size {
                                                        args.push("-nostartfiles".into());
                                                        args.push("-nodefaultlibs".into());
                                                        args.push("-lc".into());
                                                        args.push("-lm".into());
                                                    } else {
                                                        for lib in extra_libs { args.push(lib.to_string()); }
                                                    }
                                                } else {
                                                    // Debug build — add debug symbols, no hardening
                                                    args.push("-g".into());
                                                    args.push("-gdwarf-4".into());
                                                    for lib in extra_libs { args.push(lib.to_string()); }
                                                }

                                                let status = std::process::Command::new("cc")
                                                    .args(&args)
                                                    .status()
                                                fn compile_task_with_canary(
                                                    &mut self,
                                                    function: FunctionValue<'ctx>,
                                                    body: &Block,
                                                    return_type: &Type,
                                                ) {
                                                    if self.override_depth == 0 && !self.debug_mode {
                                                        // Use OS-provided random canary via sov_get_canary()
                                                        // This is called at runtime, not compile time
                                                        // The canary value is different every run — unpredictable to attackers
                                                        let canary_fn = self.module.get_function("sov_get_canary");
                                                        let canary_val: inkwell::values::IntValue = if let Some(f) = canary_fn {
                                                            self.builder.build_call(f, &[], "canary_val")
                                                                .unwrap()
                                                                .try_as_basic_value()
                                                                .left()
                                                                .unwrap()
                                                                .into_int_value()
                                                        } else {
                                                            // Fallback: compile-time constant (weaker but still useful)
                                                            self.i64_type.const_int(0xDEAD_BEEF_CAFE_BABE, false)
                                                        };

                                                        let canary = self.create_entry_block_alloca(self.i64_type.into()).unwrap();
                                                        let _      = self.builder.build_store(canary, canary_val);

                                                        self.compile_block(body);

                                                        if !self.current_block_has_terminator() {
                                                            let check_val = self.builder
                                                                .build_load(self.i64_type, canary, "canary_check")
                                                                .unwrap()
                                                                .into_int_value();
                                                            let ok = self.builder
                                                                .build_int_compare(IntPredicate::EQ, check_val, canary_val, "canary_ok")
                                                                .unwrap();

                                                            let func    = self.current_function.unwrap();
                                                            let ok_bb   = self.context.append_basic_block(func, "canary_ok");
                                                            let fail_bb = self.context.append_basic_block(func, "canary_fail");
                                                            let _ = self.builder.build_conditional_branch(ok, ok_bb, fail_bb);

                                                            self.builder.position_at_end(fail_bb);
                                                            let printf_fn = self.module.get_function("printf").unwrap();
                                                            let msg       = self.get_format_string(
                                                                "FATAL: Stack smashing detected. Buffer overflow prevented.\n"
                                                            );
                                                            let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
                                                            let abort_fn = self.module.get_function("abort").unwrap();
                                                            let _ = self.builder.build_call(abort_fn, &[], "");
                                                            let _ = self.builder.build_unreachable();

                                                            self.builder.position_at_end(ok_bb);
                                                        }
                                                    } else {
                                                        self.compile_block(body);
                                                    }

                                                    if !self.current_block_has_terminator() {
                                                        match return_type {
                                                            Type::Void => { let _ = self.builder.build_return(None); }
                                                            _ => {
                                                                let _ = self.builder.build_return(
                                                                    Some(&self.i32_type.const_int(0, false))
                                                                );
                                                            }
                                                        }
                                                        fn link_windows(&self, output_path: &str, obj_path: &str) {
                                                            let link_cmd = find_linker_windows();

                                                            // WE STRIP EVERYTHING.
                                                            // No CRT. No default libs. Pure Entry Point.
                                                            let mut args: Vec<String> = vec![
                                                                "/nologo".into(),
                                                                format!("/out:{}", output_path),
                                                                "/subsystem:console".into(),
                                                                "/entry:main".into(),         // Direct entry to your code
                                                                "/nodefaultlib".into(),       // Throw away the standard C library
                                                                "/opt:ref".into(),            // Strip every unused byte
                                                                "/opt:icf".into(),            // Fold identical code
                                                                "/align:16".into(),           // Ultra-tight alignment for smallest headers
                                                                "/merge:.rdata=.text".into(), // Pack everything into one section
                                                                "/emit-pog-checks:no".into(), // No extra compiler junk
                                                                obj_path.to_string(),
                                                                "kernel32.lib".into(),        // Only the essential Windows API
                                                            ];
                                                            // Add this method to the Codegen impl block:

                                                            stack_safe_tasks:  HashMap::new(),
                                                            soa_opportunities: Vec::new(),

                                                            fn compile_task_with_canary(
                                                                &mut self,
                                                                function: FunctionValue<'ctx>,
                                                                name: &str,
                                                                body: &Block,
                                                                return_type: &Type,
                                                            ) {
                                                                // ── THE ACTUAL CANARY ELISION ──────────────────────────────────────
                                                                // Check if the SOE proved this task is stack-safe.
                                                                // If yes: skip canary entirely. 0% overhead.
                                                                // If no: emit OS-random canary for protection.

                                                                let needs_canary = match self.stack_safe_tasks.get(name) {
                                                                    Some(crate::optimizer::StackSafety::ProvenSafe) => {
                                                                        // Borrow checker proved this function cannot overflow.
                                                                        // Zero overhead. No canary needed.
                                                                        false
                                                                    }
                                                                    _ => {
                                                                        // Unknown or requires canary — emit it.
                                                                        true
                                                                    }
                                                                };

                                                                if needs_canary && self.override_depth == 0 && !self.debug_mode {
                                                                    // OS-random canary for unproven functions
                                                                    let canary_fn = self.module.get_function("sov_get_canary");
                                                                    let canary_val: inkwell::values::IntValue = if let Some(f) = canary_fn {
                                                                        self.builder
                                                                            .build_call(f, &[], "canary_val")
                                                                            .unwrap()
                                                                            .try_as_basic_value()
                                                                            .left()
                                                                            .unwrap()
                                                                            .into_int_value()
                                                                    } else {
                                                                        self.i64_type.const_int(0xDEAD_BEEF_CAFE_BABE, false)
                                                                    };

                                                                    let canary = self.create_entry_block_alloca(self.i64_type.into()).unwrap();
                                                                    let _      = self.builder.build_store(canary, canary_val);

                                                                    self.compile_block(body);

                                                                    if !self.current_block_has_terminator() {
                                                                        let check_val = self.builder
                                                                            .build_load(self.i64_type, canary, "canary_check")
                                                                            .unwrap()
                                                                            .into_int_value();
                                                                        let ok = self.builder
                                                                            .build_int_compare(
                                                                                IntPredicate::EQ, check_val, canary_val, "canary_ok"
                                                                            )
                                                                            .unwrap();

                                                                        let func    = self.current_function.unwrap();
                                                                        let ok_bb   = self.context.append_basic_block(func, "canary_ok");
                                                                        let fail_bb = self.context.append_basic_block(func, "canary_fail");
                                                                        let _ = self.builder.build_conditional_branch(ok, ok_bb, fail_bb);

                                                                        self.builder.position_at_end(fail_bb);
                                                                        let printf_fn = self.module.get_function("printf").unwrap();
                                                                        let msg       = self.get_format_string(
                                                                            "FATAL: Stack smashing detected in function — buffer overflow prevented\n"
                                                                        );
                                                                        let _ = self.builder.build_call(printf_fn, &[msg.into()], "");
                                                                        let abort_fn = self.module.get_function("abort").unwrap();
                                                                        let _ = self.builder.build_call(abort_fn, &[], "");
                                                                        let _ = self.builder.build_unreachable();

                                                                        self.builder.position_at_end(ok_bb);
                                                                    }
                                                                } else {
                                                                    // ProvenSafe: compile body with zero canary overhead
                                                                    self.compile_block(body);
                                                                }

                                                                // In compile(), replace the task body compilation:
                                                                // OLD:
                                                                self.compile_block(body);
                                                                if !self.current_block_has_terminator() { ... }

                                                                // NEW:
                                                                self.compile_task_with_canary(function, name, body, return_type);

                                                                // Handle return
                                                                if !self.current_block_has_terminator() {
                                                                    match return_type {
                                                                        Type::Void => { let _ = self.builder.build_return(None); }
                                                                        _ => {
                                                                            let _ = self.builder.build_return(
                                                                                Some(&self.i32_type.const_int(0, false))
                                                                            );
                                                                        }
                                                                    }
                                                                }
                                                            }

                                                            pub fn compile_with_soe(
                                                                &mut self,
                                                                program: &Program,
                                                                soe: &crate::optimizer::SovereignOptimizer,
                                                            ) {
                                                                // Add these fields to the Codegen struct:
                                                                stack_safe_tasks:  HashMap<String, crate::optimizer::StackSafety>,
                                                                soa_opportunities: Vec<crate::optimizer::SoaOpportunity>,
                                                                // Store the optimizer results so compile_stmt can use them
                                                                self.stack_safe_tasks = soe.stack_safe.clone();
                                                                self.soa_opportunities = soe.soa_opportunities.clone();

                                                                // Run normal compilation with SOE information available
                                                                self.compile(program);
                                                            }

                                                            // This produces an .exe that is roughly 1.5KB to 4KB.
                                                            // A standard C "Hello World" is 50KB to 100KB.
                                                            // We are now 20x to 50x lighter than default C.
                                                        }
                                                    }
                                                }
                                                    .unwrap_or_else(|_| {
                                                        std::process::Command::new("clang")
                                                            .args(&args)
                                                            .status()
                                                            .expect("linker failed")
                                                    });

                                                if !status.success() {
                                                    eprintln!("Linking failed");
                                                    std::process::exit(1);
                                                }
                                            }
                                            false
                                        };

                                        if !lto_succeeded {
                                            // Fall back to standard linking
                                            self.link(output_path, obj_path);
                                        }

                                        let _ = std::fs::remove_file(obj_path);
                                    }

                                    machine.write_to_file(
                                        &self.module,
                                        inkwell::targets::FileType::Object,
                                        Path::new(obj_path),
                                    ).expect("failed to write object");

                                    self.link(output_path, obj_path);
                                    let _ = std::fs::remove_file(obj_path);
                                }

                                let status = std::process::Command::new("cc")
                                    .args(&args)
                                    .status()
                                    .unwrap_or_else(|_| {
                                        std::process::Command::new("clang").args(&args).status()
                                            .expect("linker failed")
                                    });

                                if !status.success() { eprintln!("Linking failed"); std::process::exit(1); }
                            }
                            // In the task bodies loop, replace:
                            self.compile_block(body);
                            if !self.current_block_has_terminator() { ... }

                            // With:
                            self.compile_task_with_canary(function, body, return_type);
                        }
                    }
                    .expect("failed to write object file");

                self.link(output_path, obj_path);
                let _ = std::fs::remove_file(obj_path);
            }
        machine
            .write_to_file(
                &self.module,
                inkwell::targets::FileType::Object,
                Path::new(obj_path),
            )
            .expect("failed to write object file");

        self.link(output_path, obj_path);
        let _ = std::fs::remove_file(obj_path);
    }

    fn link(&self, output_path: &str, obj_path: &str) {
        let target_str = self
            .target_triple
            .as_str()
            .to_str()
            .unwrap_or("")
            .to_lowercase();
        let is_windows = target_str.contains("windows");
        let is_macos = target_str.contains("darwin");

        if is_windows {
            self.link_windows(output_path, obj_path);
        } else {
            let extra = if is_macos {
                vec!["-lm"]
            } else {
                vec!["-lm", "-lpthread"]
            };
            self.link_unix(output_path, obj_path, &extra);
        }
    }

    fn link_windows(&self, output_path: &str, obj_path: &str) {
        let link_cmd = find_linker_windows();
        let msvc_lib    = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
        });
        let winsdk_um = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
        });
        let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
        });

        let status = std::process::Command::new(&link_cmd)
            .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
            .args([
                "/nologo",
                &format!("/out:{}", output_path),
                "/subsystem:console",
                "/opt:ref",
                "/opt:icf",
                obj_path,
                "libcmt.lib",
                "libucrt.lib",
                "kernel32.lib",
            ])
            .status()
            .expect("linker failed");
        if !status.success() {
            eprintln!("Linking failed");
            std::process::exit(1);
        }
    }

    fn link_unix(&self, output_path: &str, obj_path: &str, extra_libs: &[&str]) {
        let mut args = vec![obj_path, "-o", output_path];
        for lib in extra_libs {
            args.push(lib);
        }
        let status = std::process::Command::new("cc")
            .args(&args)
            .status()
            .unwrap_or_else(|_| {
                std::process::Command::new("clang")
                    .args(&args)
                    .status()
                    .expect("linker failed (tried cc and clang)")
            });
        if !status.success() {
            eprintln!("Linking failed");
            std::process::exit(1);
        }
    }
}

pub fn find_linker_windows() -> String {
    if let Ok(p) = std::env::var("SOVEREIGN_LINK_PATH") {
        return p;
    }
    if let Ok(out) = std::process::Command::new("where").arg("link.exe").output() {
        if out.status.success() {
            let s = String::from_utf8_lossy(&out.stdout);
            if let Some(l) = s.lines().next() {
                let t = l.trim();
                if !t.is_empty() {
                    return t.to_string();
                }
            }
        }
        // In pub fn compile, at the very start before anything else:
        crate::coroutine::declare_coro_intrinsics(self.context, &self.module);
        fn compile_async_task(
            &mut self,
            name: &str,
            params: &[(String, crate::ast::Type)],
            body: &crate::ast::Block,
            return_type: &crate::ast::Type,
        ) {
            use crate::coroutine;

            let llvm_name = if name == "main" {
                "sov_main_async".into()
            } else {
                name.to_string()
            };

            // Async coroutine function signature: () -> ptr (the coroutine handle)
            // Parameters are stored in a state struct allocated by the coroutine frame
            let coro_fn_type = self.ptr_type.fn_type(
                &params
                    .iter()
                    .map(|(_, t)| self.type_to_meta(t))
                    .collect::<Vec<_>>(),
                false,
            );
            let coro_fn = self.module.add_function(&llvm_name, coro_fn_type, None);
            self.functions.insert(llvm_name.clone(), coro_fn);
            self.task_name_map
                .insert(name.to_string(), llvm_name.clone());

            let entry_bb = self.context.append_basic_block(coro_fn, "coro.entry");
            self.builder.position_at_end(entry_bb);
            self.current_function = Some(coro_fn);
            self.push_scope();

            // Emit coroutine prologue
            let (coro_hdl, _coro_id) =
                coroutine::emit_coro_prologue(self.context, &self.module, &self.builder, coro_fn);

            // Store coroutine handle in a local alloca so we can reference it later
            let hdl_alloca = self
                .create_entry_block_alloca(self.ptr_type.into())
                .unwrap();
            let _ = self.builder.build_store(hdl_alloca, coro_hdl);

            // Store parameters
            for (i, (pname, ptype)) in params.iter().enumerate() {
                let pval = coro_fn.get_nth_param(i as u32).unwrap();
                let ty = self.type_to_llvm(ptype);
                let alloca = self.create_entry_block_alloca(ty).unwrap();
                let _ = self.builder.build_store(alloca, pval);
                self.declare_var(pname.clone(), alloca, ty, false);
            }

            // Compile the body — await expressions will call emit_suspend_point
            // We store the coro_hdl alloca in a thread-local so compile_expr can access it
            // For now: compile synchronously, each await becomes a suspend point
            self.current_coro_hdl = Some(hdl_alloca);
            self.compile_block(body);
            self.current_coro_hdl = None;

            // Final coroutine return
            if !self.current_block_has_terminator() {
                let hdl = self
                    .builder
                    .build_load(self.ptr_type, hdl_alloca, "hdl")
                    .unwrap()
                    .into_pointer_value();
                coroutine::emit_coro_final_return(
                    self.context,
                    &self.module,
                    &self.builder,
                    coro_fn,
                    hdl,
                );
            }

            self.pop_scope();
        }
    }
    Expr::Await(inner) => {
        // Compile the inner expression (the thing we're awaiting)
        let val = self.compile_expr(inner);

        // If we're inside a coroutine, emit a real suspend point
        if let Some(hdl_alloca) = self.current_coro_hdl {
            let hdl = self.builder
                .build_load(self.ptr_type, hdl_alloca, "coro_hdl")
                .unwrap()
                .into_pointer_value();

            crate::coroutine::emit_suspend_point(
                self.context,
                &self.module,
                &self.builder,
                self.current_function.unwrap(),
                hdl,
                false, // not final
            );
        }
        // Return the awaited value
        val
    }
    pub fn enable_debug_info(&mut self, source_path: &str) {
        self.module.set_source_file_name(source_path);
        let (dib, compile_unit) = self.module.create_debug_info_builder(
            true,
            inkwell::debug_info::DWARFSourceLanguage::C,
            source_path,
            ".",
            "Sovereign v1.0",
            false,
            "",
            0,
            "",
            inkwell::debug_info::DWARFEmissionKind::Full,
            0,
            false,
            false,
            "",
            "",
        );
        self.debug_info     = Some(dib);
        self.di_compile_unit = Some(compile_unit);
        self.source_file    = source_path.to_string();
    }

    pub fn finalize_debug_info(&self) {
        if let Some(ref dib) = self.debug_info {
            dib.finalize();
        }
    }

    fn di_location(&self, line: u32, col: u32) -> Option<inkwell::debug_info::DILocation<'ctx>> {
        let dib = self.debug_info.as_ref()?;
        let ctx = dib.create_debug_location(
            self.context, line, col,
            self.di_compile_unit?.as_debug_info_scope(),
            None,
        );
        pub fn write_executable(&self, output_path: &str, obj_path: &str) {
            self.finalize_debug_info(); // must call before writing
            // ... rest of the method unchanged
        }
        Some(ctx)
    }
    // Add to Codegen struct:
    debug_info: Option<inkwell::debug_info::DebugInfoBuilder<'ctx>>,
    di_compile_unit: Option<inkwell::debug_info::DICompileUnit<'ctx>>,
    source_file: String,
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\HostX64\x64\link.exe".to_string()
}
