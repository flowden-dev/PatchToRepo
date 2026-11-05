[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Toolchain.psm1') -Force

$stage = $null
$archiveStage = $null
try {
    Assert-Windows
    $root = Get-ProjectRoot
    $version = Get-ProjectVersion
    $binary = Join-Path $root 'build/PatchToRepo.exe'
    Assert-ApplicationBinary -Path $binary
    $dist = Join-Path $root 'dist'
    [IO.Directory]::CreateDirectory($dist) | Out-Null
    $id = [guid]::NewGuid().ToString('N')
    $stage = Join-Path $dist ('package-' + $id)
    [IO.Directory]::CreateDirectory((Join-Path $stage 'docs')) | Out-Null
    [IO.File]::Copy($binary, (Join-Path $stage 'PatchToRepo.exe'))
    foreach ($file in @('LICENSE', 'THIRD_PARTY_NOTICES.md')) {
        [IO.File]::Copy((Join-Path $root $file), (Join-Path $stage $file))
    }
    [IO.File]::Copy((Join-Path $root 'packaging/README.md'), (Join-Path $stage 'README.md'))
    [IO.File]::Copy((Join-Path $root 'docs/user-guide.md'), (Join-Path $stage 'docs/user-guide.md'))
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $name = "PatchToRepo-$version-win-x64.zip"
    $archiveStage = Join-Path $dist ($id + '.zip')
    [IO.Compression.ZipFile]::CreateFromDirectory($stage, $archiveStage, [IO.Compression.CompressionLevel]::Optimal, $false)
    $output = Join-Path $dist $name
    Install-CompletedFile -Source $archiveStage -Destination $output
    $hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(($output + '.sha256'), "$hash  $name`r`n", [Text.Encoding]::ASCII)
    Write-Host "Packaged $output"
    Write-Output $output
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($archiveStage -and [IO.File]::Exists($archiveStage)) { [IO.File]::Delete($archiveStage) }
    if ($stage -and [IO.Directory]::Exists($stage)) { [IO.Directory]::Delete($stage, $true) }
}
