$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Test-PythonTkinter($ExePath) {
    & $ExePath -c "import tkinter" *> $null
    return $LASTEXITCODE -eq 0
}

function Remove-GeneratedDirectory($Path) {
    $rootFull = [System.IO.Path]::GetFullPath($Root)
    $targetFull = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside project: $targetFull"
    }
    if (Test-Path $targetFull) {
        Remove-Item -LiteralPath $targetFull -Recurse -Force
    }
}

$Candidates = @()
$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if ($SystemPython) {
    $Candidates += $SystemPython.Source
}

$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $BundledPython) {
    $Candidates += $BundledPython
}

$Python = $null
foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
    if (Test-PythonTkinter $Candidate) {
        $Python = $Candidate
        break
    }
}

if (-not $Python) {
    throw "No Python with Tkinter support was found."
}

$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Marker = Join-Path $VenvDir ".python_source"
$NeedNewVenv = -not (Test-Path $VenvPython)
if (-not $NeedNewVenv) {
    if (Test-Path $Marker) {
        $RecordedPython = (Get-Content $Marker -Raw).Trim()
        $NeedNewVenv = $RecordedPython -ne $Python
    } else {
        $NeedNewVenv = $true
    }
}

if ($NeedNewVenv) {
    Remove-GeneratedDirectory $VenvDir
    & $Python -m venv $VenvDir
    Set-Content -Path $Marker -Value $Python -NoNewline
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements-build.txt")

& $VenvPython -m PyInstaller `
    --noconsole `
    --onefile `
    --clean `
    --name "FrequencyWatermarkTool" `
    --workpath (Join-Path $Root "build") `
    --distpath (Join-Path $Root "dist") `
    --specpath (Join-Path $Root "build") `
    --collect-submodules PIL `
    (Join-Path $Root "app.py")

Write-Host ""
Write-Host "EXE created:"
Write-Host (Join-Path $Root "dist\FrequencyWatermarkTool.exe")
