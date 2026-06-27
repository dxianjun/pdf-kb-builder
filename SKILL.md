---
name: pdf-kb-builder
description: Use when Codex needs to turn PDFs in a user-specified directory into a searchable local knowledge base, especially for Chinese/traditional-Chinese PDFs, OCR-backed extraction, PDF-to-Markdown repair, QA overrides, supplemental indexes, or fast retrieval over PDF training materials.
---

# PDF KB Builder

## Core Rule

Build the knowledge base from source PDFs first, then verify retrieval from generated artifacts. Do not answer from memory when the KB can be built or searched.

## Workflow

1. Confirm the source directory that contains PDFs.
2. Ensure dependencies are available. On Windows, run `scripts/install_windows_dependencies.ps1` if tools are missing.
3. Build the KB:

```powershell
$env:AI_TOOLS_HOME = "D:\ai_tools"
python path\to\pdf-kb-builder\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

4. Include optional curated material:
   - Place `qa_overrides.jsonl` under `.pdf_kb/` for high-priority exact answers.
   - Place `00_*.md` under `.pdf_kb/markdown/` for supplemental Markdown indexes.
   - Re-run `build --resume` after adding supplemental files.
5. Search:

```powershell
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "查詢文字" --kb ".pdf_kb\markdown_chunks.jsonl" --qa ".pdf_kb\qa_overrides.jsonl"
```

## Generated KB Layout

- `.pdf_kb/markdown/*.md`: extracted Markdown per PDF, with OCR text for pages that lack a text layer.
- `.pdf_kb/markdown_chunks.jsonl`: searchable chunks.
- `.pdf_kb/manifest.json`: source files, hashes, line counts, chunk counts.
- `.pdf_kb/catalog.md`: human-readable catalog.
- `.pdf_kb/coverage_report.json`: native text / OCR / no-text page statistics.
- `.pdf_kb/qa_overrides.jsonl`: optional curated answers, searched before chunks.

## Dependencies

Use `scripts/requirements.txt` for Python packages and `scripts/install_windows_dependencies.ps1` for Windows setup. Read `references/dependencies.md` before changing dependency behavior.

The installer covers:

- PDF tools: PyMuPDF, pypdf, pdfplumber, pypdfium2, markitdown, reportlab.
- OCR tools: rapidocr, onnxruntime, opencv-python-headless, Pillow, numpy.
- Chinese conversion: opencc-python-reimplemented.
- Windows OCR language capabilities: zh-HK, zh-TW, zh-CN.
- Windows CJK font capabilities and common font checks.

## Search Behavior

- QA overrides are intentionally high priority.
- Supplemental `00_*.md` files are indexed as `doc_id: 0`, `-1`, etc.
- Chunk search is lexical and deterministic; for ambiguous product names, prefer adding narrow QA overrides with source line citations.

## Validation

Run these before saying the KB is ready:

```powershell
python -m unittest discover -s path\to\pdf-kb-builder\scripts\tests
python path\to\pdf-kb-builder\scripts\pdf_kb.py deps
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "known query" --kb ".pdf_kb\markdown_chunks.jsonl"
```

For Chinese PDFs, also inspect `.pdf_kb/coverage_report.json`: pages in `no_ocr_text_pages` should be blank, photos, separators, or otherwise non-text pages.
