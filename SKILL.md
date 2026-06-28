---
name: pdf-kb-builder
description: Use when Codex needs to turn PDFs in a user-specified directory into a searchable local knowledge base, especially for Chinese/traditional-Chinese PDFs, batch MarkItDown-first PDF-to-Markdown conversion, OCR-backed extraction, PDF coverage repair, QA overrides, supplemental indexes, or fast retrieval over PDF training materials.
---

# PDF KB Builder

## Core Rule

Always build from source PDFs before answering. For new or changed PDFs, batch-generate all MarkItDown Markdown bases first, then run the cross-check and repair stage with PyMuPDF, pdfplumber, Windows OCR, and RapidOCR.

Every response produced by this skill must include source citations. Answers must include sources. For product answers, cite KB search metadata. For build/update/validation work, cite generated artifacts or command evidence such as `.pdf_kb/manifest.json`, `.pdf_kb/catalog.md`, `.pdf_kb/coverage_report.json`, `markdown_chunks.jsonl`, or test/dependency command output. Do not provide a source-free final answer when this skill is used.

When answering from a KB search result, include a concise source citation in the answer. For `qa_override` results, cite each relevant `sources[].markdown_file`, `sources[].line`, and short `quote`. For Markdown chunk results, cite `markdown_file`, `start_line`, `end_line`, and `pdf_file` when available. If no source metadata is available, say that the answer is not sufficiently traceable and re-run search or inspect the Markdown before answering.

## Workflow

1. Confirm the source directory that contains PDFs.
2. Ensure dependencies are available. On Windows, run `scripts/install_windows_dependencies.ps1` if tools are missing.
3. Build the KB:

```powershell
$env:AI_TOOLS_HOME = "D:\ai_tools"
python path\to\pdf-kb-builder\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

4. The build pipeline is mandatory:
   - For every new or changed PDF, run MarkItDown first and write the Markdown base.
   - Only after the MarkItDown batch finishes, extract page text with PyMuPDF and pdfplumber.
   - If a page is missing from the MarkItDown result, append the best PyMuPDF/pdfplumber text as a `PDF 第 N 页补漏` section.
   - If neither native extractor finds text, run Windows OCR first, then RapidOCR only if Windows OCR returns no text.
   - Record source coverage in `.pdf_kb/coverage_report.json`.
5. Include optional curated material:
   - Place `qa_overrides.jsonl` under `.pdf_kb/` for high-priority exact answers.
   - Place `00_*.md` under `.pdf_kb/markdown/` for supplemental Markdown indexes.
   - Re-run `build --resume` after adding supplemental files.
6. Re-run `build` whenever PDFs are added, deleted, or changed. The script synchronizes `.pdf_kb/markdown`, removes generated Markdown for deleted PDFs, reuses unchanged PDFs by hash, regenerates changed PDFs, and rebuilds `markdown_chunks.jsonl`.
7. Search by KB directory so retrieval stays decoupled from KB content:

```powershell
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "查询文字" --kb-dir "D:\path\to\pdf-folder\.pdf_kb"
```

## Generated KB Layout

- `.pdf_kb/markdown/*.md`: MarkItDown output plus page-level repaired Markdown.
- `.pdf_kb/markdown_chunks.jsonl`: searchable chunks.
- `.pdf_kb/manifest.json`: source paths, generated Markdown paths, hashes, line counts, chunk counts; used for sync.
- `.pdf_kb/catalog.md`: human-readable catalog.
- `.pdf_kb/coverage_report.json`: MarkItDown status, PyMuPDF/pdfplumber pages, Windows OCR pages, RapidOCR pages, repaired pages, and no-text pages.
- `.pdf_kb/qa_overrides.jsonl`: optional curated answers, searched before chunks.

## Dependencies

Use `scripts/requirements.txt` for Python packages and `scripts/install_windows_dependencies.ps1` for Windows setup. Read `references/dependencies.md` before changing dependency behavior.

The installer covers:

- Dependency checks before installation. Existing Python imports are skipped; only missing packages are installed to the target path.
- PDF tools: MarkItDown, PyMuPDF, pdfplumber, pypdf, pypdfium2, reportlab.
- OCR tools: Windows OCR runtime (`winsdk`), RapidOCR, onnxruntime, opencv-python-headless, Pillow, numpy.
- Chinese conversion: opencc-python-reimplemented.
- Windows OCR language capabilities: zh-HK, zh-TW, zh-CN, installed only when missing.
- Windows CJK font checks. Existing common CJK font files are skipped; if none are found, Windows CJK font capabilities are installed when elevation is available.

## Search Behavior

- Any response produced while using this skill must include a source or verification basis.
- QA overrides are intentionally high priority.
- Supplemental `00_*.md` files are indexed as `doc_id: 0`, `-1`, etc.
- Search code lives in the skill script; KB files contain only generated content and indexes. Updating the KB does not require changing the skill package.
- Every KB-backed answer must include source file and line metadata: `markdown_file` plus `line` for QA overrides, or `markdown_file` plus `start_line`/`end_line` for chunks.
- Chunk search is lexical and deterministic; for ambiguous product names, prefer adding narrow QA overrides with source line citations.

## Validation

Run these before saying the KB is ready:

```powershell
python -m unittest discover -s path\to\pdf-kb-builder\scripts\tests
python path\to\pdf-kb-builder\scripts\pdf_kb.py deps
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "known query" --kb ".pdf_kb\markdown_chunks.jsonl"
```

For Chinese PDFs, inspect `.pdf_kb/coverage_report.json`: pages in `no_ocr_text_pages` should be blank, photos, separators, or otherwise non-text pages.
