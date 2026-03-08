$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Executable $($Arguments -join ' ')"
    }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $root ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$pythonExe = "python"

if (-not (Test-Path $venvPath)) {
    try {
        Invoke-Step -Executable "python" -Arguments @("-m", "venv", $venvPath)
    }
    catch {
        Write-Warning "Failed to create .venv, fallback to system Python."
    }
}

$venvHasPip = $false
if (Test-Path $venvPython) {
    try {
        & $venvPython -c "import pip" >$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            $venvHasPip = $true
        }
    }
    catch {
        $venvHasPip = $false
    }

    if ($venvHasPip) {
        $pythonExe = $venvPython
    }
    else {
        Write-Warning ".venv exists but pip is unavailable, fallback to system Python."
    }
}

Invoke-Step -Executable $pythonExe -Arguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Step -Executable $pythonExe -Arguments @("-m", "pip", "install", "-r", (Join-Path $root "requirements.txt"))
Invoke-Step -Executable $pythonExe -Arguments @("-m", "pip", "install", "pyinstaller")

$distPath = Join-Path $root "dist"
$buildPath = Join-Path $root "build"

if (Test-Path $distPath) {
    Remove-Item -Path $distPath -Recurse -Force
}
if (Test-Path $buildPath) {
    Remove-Item -Path $buildPath -Recurse -Force
}

Invoke-Step -Executable $pythonExe -Arguments @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "RubinSolarClock",
    "--collect-all", "customtkinter",
    "--hidden-import", "pystray._win32",
    (Join-Path $root "main.py")
)

Write-Host "Build finished. Output: $distPath\RubinSolarClock.exe"
