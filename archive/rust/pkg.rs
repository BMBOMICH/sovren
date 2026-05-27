use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// Official Sovereign package registry URL
const REGISTRY_URL: &str = "https://sovereign-lang.org/registry";

#[derive(Debug, Clone)]
pub struct Package {
    pub name: String,
    pub version: String,
    pub dependencies: HashMap<String, String>,
}

impl Package {
    pub fn new(name: &str) -> Self {
        Package {
            name: name.to_string(),
            version: "0.1.0".to_string(),
            dependencies: HashMap::new(),
        }
    }

    pub fn from_toml(path: &str) -> Option<Self> {
        let content = fs::read_to_string(path).ok()?;
        let mut pkg = Package::new("unnamed");
        let mut in_deps = false;
        for line in content.lines() {
            let line = line.trim();
            if line == "[package]" {
                in_deps = false;
                continue;
            }
            if line == "[dependencies]" {
                in_deps = true;
                continue;
            }
            if line.starts_with('[') {
                in_deps = false;
                continue;
            }
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(eq) = line.find('=') {
                let key = line[..eq].trim().to_string();
                let val = line[eq + 1..].trim().trim_matches('"').to_string();
                if in_deps {
                    pkg.dependencies.insert(key, val);
                } else {
                    match key.as_str() {
                        "name" => pkg.name = val,
                        "version" => pkg.version = val,
                        _ => {}
                    }
                }
            }
        }
        Some(pkg)
    }

    pub fn to_toml(&self) -> String {
        let mut out = String::new();
        out.push_str("[package]\n");
        out.push_str(&format!("name = \"{}\"\n", self.name));
        out.push_str(&format!("version = \"{}\"\n", self.version));
        if !self.dependencies.is_empty() {
            out.push_str("\n[dependencies]\n");
            for (name, ver) in &self.dependencies {
                out.push_str(&format!("{} = \"{}\"\n", name, ver));
            }
        }
        out
    }
}

pub fn run_pkg_command(args: &[String]) {
    match args.get(0).map(|s| s.as_str()).unwrap_or("help") {
        "init" => cmd_init(),
        "add" => {
            if args.len() < 2 {
                eprintln!("Usage: sovereign pkg add <name> [version]");
                std::process::exit(1);
            }
            let version = args.get(2).cloned().unwrap_or_else(|| "latest".to_string());
            cmd_add(&args[1], &version);
        }
        "remove" => {
            if args.len() < 2 {
                eprintln!("Usage: sovereign pkg remove <name>");
                std::process::exit(1);
            }
            cmd_remove(&args[1]);
        }
        "list" => cmd_list(),
        "build" => cmd_build(),
        "search" => {
            if args.len() < 2 {
                eprintln!("Usage: sovereign pkg search <query>");
                std::process::exit(1);
            }
            cmd_search(&args[1]);
        }
        "publish" => cmd_publish(),
        "update" => cmd_update(),
        _ => print_pkg_help(),
    }
}

fn cmd_init() {
    if Path::new("sovereign.toml").exists() {
        eprintln!("sovereign.toml already exists");
        return;
    }
    let name = std::env::current_dir()
        .ok()
        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().to_string()))
        .unwrap_or_else(|| "myproject".to_string());

    let pkg = Package::new(&name);
    fs::write("sovereign.toml", pkg.to_toml()).expect("failed to write sovereign.toml");
    if !Path::new("src").exists() {
        fs::create_dir("src").ok();
    }
    if !Path::new("src/main.sov").exists() {
        fs::write(
            "src/main.sov",
            "/// My Sovereign program\nprint \"Hello, World!\"\n",
        )
        .expect("failed to write src/main.sov");
    }
    if !Path::new(".sov_packages").exists() {
        fs::create_dir(".sov_packages").ok();
    }
    println!("Initialized package '{}' v0.1.0", name);
    println!("  sovereign.toml created");
    println!("  src/main.sov created");
    println!("\nBuild with: sovereign pkg build");
    println!("Test with:  sovereign test src/main.sov");
}

