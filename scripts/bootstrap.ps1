# Privacy AI Workstation — Windows bootstrap
# Installs Python 3.12 (if needed) via winget, then runs the workstation CLI.
#
# Usage:
#   .\scripts\bootstrap.ps1
#   .\scripts\bootstrap.ps1 audit
#   .\scripts\bootstrap.ps1 install --yes --start
#
# Manual Python download (if winget is unavailable):
#   https://www.python.org/downloads/windows/
#   Choose the latest stable 64-bit installer, enable "Add python.exe to PATH".

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $Root "privacy-ai-workstation.py"
$MinMajor = 3
$MinMinor = 10
$PreferredWingetId = "Python.Python.3.12"
$PythonDownloads = "https://www.python.org/downloads/windows/"

function Test-IsStorePythonAlias {
    param([string]$Path)
    if (-not $Path) { return $true }
    return ($Path -match '(?i)\\WindowsApps\\')
}

function Test-PythonVersion {
    param([string]$Exe)

    if (Test-IsStorePythonAlias -Path $Exe) {
        return $false
    }

    try {
        $output = & $Exe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if (-not $output) { return $false }
        $parts = $output.Trim().Split(".")
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        return ($major -gt $MinMajor) -or ($major -eq $MinMajor -and $minor -ge $MinMinor)
    } catch {
        return $false
    }
}

function Find-PythonViaPyLauncher {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }

    try {
        # Prefer executable path from py -3 (avoids Microsoft Store alias)
        $output = & $cmd.Source -3 -c "import sys; print(sys.executable); print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if ($output -and $output.Count -ge 2) {
            $exe = $output[0].Trim()
            $verParts = $output[1].Trim().Split(".")
            $major = [int]$verParts[0]
            $minor = [int]$verParts[1]
            if (-not (Test-IsStorePythonAlias -Path $exe)) {
                if (($major -gt $MinMajor) -or ($major -eq $MinMajor -and $minor -ge $MinMinor)) {
                    return $exe
                }
            }
        }
    } catch { }

    return $null
}

function Find-PythonViaPath {
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if (Test-IsStorePythonAlias -Path $cmd.Source) { continue }
        if (Test-PythonVersion -Exe $cmd.Source) {
            return $cmd.Source
        }
    }
    return $null
}

function Find-Python {
    $found = Find-PythonViaPyLauncher
    if ($found) { return $found }

    $found = Find-PythonViaPath
    if ($found) { return $found }

    # Refresh PATH from Machine + User in case Python was just installed
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")

    $found = Find-PythonViaPyLauncher
    if ($found) { return $found }

    return Find-PythonViaPath
}

if (-not (Test-Path $Script)) {
    Write-Error "Could not find privacy-ai-workstation.py at $Script"
}

Write-Host "Privacy AI Workstation bootstrap" -ForegroundColor Cyan
Write-Host "Checking for Python $MinMajor.$MinMinor+ ..."

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Host "Python $MinMajor.$MinMinor+ not found." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host ""
        Write-Host "winget is not available, so Python cannot be installed automatically." -ForegroundColor Red
        Write-Host "Download and install Python manually, then re-run this script:"
        Write-Host "  $PythonDownloads"
        Write-Host "During setup, enable: Add python.exe to PATH"
        exit 1
    }

    Write-Host "Installing $PreferredWingetId via winget ..."
    & winget install --id $PreferredWingetId --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "winget install failed. Install Python manually from:" -ForegroundColor Red
        Write-Host "  $PythonDownloads"
        exit 1
    }

    # New PATH entries usually need a refreshed session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")

    $pythonExe = Find-Python
    if (-not $pythonExe) {
        Write-Host ""
        Write-Host "Python was installed, but this shell cannot see it yet." -ForegroundColor Yellow
        Write-Host "Close this terminal, open a new one, then run:"
        Write-Host "  .\scripts\bootstrap.ps1 $($args -join ' ')"
        Write-Host "Or:"
        Write-Host "  .\scripts\install.ps1 $($args -join ' ')"
        exit 0
    }
}

Write-Host "Using Python: $pythonExe"
& $pythonExe --version

$argsList = $args
if ($argsList.Count -eq 0) {
    $argsList = @("install")
}

Write-Host "Running: privacy-ai-workstation.py $($argsList -join ' ')" -ForegroundColor Cyan
& $pythonExe $Script @argsList
exit $LASTEXITCODE
