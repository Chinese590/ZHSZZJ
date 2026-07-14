param(
    [string]$Version = "1.0.0",
    [string]$OutputDirectory = "$PSScriptRoot\..\artifacts"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$source = Join-Path $repoRoot "desktop\production"
$buildRoot = Join-Path $repoRoot "build\app"
$packageRoot = Join-Path $buildRoot "package"

Remove-Item $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item $packageRoot -ItemType Directory -Force | Out-Null
New-Item $OutputDirectory -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $source "*") $packageRoot -Recurse -Force
@{
    schema_version = 1
    app_version = $Version
    entrypoint = "app/main.py"
    built_at_utc = [DateTime]::UtcNow.ToString("O")
} | ConvertTo-Json | Set-Content (Join-Path $packageRoot "app-version.json") -Encoding UTF8

$zipPath = Join-Path $OutputDirectory "app.zip"
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host $zipPath
