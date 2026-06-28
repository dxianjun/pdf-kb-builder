# Dependencies

Windows 使用 `scripts/install_windows_dependencies.ps1` 安装依赖。脚本会把 Python 套件安装到指定目录，例如 `D:\ai_tools`；`pdf_kb.py` 会自动把 `AI_TOOLS_HOME` 加入 `sys.path`。

## Required Python Packages

- `markitdown`：建库第一阶段批量转换新增或变更 PDF，产生 Markdown 基底。
- `pymupdf`：PDF 渲染、页数判定、原生文字抽取，以及 OCR 前的页面图片输出。
- `pdfplumber`：第二套原生文字抽取工具，用于和 PyMuPDF 交叉检查漏抽内容。
- `winsdk`：调用 Windows OCR runtime；需配合 Windows OCR 语言包。
- `rapidocr`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`：Windows OCR 无结果时的 OCR 回退方案。
- `opencc-python-reimplemented`：简繁转换到香港繁体中文。
- `pypdf`, `pypdfium2`, `reportlab`：辅助 PDF 工具与测试/转换能力。

## Sync Contract

`build` uses `.pdf_kb/manifest.json` as the content cache and sync record. Keep search logic in `scripts/pdf_kb.py`; keep KB data in `.pdf_kb`. Do not copy generated KB content into the skill package.

- Added PDF: create a new stable Markdown file under `.pdf_kb/markdown`.
- Deleted PDF: remove the generated Markdown recorded by the old manifest.
- Changed PDF: compare SHA-256 and regenerate Markdown.
- Unchanged PDF: reuse Markdown and rebuild indexes.
- Supplemental `00_*.md` files are user-managed and must not be deleted by sync.

## Windows Capabilities

需要繁体中文 OCR 或字体时，使用系统管理员 PowerShell 安装：

- `Language.OCR~~~zh-HK~0.0.1.0`
- `Language.OCR~~~zh-TW~0.0.1.0`
- `Language.OCR~~~zh-CN~0.0.1.0`
- `Language.Fonts.Hant~~~und-HANT~0.0.1.0`
- `Language.Fonts.Hans~~~und-HANS~0.0.1.0`

## Fonts

不要把 Windows 专有字体复制进技能包。验证主机至少具备以下其中一种字体：

- Microsoft JhengHei: `msjh.ttc`
- MingLiU/PMingLiU: `mingliu.ttc`
- Noto Sans CJK
- SimSun/SimHei for Simplified Chinese fallback
