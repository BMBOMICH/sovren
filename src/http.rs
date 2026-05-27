/// HTTP client for Sovereign package manager.
/// Uses WinHTTP on Windows, libcurl on Linux/macOS.
/// Falls back to a subprocess calling curl if neither is available.
use std::io::Write;
use std::path::Path;

#[derive(Debug)]
pub struct HttpResponse {
    pub status: u32,
    pub body: String,
}

pub fn get(url: &str) -> Result<HttpResponse, String> {
    // Try each method in order
    if cfg!(target_os = "windows") {
        winhttp_get(url)
            .or_else(|_| curl_subprocess_get(url))
            .or_else(|_| powershell_get(url))
    } else {
        curl_subprocess_get(url).or_else(|_| wget_subprocess_get(url))
    }
}

pub fn download_file(url: &str, dest: &str) -> Result<(), String> {
    if cfg!(target_os = "windows") {
        curl_subprocess_download(url, dest).or_else(|_| powershell_download(url, dest))
    } else {
        curl_subprocess_download(url, dest).or_else(|_| wget_subprocess_download(url, dest))
    }
}

// ── Windows: WinHTTP via powershell (no extra dependencies) ──────────────

fn powershell_get(url: &str) -> Result<HttpResponse, String> {
    let script = format!(
        r#"$r = Invoke-WebRequest -Uri '{}' -UseBasicParsing; Write-Output $r.StatusCode; Write-Output '---BODY---'; Write-Output $r.Content"#,
        url
    );
    let output = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .output()
        .map_err(|e| e.to_string())?;

    let text = String::from_utf8_lossy(&output.stdout).to_string();
    let parts: Vec<&str> = text.splitn(2, "---BODY---").collect();
    let status: u32 = parts.get(0).unwrap_or(&"0").trim().parse().unwrap_or(0);
    let body = parts.get(1).unwrap_or(&"").trim().to_string();

    if output.status.success() {
        Ok(HttpResponse { status, body })
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn powershell_download(url: &str, dest: &str) -> Result<(), String> {
    let script = format!(
        r#"Invoke-WebRequest -Uri '{}' -OutFile '{}' -UseBasicParsing"#,
        url, dest
    );
    let status = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .status()
        .map_err(|e| e.to_string())?;

    if status.success() {
        Ok(())
    } else {
        Err("PowerShell download failed".into())
    }
}

// ── curl (cross-platform) ─────────────────────────────────────────────────

fn curl_subprocess_get(url: &str) -> Result<HttpResponse, String> {
    let output = std::process::Command::new("curl")
        .args(["-s", "-w", "\n%{http_code}", "--max-time", "30", url])
        .output()
        .map_err(|_| "curl not found".to_string())?;

    let text = String::from_utf8_lossy(&output.stdout).to_string();
    let lines: Vec<&str> = text.rsplitn(2, '\n').collect();
    let status: u32 = lines.get(0).unwrap_or(&"0").trim().parse().unwrap_or(0);
    let body = lines.get(1).unwrap_or(&"").to_string();

    Ok(HttpResponse { status, body })
}

fn curl_subprocess_download(url: &str, dest: &str) -> Result<(), String> {
    let status = std::process::Command::new("curl")
        .args(["-s", "-L", "--max-time", "60", "-o", dest, url])
        .status()
        .map_err(|_| "curl not found".to_string())?;

    if status.success() {
        Ok(())
    } else {
        Err("curl download failed".into())
    }
}

// ── wget (Linux fallback) ─────────────────────────────────────────────────

fn wget_subprocess_get(url: &str) -> Result<HttpResponse, String> {
    let output = std::process::Command::new("wget")
        .args(["-q", "-O", "-", "--timeout=30", url])
        .output()
        .map_err(|_| "wget not found".to_string())?;

    let body = String::from_utf8_lossy(&output.stdout).to_string();
    Ok(HttpResponse {
        status: if output.status.success() { 200 } else { 0 },
        body,
    })
}

fn wget_subprocess_download(url: &str, dest: &str) -> Result<(), String> {
    let status = std::process::Command::new("wget")
        .args(["-q", "--timeout=60", "-O", dest, url])
        .status()
        .map_err(|_| "wget not found".to_string())?;

    if status.success() {
        Ok(())
    } else {
        Err("wget download failed".into())
    }
}

// ── Windows WinHTTP (native, no curl needed) ──────────────────────────────

#[cfg(target_os = "windows")]
fn winhttp_get(url: &str) -> Result<HttpResponse, String> {
    // Parse URL
    let (host, path) = parse_url(url)?;
    let is_https = url.starts_with("https://");

    // Use PowerShell as the actual implementation since WinHTTP
    // requires unsafe FFI setup that is complex to maintain
    powershell_get(url)
}

#[cfg(not(target_os = "windows"))]
fn winhttp_get(_url: &str) -> Result<HttpResponse, String> {
    Err("WinHTTP only available on Windows".into())
}

fn parse_url(url: &str) -> Result<(String, String), String> {
    let without_scheme = url
        .trim_start_matches("https://")
        .trim_start_matches("http://");
    let slash_pos = without_scheme.find('/').unwrap_or(without_scheme.len());
    let host = without_scheme[..slash_pos].to_string();
    let path = if slash_pos < without_scheme.len() {
        without_scheme[slash_pos..].to_string()
    } else {
        "/".to_string()
    };
    Ok((host, path))
}
