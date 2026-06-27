# Dependencies

Windows 使用 `scripts/install_windows_dependencies.ps1` 安裝依賴。腳本會把 Python 套件安裝到指定目錄，例如 `D:\ai_tools`；`pdf_kb.py` 會自動把 `AI_TOOLS_HOME` 加入 `sys.path`。

## Required Python Packages

- `markitdown`：第一次轉換 PDF 時產生 Markdown 基底。
- `pymupdf`：PDF 渲染、頁數判定、原生文字抽取，以及 OCR 前的頁面圖片輸出。
- `pdfplumber`：第二套原生文字抽取工具，用於和 PyMuPDF 交叉檢查漏抽內容。
- `winsdk`：呼叫 Windows OCR runtime；需配合 Windows OCR 語言包。
- `rapidocr`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`：Windows OCR 無結果時的 OCR 回退方案。
- `opencc-python-reimplemented`：簡繁轉換到香港繁體中文。
- `pypdf`, `pypdfium2`, `reportlab`：輔助 PDF 工具與測試/轉換能力。

## Sync Contract

`build` uses `.pdf_kb/manifest.json` as the content cache and sync record. Keep search logic in `scripts/pdf_kb.py`; keep KB data in `.pdf_kb`. Do not copy generated KB content into the skill package.

- Added PDF: create a new stable Markdown file under `.pdf_kb/markdown`.
- Deleted PDF: remove the generated Markdown recorded by the old manifest.
- Changed PDF: compare SHA-256 and regenerate Markdown.
- Unchanged PDF: reuse Markdown and rebuild indexes.
- Supplemental `00_*.md` files are user-managed and must not be deleted by sync.

## Windows Capabilities

需要繁體中文 OCR 或字體時，使用系統管理員 PowerShell 安裝：

- `Language.OCR~~~zh-HK~0.0.1.0`
- `Language.OCR~~~zh-TW~0.0.1.0`
- `Language.OCR~~~zh-CN~0.0.1.0`
- `Language.Fonts.Hant~~~und-HANT~0.0.1.0`
- `Language.Fonts.Hans~~~und-HANS~0.0.1.0`

## Fonts

不要把 Windows 專有字體複製進技能包。驗證主機至少具備以下其中一種字體：

- Microsoft JhengHei: `msjh.ttc`
- MingLiU/PMingLiU: `mingliu.ttc`
- Noto Sans CJK
- SimSun/SimHei for Simplified Chinese fallback
