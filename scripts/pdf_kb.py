from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


AI_TOOLS_HOME = Path(os.environ.get("AI_TOOLS_HOME", r"D:\ai_tools"))
if AI_TOOLS_HOME.exists():
    sys.path.insert(0, str(AI_TOOLS_HOME))

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - dependency check reports this
    OpenCC = None  # type: ignore

try:
    from markitdown import MarkItDown  # type: ignore
except Exception:  # pragma: no cover
    MarkItDown = None  # type: ignore

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None  # type: ignore

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    from rapidocr import RapidOCR  # type: ignore
except Exception:  # pragma: no cover
    RapidOCR = None  # type: ignore


HK_CONVERTER = OpenCC("s2hk") if OpenCC else None
MIN_QA_SCORE = 180


VARIANT_REPLACEMENTS = {
    "糖ji": "糖愈",
    "糖疾": "糖愈",
    "心疾": "心愈",
    "自主人生": "智主人生",
    "垫底费": "自付费",
    "百份比": "百分比",
    "\u5d57": "岁",
    "\u6b73": "岁",
}


MOJIBAKE_MARKERS = (
    "\u9286",
    "\u9225",
    "\u7ef2",
    "\u9422",
    "\u7035",
    "\u6dc7",
    "\u95c5",
    "\u7477",
    "\u9359",
    "\u5bee",
    "\u9435",
    "\u95ac",
    "\u9429",
)


def to_hk(text: str) -> str:
    if HK_CONVERTER:
        return HK_CONVERTER.convert(text)
    return text


def repair_mojibake(text: str) -> str:
    if not text or not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("cp936", errors="replace").decode("utf-8", errors="replace")
    except Exception:
        return text
    return repaired if mojibake_score(repaired) < mojibake_score(text) else text


def mojibake_score(text: str) -> int:
    return sum(text.count(marker) * 5 for marker in MOJIBAKE_MARKERS) + text.count("�") * 20


def normalize_markdown(text: str) -> str:
    text = to_hk(repair_mojibake(text or ""))
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def safe_name(doc_id: int, pdf_path: Path) -> str:
    stem = to_hk(repair_mojibake(pdf_path.stem))
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return f"{doc_id:02d}_{stem[:90]}.md"


def stable_markdown_name(relative_pdf: str, pdf_path: Path) -> str:
    digest = hashlib.sha1(relative_pdf.replace("\\", "/").encode("utf-8")).hexdigest()[:12]
    stem = to_hk(repair_mojibake(pdf_path.stem))
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip() or "document"
    return f"pdf_{digest}_{stem[:80]}.md"


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def source_key(item: dict[str, Any]) -> str:
    return str(item.get("source_path") or item.get("pdf_file") or "")


def remove_stale_generated_markdown(
    *,
    source_dir: Path,
    markdown_dir: Path,
    previous_manifest: list[dict[str, Any]],
    expected_markdown_by_source: dict[str, Path],
) -> None:
    markdown_root = markdown_dir.resolve()
    for item in previous_manifest:
        if item.get("source_type") == "supplemental_markdown":
            continue
        key = source_key(item)
        markdown_file = item.get("markdown_file")
        if not key or not markdown_file:
            continue
        old_path = (source_dir / markdown_file).resolve()
        expected_path = expected_markdown_by_source.get(key)
        if key in expected_markdown_by_source and expected_path and old_path == expected_path.resolve():
            continue
        try:
            old_path.relative_to(markdown_root)
        except ValueError:
            continue
        if old_path.name.startswith("00_"):
            continue
        if old_path.exists():
            old_path.unlink()


def line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    current = 0
    for line in lines:
        offsets.append(current)
        current += len(line)
    return offsets


