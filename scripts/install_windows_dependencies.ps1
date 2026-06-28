param(
    [string]$TargetPath = "D:\ai_tools",
    [string]$Python = "python",
    [switch]$SkipWindowsCapabilities,
    [switch]$UpdateUserEnv
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptRoot
$assetsRoot = Join-Path $skillRoot "assets"
$requirements = Join-Path $scriptRoot "requirements.txt"

$pythonImportMap = @{
    "markitdown" = @("markitdown")
    "winsdk" = @("winsdk")
    "opencc-python-reimplemented" = @("opencc")
    "pymupdf" = @("fitz")
    "pypdf" = @("pypdf")
    "pdfplumber" = @("pdfplumber")
    "pypdfium2" = @("pypdfium2")
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

function Invoke-PythonWithInstallTarget {
    param([string]$Code)

    $previousTarget = $env:PDF_KB_INSTALL_TARGET
    try {
        $env:PDF_KB_INSTALL_TARGET = $TargetPath
        & $Python -c $Code
        return $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousTarget) {
            Remove-Item Env:\PDF_KB_INSTALL_TARGET -ErrorAction SilentlyContinue
        }
        else {
            $env:PDF_KB_INSTALL_TARGET = $previousTarget
        }
    }
}

function Test-PythonImports {
    param([string[]]$Imports)

    $moduleList = ConvertTo-PythonListLiteral $Imports
    $check = @"
import importlib.util
import os
import sys
sys.path.insert(0, os.environ['PDF_KB_INSTALL_TARGET'])
modules = $moduleList
missing = [module for module in modules if importlib.util.find_spec(module) is None]
raise SystemExit(1 if missing else 0)
"@
    return (Invoke-PythonWithInstallTarget $check) -eq 0
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

function Copy-FileIfMissing {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$ExistingMessage,
        [string]$CopyMessage
    )

    if (Test-Path -LiteralPath $Destination) {
        Write-Host "$ExistingMessage $Destination"
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Write-Host "$CopyMessage $Destination"
    Copy-Item -LiteralPath $Source -Destination $Destination
}

function Install-BundledRapidOcrModels {
    $sourceDir = Join-Path $assetsRoot "rapidocr\models"
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Warning "Bundled RapidOCR model directory not found: $sourceDir"
        return
    }

    $targetDir = Join-Path $TargetPath "rapidocr\models"
    foreach ($model in Get-ChildItem -LiteralPath $sourceDir -File -Filter "*.onnx") {
        $destination = Join-Path $targetDir $model.Name
        Copy-FileIfMissing `
            -Source $model.FullName `
            -Destination $destination `
            -ExistingMessage "Skipping existing bundled RapidOCR model:" `
            -CopyMessage "Copying bundled RapidOCR model:"
    }
}

function Install-BundledFonts {
    $sourceDir = Join-Path $assetsRoot "fonts"
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Warning "Bundled font directory not found: $sourceDir"
        return
    }

    $targetDir = Join-Path $TargetPath "fonts"
    $fontFiles = Get-ChildItem -LiteralPath $sourceDir -File | Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".ttf", ".ttc", ".otf")
    }
    foreach ($font in $fontFiles) {
        $destination = Join-Path $targetDir $font.Name
        Copy-FileIfMissing `
            -Source $font.FullName `
            -Destination $destination `
            -ExistingMessage "Skipping existing bundled font:" `
            -CopyMessage "Copying bundled font:"
    }
}

function Get-WindowsOcrManifest {
    $manifestPath = Join-Path $assetsRoot "windows-ocr\capabilities.json"
    if (Test-Path -LiteralPath $manifestPath) {
        return Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
    }
    return $null
}

function Get-BundledWindowsOcrCapabilities {
    $manifest = Get-WindowsOcrManifest
    if ($manifest -and $manifest.ocr_capabilities) {
        return @($manifest.ocr_capabilities)
    }
    return @(
        "Language.OCR~~~zh-HK~0.0.1.0",
        "Language.OCR~~~zh-TW~0.0.1.0",
        "Language.OCR~~~zh-CN~0.0.1.0"
    )
}

function Get-BundledWindowsOcrRuntimeLanguageTags {
    $manifest = Get-WindowsOcrManifest
    if ($manifest -and $manifest.runtime_language_tags) {
        return @($manifest.runtime_language_tags)
    }
    return @("zh-Hant-HK", "zh-Hant-TW", "zh-Hans-CN", "en-US")
}

