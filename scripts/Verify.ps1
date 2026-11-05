[CmdletBinding()]
param([string]$AutoItDir = '', [switch]$IncludeCompiled)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Toolchain.psm1') -Force

function Test-NativeMode {
    param([string]$Executable, [string[]]$Arguments, [string]$Name)
    $root = Get-ProjectRoot
    $logDir = Join-Path $root 'build/test-logs'
    [IO.Directory]::CreateDirectory($logDir) | Out-Null
    $log = Join-Path $logDir ($Name + '.log')
    # Remove a previous success marker before starting a new attempt.
    [IO.File]::WriteAllText($log, "Starting $Name native tests.`r`n")
    $result = Invoke-CapturedProcess -FilePath $Executable -Arguments $Arguments -TimeoutSeconds 300
    $text = $result.StdOut + $result.StdErr
    [IO.File]::WriteAllText($log, $text, (New-Object Text.UTF8Encoding($false)))
    Write-Host $text
    if ($result.ExitCode -ne 0 -or $result.StdOut -notmatch '(?m)^PATCHTOREPO_SELFTEST_PASS\r?$') {
        throw "$Name native self-tests failed or did not finish (exit $($result.ExitCode)). Log: $log"
    }
    Write-Host "$Name native self-tests passed. Log: $log"
}

try {
    $toolchain = Resolve-AutoItToolchain -AutoItDir $AutoItDir
    $root = Get-ProjectRoot
    Get-ProjectVersion | Out-Null
    Invoke-SyntaxCheck -Toolchain $toolchain
    Test-NativeMode -Executable $toolchain.Interpreter -Arguments @('/ErrorStdOut', (Join-Path $root 'PatchToRepo.au3'), '--self-test') -Name 'source'
    if ($IncludeCompiled) {
        $binary = Join-Path $root 'build/PatchToRepo.exe'
        if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'Build the EXE before using -IncludeCompiled.' }
        Assert-ApplicationBinary -Path $binary
        Test-NativeMode -Executable $binary -Arguments @('/ErrorStdOut', '--self-test') -Name 'compiled'
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
