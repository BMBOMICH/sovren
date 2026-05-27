/// Profile-Guided Optimization for Sovereign.
///
/// Usage:
///   sovereign build main.sov --pgo-generate    step 1: instrument
///   ./main.exe                                  step 2: run workload
///   sovereign build main.sov --pgo-use          step 3: optimized build
///
/// PGO allows LLVM to optimize based on real execution data.
/// This can beat C compiled with -O3 because LLVM knows exactly
/// which branches are hot, which functions to inline, and which
/// loops to unroll.
use std::path::Path;

pub const PGO_PROFILE_DIR: &str = ".sov_pgo";
pub const PGO_PROFILE_FILE: &str = ".sov_pgo/merged.profdata";

pub fn pgo_generate_flags() -> String {
    // Tell LLVM to instrument the binary for profiling
    format!("-fprofile-generate={}", PGO_PROFILE_DIR)
}

pub fn pgo_use_flags() -> String {
    format!("-fprofile-use={}", PGO_PROFILE_FILE)
}

/// Check if a PGO profile exists from a previous run
pub fn profile_exists() -> bool {
    // Check for raw profile files
    if let Ok(entries) = std::fs::read_dir(PGO_PROFILE_DIR) {
        for entry in entries.flatten() {
            if entry.path().extension().map_or(false, |e| e == "profraw") {
                return true;
            }
        }
    }
    false
}

/// Merge raw profile data into a single file
pub fn merge_profiles() -> bool {
    std::fs::create_dir_all(PGO_PROFILE_DIR).ok();

    // Find all .profraw files
    let raw_files: Vec<String> = std::fs::read_dir(PGO_PROFILE_DIR)
        .ok()
        .map(|entries| {
            entries
                .flatten()
                .filter(|e| e.path().extension().map_or(false, |ext| ext == "profraw"))
                .map(|e| e.path().to_string_lossy().to_string())
                .collect()
        })
        .unwrap_or_default();

    if raw_files.is_empty() {
        eprintln!(
            "No profile data found in {}. Run the instrumented binary first.",
            PGO_PROFILE_DIR
        );
        return false;
    }

    // Use llvm-profdata to merge
    let mut args = vec![
        "merge".to_string(),
        "-o".to_string(),
        PGO_PROFILE_FILE.to_string(),
    ];
    args.extend(raw_files);

    // Try to find llvm-profdata
    let profdata = find_llvm_profdata();
    let status = std::process::Command::new(&profdata).args(&args).status();

    match status {
        Ok(s) if s.success() => {
            println!("Profile data merged: {}", PGO_PROFILE_FILE);
            true
        }
        _ => {
            eprintln!("Warning: llvm-profdata not found. Skipping profile merge.");
            eprintln!("Install: llvm-18 package or set SOVEREIGN_LLVM_PROFDATA env var");
            false
        }
    }
}

fn find_llvm_profdata() -> String {
    if let Ok(p) = std::env::var("SOVEREIGN_LLVM_PROFDATA") {
        return p;
    }
    for candidate in &["llvm-profdata-18", "llvm-profdata", "llvm-profdata-17"] {
        if std::process::Command::new("which")
            .arg(candidate)
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
        {
            return candidate.to_string();
        }
        if std::process::Command::new("where")
            .arg(candidate)
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
        {
            return candidate.to_string();
        }
    }
    "llvm-profdata".to_string()
}
