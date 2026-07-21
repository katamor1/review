[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Python $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Push-Location $repoRoot
try {
    Invoke-PythonCommand -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-PythonCommand -Arguments @("-m", "pip", "install", "-e", ".[dev,release]")

    if (-not $SkipTests) {
        Invoke-PythonCommand -Arguments @("-m", "pytest")
    }

    Remove-Item -Recurse -Force "build", "dist" -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path "build" | Out-Null

    Invoke-PythonCommand -Arguments @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--noupx",
        "--name", "review-stats",
        "--paths", (Join-Path $repoRoot "src"),
        "--specpath", (Join-Path $repoRoot "build"),
        "--workpath", (Join-Path $repoRoot "build\pyinstaller"),
        "--distpath", (Join-Path $repoRoot "dist"),
        (Join-Path $repoRoot "src\bzr_step_count\release.py")
    )

    $executable = Join-Path $repoRoot "dist\review-stats.exe"
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "PyInstaller completed without producing $executable"
    }

    $item = Get-Item -LiteralPath $executable
    Write-Host ("Built {0} ({1:N0} bytes)" -f $item.FullName, $item.Length)
}
finally {
    Pop-Location
}
