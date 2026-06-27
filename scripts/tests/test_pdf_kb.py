from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdf_kb


class PdfKbBuilderTests(unittest.TestCase):
    def test_make_chunks_keeps_line_numbers(self) -> None:
        markdown = "# Title\n\nAlpha beta gamma.\n\nSecond section has searchable text.\n"

        chunks = pdf_kb.make_chunks(markdown, size=30, overlap=0)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["start_line"], 1)
        self.assertIn("Alpha", " ".join(chunk["text"] for chunk in chunks))

    def test_supplemental_markdown_is_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out = root / ".pdf_kb"
            markdown_dir = out / "markdown"
            markdown_dir.mkdir(parents=True)
            (markdown_dir / "00_補充問答索引.md").write_text(
                "# 補充問答索引\n\n問題：測試問題\n答案：測試答案\n",
                encoding="utf-8",
            )

            chunks = pdf_kb.collect_supplemental_chunks(root, out)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["doc_id"], 0)
        self.assertIn("00_補充問答索引.md", chunks[0]["markdown_file"])
        self.assertIn("測試答案", chunks[0]["text"])

    def test_search_prefers_qa_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            kb = root / "chunks.jsonl"
            qa = root / "qa.jsonl"
            kb.write_text(
                json.dumps(
                    {
                        "doc_id": 1,
                        "pdf_file": "sample.pdf",
                        "markdown_file": "sample.md",
                        "chunk": 1,
                        "start_line": 1,
                        "end_line": 2,
                        "heading": "",
                        "text": "普通內容 測試問題",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            qa.write_text(
                json.dumps(
                    {
                        "id": "answer",
                        "product": "測試產品",
                        "question": "測試問題",
                        "aliases": ["測試問題"],
                        "answer": "QA 優先答案",
                        "sources": [],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            results = pdf_kb.search("測試問題", kb, qa, limit=1)

        self.assertEqual(results[0]["source_type"], "qa_override")
        self.assertEqual(results[0]["answer"], "QA 優先答案")

    def test_pdf_to_markdown_runs_markitdown_before_cross_checking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "sample.pdf"
            md = root / "sample.md"
            pdf.write_bytes(b"%PDF-1.4\n")
            calls: list[str] = []

            def fake_markitdown(path: Path) -> str:
                calls.append("markitdown")
                return "# Base\n\nbase-only text\n"

            def fake_pymupdf(path: Path) -> tuple[dict[int, str], int]:
                calls.append("pymupdf")
                return {1: "pymupdf supplemental text"}, 1

            def fake_pdfplumber(path: Path) -> tuple[dict[int, str], int]:
                calls.append("pdfplumber")
                return {1: ""}, 1

            with (
                patch.object(pdf_kb, "convert_with_markitdown", fake_markitdown, create=True),
                patch.object(pdf_kb, "extract_pages_with_pymupdf", fake_pymupdf, create=True),
                patch.object(pdf_kb, "extract_pages_with_pdfplumber", fake_pdfplumber, create=True),
                patch.object(pdf_kb, "windows_ocr_page", return_value=[], create=True),
                patch.object(pdf_kb, "rapidocr_page", return_value=[], create=True),
            ):
                stats = pdf_kb.pdf_to_markdown(pdf, md)
                markdown = md.read_text(encoding="utf-8")

        self.assertLess(calls.index("markitdown"), calls.index("pymupdf"))
        self.assertLess(calls.index("markitdown"), calls.index("pdfplumber"))
        self.assertIn("base-only text", markdown)
        self.assertIn("pymupdf supplemental text", markdown)
        self.assertEqual(stats["markitdown_status"], "ok")
        self.assertEqual(stats["supplemented_pages"], [1])

    def test_windows_ocr_is_used_before_rapidocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "scan.pdf"
            md = root / "scan.md"
            pdf.write_bytes(b"%PDF-1.4\n")

            with (
                patch.object(pdf_kb, "convert_with_markitdown", return_value="# Base\n\n", create=True),
                patch.object(pdf_kb, "extract_pages_with_pymupdf", return_value=({1: ""}, 1), create=True),
                patch.object(pdf_kb, "extract_pages_with_pdfplumber", return_value=({1: ""}, 1), create=True),
                patch.object(pdf_kb, "windows_ocr_page", return_value=["windows ocr text"], create=True) as windows_ocr,
                patch.object(pdf_kb, "rapidocr_page", return_value=["rapid ocr text"], create=True) as rapid_ocr,
            ):
                stats = pdf_kb.pdf_to_markdown(pdf, md)
                markdown = md.read_text(encoding="utf-8")

        windows_ocr.assert_called_once()
        rapid_ocr.assert_not_called()
        self.assertIn("windows ocr text", markdown)
        self.assertEqual(stats["windows_ocr_pages"], [1])
        self.assertEqual(stats["rapidocr_pages"], [])

    def test_rapidocr_fills_page_when_windows_ocr_has_no_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "scan.pdf"
            md = root / "scan.md"
            pdf.write_bytes(b"%PDF-1.4\n")

            with (
                patch.object(pdf_kb, "convert_with_markitdown", return_value="# Base\n\n", create=True),
                patch.object(pdf_kb, "extract_pages_with_pymupdf", return_value=({1: ""}, 1), create=True),
                patch.object(pdf_kb, "extract_pages_with_pdfplumber", return_value=({1: ""}, 1), create=True),
                patch.object(pdf_kb, "windows_ocr_page", return_value=[], create=True),
                patch.object(pdf_kb, "rapidocr_page", return_value=["rapid ocr text"], create=True),
            ):
                stats = pdf_kb.pdf_to_markdown(pdf, md)
                markdown = md.read_text(encoding="utf-8")

        self.assertIn("rapid ocr text", markdown)
        self.assertEqual(stats["windows_ocr_pages"], [])
        self.assertEqual(stats["rapidocr_pages"], [1])

    def test_build_sync_removes_markdown_for_deleted_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.pdf"
            second = root / "second.pdf"
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            def fake_pdf_to_markdown(pdf_path: Path, md_path: Path, **_: object) -> dict[str, object]:
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(f"# {pdf_path.stem}\n\nsearchable {pdf_path.stem}\n", encoding="utf-8")
                return {"pages": 1, "markitdown_status": "test"}

            with patch.object(pdf_kb, "pdf_to_markdown", fake_pdf_to_markdown):
                pdf_kb.build_kb(root)
                second.unlink()
                pdf_kb.build_kb(root)

            markdown_files = sorted(path.name for path in (root / ".pdf_kb" / "markdown").glob("*.md"))
            self.assertEqual(len(markdown_files), 1)
            self.assertNotIn("second", "\n".join(markdown_files))
            chunks = (root / ".pdf_kb" / "markdown_chunks.jsonl").read_text(encoding="utf-8")
            self.assertIn("searchable first", chunks)
            self.assertNotIn("searchable second", chunks)

    def test_build_reuses_unchanged_pdf_and_regenerates_changed_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "policy.pdf"
            pdf.write_bytes(b"v1")
            calls: list[bytes] = []

            def fake_pdf_to_markdown(pdf_path: Path, md_path: Path, **_: object) -> dict[str, object]:
                content = pdf_path.read_bytes()
                calls.append(content)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(f"# policy\n\n{content.decode()}\n", encoding="utf-8")
                return {"pages": 1, "markitdown_status": "test"}

            with patch.object(pdf_kb, "pdf_to_markdown", fake_pdf_to_markdown):
                pdf_kb.build_kb(root)
                pdf_kb.build_kb(root)
                pdf.write_bytes(b"v2")
                pdf_kb.build_kb(root)

        self.assertEqual(calls, [b"v1", b"v2"])

    def test_search_resolves_paths_from_kb_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            kb_dir = Path(temp_dir) / ".pdf_kb"
            kb_dir.mkdir()
            (kb_dir / "markdown_chunks.jsonl").write_text(
                json.dumps(
                    {
                        "doc_id": 1,
                        "pdf_file": "policy.pdf",
                        "markdown_file": ".pdf_kb/markdown/policy.md",
                        "chunk": 1,
                        "start_line": 1,
                        "end_line": 2,
                        "heading": "",
                        "text": "alpha searchable policy content",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            results = pdf_kb.search_kb_dir("alpha policy", kb_dir, limit=1)

        self.assertEqual(results[0]["source_type"], "markdown_chunk")
        self.assertIn("alpha searchable", results[0]["text"])


if __name__ == "__main__":
    unittest.main()
