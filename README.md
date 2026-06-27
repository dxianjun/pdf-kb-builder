# PDF KB Builder

将指定目录下的 PDF 文件转换为可检索的本地知识库，支持 PDF 原生文字抽取、图片页 OCR 补抽、繁体中文处理、QA override 优先答案和补充 Markdown 索引。

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

Windows 推荐把工具依赖安装到 `D:\ai_tools`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -UpdateUserEnv
```

如果不想安装 Windows OCR/字体能力，只安装 Python 包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -SkipWindowsCapabilities
```

## 建立知识库

```powershell
$env:AI_TOOLS_HOME = "D:\ai_tools"
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

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
python .\scripts\pdf_kb.py search "查询内容" --kb "D:\path\to\pdf-folder\.pdf_kb\markdown_chunks.jsonl"
```

如果有 `qa_overrides.jsonl`，默认会优先返回精确问答：

```powershell
python .\scripts\pdf_kb.py search "查询内容" --kb ".pdf_kb\markdown_chunks.jsonl" --qa ".pdf_kb\qa_overrides.jsonl"
```

## 补充内容

- `qa_overrides.jsonl`：放在 `.pdf_kb/`，用于高优先级标准答案。
- `00_*.md`：放在 `.pdf_kb/markdown/`，会作为补充 Markdown 索引加入 chunks。
- 修改补充内容后，运行：

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
- `coverage_report.json` 中 `no_ocr_text_pages` 是否主要为封面、照片、分隔页或空白页。
- 用已知问题搜索一次，确认能命中正确来源。

## 说明

`SKILL.md` 是给 Codex 使用的技能入口；`README.md` 是给人快速上手的说明文件。若两者有冲突，以 `SKILL.md` 和脚本实际参数为准。
