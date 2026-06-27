# Dependencies

Use `scripts/install_windows_dependencies.ps1` on Windows. It installs Python packages into a target directory such as `D:\ai_tools`; `pdf_kb.py` automatically prepends `AI_TOOLS_HOME` to `sys.path`.

## Required Python Packages

- `pymupdf`: PDF rendering and native text extraction.
- `rapidocr`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`: OCR for image-only pages.
- `opencc-python-reimplemented`: Simplified/traditional conversion to Hong Kong Traditional Chinese.
- `pypdf`, `pdfplumber`, `pypdfium2`, `markitdown`, `reportlab`: companion PDF extraction/rendering/conversion tools.

## Windows Capabilities

Install these with elevated PowerShell when Traditional Chinese OCR or fonts are required:

- `Language.OCR~~~zh-HK~0.0.1.0`
- `Language.OCR~~~zh-TW~0.0.1.0`
- `Language.OCR~~~zh-CN~0.0.1.0`
- `Language.Fonts.Hant~~~und-HANT~0.0.1.0`
- `Language.Fonts.Hans~~~und-HANS~0.0.1.0`

## Fonts

Do not copy proprietary Windows fonts into the skill. Validate that the host has at least one of:

- Microsoft JhengHei: `msjh.ttc`
- MingLiU/PMingLiU: `mingliu.ttc`
- Noto Sans CJK
- SimSun/SimHei for Simplified Chinese fallback
