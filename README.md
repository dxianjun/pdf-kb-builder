# PDF KB Builder

将指定目录下的 PDF 文件转换成可检索的本地知识库。建库时，流程固定为：先批量用 MarkItDown 为所有新增或变更 PDF 产生 Markdown 基底，再用 PyMuPDF、pdfplumber、Windows OCR Runtime API、RapidOCR 逐页交叉补漏。

## 目录结构

```text
pdf-kb-builder/
  SKILL.md
  README.md
  scripts/
    pdf_kb.py
    install_windows_dependencies.ps1
    requirements.txt
    tests/
  references/
    dependencies.md
  assets/
    fonts/font-manifest.json
    fonts/NotoSansSC-VF.ttf
    rapidocr/models/*.onnx
    windows-ocr/capabilities.json
  tools/                  # 安装脚本创建，放本技能自己的依赖；不提交
```

## 安装依赖

Windows 安装脚本默认会在技能包自己的目录下创建 `tools`，并把缺少的 Python 包、RapidOCR 模型和随包字体安装/复制到这个目录。安装到 `D:\ai_tools\pdf-kb\pdf-kb-builder` 后，默认补缺目录就是 `D:\ai_tools\pdf-kb\pdf-kb-builder\tools`。如需明确安装到其他目录，可以使用 `-TargetPath`；这不是“必须使用技能内 tools”的硬性限制。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1
```

安装脚本会先复制随包 RapidOCR 模型和随包 CJK 字体，`tools` 中已有同名文件则跳过；再用“系统/全局 Python 包（`site.getsitepackages()`、`site.getusersitepackages()`、`sys.path`） + `D:\ai_tools` 及其所有直接子目录 + `AI_TOOLS_HOME` 及其所有直接子目录 + 技能 `tools`”联合检查 Python 包，只把仍然缺少的包安装到目标目录。运行时也会把这些位置一起加入可用依赖来源，所以可以调用系统全局包和 `D:\ai_tools` 里的已有包。脚本默认设置用户环境变量 `PDF_KB_TOOLS_HOME` 并把目标目录追加到用户 `Path`。它不会删除或覆盖 `D:\ai_tools` 根目录下原有的工具包，也不会把 `AI_TOOLS_HOME` 改成别的值。卸载时使用 `-Uninstall`；脚本只删除技能包默认的 `tools` 目录，并且只清理指向该目录的 `PDF_KB_TOOLS_HOME` / `Path`，不会删除自定义 `-TargetPath` 或 `D:\ai_tools` 中的其他工具。

Windows OCR 以 Runtime API 实测为准：能通过 `winsdk` 调用 `zh-Hant-HK`、`zh-Hant-TW`、`zh-Hans-CN` 或用户语言 profile engine 时，即视为可用，不再查询或安装 OCR capability。只有 Runtime API 不可用且当前 PowerShell 有管理员权限时，才尝试安装 Windows OCR capability。

如果不想安装 Windows OCR/字体 capability，只安装/复制本技能包可处理的依赖：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -SkipWindowsCapabilities
```

## 建立知识库

```powershell
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

建库流程：

1. MarkItDown 先批量把所有新增或变更 PDF 转成 Markdown 基底。
2. MarkItDown 批量阶段完成后，PyMuPDF 和 pdfplumber 再逐页抽取文字，检查是否漏页或漏段。
3. 若原生文字抽不到，先跑 Windows OCR Runtime API。
4. Windows OCR Runtime API 没有结果时，才回落 RapidOCR。
5. 漏抽出的内容会补到 `.pdf_kb/markdown/*.md` 的 `PDF 第 N 页补漏` 区段。

再次执行同一条 `build` 命令即可同步更新：

- 新增 PDF：自动产生新的 Markdown，并重建索引。
- 删除 PDF：自动移除之前生成的 Markdown，并从索引中移除。
- 修改 PDF：根据文件 hash 自动重新转换。
- 未修改 PDF：直接复用已有 Markdown，只重建索引。

默认输出到 PDF 目录下的 `.pdf_kb`：

```text
.pdf_kb/
  markdown/
  markdown_chunks.jsonl
  manifest.json
  catalog.md
  coverage_report.json
  qa_overrides.jsonl        # 可选
```

## 搜索知识库

```powershell
python .\scripts\pdf_kb.py search "查询内容" --kb-dir "D:\path\to\pdf-folder\.pdf_kb"
```

如果有 `qa_overrides.jsonl`，默认会优先返回精确问答：

```powershell
python .\scripts\pdf_kb.py search "查询内容" --kb ".pdf_kb\markdown_chunks.jsonl" --qa ".pdf_kb\qa_overrides.jsonl"
```

建议优先使用 `--kb-dir`，让搜索能力和知识库内容解耦；更新知识库时只改 `.pdf_kb` 产物，不需要修改技能包或搜索脚本。

## 回答来源规则

凡是用这个技能产生的回复都必须附来源：

- 命中 `qa_override`：附 `sources[].markdown_file`、`sources[].line` 和简短 `quote`。
- 命中普通 chunk：附 `markdown_file`、`start_line`、`end_line`，可同时附 `pdf_file`。
- 建库、更新、修补或验证时：附 `.pdf_kb/manifest.json`、`.pdf_kb/catalog.md`、`.pdf_kb/coverage_report.json`、`markdown_chunks.jsonl` 或命令输出作为依据。
- 如果没有来源字段，不应直接给确定答案；先重新搜索或打开 Markdown 核对。

## 补充内容

- `qa_overrides.jsonl`：放在 `.pdf_kb/`，用于高优先级标准答案。
- `00_*.md`：放在 `.pdf_kb/markdown/`，会作为补充 Markdown 索引加入 chunks。
- 修改补充内容后，执行：

```powershell
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --resume
```

## 验证

验证安装逻辑时，不要只在已有 `tools` 目录上重复跑。应先用 `-Uninstall` 删除本技能默认的 `tools`，再重新执行安装脚本；这能确认系统/全局 Python 包、`D:\ai_tools`、`AI_TOOLS_HOME` 和重新创建的技能 `tools` 会被联合检查，并且缺少的包才会补装。这个验证只允许删除本技能自己的 `tools`，不能删除 `D:\ai_tools` 根目录或其中已有工具。

```powershell
python -m unittest discover -s .\scripts\tests
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -Uninstall
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -SkipWindowsCapabilities
python .\scripts\pdf_kb.py deps
```

建库后检查：

- `catalog.md` 是否列出全部 PDF。
- `coverage_report.json` 中 `markitdown_status` 是否为 `ok`。
- `coverage_report.json` 中 `supplemented_pages`、`windows_ocr_pages`、`rapidocr_pages` 是否符合预期。
- `pdf_kb.py deps` 中 `windows_ocr_runtime_api` 是否显示 `zh-Hant-HK`、`zh-Hant-TW`、`zh-Hans-CN` 或 `profile_engine` 可用。
- 新增/删除 PDF 后重新执行 `build`，确认 `.pdf_kb/markdown` 和 `markdown_chunks.jsonl` 已同步。
- `no_ocr_text_pages` 是否主要为封面、照片、分隔页或空白页。
- 用已知问题搜索一次，确认能命中正确来源。

## 说明

`SKILL.md` 是给 Codex 使用的技能入口；`README.md` 是给人快速上手的说明文件。若两者有冲突，以 `SKILL.md` 和脚本实际参数为准。