def heading_for_line(lines: list[str], line_number: int) -> str:
    for index in range(line_number - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            return stripped
    return ""


def make_chunks(markdown: str, size: int = 1500, overlap: int = 220) -> list[dict[str, Any]]:
    lines = markdown.splitlines(keepends=True)
    offsets = line_offsets(lines)
    spans: list[tuple[int, int, str]] = []
    position = 0

    while position < len(markdown):
        match = re.match(r"\s+", markdown[position:])
        if match:
            position += len(match.group(0))
            continue
        end = position
        while end < len(markdown) and not markdown[end].isspace():
            end += 1
        spans.append((position, end, markdown[position:end]))
        position = end

    def line_for_offset(offset: int) -> int:
        line = 1
        for index, value in enumerate(offsets):
            if value <= offset:
                line = index + 1
            else:
                break
        return line

    chunks: list[dict[str, Any]] = []
    current_words: list[str] = []
    current_start = 0
    current_end = 0
    current_len = 0

    for index, (start, end, word) in enumerate(spans):
        if not current_words:
            current_start = start
        current_words.append(word)
        current_end = end
        current_len += len(word) + 1

        if current_len >= size or index == len(spans) - 1:
            start_line = line_for_offset(current_start)
            end_line = line_for_offset(current_end)
            chunks.append(
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "heading": heading_for_line(lines, start_line),
                    "text": " ".join(current_words).strip(),
                }
            )

            overlap_words: list[str] = []
            overlap_len = 0
            for overlap_word in reversed(current_words):
                overlap_words.insert(0, overlap_word)
                overlap_len += len(overlap_word) + 1
                if overlap_len >= overlap:
                    break
            current_words = overlap_words
            current_len = overlap_len
            if current_words:
                current_start = max(current_start, current_end - overlap_len)

    return chunks


