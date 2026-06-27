from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
