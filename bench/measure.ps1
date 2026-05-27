# Run this to compare binary sizes
# Sovereign vs C

Write-Host "Building Sovereign hello world..."
sovereign build hello.sov --size -o hello_sovereign.exe
$sov_size = (Get-Item hello_sovereign.exe).Length

Write-Host "Building C hello world..."
$c_code = @'
#include <stdio.h>
int main() { printf("Hello, World!\n"); return 0; }
'@
Set-Content hello.c $c_code

# Default C compilation (what most people use)
cl.exe /O2 hello.c /Fe:hello_c_default.exe
$c_default_size = (Get-Item hello_c_default.exe).Length

# Sovereign Binary Size Comparison
# Run this to prove Sovereign produces smaller binaries than C
#
# Usage: powershell -File measure_size.ps1

Write-Host "========================================"
Write-Host "  Sovereign vs C — Binary Size Test"
Write-Host "========================================"
Write-Host ""

# ── Build Sovereign hello world ──────────────────────────────────────────
Write-Host "Building Sovereign hello world (--size)..."
Set-Content -Path "hello_sov.sov" -Value 'print "Hello, World!"'

$sov_result = & sovereign build hello_sov.sov --size -o hello_sov.exe 2>&1
if (-not (Test-Path "hello_sov.exe")) {
    Write-Host "ERROR: Sovereign build failed" -ForegroundColor Red
    Write-Host $sov_result
    exit 1
}
$sov_size = (Get-Item "hello_sov.exe").Length

# ── Build C hello world (default flags) ──────────────────────────────────
Write-Host "Building C hello world (default cl.exe flags)..."
Set-Content -Path "hello_c.c" -Value @"
#include <stdio.h>
int main() {
    printf("Hello, World!\n");
    return 0;
}
"@

$cl_default = & cmd /c "cl.exe /O2 /nologo hello_c.c /Fe:hello_c_default.exe 2>&1"
$c_default_size = 0
if (Test-Path "hello_c_default.exe") {
    $c_default_size = (Get-Item "hello_c_default.exe").Length
} else {
    Write-Host "Note: cl.exe not found, skipping C comparison" -ForegroundColor Yellow
}

# ── Build C hello world (aggressive flags) ────────────────────────────────
Write-Host "Building C hello world (aggressive flags)..."
$cl_aggressive = & cmd /c "cl.exe /O2 /Gy /GL /nologo hello_c.c /Fe:hello_c_aggressive.exe /link /LTCG /opt:ref /opt:icf /DYNAMICBASE /NXCOMPAT 2>&1"
$c_aggressive_size = 0
if (Test-Path "hello_c_aggressive.exe") {
    $c_aggressive_size = (Get-Item "hello_c_aggressive.exe").Length
}

# ── Results ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================"
Write-Host "  RESULTS"
Write-Host "========================================"
Write-Host ""
Write-Host "  Sovereign (--size):        $sov_size bytes" -ForegroundColor Cyan

if ($c_default_size -gt 0) {
    Write-Host "  C (default -O2):           $c_default_size bytes"
    Write-Host "  C (aggressive LTCG):       $c_aggressive_size bytes"
    Write-Host ""

    if ($sov_size -lt $c_default_size) {
        $diff = $c_default_size - $sov_size
        Write-Host "  ✅ Sovereign is $diff bytes SMALLER than default C" -ForegroundColor Green
    } elseif ($sov_size -eq $c_default_size) {
        Write-Host "  ✅ Sovereign is EQUAL to default C" -ForegroundColor Green
    } else {
        $diff = $sov_size - $c_default_size
        Write-Host "  ⚠️  Sovereign is $diff bytes larger than default C" -ForegroundColor Yellow
        Write-Host "  (This may indicate CRT is still linked — check linker flags)"
    }

    if ($c_aggressive_size -gt 0) {
        if ($sov_size -lt $c_aggressive_size) {
            Write-Host "  ✅ Sovereign is SMALLER than aggressively compiled C" -ForegroundColor Green
        } elseif ($sov_size -le $c_aggressive_size) {
            Write-Host "  ✅ Sovereign matches aggressively compiled C" -ForegroundColor Green
        }
    }
}

Write-Host ""

# ── Cleanup ───────────────────────────────────────────────────────────────
Remove-Item -ErrorAction SilentlyContinue `
    hello_sov.sov, hello_sov.exe, `
    hello_c.c, hello_c.obj, `
    hello_c_default.exe, hello_c_aggressive.exe, `
    hello_c_default.obj, hello_c_aggressive.obj

Write-Host "Done."
# C with same aggressive flags
cl.exe /O2 /Gy /GL hello.c /Fe:hello_c_aggressive.exe /link /LTCG /opt:ref /opt:icf /nodefaultlib /entry:main kernel32.lib ucrt.lib
$c_aggressive_size = (Get-Item hello_c_aggressive.exe).Length

Write-Host ""
Write-Host "=== Binary Size Comparison ==="
Write-Host "Sovereign --size:    $sov_size bytes"
Write-Host "C default (-O2):     $c_default_size bytes"
Write-Host "C aggressive (LTCG): $c_aggressive_size bytes"

if ($sov_size -lt $c_default_size) {
    Write-Host ""
    Write-Host "Sovereign is SMALLER than default C by $($c_default_size - $sov_size) bytes"
}

# Cleanup
Remove-Item -ErrorAction SilentlyContinue hello.c, hello_c_default.exe, hello_c_aggressive.exe, hello_sovereign.exe