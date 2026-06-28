# Dependencies

Windows 使用 `scripts/install_windows_dependencies.ps1` 安装依赖。脚本会先复制随包资源，目标目录中已有同名模型或字体则跳过；再检测本机和目标目录中已有的 Python import；已有的包跳过，缺少的包才安装到指定目录，例如 `D:\ai_tools`。`pdf_kb.py` 会自动把 `AI_TOOLS_HOME` 加入 `sys.path`。

## Required Python Packages

- `markitdown`：建库第一阶段批量转换新增或变更 PDF，产生 Markdown 基底。
- `pymupdf`：PDF 渲染、页数判定、原生文字抽取，以及 OCR 前的页面图片输出。
- `pdfplumber`：第二套原生文字抽取工具，用于和 PyMuPDF 交叉检查漏抽内容。
- `winsdk`：调用 Windows OCR Runtime API。可用性以 API 实测为准，不以 `Get-WindowsCapability` 查询结果为准。
- `rapidocr`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`：Windows OCR Runtime API 无结果时的 OCR 回退方案。
- `opencc-python-reimplemented`：简繁转换到香港繁体中文。
- `pypdf`, `pypdfium2`：辅助 PDF 工具与转换能力。

## Sync Contract

`build` uses `.pdf_kb/manifest.json` as the content cache and sync record. Keep search logic in `scripts/pdf_kb.py`; keep KB data in `.pdf_kb`. Do not copy generated KB content into the skill package.

- Added PDF: create a new stable Markdown file under `.pdf_kb/markdown`.
- Deleted PDF: remove the generated Markdown recorded by the old manifest.
- Changed PDF: compare SHA-256 and regenerate Markdown.
- Unchanged PDF: reuse Markdown and rebuild indexes.
- Supplemental `00_*.md` files are user-managed and must not be deleted by sync.

## Bundled Assets

- `assets/rapidocr/models/*.onnx`：随包 RapidOCR 检测、分类、识别模型。安装脚本复制到 `<TargetPath>\rapidocr\models`，已有则跳过。
- `assets/fonts/NotoSansSC-VF.ttf`：随包开源 CJK 兜底字体。安装脚本复制到 `<TargetPath>\fonts`，已有则跳过。
- `assets/windows-ocr/capabilities.json`：记录 OCR Runtime API 语言标签和 Windows capability 兜底名称。Windows OCR runtime 本身是系统能力，不能作为普通文件打包。

## Windows OCR Runtime

优先使用 Windows OCR Runtime API 检测实际可用性：

- `zh-Hant-HK`
- `zh-Hant-TW`
- `zh-Hans-CN`
- `profile_engine`

如果上述 API 实测可用，即使 `Get-WindowsCapability -Online` 因当前会话没有管理员权限而失败，也应视为 Windows OCR 可用。只有 Runtime API 检测失败，并且当前 PowerShell 是管理员权限时，才尝试安装以下 Windows capability：

- `Language.OCR~~~zh-HK~0.0.1.0`
- `Language.OCR~~~zh-TW~0.0.1.0`
- `Language.OCR~~~zh-CN~0.0.1.0`
- `Language.Fonts.Hant~~~und-HANT~0.0.1.0`
- `Language.Fonts.Hans~~~und-HANS~0.0.1.0`

OCR capability 是兜底安装路径；已安装则跳过。字体会先检测随包字体和常见 CJK 字体文件；只在未找到字体文件时，才尝试安装 Windows CJK 字体 capability。

## Fonts

不要把 Windows 专有字体复制进技能包。技能包可携带开源 CJK 字体作为兜底；同时验证主机至少具备以下其中一种字体：

- Microsoft JhengHei: `msjh.ttc`
- MingLiU/PMingLiU: `mingliu.ttc`
- Noto Sans CJK / Noto Sans SC
- SimSun/SimHei for Simplified Chinese fallback
