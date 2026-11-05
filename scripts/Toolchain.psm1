Set-StrictMode -Version Latest

function Get-ProjectRoot {
    return [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
}

function Assert-Windows {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Building and native verification require Windows x64.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'A 64-bit Windows installation is required.'
    }
}

function Get-ProjectVersion {
    $root = Get-ProjectRoot
    $version = [IO.File]::ReadAllText((Join-Path $root 'VERSION')).Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must contain major.minor.patch.' }
    $source = [IO.File]::ReadAllText((Join-Path $root 'PatchToRepo.au3'))
    $expected = "$version.0"
    foreach ($pattern in @(
        '(?m)^#pragma compile\(FileVersion, ([\d.]+)\)\r?$',
        '(?m)^#pragma compile\(ProductVersion, ([\d.]+)\)\r?$',
        '(?m)^#AutoIt3Wrapper_Res_Fileversion=([\d.]+)\r?$'
    )) {
        $match = [regex]::Match($source, $pattern)
        if (-not $match.Success -or $match.Groups[1].Value -ne $expected) {
            throw "Source version metadata does not match VERSION ($version)."
        }
    }
    return $version
}

function Resolve-AutoItToolchain {
    param([string]$AutoItDir = '')
    Assert-Windows
    $candidates = New-Object 'Collections.Generic.List[string]'
    if ($AutoItDir) {
        $candidates.Add([IO.Path]::GetFullPath($AutoItDir))
    } elseif ($env:AUTOIT_HOME) {
        $candidates.Add([IO.Path]::GetFullPath($env:AUTOIT_HOME))
    } else {
        foreach ($base in @($env:ProgramW6432, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
            if ($base) { $candidates.Add((Join-Path $base 'AutoIt3')) }
        }
        $candidates.Add((Join-Path (Get-ProjectRoot) '.tools/autoit/install'))
    }
    foreach ($candidate in $candidates) {
        $interpreter = Join-Path $candidate 'AutoIt3_x64.exe'
        $checker = Join-Path $candidate 'Au3Check.exe'
        $compiler = Join-Path $candidate 'Aut2Exe/Aut2exe_x64.exe'
        if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
            $compiler = Join-Path $candidate 'Aut2Exe/Aut2exe.exe'
        }
        $complete = $true
        foreach ($file in @($interpreter, $checker, $compiler)) {
            if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { $complete = $false }
        }
        if (-not $complete) { continue }
        $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($interpreter)
        $version = [version]::new($info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart)
        if ($version -lt [version]'3.3.16.1') { throw "AutoIt $version is too old; use 3.3.16.1 or newer." }
        return [pscustomobject]@{ Root = $candidate; Interpreter = $interpreter; Checker = $checker; Compiler = $compiler; Version = $version }
    }
    throw 'A complete AutoIt toolchain was not found. Install AutoIt, pass -AutoItDir, or run scripts/Setup-AutoIt.ps1.'
}

function ConvertTo-WindowsArgument {
    param([AllowEmptyString()][string]$Value)
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = (Get-ProjectRoot),
        [int]$TimeoutSeconds = 180
    )
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $FilePath
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' ')
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw "Cannot start $FilePath" }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            $process.WaitForExit()
            throw "Process timed out after $TimeoutSeconds seconds: $FilePath"
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdout.GetAwaiter().GetResult()
            StdErr = $stderr.GetAwaiter().GetResult()
        }
    } finally { $process.Dispose() }
}

function Invoke-SyntaxCheck {
    param([Parameter(Mandatory = $true)]$Toolchain)
    $source = Join-Path (Get-ProjectRoot) 'PatchToRepo.au3'
    $result = Invoke-CapturedProcess -FilePath $Toolchain.Checker -Arguments @('-d', '-w', '3', '-w', '4', '-w', '5', '-w', '6', $source)
    if ($result.StdOut) { Write-Host $result.StdOut }
    if ($result.StdErr) { Write-Host $result.StdErr }
    if ($result.ExitCode -ne 0) { throw "Au3Check failed with exit code $($result.ExitCode)." }
}

function Assert-ApplicationBinary {
    param([Parameter(Mandatory = $true)][string]$Path)
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 256 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) { throw 'Output is not a PE executable.' }
    $pe = [BitConverter]::ToInt32($bytes, 0x3C)
    if ($pe -lt 0 -or $pe -gt $bytes.Length - 94) { throw 'Output has an invalid PE header offset.' }
    if ([BitConverter]::ToUInt32($bytes, $pe) -ne 0x4550 -or [BitConverter]::ToUInt16($bytes, $pe + 4) -ne 0x8664) {
        throw 'Output is not a Windows x64 executable.'
    }
    if ([BitConverter]::ToUInt16($bytes, $pe + 24) -ne 0x20B -or [BitConverter]::ToUInt16($bytes, $pe + 92) -ne 2) {
        throw 'Output is not a PE32+ Windows GUI application.'
    }
    $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
    $actual = '{0}.{1}.{2}.{3}' -f $info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart
    $expected = (Get-ProjectVersion) + '.0'
    if ($actual -ne $expected) { throw "Compiled version $actual does not match $expected." }
}

function Install-CompletedFile {
    param([Parameter(Mandatory = $true)][string]$Source, [Parameter(Mandatory = $true)][string]$Destination)
    if ([IO.File]::Exists($Destination)) {
        [IO.File]::Replace($Source, $Destination, $null)
    } else { [IO.File]::Move($Source, $Destination) }
}

Export-ModuleMember -Function Get-ProjectRoot, Assert-Windows, Get-ProjectVersion, Resolve-AutoItToolchain, ConvertTo-WindowsArgument, Invoke-CapturedProcess, Invoke-SyntaxCheck, Assert-ApplicationBinary, Install-CompletedFile
