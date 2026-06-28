# PDF KB Builder

将指定目录下的 PDF 文件转换成可检索的本地知识库。建库时，流程固定为：先批量用 MarkItDown 为所有新增或变更 PDF 产生 Markdown 基底，再用 PyMuPDF、pdfplumber、Windows OCR、RapidOCR 逐页交叉补漏。

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
```

## 安装依赖

Windows 建议把工具依赖安装到 `D:\ai_tools`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -UpdateUserEnv
```

如果不想安装 Windows OCR/字体能力，只安装 Python 套件：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -SkipWindowsCapabilities
```

## 建立知识库

```powershell
$env:AI_TOOLS_HOME = "D:\ai_tools"
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

建库流程：

1. MarkItDown 先批量把所有新增或变更 PDF 转成 Markdown 基底。
2. MarkItDown 批量阶段完成后，PyMuPDF 和 pdfplumber 再逐页抽取文字，检查是否漏页或漏段。
3. 若原生文字抽不到，先跑 Windows OCR。
4. Windows OCR 没有结果时，才回落 RapidOCR。
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

```powershell
python -m unittest discover -s .\scripts\tests
python .\scripts\pdf_kb.py deps
```

建库后检查：

- `catalog.md` 是否列出全部 PDF。
- `coverage_report.json` 中 `markitdown_status` 是否为 `ok`。
- `coverage_report.json` 中 `supplemented_pages`、`windows_ocr_pages`、`rapidocr_pages` 是否符合预期。
- 新增/删除 PDF 后重新执行 `build`，确认 `.pdf_kb/markdown` 和 `markdown_chunks.jsonl` 已同步。
- `no_ocr_text_pages` 是否主要为封面、照片、分隔页或空白页。
- 用已知问题搜索一次，确认能命中正确来源。

## 说明

`SKILL.md` 是给 Codex 使用的技能入口；`README.md` 是给人快速上手的说明文件。若两者有冲突，以 `SKILL.md` 和脚本实际参数为准。
