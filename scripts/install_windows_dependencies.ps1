param(
    [string]$TargetPath = "",
    [string]$Python = "python",
    [switch]$Uninstall,
    [switch]$SkipWindowsCapabilities,
    [switch]$UpdateUserEnv,
    [switch]$SkipUserEnv
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
    "rapidocr_onnxruntime" = @("rapidocr_onnxruntime:RapidOCR")
    "onnxruntime" = @("onnxruntime")
    "opencv-python-headless" = @("cv2")
    "pillow" = @("PIL")
    "numpy" = @("numpy")
}

function Resolve-InstallTargetPath {
    param([string]$RequestedPath)

    if ([string]::IsNullOrWhiteSpace($RequestedPath)) {
        $RequestedPath = Get-OwnedToolsPath
    }
    return [System.IO.Path]::GetFullPath($RequestedPath)
}

function Get-OwnedToolsPath {
    return [System.IO.Path]::GetFullPath((Join-Path $skillRoot "tools"))
}

function Add-UniquePath {
    param(
        [System.Collections.Generic.List[string]]$Paths,
        [string]$PathToAdd
    )

    if ([string]::IsNullOrWhiteSpace($PathToAdd)) {
        return
    }

    $fullPath = [System.IO.Path]::GetFullPath($PathToAdd)
    foreach ($existing in $Paths) {
        if (Test-IsSamePath $existing $fullPath) {
            return
        }
    }
    $Paths.Add($fullPath) | Out-Null
}

function Get-DependencySearchPaths {
    $paths = New-Object System.Collections.Generic.List[string]
    Add-UniquePath $paths $TargetPath
    Add-UniquePath $paths "D:\ai_tools"

    foreach ($scope in @("Process", "User", "Machine")) {
        $aiToolsHome = [Environment]::GetEnvironmentVariable("AI_TOOLS_HOME", $scope)
        Add-UniquePath $paths $aiToolsHome
    }

    return @($paths)
}

function Test-IsSamePath {
    param(
        [string]$Left,
        [string]$Right
    )

    $leftFull = [System.IO.Path]::GetFullPath($Left).TrimEnd("\")
    $rightFull = [System.IO.Path]::GetFullPath($Right).TrimEnd("\")
    return [string]::Equals($leftFull, $rightFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function Add-UserPathEntry {
    param([string]$PathToAdd)

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if ($currentPath) {
        $entries = $currentPath -split ";" | Where-Object { $_.Trim() }
    }

    foreach ($entry in $entries) {
        if (Test-IsSamePath $entry $PathToAdd) {
            Write-Host "User Path already contains $PathToAdd"
            return
        }
    }

    $newPath = if ($currentPath) { "$currentPath;$PathToAdd" } else { $PathToAdd }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added $PathToAdd to user Path"
}

function Remove-UserPathEntry {
    param([string]$PathToRemove)

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $currentPath) {
        return
    }

    $keptEntries = New-Object System.Collections.Generic.List[string]
    $removed = $false
    foreach ($entry in ($currentPath -split ";")) {
        $trimmed = $entry.Trim()
        if (-not $trimmed) {
            continue
        }
        if (Test-IsSamePath $trimmed $PathToRemove) {
            $removed = $true
            continue
        }
        $keptEntries.Add($trimmed) | Out-Null
    }

    if ($removed) {
        [Environment]::SetEnvironmentVariable("Path", ($keptEntries -join ";"), "User")
        Write-Host "Removed $PathToRemove from user Path"
    }
}

function Uninstall-OwnedTools {
    $ownedTools = Get-OwnedToolsPath
    $expectedTools = [System.IO.Path]::GetFullPath((Join-Path $skillRoot "tools"))
    if (-not (Test-IsSamePath $ownedTools $expectedTools)) {
        throw "Refusing to uninstall unexpected tools path: $ownedTools"
    }

    if (Test-Path -LiteralPath $ownedTools) {
        Remove-Item -LiteralPath $ownedTools -Recurse -Force
        Write-Host "Removed skill-owned tools directory: $ownedTools"
    }
    else {
        Write-Host "Skill-owned tools directory does not exist: $ownedTools"
    }

    $currentToolsHome = [Environment]::GetEnvironmentVariable("PDF_KB_TOOLS_HOME", "User")
    if ($currentToolsHome -and (Test-IsSamePath $currentToolsHome $ownedTools)) {
        [Environment]::SetEnvironmentVariable("PDF_KB_TOOLS_HOME", $null, "User")
        Write-Host "Removed user PDF_KB_TOOLS_HOME"
    }
    elseif ($currentToolsHome) {
        Write-Host "Leaving user PDF_KB_TOOLS_HOME unchanged: $currentToolsHome"
    }

    Remove-UserPathEntry $ownedTools
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
    $previousSearchPaths = $env:PDF_KB_INSTALL_PATHS
    try {
        $env:PDF_KB_INSTALL_TARGET = $TargetPath
        $env:PDF_KB_INSTALL_PATHS = (Get-DependencySearchPaths) -join [System.IO.Path]::PathSeparator
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

        if ($null -eq $previousSearchPaths) {
            Remove-Item Env:\PDF_KB_INSTALL_PATHS -ErrorAction SilentlyContinue
        }
        else {
            $env:PDF_KB_INSTALL_PATHS = $previousSearchPaths
        }
    }
}

function Test-PythonImports {
    param([string[]]$Imports)

    $moduleList = ConvertTo-PythonListLiteral $Imports
    $check = @"
import importlib.util
import importlib
import os
import sys
for path in reversed([p for p in os.environ.get('PDF_KB_INSTALL_PATHS', '').split(os.pathsep) if p]):
    if os.path.isdir(path):
        sys.path.insert(0, path)
checks = $moduleList

missing = []
for check in checks:
    module_name, _, attr_path = check.partition(':')
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        missing.append(check)
        continue
    if attr_path:
        try:
            module = importlib.import_module(module_name)
            for part in attr_path.split('.'):
                module = getattr(module, part)
        except Exception:
            missing.append(check)
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
for path in reversed([p for p in os.environ.get('PDF_KB_INSTALL_PATHS', '').split(os.pathsep) if p]):
    if os.path.isdir(path):
        sys.path.insert(0, path)
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

if ($Uninstall) {
    Uninstall-OwnedTools
    Write-Host "Done"
    return
}

$TargetPath = Resolve-InstallTargetPath $TargetPath

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
Install-BundledRapidOcrModels
Install-BundledFonts

$missingRequirements = Get-MissingPythonRequirements $requirements
Install-MissingPythonRequirements $missingRequirements

if (-not $SkipUserEnv) {
    [Environment]::SetEnvironmentVariable("PDF_KB_TOOLS_HOME", $TargetPath, "User")
    Write-Host "Set user PDF_KB_TOOLS_HOME=$TargetPath"
    Add-UserPathEntry $TargetPath
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
$validationImports = @("fitz", "markitdown", "pypdf", "pdfplumber", "rapidocr_onnxruntime:RapidOCR", "opencc", "PIL", "numpy", "winsdk")
if (-not (Test-PythonImports $validationImports)) {
    throw "Dependency validation failed"
}

Write-Host "Done"