function Get-BundledWindowsFontCapabilities {
    $manifest = Get-WindowsOcrManifest
    if ($manifest -and $manifest.font_capabilities) {
        return @($manifest.font_capabilities)
    }
    return @(
        "Language.Fonts.Hant~~~und-HANT~0.0.1.0",
        "Language.Fonts.Hans~~~und-HANS~0.0.1.0"
    )
}

function Test-WindowsOcrRuntime {
    $languageTags = ConvertTo-PythonListLiteral (Get-BundledWindowsOcrRuntimeLanguageTags)
    $check = @"
import os
import sys
sys.path.insert(0, os.environ['PDF_KB_INSTALL_TARGET'])
try:
    import winsdk.windows.globalization as win_globalization
    import winsdk.windows.media.ocr as win_ocr
    tags = $languageTags
    supported = {
        tag: bool(win_ocr.OcrEngine.is_language_supported(win_globalization.Language(tag)))
        for tag in tags
    }
    profile_engine = win_ocr.OcrEngine.try_create_from_user_profile_languages() is not None
    required = ['zh-Hant-HK', 'zh-Hant-TW', 'zh-Hans-CN']
    ok = all(supported.get(tag, False) for tag in required) or profile_engine
    raise SystemExit(0 if ok else 1)
except Exception as exc:
    print(f'Windows OCR runtime check failed: {type(exc).__name__}: {exc}')
    raise SystemExit(1)
"@
    $exitCode = Invoke-PythonWithInstallTarget $check
    if ($exitCode -eq 0) {
        Write-Host "Windows OCR runtime is available through Windows OCR API"
        return $true
    }

    Write-Warning "Windows OCR runtime is not available through Windows OCR API."
    return $false
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
    $targetFontDir = Join-Path $TargetPath "fonts"
    $bundledFonts = @()
    if (Test-Path -LiteralPath $targetFontDir) {
        $bundledFonts = Get-ChildItem -LiteralPath $targetFontDir -File | Where-Object {
            $_.Extension.ToLowerInvariant() -in @(".ttf", ".ttc", ".otf")
        } | Select-Object -ExpandProperty FullName
    }

    return @(
        $bundledFonts
        "$env:WINDIR\Fonts\msjh.ttc",
        "$env:WINDIR\Fonts\mingliu.ttc",
        "$env:WINDIR\Fonts\NotoSansCJK-Regular.ttc",
        "$env:WINDIR\Fonts\NotoSansSC-VF.ttf",
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
Install-BundledRapidOcrModels
Install-BundledFonts

$missingRequirements = Get-MissingPythonRequirements $requirements
Install-MissingPythonRequirements $missingRequirements

if ($UpdateUserEnv) {
    [Environment]::SetEnvironmentVariable("AI_TOOLS_HOME", $TargetPath, "User")
    Write-Host "Set user AI_TOOLS_HOME=$TargetPath"
}

$ocrCapabilities = Get-BundledWindowsOcrCapabilities
$fontCapabilities = Get-BundledWindowsFontCapabilities
$windowsOcrRuntimeAvailable = Test-WindowsOcrRuntime

Write-Host "Checking common CJK fonts"
$cjkFontAvailable = Test-CjkFontAvailable

if (-not $SkipWindowsCapabilities) {
    if ($windowsOcrRuntimeAvailable) {
        Write-Host "Windows OCR runtime is available through Windows OCR API; skipping Windows OCR capability installation."
    }

    if ($cjkFontAvailable) {
        Write-Host "At least one common CJK font already exists; skipping Windows CJK font capability installation."
    }

    if ($windowsOcrRuntimeAvailable -and $cjkFontAvailable) {
        Write-Host "Windows OCR runtime and CJK fonts are already available."
    }
    elseif (-not (Test-IsAdministrator)) {
        Write-Warning "Missing Windows OCR/font capability fallback requires an elevated PowerShell. Re-run as Administrator or use -SkipWindowsCapabilities."
    }
    else {
        if (-not $windowsOcrRuntimeAvailable) {
            foreach ($capability in $ocrCapabilities) {
                Install-WindowsCapabilityIfMissing $capability
            }
        }

        if (-not $cjkFontAvailable) {
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
    if (-not $windowsOcrRuntimeAvailable) {
        Write-Warning "Windows OCR runtime is not available, and -SkipWindowsCapabilities was set."
    }
    if (-not $cjkFontAvailable) {
        Write-Warning "No common CJK font found, and -SkipWindowsCapabilities was set."
    }
}

Write-Host "Validating Python imports"
$validationImports = @("fitz", "markitdown", "pypdf", "pdfplumber", "rapidocr", "opencc", "PIL", "numpy", "winsdk")
if (-not (Test-PythonImports $validationImports)) {
    throw "Dependency validation failed"
}

Write-Host "Done"
