[CmdletBinding()]
param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Toolchain.psm1') -Force

$stage = $null
try {
    Assert-Windows
    $root = Get-ProjectRoot
    $pin = Get-Content -LiteralPath (Join-Path $root 'tools/autoit-toolchain.json') -Raw | ConvertFrom-Json
    if (-not $Destination) { $Destination = Join-Path $root '.tools/autoit' }
    $Destination = [IO.Path]::GetFullPath($Destination)
    if (Test-Path -LiteralPath $Destination) {
        throw "Destination already exists: $Destination. Reuse its install folder with -AutoItDir, or choose a new empty destination."
    }
    $parent = [IO.Path]::GetDirectoryName($Destination)
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $stage = Join-Path $parent ('autoit-setup-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    $archive = Join-Path $stage 'autoit.zip'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-Host "Downloading pinned AutoIt $($pin.version) from its official archive..."
    Invoke-WebRequest -Uri $pin.url -OutFile $archive -UseBasicParsing -TimeoutSec 120
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $pin.sha256) { throw 'The AutoIt download SHA-256 does not match the pinned value. No downloaded executable was run.' }
    $expanded = Join-Path $stage 'expanded'
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded
    $toolchain = Resolve-AutoItToolchain -AutoItDir (Join-Path $expanded $pin.extractedRoot)
    if ($toolchain.Version -ne [version]$pin.version) { throw 'Downloaded tool version does not match the pinned version.' }
    [IO.Directory]::Move($expanded, $Destination)
    $installed = Join-Path $Destination $pin.extractedRoot
    Write-Host "AutoIt is ready at $installed"
    Write-Output $installed
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($stage -and [IO.Directory]::Exists($stage)) { [IO.Directory]::Delete($stage, $true) }
}
