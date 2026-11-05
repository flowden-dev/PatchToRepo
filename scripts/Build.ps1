[CmdletBinding()]
param([string]$AutoItDir = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Toolchain.psm1') -Force

$stage = $null
try {
    $toolchain = Resolve-AutoItToolchain -AutoItDir $AutoItDir
    $root = Get-ProjectRoot
    $version = Get-ProjectVersion
    $icon = Join-Path $root 'assets/PatchToRepo.ico'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw 'The icon is missing; extract or clone the complete repository.' }
    Invoke-SyntaxCheck -Toolchain $toolchain
    $build = Join-Path $root 'build'
    [IO.Directory]::CreateDirectory($build) | Out-Null
    $stage = Join-Path $build ('PatchToRepo-build-' + [guid]::NewGuid().ToString('N') + '.exe')
    $result = Invoke-CapturedProcess -FilePath $toolchain.Compiler -Arguments @(
        '/in', (Join-Path $root 'PatchToRepo.au3'), '/out', $stage, '/icon', $icon, '/x64', '/gui'
    )
    if ($result.StdOut) { Write-Host $result.StdOut }
    if ($result.StdErr) { Write-Host $result.StdErr }
    if ($result.ExitCode -ne 0 -or -not [IO.File]::Exists($stage)) { throw "Aut2Exe did not produce a successful build (exit $($result.ExitCode))." }
    Assert-ApplicationBinary -Path $stage
    $output = Join-Path $build 'PatchToRepo.exe'
    Install-CompletedFile -Source $stage -Destination $output
    Write-Host "Built Patch to Repo $version with AutoIt $($toolchain.Version): $output"
    Write-Output $output
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($stage -and [IO.File]::Exists($stage)) { [IO.File]::Delete($stage) }
}
