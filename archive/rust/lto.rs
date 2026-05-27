/// Link-Time Optimization (LTO) for Sovereign.
///
/// LTO allows LLVM to see the entire program at once during
/// optimization, enabling:
///   - Cross-module inlining
///   - Global dead code elimination
///   - Cross-module constant propagation
///   - Interprocedural optimization
///
/// C compiled with plain -O3 does NOT use LTO by default.
/// Sovereign will use it by default.
/// This is a genuine speed advantage.
use inkwell::module::Module;
use inkwell::targets::{Target, TargetMachine, TargetTriple};
use std::path::Path;

pub struct LtoConfig {
    pub enabled: bool,
    pub thin: bool, // ThinLTO = faster compile, nearly same perf as full LTO
    pub cache_dir: String,
}

impl Default for LtoConfig {
    fn default() -> Self {
        LtoConfig {
            enabled: true,
            thin: true, // ThinLTO by default — fast and effective
            cache_dir: ".sov_lto_cache".to_string(),
        }
    }
}

/// Emit LTO bitcode instead of object file.
/// The linker then does the final optimization and code generation.
pub fn emit_lto_bitcode<'ctx>(module: &Module<'ctx>, output_path: &str) -> Result<(), String> {
    let bc_path = format!("{}.bc", output_path.trim_end_matches(".obj"));
    module.write_bitcode_to_path(Path::new(&bc_path));
    Ok(())
}

/// Run LTO using lld (LLVM's linker) which supports LTO natively
pub fn link_with_lto(
    obj_paths: &[String],
    output_path: &str,
    target_triple: &TargetTriple,
    optimize_size: bool,
    thin: bool,
) -> bool {
    let target_str = target_triple.as_str().to_str().unwrap_or("").to_lowercase();
    let is_windows = target_str.contains("windows");

    let lto_flag = if thin { "-flto=thin" } else { "-flto" };
    let opt_flag = if optimize_size { "-Oz" } else { "-O3" };

    if is_windows {
        link_lto_windows(obj_paths, output_path, thin, optimize_size)
    } else {
        link_lto_unix(obj_paths, output_path, lto_flag, opt_flag)
    }
}

fn link_lto_unix(obj_paths: &[String], output_path: &str, lto_flag: &str, opt_flag: &str) -> bool {
    // Try clang first (supports LTO best)
    let mut args: Vec<String> = vec![
        lto_flag.to_string(),
        opt_flag.to_string(),
        "-o".to_string(),
        output_path.to_string(),
        "-Wl,--strip-all".to_string(),   // strip debug from release
        "-Wl,--gc-sections".to_string(), // remove unused sections
        "-lm".to_string(),
    ];
    args.extend(obj_paths.iter().cloned());

    let status = std::process::Command::new("clang").args(&args).status();

    match status {
        Ok(s) if s.success() => true,
        _ => {
            // Fall back to cc without LTO
            eprintln!("Note: LTO requires clang. Falling back to standard linking.");
            false
        }
    }
}

fn link_lto_windows(
    obj_paths: &[String],
    output_path: &str,
    thin: bool,
    optimize_size: bool,
) -> bool {
    // On Windows, LTCG (Link-Time Code Generation) is MSVC's LTO
    // /GL compiles with LTCG support
    // /LTCG links with full optimization
    // This is exactly what /O2 + /LTCG does in release builds

    if let Ok(link_cmd) = std::env::var("SOVEREIGN_LINK_PATH").or_else(|_| {
        Ok::<String, ()>(
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\HostX64\x64\link.exe".to_string()
        )
    }) {
        let msvc_lib = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
        });
        let winsdk_um = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
        });
        let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
        });

        let mut args: Vec<String> = vec![
            "/nologo".into(),
            format!("/out:{}", output_path),
            "/subsystem:console".into(),
            "/opt:ref".into(),
            "/opt:icf".into(),
            "/Gy".into(),
            "/LTCG".into(),              // Full link-time code generation
            "/merge:.rdata=.text".into(),
            "/nodefaultlib".into(),
            "/entry:main".into(),
            "kernel32.lib".into(),
            "ucrt.lib".into(),
        ];
        args.extend(obj_paths.iter().cloned());

        let status = std::process::Command::new(&link_cmd)
            .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
            .args(&args)
            .status();

        return status.map(|s| s.success()).unwrap_or(false);
    }
    false
}