def pdf_to_markdown(
    pdf_path: Path,
    md_path: Path,
    *,
    use_ocr: bool = True,
    zoom: float = 2.0,
    min_text_chars: int = 5,
) -> dict[str, Any]:
    markitdown_error = ""
    try:
        markitdown_text = convert_with_markitdown(pdf_path)
        markitdown_status = "ok"
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - depends on converter internals
        markitdown_text = ""
        markitdown_status = "error"
        markitdown_error = f"{type(exc).__name__}: {exc}"

    extraction_errors: dict[str, str] = {}
    try:
        pymupdf_pages, pymupdf_page_count = extract_pages_with_pymupdf(pdf_path)
    except Exception as exc:  # pragma: no cover - corrupt PDF / library behavior
        pymupdf_pages, pymupdf_page_count = {}, 0
        extraction_errors["pymupdf"] = f"{type(exc).__name__}: {exc}"

    try:
        pdfplumber_pages, pdfplumber_page_count = extract_pages_with_pdfplumber(pdf_path)
    except Exception as exc:  # pragma: no cover - corrupt PDF / library behavior
        pdfplumber_pages, pdfplumber_page_count = {}, 0
        extraction_errors["pdfplumber"] = f"{type(exc).__name__}: {exc}"

    page_count = max(
        [pymupdf_page_count, pdfplumber_page_count, *pymupdf_pages.keys(), *pdfplumber_pages.keys()],
        default=0,
    )
    rapid_engine = None
    lines: list[str] = [
        f"# {to_hk(repair_mojibake(pdf_path.stem))}",
        "",
        f"> Source PDF: `{pdf_path.name}`",
        "",
        "## MarkItDown 转换结果",
        "",
    ]
    if markitdown_text.strip():
        lines.append(markitdown_text.strip())
        lines.append("")
    elif markitdown_error:
        lines.append(f"_MarkItDown 转换失败：{markitdown_error}_")
        lines.append("")

    base_compact = compact_text(markitdown_text)
    pymupdf_text_pages = [
        page_number for page_number, text in pymupdf_pages.items() if useful_text(text, min_text_chars)
    ]
    pdfplumber_text_pages = [
        page_number for page_number, text in pdfplumber_pages.items() if useful_text(text, min_text_chars)
    ]
    windows_ocr_pages: list[int] = []
    rapidocr_pages: list[int] = []
    ocr_pages: list[int] = []
    no_ocr_pages: list[int] = []
    supplemented_pages: list[int] = []
    page_sources: list[dict[str, Any]] = []

    for page_number in range(1, page_count + 1):
        source, page_text = best_native_page_text(
            page_number,
            pymupdf_pages.get(page_number, ""),
            pdfplumber_pages.get(page_number, ""),
            min_text_chars,
        )

        if not page_text and use_ocr:
            windows_lines = windows_ocr_page(pdf_path, page_number, zoom)
            if windows_lines:
                source = "windows_ocr"
                page_text = "\n".join(windows_lines)
                windows_ocr_pages.append(page_number)
                ocr_pages.append(page_number)
            else:
                if rapid_engine is None and RapidOCR is not None and np is not None:
                    rapid_engine = RapidOCR()
                rapid_lines = rapidocr_page(pdf_path, page_number, zoom, rapid_engine)
                if rapid_lines:
                    source = "rapidocr"
                    page_text = "\n".join(rapid_lines)
                    rapidocr_pages.append(page_number)
                    ocr_pages.append(page_number)

        page_compact = compact_text(page_text)
        already_in_markitdown = bool(page_compact and page_compact in base_compact)
        if page_text and not already_in_markitdown:
            lines.append(f"## PDF 第 {page_number} 页补漏（{source}）")
            lines.append("")
            lines.append(normalize_markdown(page_text).strip())
            lines.append("")
            supplemented_pages.append(page_number)

        if not page_text:
            no_ocr_pages.append(page_number)

        page_sources.append(
            {
                "page": page_number,
                "source": source or "none",
                "chars": len(page_text.strip()),
                "already_in_markitdown": already_in_markitdown,
                "added_to_markdown": page_number in supplemented_pages,
            }
        )

    if page_count == 0 and not markitdown_text.strip():
        lines.append("_未能从 MarkItDown、PyMuPDF 或 pdfplumber 抽取内容。_")
        lines.append("")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    return {
        "pages": page_count,
        "markitdown_status": markitdown_status,
        "markitdown_chars": len(markitdown_text.strip()),
        "markitdown_error": markitdown_error,
        "native_text_pages": len(set(pymupdf_text_pages + pdfplumber_text_pages)),
        "pymupdf_text_pages": pymupdf_text_pages,
        "pdfplumber_text_pages": pdfplumber_text_pages,
        "windows_ocr_pages": windows_ocr_pages,
        "rapidocr_pages": rapidocr_pages,
        "ocr_pages": ocr_pages,
        "no_ocr_text_pages": no_ocr_pages,
        "supplemented_pages": supplemented_pages,
        "page_sources": page_sources,
        "extraction_errors": extraction_errors,
    }


def convert_with_markitdown(pdf_path: Path) -> str:
    if MarkItDown is None:
        raise RuntimeError("MarkItDown is missing. Install dependencies before building.")
    result = MarkItDown().convert(pdf_path)
    text = getattr(result, "text_content", None) or getattr(result, "markdown", None) or str(result)
    return normalize_markdown(text) if str(text).strip() else ""


def extract_pages_with_pymupdf(pdf_path: Path) -> tuple[dict[int, str], int]:
    if fitz is None:
        return {}, 0
    document = fitz.open(pdf_path)
    pages: dict[int, str] = {}
    for page_index in range(document.page_count):
        page_number = page_index + 1
        pages[page_number] = normalize_markdown(document[page_index].get_text("text") or "").strip()
    return pages, document.page_count


def extract_pages_with_pdfplumber(pdf_path: Path) -> tuple[dict[int, str], int]:
    if pdfplumber is None:
        return {}, 0
    pages: dict[int, str] = {}
    with pdfplumber.open(pdf_path) as document:
        for page_index, page in enumerate(document.pages, start=1):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            pages[page_index] = normalize_markdown(text).strip()
        return pages, len(document.pages)


