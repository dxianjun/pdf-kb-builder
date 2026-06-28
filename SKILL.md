---
name: pdf-kb-builder
description: Use when Codex needs to turn PDFs in a user-specified directory into a searchable local knowledge base, especially for Chinese/traditional-Chinese PDFs, batch MarkItDown-first PDF-to-Markdown conversion, reindexing existing Markdown, cross-checking existing Markdown against PDFs, OCR-backed extraction, PDF coverage repair, QA overrides, supplemental indexes, or fast retrieval over PDF training materials.
---

# PDF KB Builder

## Core Rule

Default to building from source PDFs before answering. For new or changed PDFs, batch-generate all MarkItDown Markdown bases first, then run the cross-check and repair stage with PyMuPDF, pdfplumber, Windows OCR Runtime API, and RapidOCR.

If the user explicitly provides or asks to reuse an existing `.pdf_kb/markdown` directory, do not rerun MarkItDown unless requested. Use `reindex` to rebuild manifests, chunks, catalog, and coverage metadata from existing Markdown only. Use `cross-check` when existing Markdown should be repaired against the source PDFs without regenerating the MarkItDown base.

Every response produced by this skill must include source citations. Answers must include sources. For product answers, cite KB search metadata. For build/update/validation work, cite generated artifacts or command evidence such as `.pdf_kb/manifest.json`, `.pdf_kb/catalog.md`, `.pdf_kb/coverage_report.json`, `markdown_chunks.jsonl`, or test/dependency command output. Do not provide a source-free final answer when this skill is used.

When answering from a KB search result, include a concise source citation in the answer. For `qa_override` results, cite each relevant `sources[].markdown_file`, `sources[].line`, and short `quote`. For Markdown chunk results, cite `markdown_file`, `start_line`, `end_line`, and `pdf_file` when available. If no source metadata is available, say that the answer is not sufficiently traceable and re-run search or inspect the Markdown before answering.

## Workflow

1. Confirm the source directory that contains PDFs.
2. Ensure dependencies are available. On Windows, run `scripts/install_windows_dependencies.ps1` if tools are missing.
3. Choose the build mode:
   - Normal source build: use `build`.
   - Existing Markdown only: use `reindex` or `build --from-existing-markdown`.
   - Existing Markdown plus PDF coverage repair: use `cross-check`.
4. Build the KB from source PDFs:

