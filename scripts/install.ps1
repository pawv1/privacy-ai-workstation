# Privacy AI Workstation — Windows helper
# Usage:
#   .\scripts\install.ps1
#   .\scripts\install.ps1 audit
#   .\scripts\install.ps1 install --update --yes
#
# If Python is missing, use .\scripts\bootstrap.ps1 instead.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $Root "privacy-ai-workstation.py"
$MinMajor = 3
$MinMinor = 10

function Test-IsStorePythonAlias {
    param([string]$Path)
    if (-not $Path) { return $true }
    return ($Path -match '(?i)\\WindowsApps\\')
}

function Test-PythonVersion {
    param([string]$Exe)
    if (Test-IsStorePythonAlias -Path $Exe) { return $false }
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

function Find-Python {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $output = & $pyCmd.Source -3 -c "import sys; print(sys.executable); print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
            if ($output -and $output.Count -ge 2) {
                $exe = $output[0].Trim()
                $parts = $output[1].Trim().Split(".")
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if (-not (Test-IsStorePythonAlias -Path $exe)) {
                    if (($major -gt $MinMajor) -or ($major -eq $MinMajor -and $minor -ge $MinMinor)) {
                        return $exe
                    }
                }
            }
        } catch { }
    }

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

if (-not (Test-Path $Script)) {
    Write-Error "Could not find privacy-ai-workstation.py at $Script"
}

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Host "Python $MinMajor.$MinMinor+ was not found." -ForegroundColor Yellow
    Write-Host "Use the bootstrap script to install Python, then continue:"
    Write-Host "  .\scripts\bootstrap.ps1"
    Write-Host "Or download Python from:"
    Write-Host "  https://www.python.org/downloads/windows/"
    exit 1
}

$argsList = $args
if ($argsList.Count -eq 0) {
    $argsList = @("install")
}

& $pythonExe $Script @argsList
exit $LASTEXITCODE
