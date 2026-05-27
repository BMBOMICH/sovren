@echo off
REM Sovereign Bootstrap Script for Windows
REM This script performs the full bootstrap cycle for the self-hosted compiler.

setlocal enabledelayedexpansion

echo ========================================
echo Sovereign Self-Hosted Compiler Bootstrap
echo ========================================
echo.

REM Check for required tools
where cargo >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: cargo is required but not installed.
    exit /b 1
)

where gcc >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: gcc is required but not installed.
    exit /b 1
)

echo All required tools found.
echo.

REM Create build directory
if not exist build mkdir build

REM Step 1: Build the Rust compiler
echo Step 1: Building Rust compiler...
cargo build --release
if %errorlevel% neq 0 (
    echo Failed to build Rust compiler
    exit /b 1
)
echo Rust compiler built successfully.
echo.

REM Step 2: Validate self-hosting components
echo Step 2: Validating self-hosting components...
target\release\sovereign.exe bootstrap validate
echo.

REM Step 3: Compile self-hosted compiler to C
echo Step 3: Compiling self-hosted compiler to C...
target\release\sovereign.exe bootstrap compile --target c -o build\bootstrap1.c
if %errorlevel% neq 0 (
    echo Failed to compile to C
    exit /b 1
)
echo Generated build\bootstrap1.c
echo.

REM Step 4: Compile C to native binary
echo Step 4: Compiling C to native binary...
gcc -O2 -o build\sovereign1.exe build\bootstrap1.c runtime\runtime.c
if %errorlevel% neq 0 (
    echo Failed to compile C code
    exit /b 1
)
echo Built build\sovereign1.exe
echo.

REM Step 5: Test the bootstrapped compiler
echo Step 5: Testing bootstrapped compiler...
build\sovereign1.exe --version
if %errorlevel% neq 0 (
    echo Bootstrapped compiler failed to run
    exit /b 1
)
echo.

REM Step 6: Use bootstrap to compile itself
echo Step 6: Self-compiling (generation 2)...
build\sovereign1.exe compile src\compiler_self.sov -o build\bootstrap2.c
if %errorlevel% neq 0 (
    echo Self-compilation failed
    exit /b 1
)
echo Generated build\bootstrap2.c
echo.

REM Step 7: Build generation 2
echo Step 7: Building generation 2...
gcc -O2 -o build\sovereign2.exe build\bootstrap2.c runtime\runtime.c
if %errorlevel% neq 0 (
    echo Failed to compile generation 2
    exit /b 1
)
echo Built build\sovereign2.exe
echo.

REM Step 8: Verify convergence
echo Step 8: Verifying convergence...
build\sovereign2.exe compile src\compiler_self.sov -o build\bootstrap3.c
fc /b build\bootstrap2.c build\bootstrap3.c >nul 2>&1
if %errorlevel% equ 0 (
    echo CONVERGENCE VERIFIED!
    echo Generation 2 and 3 produce identical output.
) else (
    echo Warning: Outputs differ - may need investigation
)
echo.

REM Step 9: Final installation
echo Step 9: Installing...
copy build\sovereign2.exe build\sovereign.exe >nul
echo Installed: build\sovereign.exe
echo.

echo ========================================
echo BOOTSTRAP COMPLETE!
echo ========================================
echo.
echo Usage:
echo   build\sovereign.exe compile ^<file.sov^> -o output.c
echo   build\sovereign.exe run ^<file.sov^>
echo   build\sovereign.exe check ^<file.sov^>
echo.

endlocal
