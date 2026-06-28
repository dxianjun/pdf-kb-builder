param(
    [string]$TargetPath = "D:\ai_tools",
    [string]$Python = "python",
    [switch]$SkipWindowsCapabilities,
    [switch]$UpdateUserEnv
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$requirements = Join-Path $scriptRoot "requirements.txt"

$pythonImportMap = @{
    "markitdown" = @("markitdown")
    "winsdk" = @("winsdk")
    "opencc-python-reimplemented" = @("opencc")
    "pymupdf" = @("fitz")
    "pypdf" = @("pypdf")
    "pdfplumber" = @("pdfplumber")
    "pypdfium2" = @("pypdfium2")
    "reportlab" = @("reportlab")
    "rapidocr" = @("rapidocr")
    "onnxruntime" = @("onnxruntime")
    "opencv-python-headless" = @("cv2")
    "pillow" = @("PIL")
    "numpy" = @("numpy")
}

function Get-RequirementName {
    param([string]$Requirement)

    return (($Requirement -split "[<>=!~; ]", 2)[0]).Trim().ToLowerInvariant()
}

function ConvertTo-PythonListLiteral {
    param([string[]]$Values)

    $quoted = foreach ($value in $Values) {
        "'" + ($value -replace "'", "\\'") + "'"
    }
    return "[" + ($quoted -join ", ") + "]"
}

function Test-PythonImports {
    param([string[]]$Imports)

    $moduleList = ConvertTo-PythonListLiteral $Imports
    $check = @"
import importlib.util
import sys
sys.path.insert(0, r"$TargetPath")
modules = $moduleList
missing = [module for module in modules if importlib.util.find_spec(module) is None]
raise SystemExit(1 if missing else 0)
"@
    & $Python -c $check
    return $LASTEXITCODE -eq 0
}

function Get-MissingPythonRequirements {
    param([string]$RequirementsPath)

    $missing = New-Object System.Collections.Generic.List[string]
    foreach ($line in Get-Content -LiteralPath $RequirementsPath -Encoding UTF8) {
        $requirement = $line.Trim()
        if (-not $requirement -or $requirement.StartsWith("#")) {
            continue
        }

        $name = Get-RequirementName $requirement
        $imports = $pythonImportMap[$name]
        if (-not $imports) {
            $imports = @($name.Replace("-", "_"))
        }

        if (Test-PythonImports $imports) {
            Write-Host "Python requirement already available: $requirement"
        }
        else {
            Write-Host "Python requirement missing: $requirement"
            $missing.Add($requirement) | Out-Null
        }
    }
    return @($missing)
}

function Install-MissingPythonRequirements {
    param([string[]]$MissingRequirements)

    if (-not $MissingRequirements -or $MissingRequirements.Count -eq 0) {
        Write-Host "No missing Python dependencies"
        return
    }

    New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
    $tempRequirements = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -LiteralPath $tempRequirements -Value $MissingRequirements -Encoding UTF8
        Write-Host "Installing missing Python dependencies to $TargetPath"
        & $Python -m pip install --upgrade --target $TargetPath -r $tempRequirements
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempRequirements) {
            Remove-Item -LiteralPath $tempRequirements -Force
        }
    }
}

function Test-IsAdministrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-WindowsCapabilityIfMissing {
    param([string]$Capability)

    $state = (Get-WindowsCapability -Online -Name $Capability -ErrorAction SilentlyContinue).State
    if ($state -eq "Installed") {
        Write-Host "$Capability already installed"
        return
    }

    Write-Host "Installing $Capability"
    Add-WindowsCapability -Online -Name $Capability | Out-Null
}

function Get-CjkFontCandidates {
    return @(
        "$env:WINDIR\Fonts\msjh.ttc",
        "$env:WINDIR\Fonts\mingliu.ttc",
        "$env:WINDIR\Fonts\NotoSansCJK-Regular.ttc",
        "$env:WINDIR\Fonts\simsun.ttc",
        "$env:WINDIR\Fonts\simhei.ttf"
    )
}

function Test-CjkFontAvailable {
    $found = $false
    foreach ($font in Get-CjkFontCandidates) {
        if (Test-Path -LiteralPath $font) {
            Write-Host "Found font: $font"
            $found = $true
        }
    }
    return $found
}

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null

$missingRequirements = Get-MissingPythonRequirements $requirements
Install-MissingPythonRequirements $missingRequirements

if ($UpdateUserEnv) {
    [Environment]::SetEnvironmentVariable("AI_TOOLS_HOME", $TargetPath, "User")
    Write-Host "Set user AI_TOOLS_HOME=$TargetPath"
}

$ocrCapabilities = @(
    "Language.OCR~~~zh-HK~0.0.1.0",
    "Language.OCR~~~zh-TW~0.0.1.0",
    "Language.OCR~~~zh-CN~0.0.1.0"
)
$fontCapabilities = @(
    "Language.Fonts.Hant~~~und-HANT~0.0.1.0",
    "Language.Fonts.Hans~~~und-HANS~0.0.1.0"
)

if (-not $SkipWindowsCapabilities) {
    if (-not (Test-IsAdministrator)) {
        Write-Warning "Windows OCR/font capabilities require an elevated PowerShell. Re-run as Administrator or use -SkipWindowsCapabilities."
    }
    else {
        foreach ($capability in $ocrCapabilities) {
            Install-WindowsCapabilityIfMissing $capability
        }

        Write-Host "Checking common CJK fonts"
        if (Test-CjkFontAvailable) {
            Write-Host "At least one common CJK font already exists; skipping Windows CJK font capability installation."
        }
        else {
            Write-Host "No common CJK font found; installing Windows CJK font capabilities."
            foreach ($capability in $fontCapabilities) {
                Install-WindowsCapabilityIfMissing $capability
            }

            if (-not (Test-CjkFontAvailable)) {
                Write-Warning "No common CJK font was found after installing font capabilities."
            }
        }
    }
}
else {
    Write-Host "Checking common CJK fonts"
    if (-not (Test-CjkFontAvailable)) {
        Write-Warning "No common CJK font found, and -SkipWindowsCapabilities was set."
    }
}

Write-Host "Validating Python imports"
$validationImports = @("fitz", "markitdown", "pypdf", "pdfplumber", "rapidocr", "opencc", "PIL", "numpy", "winsdk")
if (-not (Test-PythonImports $validationImports)) {
    throw "Dependency validation failed"
}

Write-Host "Done"
