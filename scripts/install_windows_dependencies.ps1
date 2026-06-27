param(
    [string]$TargetPath = "D:\ai_tools",
    [string]$Python = "python",
    [switch]$SkipWindowsCapabilities,
    [switch]$UpdateUserEnv
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$requirements = Join-Path $scriptRoot "requirements.txt"

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null

Write-Host "Installing Python dependencies to $TargetPath"
& $Python -m pip install --upgrade --target $TargetPath -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed with exit code $LASTEXITCODE"
}

if ($UpdateUserEnv) {
    [Environment]::SetEnvironmentVariable("AI_TOOLS_HOME", $TargetPath, "User")
    Write-Host "Set user AI_TOOLS_HOME=$TargetPath"
}

if (-not $SkipWindowsCapabilities) {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Warning "Windows OCR/font capabilities require an elevated PowerShell. Re-run as Administrator or use -SkipWindowsCapabilities."
    }
    else {
        $capabilities = @(
            "Language.OCR~~~zh-HK~0.0.1.0",
            "Language.OCR~~~zh-TW~0.0.1.0",
            "Language.OCR~~~zh-CN~0.0.1.0",
            "Language.Fonts.Hant~~~und-HANT~0.0.1.0",
            "Language.Fonts.Hans~~~und-HANS~0.0.1.0"
        )

        foreach ($capability in $capabilities) {
            $state = (Get-WindowsCapability -Online -Name $capability -ErrorAction SilentlyContinue).State
            if ($state -eq "Installed") {
                Write-Host "$capability already installed"
                continue
            }
            Write-Host "Installing $capability"
            Add-WindowsCapability -Online -Name $capability | Out-Null
        }
    }
}

Write-Host "Checking common CJK fonts"
$fontCandidates = @(
    "$env:WINDIR\Fonts\msjh.ttc",
    "$env:WINDIR\Fonts\mingliu.ttc",
    "$env:WINDIR\Fonts\NotoSansCJK-Regular.ttc",
    "$env:WINDIR\Fonts\simsun.ttc",
    "$env:WINDIR\Fonts\simhei.ttf"
)
foreach ($font in $fontCandidates) {
    if (Test-Path $font) {
        Write-Host "Found font: $font"
    }
}

Write-Host "Validating Python imports"
$validation = @"
import sys
sys.path.insert(0, r"$TargetPath")
import fitz, pypdf, pdfplumber, rapidocr, opencc, PIL, numpy
print("dependencies ok")
"@
& $Python -c $validation
if ($LASTEXITCODE -ne 0) {
    throw "Dependency validation failed with exit code $LASTEXITCODE"
}

Write-Host "Done"
