from __future__ import annotations

import argparse
import hashlib
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
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

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
    "糖ji": "糖癒",
    "糖疾": "糖癒",
    "心疾": "心癒",
    "自主人生": "智主人生",
    "墊底費": "自付費",
    "百份比": "百分比",
    "嵗": "歲",
    "歳": "歲",
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
    if fitz is None:
        raise RuntimeError("PyMuPDF is missing. Install dependencies before building.")

    document = fitz.open(pdf_path)
    engine = RapidOCR() if use_ocr and RapidOCR is not None and np is not None else None
    lines: list[str] = [
        f"# {to_hk(repair_mojibake(pdf_path.stem))}",
        "",
        f"> Source PDF: `{pdf_path.name}`",
        "",
    ]
    native_pages = 0
    ocr_pages: list[int] = []
    no_ocr_pages: list[int] = []

    for page_index in range(document.page_count):
        page_number = page_index + 1
        page = document[page_index]
        native_text = normalize_markdown(page.get_text("text") or "")
        lines.append(f"## PDF 第 {page_number} 頁")
        lines.append("")

        if len(native_text.strip()) >= min_text_chars:
            native_pages += 1
            lines.append(native_text.strip())
            lines.append("")
            continue

        if engine is None:
            no_ocr_pages.append(page_number)
            lines.append("_此頁沒有可抽取文字層，且 OCR 未啟用或依賴缺失。_")
            lines.append("")
            continue

        ocr_lines = ocr_page(engine, page, zoom)
        if ocr_lines:
            ocr_pages.append(page_number)
            lines.extend(ocr_lines)
        else:
            no_ocr_pages.append(page_number)
            lines.append("_此頁 OCR 未識別出文字。_")
        lines.append("")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    return {
        "pages": document.page_count,
        "native_text_pages": native_pages,
        "ocr_pages": ocr_pages,
        "no_ocr_text_pages": no_ocr_pages,
    }


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

    manifest: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for doc_id, pdf_path in enumerate(pdfs, start=1):
        md_path = markdown_dir / safe_name(doc_id, pdf_path)
        if resume and md_path.exists() and md_path.stat().st_size > 0:
            stats = {"pages": None, "native_text_pages": None, "ocr_pages": [], "no_ocr_text_pages": []}
        else:
            stats = pdf_to_markdown(pdf_path, md_path, use_ocr=use_ocr)

        markdown = md_path.read_text(encoding="utf-8", errors="replace")
        doc_chunks = make_chunks(markdown)
        rel_pdf = to_hk(repair_mojibake(str(pdf_path.relative_to(source_dir))))
        rel_md = str(md_path.relative_to(source_dir))

        manifest.append(
            {
                "doc_id": doc_id,
                "pdf_file": rel_pdf,
                "markdown_file": rel_md,
                "chars": len(markdown),
                "lines": len(markdown.splitlines()),
                "chunks": len(doc_chunks),
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            }
        )
        coverage.append({"doc_id": doc_id, "pdf_file": rel_pdf, **stats})

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
                "markdown_file": str(md_path.relative_to(source_dir)),
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


def dependency_status() -> dict[str, bool]:
    return {
        "opencc": OpenCC is not None,
        "pymupdf": fitz is not None,
        "numpy": np is not None,
        "rapidocr": RapidOCR is not None,
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

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--kb", default=".pdf_kb/markdown_chunks.jsonl")
    search_parser.add_argument("--qa", default=".pdf_kb/qa_overrides.jsonl")
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
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "search":
        result = search(args.query, Path(args.kb), Path(args.qa), args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "deps":
        print(json.dumps(dependency_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
