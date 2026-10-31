[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $IdentityName,

    [Parameter(Mandatory = $true)]
    [string] $Publisher,

    [Parameter(Mandatory = $true)]
    [string] $PublisherDisplayName,

    [Parameter(Mandatory = $true)]
    [string] $Version,

    [string] $SourceExe,
    [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($SourceExe)) {
    $SourceExe = Join-Path $root 'sovren.exe'
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $root 'artifacts\store'
}

if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) {
    throw "Sovren executable not found: $SourceExe"
}
if ([IO.Path]::GetExtension($SourceExe) -ne '.exe') {
    throw 'SourceExe must name a Windows .exe file.'
}
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)\.(\d+)$') {
    throw "MSIX version must contain four numbers, for example 1.2.3.0; got '$Version'."
}
$versionParts = $Version.Split('.') | ForEach-Object { [int] $_ }
if ($versionParts[0] -lt 1) {
    throw 'The major package version must be at least 1.'
}
foreach ($part in $versionParts) {
    if ($part -lt 0 -or $part -gt 65535) {
        throw "Every MSIX version component must be between 0 and 65535; got '$Version'."
    }
}
if ([string]::IsNullOrWhiteSpace($IdentityName) -or
    [string]::IsNullOrWhiteSpace($Publisher) -or
    [string]::IsNullOrWhiteSpace($PublisherDisplayName)) {
    throw 'Partner Center identity values must not be empty.'
}
if ($IdentityName.Contains('@@') -or $Publisher.Contains('@@')) {
    throw 'Replace all placeholder Partner Center identity values before packaging.'
}

$layout = Join-Path $OutputDirectory 'layout'
$packagePath = Join-Path $OutputDirectory ("Sovren-{0}-x64.msix" -f $Version)
if (Test-Path -LiteralPath $layout) {
    Remove-Item -LiteralPath $layout -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $layout 'Assets') -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

Copy-Item -LiteralPath $SourceExe -Destination (Join-Path $layout 'sovren.exe')
Copy-Item -LiteralPath (Join-Path $root 'runtime.sov') -Destination $layout
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $layout
Copy-Item -LiteralPath (Join-Path $root 'library') -Destination (Join-Path $layout 'library') -Recurse
Copy-Item -LiteralPath (Join-Path $root 'store\Assets\StoreLogo.png') -Destination (Join-Path $layout 'Assets\StoreLogo.png')
Copy-Item -LiteralPath (Join-Path $root 'store\Assets\Square150x150Logo.png') -Destination (Join-Path $layout 'Assets\Square150x150Logo.png')
Copy-Item -LiteralPath (Join-Path $root 'store\Assets\Square44x44Logo.png') -Destination (Join-Path $layout 'Assets\Square44x44Logo.png')

$template = Get-Content -LiteralPath (Join-Path $root 'store\Package.appxmanifest.in') -Raw
$xmlEscape = {
    param([string] $value)
    return [Security.SecurityElement]::Escape($value)
}
$manifest = $template.Replace('@@IDENTITY_NAME@@', (& $xmlEscape $IdentityName))
$manifest = $manifest.Replace('@@PUBLISHER@@', (& $xmlEscape $Publisher))
$manifest = $manifest.Replace('@@PUBLISHER_DISPLAY_NAME@@', (& $xmlEscape $PublisherDisplayName))
$manifest = $manifest.Replace('@@VERSION@@', $Version)
if ($manifest.Contains('@@')) {
    throw 'The generated manifest still contains an unresolved placeholder.'
}
$manifestPath = Join-Path $layout 'Package.appxmanifest'
[IO.File]::WriteAllText($manifestPath, $manifest, [Text.UTF8Encoding]::new($false))
$null = [xml] (Get-Content -LiteralPath $manifestPath -Raw)

$makeAppx = Get-Command MakeAppx.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $makeAppx) {
    $makeAppx = $makeAppx.Source
} else {
    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $makeAppx = Get-ChildItem -LiteralPath $kits -Filter MakeAppx.exe -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -match '\\x64$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if ([string]::IsNullOrWhiteSpace($makeAppx) -or -not (Test-Path -LiteralPath $makeAppx)) {
    throw 'MakeAppx.exe was not found. Install the Windows 10/11 SDK.'
}

if (Test-Path -LiteralPath $packagePath) {
    Remove-Item -LiteralPath $packagePath -Force
}
& $makeAppx pack /d $layout /p $packagePath /o
if ($LASTEXITCODE -ne 0) {
    throw "MakeAppx failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) {
    throw 'MakeAppx reported success but produced no MSIX package.'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($packagePath)
try {
    $entryNames = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($required in @('AppxManifest.xml', 'sovren.exe', 'runtime.sov', 'library/file.sov')) {
        if ($entryNames -notcontains $required) {
            throw "Generated package is missing required entry '$required'."
        }
    }
} finally {
    $archive.Dispose()
}

$hash = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
$hashPath = "$packagePath.sha256"
[IO.File]::WriteAllText($hashPath, "$hash  $([IO.Path]::GetFileName($packagePath))`n", [Text.UTF8Encoding]::new($false))

Write-Host "MSIX package: $packagePath"
Write-Host "SHA-256:      $hash"
Write-Host 'This package is intentionally unsigned. Microsoft signs it during Store certification.'
if ($env:GITHUB_OUTPUT) {
    "package=$packagePath" | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append
    "hash=$hash" | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append
}