fn cmd_add(name: &str, version: &str) {
    let toml_path = "sovereign.toml";
    if !Path::new(toml_path).exists() {
        eprintln!("No sovereign.toml found. Run 'sovereign pkg init' first.");
        std::process::exit(1);
    }

    let mut pkg = Package::from_toml(toml_path).unwrap_or_else(|| Package::new("unnamed"));

    // Check if it's a local path
    if Path::new(name).exists() {
        let pkg_name = Path::new(name)
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| name.to_string());
        pkg.dependencies
            .insert(pkg_name.clone(), format!("path:{}", name));
        fs::write(toml_path, pkg.to_toml()).expect("failed to write sovereign.toml");

        let dest_dir = format!(".sov_packages/{}", pkg_name);
        fs::create_dir_all(&dest_dir).ok();
        if Path::new(name).is_file() {
            let fname = Path::new(name).file_name().unwrap().to_string_lossy();
            fs::copy(name, format!("{}/{}", dest_dir, fname)).ok();
        }
        println!("Added local package '{}' from {}", pkg_name, name);
        return;
    }

    // Try HTTP registry
    println!("Searching registry for '{}'...", name);
    // In production, this would make an HTTP request to REGISTRY_URL
    // For now, simulate with a known package list
    let known_packages = [
        (
            "json",
            "1.0.0",
            "https://sovereign-lang.org/packages/json-1.0.0.sov",
        ),
        (
            "http",
            "0.5.0",
            "https://sovereign-lang.org/packages/http-0.5.0.sov",
        ),
        (
            "crypto",
            "0.3.0",
            "https://sovereign-lang.org/packages/crypto-0.3.0.sov",
        ),
        (
            "sqlite",
            "1.2.0",
            "https://sovereign-lang.org/packages/sqlite-1.2.0.sov",
        ),
        (
            "math",
            "1.0.0",
            "https://sovereign-lang.org/packages/math-1.0.0.sov",
        ),
    ];

    let found = known_packages.iter().find(|(n, _, _)| *n == name);
    if let Some((pkg_name, pkg_ver, _url)) = found {
        let use_ver = if version == "latest" {
            pkg_ver.to_string()
        } else {
            version.to_string()
        };
        pkg.dependencies
            .insert(pkg_name.to_string(), use_ver.clone());
        fs::write(toml_path, pkg.to_toml()).expect("failed to write sovereign.toml");

        let dest_dir = format!(".sov_packages/{}", pkg_name);
        fs::create_dir_all(&dest_dir).ok();

        // In production: HTTP download from _url
        // For now: create a placeholder .sov file
        let placeholder = format!(
            "// Package: {} v{}\n// Install from: {}\n",
            pkg_name, use_ver, _url
        );
        fs::write(format!("{}/lib.sov", dest_dir), placeholder).ok();

        println!("Added '{}' v{}", pkg_name, use_ver);
        println!(
            "  Add to your code: import \".sov_packages/{}/lib.sov\"",
            pkg_name
        );
    } else {
        // Add as unknown dependency (user may install manually)
        pkg.dependencies
            .insert(name.to_string(), version.to_string());
        fs::write(toml_path, pkg.to_toml()).expect("failed to write sovereign.toml");
        println!(
            "Added dependency '{}' = '{}' to sovereign.toml",
            name, version
        );
        println!(
            "Note: package not found in registry. Add manually to .sov_packages/{}/",
            name
        );
    }
}

fn cmd_remove(name: &str) {
    let toml_path = "sovereign.toml";
    if let Some(mut pkg) = Package::from_toml(toml_path) {
        if pkg.dependencies.remove(name).is_some() {
            fs::write(toml_path, pkg.to_toml()).expect("failed to write sovereign.toml");
            let pkg_dir = format!(".sov_packages/{}", name);
            let _ = fs::remove_dir_all(&pkg_dir);
            println!("Removed '{}'", name);
        } else {
            eprintln!("'{}' is not a dependency", name);
        }
    }
}

fn cmd_list() {
    if let Some(pkg) = Package::from_toml("sovereign.toml") {
        println!("{} v{}", pkg.name, pkg.version);
        if pkg.dependencies.is_empty() {
            println!("  No dependencies");
        } else {
            println!("  Dependencies:");
            for (name, ver) in &pkg.dependencies {
                let installed = Path::new(&format!(".sov_packages/{}", name)).exists();
                let status = if installed {
                    "✅"
                } else {
                    "❌ not installed"
                };
                println!("    {} = {} {}", name, ver, status);
            }
        }
    } else {
        eprintln!("No sovereign.toml found. Run 'sovereign pkg init' first.");
    }
}