def useful_text(text: str, min_text_chars: int) -> bool:
    return len(compact_text(text)) >= min_text_chars


def best_native_page_text(
    page_number: int,
    pymupdf_text: str,
    pdfplumber_text: str,
    min_text_chars: int,
) -> tuple[str, str]:
    candidates = [
        ("pymupdf", normalize_markdown(pymupdf_text).strip()),
        ("pdfplumber", normalize_markdown(pdfplumber_text).strip()),
    ]
    source, text = max(candidates, key=lambda item: len(compact_text(item[1])))
    if useful_text(text, min_text_chars):
        return source, text
    return "", ""


def windows_ocr_page(pdf_path: Path, page_number: int, zoom: float = 2.0) -> list[str]:
    if fitz is None:
        return []
    try:
        import winsdk.windows.globalization as win_globalization  # type: ignore
        import winsdk.windows.graphics.imaging as win_imaging  # type: ignore
        import winsdk.windows.media.ocr as win_ocr  # type: ignore
        import winsdk.windows.storage.streams as win_streams  # type: ignore
    except Exception:
        return []

    try:
        png_bytes = render_page_png(pdf_path, page_number, zoom)
        return asyncio.run(
            windows_ocr_png_bytes(
                png_bytes,
                win_globalization,
                win_imaging,
                win_ocr,
                win_streams,
            )
        )
    except Exception:
        return []


async def windows_ocr_png_bytes(
    png_bytes: bytes,
    win_globalization: Any,
    win_imaging: Any,
    win_ocr: Any,
    win_streams: Any,
) -> list[str]:
    stream = win_streams.InMemoryRandomAccessStream()
    writer = win_streams.DataWriter(stream)
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await win_imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    language_tags = ["zh-Hant-HK", "zh-Hant-TW", "zh-Hans-CN", "en-US"]
    engines: list[Any] = []
    for tag in language_tags:
        language = win_globalization.Language(tag)
        if win_ocr.OcrEngine.is_language_supported(language):
            engine = win_ocr.OcrEngine.try_create_from_language(language)
            if engine is not None:
                engines.append(engine)

    profile_engine = win_ocr.OcrEngine.try_create_from_user_profile_languages()
    if profile_engine is not None:
        engines.append(profile_engine)

    seen: set[str] = set()
    for engine in engines:
        result = await engine.recognize_async(bitmap)
        lines = []
        for line in result.lines:
            text = " ".join(word.text for word in line.words).strip()
            text = normalize_markdown(text).strip()
            if text:
                lines.append(text)
        joined = "\n".join(lines)
        key = compact_text(joined)
        if key and key not in seen:
            seen.add(key)
            return lines
    return []


def render_page_png(pdf_path: Path, page_number: int, zoom: float) -> bytes:
    document = fitz.open(pdf_path)
    page = document[page_number - 1]
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pixmap.tobytes("png")


def rapidocr_page(
    pdf_path: Path,
    page_number: int,
    zoom: float = 2.0,
    engine: Any | None = None,
) -> list[str]:
    if fitz is None or np is None or RapidOCR is None:
        return []
    document = fitz.open(pdf_path)
    page = document[page_number - 1]
    return ocr_page(engine or RapidOCR(), page, zoom)


def ocr_page(engine: Any, page: Any, zoom: float) -> list[str]:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    result = engine(image)
    texts = list(getattr(result, "txts", None) or [])
    boxes_value = getattr(result, "boxes", None)
    boxes = list(boxes_value) if boxes_value is not None else []
    rows: list[tuple[float, float, str]] = []

    for index, text in enumerate(texts):
        cleaned = normalize_markdown(str(text)).strip()
        if not cleaned:
            continue
        box = boxes[index] if index < len(boxes) else None
        if box is not None:
            top = float(min(point[1] for point in box))
            left = float(min(point[0] for point in box))
        else:
            top = float(index)
            left = 0.0
        rows.append((top, left, cleaned))

    rows.sort(key=lambda item: (round(item[0] / 8.0), item[1]))
    return [row[2] for row in rows]


