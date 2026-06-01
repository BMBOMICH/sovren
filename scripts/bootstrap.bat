@echo off
cd /d "%~dp0\.."

echo Sovereign Bootstrap v0.1.0
echo.

where gcc >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: gcc is required but not installed.
    exit /b 1
)

if not exist build mkdir build

echo Stage 1: Building bootstrap compiler...
gcc -O2 bootstrap/sovereign.c -o build/sovereign.exe -lm
if %errorlevel% neq 0 (echo Failed & exit /b 1)
echo Done.

echo Stage 2: Compiling .sov sources to C...
build\sovereign.exe build compiler/main.sov -o build/stage1.c
if %errorlevel% neq 0 (echo Failed & exit /b 1)
echo Done.

echo Stage 3: Building compiler from Stage 2 output...
gcc -O2 build/stage1.c runtime/runtime.c -o build/sovereign2.exe -lm
if %errorlevel% neq 0 (echo Failed & exit /b 1)
echo Done.

echo Stage 4: Self-compiling with Stage 3...
build\sovereign2.exe build compiler/main.sov -o build/stage2.c
if %errorlevel% neq 0 (echo Failed & exit /b 1)
echo Done.

echo Verifying convergence...
fc /b build/stage1.c build/stage2.c >nul 2>&1
if %errorlevel% equ 0 (
    echo SUCCESS: Self-hosting verified.
) else (
    echo WARNING: Outputs differ.
)
