# Dependencies

Windows 使用 `scripts/install_windows_dependencies.ps1` 安装依赖。脚本默认目标是技能根目录下的 `tools`。如果用户明确需要其他依赖目录，可以传入 `-TargetPath`；这不是必须使用技能内 `tools` 的硬性限制。脚本先联合检测系统/全局 Python 包（`site.getsitepackages()`、`site.getusersitepackages()`、`sys.path`）与 `AI_TOOLS_HOME`（若已设置）及其直接子目录；已有的包跳过，缺少的包才安装到目标目录。`pdf_kb.py` 会自动把 `PDF_KB_TOOLS_HOME` 或默认 `tools`、`AI_TOOLS_HOME`（若已设置）及其子目录加入 `sys.path`，同时保留 Python 自身的全局路径。

不要把依赖包安装到 `AI_TOOLS_HOME` 根目录，也不要清理或覆盖该目录中已有的其他工具包。若需要卸载，使用 `-Uninstall`；卸载逻辑只删除本技能默认的 `tools` 目录，并且只清理指向该目录的 `PDF_KB_TOOLS_HOME` 和用户 `Path` 项，不删除自定义 `-TargetPath` 或外部已有工具。

验证安装流程时必须做一次空 `tools` 验证：先运行 `scripts/install_windows_dependencies.ps1 -Uninstall` 删除本技能默认 `tools`，再运行安装脚本。这样才能确认依赖检查会联合使用系统/全局 Python site-packages（`site.getsitepackages()`、`site.getusersitepackages()`、`sys.path`）、`AI_TOOLS_HOME` 及其直接子目录和重新创建的技能 `tools`，避免因为旧 `tools` 已经完整而误判验证通过。

## Required Python Packages

- `markitdown`：建库第一阶段批量转换新增或变更 PDF，产生 Markdown 基底。
- `pymupdf`：PDF 渲染、页数判定、原生文字抽取，以及 OCR 前的页面图片输出。
- `pdfplumber`：第二套原生文字抽取工具，用于和 PyMuPDF 交叉检查漏抽内容。
- `winsdk`：调用 Windows OCR Runtime API。可用性以 API 实测为准，不以 `Get-WindowsCapability` 查询结果为准。
- `rapidocr_onnxruntime`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`：Windows OCR Runtime API 无结果时的 RapidOCR 回退方案。
- `opencc-python-reimplemented`：简繁转换到香港繁体中文。
- `pypdf`, `pypdfium2`：辅助 PDF 工具与转换能力。

## Sync Contract

`build` uses `.pdf_kb/manifest.json` as the content cache and sync record. Keep search logic in `scripts/pdf_kb.py`; keep KB data in `.pdf_kb`. Do not copy generated KB content into the skill package.

- Added PDF: create a new stable Markdown file under `.pdf_kb/markdown`.
- Deleted PDF: remove the generated Markdown recorded by the old manifest.
- Changed PDF: compare SHA-256 and regenerate Markdown.
- Unchanged PDF: reuse Markdown and rebuild indexes.
- Existing Markdown reindex: rebuild `manifest.json`, `markdown_chunks.jsonl`, `catalog.md`, and `coverage_report.json` from `.pdf_kb/markdown` without invoking MarkItDown or repair.
- Existing Markdown cross-check: reuse `.pdf_kb/markdown` as the base and run PyMuPDF/pdfplumber/OCR repair without invoking MarkItDown.
- Supplemental `00_*.md` files are user-managed and must not be deleted by sync.

## Bundled Assets

- `rapidocr` 模型与字体不再内置到技能包。安装脚本不再复制 ONNX 模型或字体到 `tools`，请在运行环境中自行提供模型与可用字体；Windows OCR 与字体能力仍通过系统能力验证与可用时安装 Windows capability 的回退路径处理。
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

OCR capability 是兜底安装路径；已安装则跳过。字体会检测系统中的常见 CJK 字体文件；只在未找到时，才尝试安装 Windows CJK 字体 capability。

## Fonts

不要把 Windows 专有字体或开源 CJK 字体二进制复制进技能包。技能包只保留字体候选与 Windows capability 清单；同时验证主机至少具备以下其中一种字体：

- Microsoft JhengHei: `msjh.ttc`
- MingLiU/PMingLiU: `mingliu.ttc`
- Noto Sans CJK / Noto Sans SC
- SimSun/SimHei for Simplified Chinese fallback