def collect_supplemental_chunks(root: Path, out: Path) -> list[dict[str, Any]]:
    markdown_dir = out / "markdown"
    rows: list[dict[str, Any]] = []
    for supplemental_index, md_path in enumerate(sorted(markdown_dir.glob("00_*.md"))):
        markdown = md_path.read_text(encoding="utf-8", errors="replace")
        rel_md = str(md_path.relative_to(root))
        display_name = to_hk(repair_mojibake(md_path.name))
        for chunk_index, chunk in enumerate(make_chunks(markdown), start=1):
            rows.append(
                {
                    "doc_id": -supplemental_index,
                    "pdf_file": display_name,
                    "markdown_file": rel_md,
                    "chunk": chunk_index,
                    **chunk,
                }
            )
    return rows


def build_kb(
    source_dir: Path,
    *,
    out_dir: Path | None = None,
    recursive: bool = False,
    use_ocr: bool = True,
    resume: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    source_dir = source_dir.resolve()
    out = (out_dir or source_dir / ".pdf_kb").resolve()
    markdown_dir = out / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    pdf_pattern = "**/*.pdf" if recursive else "*.pdf"
    pdfs = sorted(
        [path for path in source_dir.glob(pdf_pattern) if out not in path.parents],
        key=lambda path: str(path.relative_to(source_dir)).lower(),
    )
    previous_manifest = load_json(out / "manifest.json", [])
    previous_coverage = load_json(out / "coverage_report.json", [])
    previous_by_source = {
        source_key(item): item
        for item in previous_manifest
        if item.get("source_type") != "supplemental_markdown" and source_key(item)
    }
    previous_coverage_by_source = {
        source_key(item): item
        for item in previous_coverage
        if isinstance(item, dict) and source_key(item)
    }
    expected_markdown_by_source: dict[str, Path] = {}
    for pdf_path in pdfs:
        rel_pdf_raw = str(pdf_path.relative_to(source_dir))
        expected_markdown_by_source[rel_pdf_raw] = (
            markdown_dir / stable_markdown_name(rel_pdf_raw, pdf_path)
        )
    remove_stale_generated_markdown(
        source_dir=source_dir,
        markdown_dir=markdown_dir,
        previous_manifest=previous_manifest,
        expected_markdown_by_source=expected_markdown_by_source,
    )

    manifest: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for doc_id, pdf_path in enumerate(pdfs, start=1):
        rel_pdf_raw = str(pdf_path.relative_to(source_dir))
        rel_pdf = to_hk(repair_mojibake(rel_pdf_raw))
        md_path = expected_markdown_by_source[rel_pdf_raw]
        pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        previous_item = previous_by_source.get(rel_pdf_raw)
        unchanged = bool(
            previous_item
            and previous_item.get("sha256") == pdf_sha
            and md_path.exists()
            and md_path.stat().st_size > 0
        )
        if unchanged and not force:
            stats = dict(previous_coverage_by_source.get(rel_pdf_raw, {}))
            stats.update({"reused": True})
        else:
            stats = pdf_to_markdown(pdf_path, md_path, use_ocr=use_ocr)
            stats["reused"] = False

        markdown = md_path.read_text(encoding="utf-8", errors="replace")
        doc_chunks = make_chunks(markdown)
        rel_md = relative_to_root(md_path, source_dir)

        manifest.append(
            {
                "doc_id": doc_id,
                "source_path": rel_pdf_raw,
                "pdf_file": rel_pdf,
                "markdown_file": rel_md,
                "chars": len(markdown),
                "lines": len(markdown.splitlines()),
                "chunks": len(doc_chunks),
                "sha256": pdf_sha,
            }
        )
        coverage.append({"doc_id": doc_id, "source_path": rel_pdf_raw, "pdf_file": rel_pdf, **stats})

        for chunk_index, chunk in enumerate(doc_chunks, start=1):
            chunks.append(
                {
                    "doc_id": doc_id,
                    "pdf_file": rel_pdf,
                    "markdown_file": rel_md,
                    "chunk": chunk_index,
                    **chunk,
                }
            )

    supplemental_chunks = collect_supplemental_chunks(source_dir, out)
    chunks.extend(supplemental_chunks)
    supplemental_files = sorted((out / "markdown").glob("00_*.md"))
    for supplemental_index, md_path in enumerate(supplemental_files):
        markdown = md_path.read_text(encoding="utf-8", errors="replace")
        manifest.append(
            {
                "doc_id": -supplemental_index,
                "pdf_file": "",
                "markdown_file": relative_to_root(md_path, source_dir),
                "chars": len(markdown),
                "lines": len(markdown.splitlines()),
                "chunks": sum(1 for row in supplemental_chunks if row["doc_id"] == -supplemental_index),
                "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                "source_type": "supplemental_markdown",
            }
        )

    write_json(out / "manifest.json", manifest)
    write_jsonl(out / "markdown_chunks.jsonl", chunks)
    write_json(out / "coverage_report.json", coverage)
    write_catalog(out / "catalog.md", manifest)

    return {"pdfs": len(pdfs), "chunks": len(chunks), "out": str(out)}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_catalog(path: Path, manifest: list[dict[str, Any]]) -> None:
    lines = ["# PDF Knowledge Base", ""]
    for item in manifest:
        if item.get("source_type") == "supplemental_markdown":
            lines.append(
                f"- [{item['doc_id']}] supplemental -> {item['markdown_file']} | "
                f"lines: {item['lines']} | chunks: {item['chunks']}"
            )
        else:
            lines.append(
                f"- [{item['doc_id']}] {item['pdf_file']} -> {item['markdown_file']} | "
                f"lines: {item['lines']} | chunks: {item['chunks']}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_query(text: str) -> str:
    text = to_hk(repair_mojibake(text or "")).lower()
    for source, target in VARIANT_REPLACEMENTS.items():
        text = text.replace(source.lower(), target.lower())
    return text


def compact_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalize_query(text))


def terms_from_query(query: str) -> list[str]:
    raw_terms = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalize_query(query))
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        if term and term not in seen:
            terms.append(term)
            seen.add(term)

    for term in raw_terms:
        add(term)
        if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) >= 4:
            for size in (2, 3):
                for index in range(0, len(term) - size + 1):
                    add(term[index : index + size])
    return terms