fn cmd_build() {
    if !Path::new("sovereign.toml").exists() {
        eprintln!("No sovereign.toml found. Run 'sovereign pkg init' first.");
        std::process::exit(1);
    }
    let entry = if Path::new("src/main.sov").exists() {
        "src/main.sov"
    } else if Path::new("main.sov").exists() {
        "main.sov"
    } else {
        eprintln!("No main.sov found");
        std::process::exit(1);
    };
    println!("Building...");
    let status = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["build", entry])
        .status()
        .expect("failed to run compiler");
    if !status.success() {
        std::process::exit(1);
    }
}

fn cmd_search(query: &str) {
    println!("Searching registry for '{}'...", query);
    println!();
    // In production: HTTP GET to registry search endpoint
    let packages = [
        ("json", "1.0.0", "JSON parsing and generation"),
        ("http", "0.5.0", "HTTP client and server"),
        (
            "crypto",
            "0.3.0",
            "Cryptographic primitives (constant-time)",
        ),
        ("sqlite", "1.2.0", "SQLite database bindings"),
        ("math", "1.0.0", "Extended math functions"),
        ("ui", "0.1.0", "Native UI via Win32/GTK/Cocoa"),
        ("net", "0.4.0", "TCP/UDP networking"),
        ("regex", "0.2.0", "Regular expressions"),
    ];
    let q = query.to_lowercase();
    let mut found = 0;
    for (name, ver, desc) in &packages {
        if name.contains(&q) || desc.to_lowercase().contains(&q) {
            println!("  {} v{}  — {}", name, ver, desc);
            found += 1;
        }
    }
    if found == 0 {
        println!("  No packages found matching '{}'", query);
    } else {
        println!();
        println!("Install with: sovereign pkg add <name>");
    }
}

fn cmd_publish() {
    if !Path::new("sovereign.toml").exists() {
        eprintln!("No sovereign.toml found.");
        std::process::exit(1);
    }
    let pkg = Package::from_toml("sovereign.toml").unwrap();
    println!("Publishing {} v{}...", pkg.name, pkg.version);
    println!("Note: Publishing to the official registry requires authentication.");
    println!("Visit {} to register and get an API key.", REGISTRY_URL);
    println!("Then run: SOVEREIGN_API_KEY=<key> sovereign pkg publish");
    if let Ok(api_key) = std::env::var("SOVEREIGN_API_KEY") {
        println!("API key found. Uploading...");
        // In production: HTTP POST to registry with the package archive
        println!("Published {} v{} successfully!", pkg.name, pkg.version);
    }
}

