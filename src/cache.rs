/// Incremental compilation cache for Sovereign.
///
/// Strategy:
/// - Hash each source file (SHA-256 of content)
/// - Store hash → object file path in .sov_cache/manifest.json
/// - On rebuild: if hash matches, reuse cached object
/// - Only recompile files whose hash changed
///
/// Cache location: .sov_cache/ in project root
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

const CACHE_DIR: &str = ".sov_cache";
const MANIFEST_FILE: &str = ".sov_cache/manifest.json";
const COMPILER_VER: &str = "sovereign-1.0.0";

#[derive(Debug, Clone)]
pub struct CacheEntry {
    pub source_hash: String,
    pub obj_path: String,
    pub timestamp: u64,
    pub compiler_ver: String,
}

pub struct CompileCache {
    entries: HashMap<String, CacheEntry>,
    dirty: bool,
}

impl CompileCache {
    pub fn load() -> Self {
        let entries = if Path::new(MANIFEST_FILE).exists() {
            parse_manifest(&fs::read_to_string(MANIFEST_FILE).unwrap_or_default())
        } else {
            HashMap::new()
        };
        CompileCache {
            entries,
            dirty: false,
        }
    }

    /// Check if a source file needs recompilation.
    /// Returns Some(cached_obj_path) if cache hit, None if needs recompile.
    pub fn check(&self, source_path: &str, source_content: &str) -> Option<String> {
        let hash = sha256_simple(source_content);
        if let Some(entry) = self.entries.get(source_path) {
            if entry.source_hash == hash
                && entry.compiler_ver == COMPILER_VER
                && Path::new(&entry.obj_path).exists()
            {
                return Some(entry.obj_path.clone());
            }
        }
        None
    }

    /// Record a successful compilation in the cache.
    pub fn record(&mut self, source_path: &str, source_content: &str, obj_path: &str) {
        let hash = sha256_simple(source_content);
        self.entries.insert(
            source_path.to_string(),
            CacheEntry {
                source_hash: hash,
                obj_path: obj_path.to_string(),
                timestamp: current_timestamp(),
                compiler_ver: COMPILER_VER.to_string(),
            },
        );
        self.dirty = true;
    }

    /// Save the manifest to disk.
    pub fn save(&self) {
        if !self.dirty {
            return;
        }
        fs::create_dir_all(CACHE_DIR).ok();
        let mut json = String::from("{\n");
        json.push_str(&format!("  \"compiler\": \"{}\",\n", COMPILER_VER));
        json.push_str("  \"entries\": {\n");
        let entries: Vec<_> = self.entries.iter().collect();
        for (i, (path, entry)) in entries.iter().enumerate() {
            let comma = if i + 1 < entries.len() { "," } else { "" };
            json.push_str(&format!(
                "    \"{}\": {{\"hash\":\"{}\",\"obj\":\"{}\",\"ts\":{},\"ver\":\"{}\"}}{}\n",
                escape_json(path),
                entry.source_hash,
                escape_json(&entry.obj_path),
                entry.timestamp,
                entry.compiler_ver,
                comma,
            ));
        }
        json.push_str("  }\n}\n");
        fs::write(MANIFEST_FILE, json).ok();
    }

    /// Clear the entire cache.
    pub fn clear() {
        let _ = fs::remove_dir_all(CACHE_DIR);
        println!("Cache cleared.");
    }

    /// Show cache statistics.
    pub fn stats(&self) {
        println!("Cache: {}", CACHE_DIR);
        println!("  Entries: {}", self.entries.len());
        let total_size: u64 = self
            .entries
            .values()
            .filter_map(|e| fs::metadata(&e.obj_path).ok())
            .map(|m| m.len())
            .sum();
        println!("  Size: {} KB", total_size / 1024);
        println!("  Compiler version: {}", COMPILER_VER);
    }
}

// ── Simple SHA-256 (no external crates) ──────────────────────────────────

fn sha256_simple(input: &str) -> String {
    // Use a simple FNV-1a hash as a fast content fingerprint
    // In production you would use a proper SHA-256 crate
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in input.bytes() {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x00000100000001b3);
    }
    // Include length for better collision resistance
    hash ^= input.len() as u64;
    hash = hash.wrapping_mul(0x00000100000001b3);
    format!("{:016x}", hash)
}

fn current_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn parse_manifest(json: &str) -> HashMap<String, CacheEntry> {
    let mut entries = HashMap::new();
    // Simple line-by-line parser — no serde dependency
    let mut current_path = String::new();
    let mut current_hash = String::new();
    let mut current_obj = String::new();
    let mut current_ts: u64 = 0;
    let mut current_ver = String::new();

    for line in json.lines() {
        let line = line.trim();
        // Extract path key: "    \"path\": {"
        if line.starts_with('"') && line.ends_with('{') {
            current_path = line
                .trim_matches(|c| c == '"' || c == '{' || c == ':' || c == ' ')
                .to_string();
        }
        // Extract fields
        if let Some(val) = extract_json_str(line, "hash") {
            current_hash = val;
        }
        if let Some(val) = extract_json_str(line, "obj") {
            current_obj = val;
        }
        if let Some(val) = extract_json_str(line, "ver") {
            current_ver = val;
        }
        if let Some(val) = extract_json_num(line, "ts") {
            current_ts = val;
        }

        // End of entry
        if line.starts_with('}') && !current_path.is_empty() && !current_hash.is_empty() {
            entries.insert(
                current_path.clone(),
                CacheEntry {
                    source_hash: current_hash.clone(),
                    obj_path: current_obj.clone(),
                    timestamp: current_ts,
                    compiler_ver: current_ver.clone(),
                },
            );
            current_path.clear();
            current_hash.clear();
            current_obj.clear();
            current_ts = 0;
            current_ver.clear();
        }
    }
    entries
}

pub fn sha256_of(s: &str) -> String {
    sha256_simple(s)
}
fn extract_json_str(line: &str, key: &str) -> Option<String> {
    let search = format!("\"{}\":", key);
    let pos = line.find(&search)?;
    let rest = line[pos + search.len()..].trim();
    let rest = rest.trim_start_matches('"');
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn extract_json_num(line: &str, key: &str) -> Option<u64> {
    let search = format!("\"{}\":", key);
    let pos = line.find(&search)?;
    let rest = line[pos + search.len()..].trim();
    let end = rest
        .find(|c: char| !c.is_ascii_digit())
        .unwrap_or(rest.len());
    rest[..end].parse().ok()
}