def score_text(text: str, terms: list[str]) -> int:
    lower = normalize_query(text)
    score = 0
    for term in terms:
        count = lower.count(term)
        if count:
            score += count * (8 + len(term))
    if terms and all(term in lower for term in terms):
        score += 50
    return score


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def search(query: str, kb_path: Path, qa_path: Path | None = None, limit: int = 8) -> list[dict[str, Any]]:
    terms = terms_from_query(query)
    results: list[tuple[int, str, dict[str, Any]]] = []
    qa_rows = load_jsonl(qa_path) if qa_path else []
    chunk_rows = load_jsonl(kb_path)
    compact_query = compact_text(query)

    for row in qa_rows:
        aliases = row.get("aliases", [])
        sources = row.get("sources", [])
        haystack = " ".join(
            [
                row.get("id", ""),
                row.get("product", ""),
                row.get("question", ""),
                " ".join(aliases),
                row.get("answer", ""),
                row.get("notes", ""),
                " ".join(source.get("quote", "") for source in sources),
            ]
        )
        score = score_text(haystack, terms)
        exact_alias_match = any(
            compact_query
            and (compact_query == compact_text(alias) or compact_text(alias) in compact_query)
            for alias in aliases
        )
        if score >= MIN_QA_SCORE or exact_alias_match:
            results.append((score + 10000, "qa", row))

    for row in chunk_rows:
        haystack = " ".join(
            [
                row.get("pdf_file", ""),
                row.get("markdown_file", ""),
                row.get("heading", ""),
                row.get("text", ""),
            ]
        )
        score = score_text(haystack, terms)
        if score:
            results.append((score, "chunk", row))

    results.sort(key=lambda item: item[0], reverse=True)
    payload: list[dict[str, Any]] = []
    for score, source_type, row in results[:limit]:
        if source_type == "qa":
            payload.append(
                {
                    "score": score,
                    "source_type": "qa_override",
                    "id": row.get("id", ""),
                    "product": row.get("product", ""),
                    "question": row.get("question", ""),
                    "answer": row.get("answer", ""),
                    "sources": row.get("sources", []),
                    "notes": row.get("notes", ""),
                }
            )
        else:
            payload.append(
                {
                    "score": score,
                    "source_type": "markdown_chunk",
                    "pdf_file": row.get("pdf_file", ""),
                    "markdown_file": row.get("markdown_file", ""),
                    "start_line": row.get("start_line", 0),
                    "end_line": row.get("end_line", 0),
                    "heading": row.get("heading", ""),
                    "text": row.get("text", "")[:900],
                }
            )
    return payload