```powershell
python path\to\pdf-kb-builder\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

5. The source-build pipeline is mandatory:
   - For every new or changed PDF, run MarkItDown first and write the Markdown base.
   - Only after the MarkItDown batch finishes, extract page text with PyMuPDF and pdfplumber.
   - If a page is missing from the MarkItDown result, append the best PyMuPDF/pdfplumber text as a `PDF 第 N 页补漏` section.
   - If neither native extractor finds text, run Windows OCR Runtime API first, then RapidOCR only if Windows OCR Runtime API returns no text.
   - Record source coverage in `.pdf_kb/coverage_report.json`.
6. For existing Markdown workflows:
   - Use `reindex` when Markdown is already trusted and only indexes need rebuilding.
   - Use `cross-check` when Markdown already exists but pages still need PyMuPDF/pdfplumber/OCR coverage repair.
   - Both modes require one existing Markdown file per source PDF under `.pdf_kb/markdown`; missing files should stop the run.
7. Include optional curated material:
   - Place `qa_overrides.jsonl` under `.pdf_kb/` for high-priority exact answers.
   - Place `00_*.md` under `.pdf_kb/markdown/` for supplemental Markdown indexes.
   - Re-run `build --resume` after adding supplemental files.
8. Re-run `build` whenever PDFs are added, deleted, or changed. The script synchronizes `.pdf_kb/markdown`, removes generated Markdown for deleted PDFs, reuses unchanged PDFs by hash, regenerates changed PDFs, and rebuilds `markdown_chunks.jsonl`.
9. Search by KB directory so retrieval stays decoupled from KB content:

```powershell
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "查询文字" --kb-dir "D:\path\to\pdf-folder\.pdf_kb"
```

Existing Markdown commands:

```powershell
python path\to\pdf-kb-builder\scripts\pdf_kb.py reindex "D:\path\to\pdf-folder" --recursive
python path\to\pdf-kb-builder\scripts\pdf_kb.py cross-check "D:\path\to\pdf-folder" --recursive
```

## Generated KB Layout

- `.pdf_kb/markdown/*.md`: MarkItDown output plus page-level repaired Markdown.
- `.pdf_kb/markdown_chunks.jsonl`: searchable chunks.
- `.pdf_kb/manifest.json`: source paths, generated Markdown paths, hashes, line counts, chunk counts; used for sync.
- `.pdf_kb/catalog.md`: human-readable catalog.
- `.pdf_kb/coverage_report.json`: MarkItDown status, PyMuPDF/pdfplumber pages, Windows OCR Runtime API pages, RapidOCR pages, repaired pages, and no-text pages.
- `.pdf_kb/qa_overrides.jsonl`: optional curated answers, searched before chunks.

In existing Markdown modes, manifest entries use `source_type: existing_markdown` or `source_type: existing_markdown_cross_checked`. Coverage entries use `markitdown_status: existing_markdown`; `cross-check` also records `coverage_status: rechecked`.

## Dependencies

Use `scripts/requirements.txt` for Python packages and `scripts/install_windows_dependencies.ps1` for Windows setup. Read `references/dependencies.md` before changing dependency behavior.

The installer covers:

- Dependency checks before installation inspect all direct child directories under `AI_TOOLS_HOME` (if set) and `AI_TOOLS_HOME` itself, plus system/global Python site packages (`site.getsitepackages()`, `site.getusersitepackages()`, `sys.path`) and the skill tools directory together before installing. If any dependency is already importable from those sources, skip reinstalling it. The default install target is the skill-owned `tools` directory next to `SKILL.md`, used only to fill missing dependencies. Explicit -TargetPath may be used when the user intentionally wants another dependency directory; the skill is not required to use only the internal `tools` directory.
- PDF tools: MarkItDown, PyMuPDF, pdfplumber, pypdf, pypdfium2.
- OCR tools: Windows OCR Runtime API via `winsdk`, RapidOCR, onnxruntime, opencv-python-headless, Pillow, numpy.
- Chinese conversion: opencc-python-reimplemented.
- Runtime dependency resolution: make system/global Python site packages (`site.getsitepackages()`, `site.getusersitepackages()`, `sys.path`), all direct child directories under `AI_TOOLS_HOME` (if set), `AI_TOOLS_HOME` itself, and `PDF_KB_TOOLS_HOME` all available for imports. Prefer the skill target for newly installed missing packages, but allow existing global/shared packages to satisfy dependencies.
- Environment isolation: the installer sets `PDF_KB_TOOLS_HOME` and appends the target dependency directory to user `Path`; do not overwrite AI_TOOLS_HOME and do not delete tools from a user-specified `AI_TOOLS_HOME` root.
- Uninstall boundary: `-Uninstall` only removes the skill-owned default tools directory next to `SKILL.md`, and only removes user environment entries that point to that exact directory. It must not delete a custom `-TargetPath`, or any previously existing external tools.
- Windows OCR availability is validated through the OCR Runtime API (`zh-Hant-HK`, `zh-Hant-TW`, `zh-Hans-CN`, and user profile engine). Use Windows capability installation only as an elevated fallback when the runtime probe fails.
- Windows CJK font checks. Existing common system CJK font files are detected; if none are found, Windows CJK font capabilities are installed when elevation is available.

## Search Behavior

- Any response produced while using this skill must include a source or verification basis.
- QA overrides are intentionally high priority.
- Supplemental `00_*.md` files are indexed as `doc_id: 0`, `-1`, etc.
- Search code lives in the skill script; KB files contain only generated content and indexes. Updating the KB does not require changing the skill package.
- Every KB-backed answer must include source file and line metadata: `markdown_file` plus `line` for QA overrides, or `markdown_file` plus `start_line`/`end_line` for chunks.
- Chunk search is lexical and deterministic; for ambiguous product names, prefer adding narrow QA overrides with source line citations.

## Validation

Fresh install verification must delete the skill-owned tools directory before rerunning the Windows installer. Use `scripts/install_windows_dependencies.ps1 -Uninstall` or a guarded deletion that verifies the resolved path is exactly the `tools` directory next to `SKILL.md`; do not delete user-specified external dependency directories for this verification. After deleting `tools`, rerun the installer and confirm dependency checks consider system/global Python site packages (`site.getsitepackages()`, `site.getusersitepackages()`, `sys.path`), `AI_TOOLS_HOME` (if set) and its direct child directories, and the recreated skill tools directory together.

Run these before saying the KB is ready:

```powershell
python -m unittest discover -s path\to\pdf-kb-builder\scripts\tests
powershell -ExecutionPolicy Bypass -File path\to\pdf-kb-builder\scripts\install_windows_dependencies.ps1 -Uninstall
powershell -ExecutionPolicy Bypass -File path\to\pdf-kb-builder\scripts\install_windows_dependencies.ps1 -SkipWindowsCapabilities
python path\to\pdf-kb-builder\scripts\pdf_kb.py deps
python path\to\pdf-kb-builder\scripts\pdf_kb.py search "known query" --kb ".pdf_kb\markdown_chunks.jsonl"
```

For Chinese PDFs, inspect `.pdf_kb/coverage_report.json`: pages in `no_ocr_text_pages` should be blank, photos, separators, or otherwise non-text pages.
