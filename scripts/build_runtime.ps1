param(
    [string]$PythonVersion = "3.11.9",
    [string]$OutputDirectory = "$PSScriptRoot\..\artifacts"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$buildRoot = Join-Path $repoRoot "build\runtime"
$runtimeRoot = Join-Path $buildRoot "runtime-win-x64"
$downloadRoot = Join-Path $buildRoot "downloads"
$requirements = Join-Path $repoRoot "release\requirements\runtime-requirements.lock"

Remove-Item $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item $runtimeRoot -ItemType Directory -Force | Out-Null
New-Item $downloadRoot -ItemType Directory -Force | Out-Null
New-Item $OutputDirectory -ItemType Directory -Force | Out-Null

$pythonZip = Join-Path $downloadRoot "python-$PythonVersion-embed-amd64.zip"
$pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip
Expand-Archive $pythonZip -DestinationPath $runtimeRoot -Force

$pthFile = Get-ChildItem $runtimeRoot -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) { throw "Embedded Python _pth file was not found." }
$pth = Get-Content $pthFile.FullName
$pth = $pth | ForEach-Object { if ($_ -eq "#import site") { "import site" } else { $_ } }
if ($pth -notcontains "Lib\site-packages") { $pth += "Lib\site-packages" }
Set-Content -Path $pthFile.FullName -Value $pth -Encoding ASCII

$getPip = Join-Path $downloadRoot "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
& (Join-Path $runtimeRoot "python.exe") $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed with exit code $LASTEXITCODE" }

& (Join-Path $runtimeRoot "python.exe") -m pip install `
    --disable-pip-version-check `
    --no-warn-script-location `
    --requirement $requirements
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed with exit code $LASTEXITCODE" }

@{
    schema_version = 1
    python_version = $PythonVersion
    architecture = "win-x64"
    built_at_utc = [DateTime]::UtcNow.ToString("O")
} | ConvertTo-Json | Set-Content (Join-Path $runtimeRoot "runtime-version.json") -Encoding UTF8

$licenseDir = Join-Path $runtimeRoot "licenses"
New-Item $licenseDir -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $repoRoot "LICENSES.md") $licenseDir

$zipPath = Join-Path $OutputDirectory "runtime-win-x64.zip"
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $runtimeRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host $zipPath