def resolve_kb_paths(
    kb_dir: Path,
    kb_path: Path | None = None,
    qa_path: Path | None = None,
) -> tuple[Path, Path | None]:
    kb_dir = kb_dir.resolve()
    resolved_kb = kb_path.resolve() if kb_path else kb_dir / "markdown_chunks.jsonl"
    resolved_qa = qa_path.resolve() if qa_path else kb_dir / "qa_overrides.jsonl"
    return resolved_kb, resolved_qa if resolved_qa.exists() else None


def search_kb_dir(query: str, kb_dir: Path, limit: int = 8, qa_path: Path | None = None) -> list[dict[str, Any]]:
    kb_path, resolved_qa = resolve_kb_paths(kb_dir, qa_path=qa_path)
    return search(query, kb_path, resolved_qa, limit)


def dependency_status() -> dict[str, bool]:
    return {
        "markitdown": MarkItDown is not None,
        "opencc": OpenCC is not None,
        "pymupdf": fitz is not None,
        "pdfplumber": pdfplumber is not None,
        "numpy": np is not None,
        "rapidocr": RapidOCR is not None,
        "windows_ocr_runtime": importlib.util.find_spec("winsdk") is not None,
        "ai_tools_home_exists": AI_TOOLS_HOME.exists(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and search OCR-backed PDF knowledge bases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("source_dir")
    build_parser.add_argument("--out")
    build_parser.add_argument("--recursive", action="store_true")
    build_parser.add_argument("--no-ocr", action="store_true")
    build_parser.add_argument("--resume", action="store_true")
    build_parser.add_argument("--force", action="store_true")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--kb-dir", default=".pdf_kb")
    search_parser.add_argument("--kb")
    search_parser.add_argument("--qa")
    search_parser.add_argument("--limit", type=int, default=8)

    subparsers.add_parser("deps")

    args = parser.parse_args()
    if args.command == "build":
        result = build_kb(
            Path(args.source_dir),
            out_dir=Path(args.out) if args.out else None,
            recursive=args.recursive,
            use_ocr=not args.no_ocr,
            resume=args.resume,
            force=args.force,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "search":
        kb_path, qa_path = resolve_kb_paths(
            Path(args.kb_dir),
            Path(args.kb) if args.kb else None,
            Path(args.qa) if args.qa else None,
        )
        result = search(args.query, kb_path, qa_path, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "deps":
        print(json.dumps(dependency_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
