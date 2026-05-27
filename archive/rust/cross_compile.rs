use inkwell::OptimizationLevel;
/// Cross-compilation support for Sovereign.
///
/// Targets:
///   windows-x64     — Windows x86_64 (MSVC ABI)
///   linux-x64       — Linux x86_64 (System V AMD64 ABI)
///   linux-arm64     — Linux AArch64
///   macos-x64       — macOS x86_64
///   macos-arm64     — macOS Apple Silicon
///   wasm32          — WebAssembly 32-bit
///
/// Usage:
///   sovereign build main.sov --target linux-x64
use inkwell::targets::{CodeModel, RelocMode, Target, TargetMachine, TargetTriple};

#[derive(Debug, Clone)]
pub struct CrossTarget {
    pub name: String,
    pub triple: String,
    pub cpu: String,
    pub features: String,
    pub linker: String,
    pub obj_ext: String,
    pub exe_ext: String,
    pub link_args: Vec<String>,
}

impl CrossTarget {
    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "windows-x64" | "windows" => Some(CrossTarget {
                name: "windows-x64".into(),
                triple: "x86_64-pc-windows-msvc".into(),
                cpu: "generic".into(),
                features: "".into(),
                linker: "link.exe".into(),
                obj_ext: "obj".into(),
                exe_ext: "exe".into(),
                link_args: vec![
                    "/nologo".into(),
                    "/subsystem:console".into(),
                    "/opt:ref".into(),
                    "/opt:icf".into(),
                    "libcmt.lib".into(),
                    "libucrt.lib".into(),
                    "kernel32.lib".into(),
                ],
            }),
            "linux-x64" | "linux" => Some(CrossTarget {
                name: "linux-x64".into(),
                triple: "x86_64-unknown-linux-gnu".into(),
                cpu: "generic".into(),
                features: "+sse4.2,+avx2".into(),
                linker: "cc".into(),
                obj_ext: "o".into(),
                exe_ext: "".into(),
                link_args: vec!["-lm".into(), "-lpthread".into(), "-ldl".into()],
            }),
            "linux-arm64" => Some(CrossTarget {
                name: "linux-arm64".into(),
                triple: "aarch64-unknown-linux-gnu".into(),
                cpu: "generic".into(),
                features: "+neon".into(),
                linker: "aarch64-linux-gnu-gcc".into(),
                obj_ext: "o".into(),
                exe_ext: "".into(),
                link_args: vec!["-lm".into(), "-lpthread".into()],
            }),
            "macos-x64" => Some(CrossTarget {
                name: "macos-x64".into(),
                triple: "x86_64-apple-macosx10.15.0".into(),
                cpu: "generic".into(),
                features: "+sse4.2".into(),
                linker: "cc".into(),
                obj_ext: "o".into(),
                exe_ext: "".into(),
                link_args: vec!["-lm".into(), "-lpthread".into()],
            }),
            "macos-arm64" | "macos" => Some(CrossTarget {
                name: "macos-arm64".into(),
                triple: "aarch64-apple-macosx11.0.0".into(),
                cpu: "apple-m1".into(),
                features: "+neon".into(),
                linker: "cc".into(),
                obj_ext: "o".into(),
                exe_ext: "".into(),
                link_args: vec!["-lm".into(), "-lpthread".into()],
            }),
            "wasm32" | "wasm" => Some(CrossTarget {
                name: "wasm32".into(),
                triple: "wasm32-unknown-unknown".into(),
                cpu: "generic".into(),
                features: "".into(),
                linker: "wasm-ld".into(),
                obj_ext: "o".into(),
                exe_ext: "wasm".into(),
                link_args: vec![
                    "--no-entry".into(),
                    "--export-all".into(),
                    "--allow-undefined".into(),
                ],
            }),
            _ => None,
        }
    }

    /// Get the native target for the current machine
    pub fn native() -> Self {
        let triple = TargetMachine::get_default_triple();
        let triple_str = triple.as_str().to_str().unwrap_or("").to_lowercase();

        if triple_str.contains("windows") {
            Self::from_name("windows-x64").unwrap()
        } else if triple_str.contains("darwin") {
            if triple_str.contains("arm") || triple_str.contains("aarch64") {
                Self::from_name("macos-arm64").unwrap()
            } else {
                Self::from_name("macos-x64").unwrap()
            }
        } else {
            if triple_str.contains("aarch64") {
                Self::from_name("linux-arm64").unwrap()
            } else {
                Self::from_name("linux-x64").unwrap()
            }
        }
    }

    /// Create an LLVM TargetMachine for this cross target
    pub fn create_target_machine(&self, opt: OptimizationLevel) -> Option<TargetMachine> {
        Target::initialize_all(&inkwell::targets::InitializationConfig::default());
        let triple = TargetTriple::create(&self.triple);
        let target = Target::from_triple(&triple).ok()?;
        target.create_target_machine(
            &triple,
            &self.cpu,
            &self.features,
            opt,
            RelocMode::Default,
            CodeModel::Default,
        )
    }

    /// Link the object file for this target
    pub fn link(&self, obj_path: &str, out_path: &str, extra_objs: &[String]) {
        if self.linker == "link.exe" {
            self.link_msvc(obj_path, out_path, extra_objs);
        } else {
            self.link_unix(obj_path, out_path, extra_objs);
        }
    }

    fn link_msvc(&self, obj_path: &str, out_path: &str, extra_objs: &[String]) {
        let link_cmd = crate::codegen::find_linker_windows();
        let msvc_lib    = std::env::var("SOVEREIGN_MSVC_LIB").unwrap_or_else(|_| {
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\lib\x64".into()
        });
        let winsdk_um = std::env::var("SOVEREIGN_WINSDK_UM").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64".into()
        });
        let winsdk_ucrt = std::env::var("SOVEREIGN_WINSDK_UCRT").unwrap_or_else(|_| {
            r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x64".into()
        });

        let mut args: Vec<String> = self.link_args.clone();
        args.push(format!("/out:{}", out_path));
        args.push(obj_path.to_string());
        for o in extra_objs {
            args.push(o.clone());
        }

        let status = std::process::Command::new(&link_cmd)
            .env("LIB", format!("{};{};{}", msvc_lib, winsdk_um, winsdk_ucrt))
            .args(&args)
            .status()
            .expect("linker failed");

        if !status.success() {
            eprintln!("Linking failed for target {}", self.name);
            std::process::exit(1);
        }
    }

    fn link_unix(&self, obj_path: &str, out_path: &str, extra_objs: &[String]) {
        let mut args: Vec<String> = Vec::new();
        args.push(obj_path.to_string());
        for o in extra_objs {
            args.push(o.clone());
        }
        args.push("-o".into());
        args.push(out_path.to_string());
        args.extend(self.link_args.clone());

        let linker = &self.linker;
        let status = std::process::Command::new(linker)
            .args(&args)
            .status()
            .unwrap_or_else(|_| {
                std::process::Command::new("cc")
                    .args(&args)
                    .status()
                    .expect("linker failed")
            });

        if !status.success() {
            eprintln!("Linking failed for target {}", self.name);
            std::process::exit(1);
        }
    }
    /// Check if wasm-ld is available, if not try to use lld or provide install instructions
    pub fn find_wasm_linker() -> Option<String> {
        // Check for wasm-ld
        for candidate in &["wasm-ld", "wasm-ld-18", "wasm-ld-17", "lld"] {
            if let Ok(out) = std::process::Command::new("where")
                .arg(candidate)
                .output()
                .or_else(|_| std::process::Command::new("which").arg(candidate).output())
            {
                if out.status.success() {
                    let s = String::from_utf8_lossy(&out.stdout);
                    if let Some(line) = s.lines().next() {
                        let t = line.trim();
                        if !t.is_empty() {
                            return Some(t.to_string());
                        }
                    }
                }
            }
        }
        None
    }

    /// Install wasm-ld automatically via available package manager
    pub fn install_wasm_toolchain() -> bool {
        println!("wasm-ld not found. Attempting to install...");

        if cfg!(target_os = "windows") {
            // Try winget
            let status = std::process::Command::new("winget")
                .args(["install", "LLVM.LLVM", "--silent"])
                .status();
            if status.map(|s| s.success()).unwrap_or(false) {
                println!("✅ LLVM (including wasm-ld) installed via winget");
                return true;
            }
            // Try chocolatey
            let status = std::process::Command::new("choco")
                .args(["install", "llvm", "-y"])
                .status();
            if status.map(|s| s.success()).unwrap_or(false) {
                println!("✅ LLVM installed via chocolatey");
                return true;
            }
            println!("Manual install: winget install LLVM.LLVM");
            println!("Or download from: https://llvm.org/builds/");
        } else if cfg!(target_os = "macos") {
            let status = std::process::Command::new("brew")
                .args(["install", "llvm"])
                .status();
            if status.map(|s| s.success()).unwrap_or(false) {
                println!("✅ LLVM installed via homebrew");
                return true;
            }
        } else {
            // Linux
            for mgr in &[
                vec!["apt-get", "install", "-y", "lld"],
                vec!["dnf", "install", "-y", "lld"],
                vec!["pacman", "-S", "--noconfirm", "lld"],
            ] {
                let status = std::process::Command::new("sudo")
                    .args(mgr.as_slice())
                    .status();
                if status.map(|s| s.success()).unwrap_or(false) {
                    println!("✅ lld installed");
                    return true;
                }
                /// In CrossTarget::link, add WASM special case:
                pub fn link(&self, obj_path: &str, out_path: &str, extra_objs: &[String]) {
                    if self.triple.contains("wasm") {
                        self.link_wasm(obj_path, out_path, extra_objs);
                        return;
                    }
                    if self.linker == "link.exe" {
                        self.link_msvc(obj_path, out_path, extra_objs);
                    } else {
                        self.link_unix(obj_path, out_path, extra_objs);
                    }
                }

                fn link_wasm(&self, obj_path: &str, out_path: &str, _extra_objs: &[String]) {
                    // Find wasm-ld
                    let linker = crate::cross_compile::find_wasm_linker().unwrap_or_else(|| {
                        // Try to install it
                        if !crate::cross_compile::install_wasm_toolchain() {
                            eprintln!("Error: wasm-ld not found.");
                            eprintln!("Install LLVM: https://llvm.org/builds/");
                            eprintln!("Or run: sovereign install-wasm-tools");
                            std::process::exit(1);
                        }
                        crate::cross_compile::find_wasm_linker().unwrap_or_else(|| {
                            eprintln!("wasm-ld still not found after install attempt");
                            std::process::exit(1);
                        })
                    });

                    let mut args: Vec<String> = vec![
                        "--no-entry".into(),
                        "--export-all".into(),
                        "--allow-undefined".into(),
                        "--lto-O3".into(),
                        format!("-o{}", out_path),
                        obj_path.to_string(),
                    ];

                    let status = std::process::Command::new(&linker)
                        .args(&args)
                        .status()
                        .expect("WASM linker failed");

                    if !status.success() {
                        eprintln!("WASM linking failed");
                        std::process::exit(1);
                    }

                    println!("WASM output: {}", out_path);
                    println!("Run in browser with: <script src=\"main.wasm\"></script>");
                    println!("Or with WASI: wasmtime {}", out_path);

                    // Generate a minimal HTML wrapper
                    let html_path = out_path.replace(".wasm", ".html");
                    let html = format!(
                        r#"<!DOCTYPE html>
                <html>
                <head><title>Sovereign WASM</title></head>
                <body>
                <script>
                WebAssembly.instantiateStreaming(fetch('{}'))
                  .then(obj => {{
                    // Call your exported functions here
                    if (obj.instance.exports.main) {{
                      obj.instance.exports.main();
                    }}
                  }});
                </script>
                </body>
                </html>"#,
                        out_path
                    );
                    std::fs::write(&html_path, html).ok();
                    println!("HTML wrapper: {}", html_path);
                }
            }
        }
        false
    }
}

/// Print all available targets
pub fn list_targets() {
    println!("Available cross-compilation targets:");
    println!("  windows-x64    — Windows x86_64 (default on Windows)");
    println!("  linux-x64      — Linux x86_64 (default on Linux)");
    println!("  linux-arm64    — Linux AArch64 (Raspberry Pi 4, servers)");
    println!("  macos-x64      — macOS Intel");
    println!("  macos-arm64    — macOS Apple Silicon (default on macOS)");
    println!("  wasm32         — WebAssembly (runs in browser or WASI)");
}