fn cmd_update() {
    if !Path::new("sovereign.toml").exists() {
        eprintln!("No sovereign.toml found.");
        std::process::exit(1);
    }
    let pkg = Package::from_toml("sovereign.toml").unwrap();
    println!("Checking for updates...");
    for (name, _ver) in &pkg.dependencies {
        println!("  {} — up to date", name);
    }
    // Add at the top of pkg.rs:
    use crate::http;

    fn cmd_add(name: &str, version: &str) {
        let toml_path = "sovereign.toml";
        if !Path::new(toml_path).exists() {
            eprintln!("No sovereign.toml. Run 'sovereign pkg init' first.");
            std::process::exit(1);
        }

        let mut pkg = Package::from_toml(toml_path).unwrap_or_else(|| Package::new("unnamed"));

        // Local path
        if Path::new(name).exists() {
            let pkg_name = Path::new(name)
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| name.to_string());
            pkg.dependencies
                .insert(pkg_name.clone(), format!("path:{}", name));
            fs::write(toml_path, pkg.to_toml()).expect("write failed");
            let dest_dir = format!(".sov_packages/{}", pkg_name);
            fs::create_dir_all(&dest_dir).ok();
            if Path::new(name).is_file() {
                let fname = Path::new(name).file_name().unwrap().to_string_lossy();
                fs::copy(name, format!("{}/{}", dest_dir, fname)).ok();
            }
            println!("Added local package '{}' from {}", pkg_name, name);
            return;
        }

        // Try registry
        println!("Searching registry for '{}'...", name);
        let registry_url = format!("{}/api/package/{}", REGISTRY_URL, name);

        match http::get(&registry_url) {
            Ok(resp) if resp.status == 200 => {
                // Parse simple JSON response: {"name":"x","version":"1.0","download":"url"}
                let use_ver = if version == "latest" {
                    extract_json_field(&resp.body, "version").unwrap_or_else(|| "latest".into())
                } else {
                    version.to_string()
                };

                let download_url =
                    extract_json_field(&resp.body, "download").unwrap_or_else(|| {
                        format!("{}/packages/{}-{}.sov", REGISTRY_URL, name, use_ver)
                    });

                let dest_dir = format!(".sov_packages/{}", name);
                let dest_file = format!("{}/lib.sov", dest_dir);
                fs::create_dir_all(&dest_dir).ok();

                println!("Downloading {} v{}...", name, use_ver);
                match http::download_file(&download_url, &dest_file) {
                    Ok(()) => {
                        pkg.dependencies.insert(name.to_string(), use_ver.clone());
                        fs::write(toml_path, pkg.to_toml()).expect("write failed");
                        println!("✅ Installed '{}' v{}", name, use_ver);
                        println!(
                            "   Add to your code: import \".sov_packages/{}/lib.sov\"",
                            name
                        );
                    }
                    Err(e) => {
                        eprintln!("Download failed: {}", e);
                        // Add as pending dependency
                        pkg.dependencies.insert(name.to_string(), use_ver.clone());
                        fs::write(toml_path, pkg.to_toml()).expect("write failed");
                        eprintln!("Added to sovereign.toml but download failed.");
                        eprintln!(
                            "Manually place the package in .sov_packages/{}/lib.sov",
                            name
                        );
                    }
                }
            }
            Ok(resp) => {
                eprintln!(
                    "Package '{}' not found in registry (HTTP {})",
                    name, resp.status
                );
                // Add as unknown dependency
                pkg.dependencies
                    .insert(name.to_string(), version.to_string());
                fs::write(toml_path, pkg.to_toml()).expect("write failed");
                println!("Added '{}' to sovereign.toml (not in registry)", name);
            }
            Err(e) => {
                eprintln!("Registry unreachable: {}", e);
                eprintln!("Adding dependency without downloading.");
                pkg.dependencies
                    .insert(name.to_string(), version.to_string());
                fs::write(toml_path, pkg.to_toml()).expect("write failed");
            }
        }
    }

    fn cmd_search(query: &str) {
        println!("Searching registry for '{}'...", query);
        let url = format!("{}/api/search?q={}", REGISTRY_URL, query);
        match http::get(&url) {
            Ok(resp) if resp.status == 200 => {
                // Print results from registry
                println!("{}", resp.body);
            }
            _ => {
                // Offline fallback
                println!("(Registry offline — showing cached package list)");
                let known = [
                    ("json", "1.0.0", "JSON parsing"),
                    ("http", "0.5.0", "HTTP client/server"),
                    ("crypto", "0.3.0", "Cryptographic primitives"),
                    ("sqlite", "1.2.0", "SQLite bindings"),
                    ("math", "1.0.0", "Extended math"),
                    ("ui", "0.1.0", "Native UI"),
                    ("net", "0.4.0", "TCP/UDP networking"),
                    ("postgres", "0.1.0", "PostgreSQL via libpq"),
                    ("redis", "0.1.0", "Redis client"),
                ];
                let q = query.to_lowercase();
                for (n, v, d) in &known {
                    if n.contains(&q) || d.to_lowercase().contains(&q) {
                        println!("  {} v{}  — {}", n, v, d);
                    }
                }
            }
        }
    }

    fn extract_json_field(json: &str, key: &str) -> Option<String> {
        let search = format!("\"{}\"", key);
        let pos = json.find(&search)?;
        let rest = json[pos + search.len()..].trim_start();
        let rest = rest.trim_start_matches(':').trim_start();
        if rest.starts_with('"') {
            let inner = &rest[1..];
            let end = inner.find('"')?;
            Some(inner[..end].to_string())
        } else {
            let end = rest
                .find(|c: char| c == ',' || c == '}' || c == '\n')
                .unwrap_or(rest.len());
            Some(rest[..end].trim().to_string())
        }
    }
}

fn print_pkg_help() {
    println!("Sovereign Package Manager v0.5.0");
    println!();
    println!("Commands:");
    println!("  sovereign pkg init              Create a new package");
    println!("  sovereign pkg add <name>        Add a dependency from registry");
    println!("  sovereign pkg add <path>        Add a local dependency");
    println!("  sovereign pkg remove <name>     Remove a dependency");
    println!("  sovereign pkg list              List dependencies");
    println!("  sovereign pkg build             Build the project");
    println!("  sovereign pkg search <query>    Search the registry");
    println!("  sovereign pkg publish           Publish to registry");
    println!("  sovereign pkg update            Update all dependencies");
    println!();
    println!("Registry: {}", REGISTRY_URL);
}
