param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$OutputDirectory = "$PSScriptRoot\..\artifacts\launcher"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$project = Join-Path $repoRoot "launcher\src\DataTangQCTool.Launcher\DataTangQCTool.Launcher.csproj"
$settings = Join-Path $repoRoot "launcher\src\DataTangQCTool.Launcher\launcher.settings.json"

@{
    manifest_url = "https://github.com/$Repository/releases/latest/download/stable-manifest.json"
    allowed_release_prefix = "https://github.com/$Repository/releases/download/"
} | ConvertTo-Json | Set-Content $settings -Encoding UTF8

Remove-Item $OutputDirectory -Recurse -Force -ErrorAction SilentlyContinue

dotnet publish $project `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:Version=$Version `
    -p:AssemblyVersion=$Version.0 `
    -p:FileVersion=$Version.0 `
    -o $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "Launcher publish failed with exit code $LASTEXITCODE" }
