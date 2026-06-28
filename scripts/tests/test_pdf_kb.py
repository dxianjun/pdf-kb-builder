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
            (markdown_dir / "00_补充问答索引.md").write_text(
                "# 补充问答索引\n\n问题：测试问题\n答案：测试答案\n",
                encoding="utf-8",
            )

            chunks = pdf_kb.collect_supplemental_chunks(root, out)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["doc_id"], 0)
        self.assertIn("00_补充问答索引.md", chunks[0]["markdown_file"])
        self.assertIn("测试答案", chunks[0]["text"])

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
                        "text": "普通内容 测试问题",
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
                        "product": "测试产品",
                        "question": "测试问题",
                        "aliases": ["测试问题"],
                        "answer": "QA 优先答案",
                        "sources": [],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            results = pdf_kb.search("测试问题", kb, qa, limit=1)

        self.assertEqual(results[0]["source_type"], "qa_override")
        self.assertEqual(results[0]["answer"], "QA 优先答案")

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

    def test_build_batches_markitdown_before_cross_checking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.pdf"
            second = root / "second.pdf"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            calls: list[str] = []

            def fake_markitdown(path: Path) -> str:
                calls.append(f"markitdown:{path.name}")
                return f"# {path.stem}\n\nbase {path.stem}\n"

            def fake_pymupdf(path: Path) -> tuple[dict[int, str], int]:
                calls.append(f"pymupdf:{path.name}")
                return {1: f"pymupdf {path.stem}"}, 1

            with (
                patch.object(pdf_kb, "convert_with_markitdown", fake_markitdown, create=True),
                patch.object(pdf_kb, "extract_pages_with_pymupdf", fake_pymupdf, create=True),
                patch.object(pdf_kb, "extract_pages_with_pdfplumber", return_value=({}, 0), create=True),
                patch.object(pdf_kb, "windows_ocr_page", return_value=[], create=True),
                patch.object(pdf_kb, "rapidocr_page", return_value=[], create=True),
            ):
                pdf_kb.build_kb(root)

        self.assertEqual(calls[:2], ["markitdown:first.pdf", "markitdown:second.pdf"])
        self.assertGreater(calls.index("pymupdf:first.pdf"), calls.index("markitdown:second.pdf"))
        self.assertGreater(calls.index("pymupdf:second.pdf"), calls.index("markitdown:second.pdf"))

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

            def fake_write_markitdown_base(pdf_path: Path, md_path: Path) -> dict[str, object]:
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(f"# {pdf_path.stem}\n\nsearchable {pdf_path.stem}\n", encoding="utf-8")
                return {"markitdown_status": "test", "markitdown_chars": md_path.stat().st_size}

            def fake_repair_cross_check(pdf_path: Path, md_path: Path, **_: object) -> dict[str, object]:
                return {"pages": 1, "markitdown_status": "test"}

            with (
                patch.object(pdf_kb, "write_markitdown_base_markdown", fake_write_markitdown_base),
                patch.object(pdf_kb, "repair_markdown_with_cross_check", fake_repair_cross_check),
            ):
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

            def fake_write_markitdown_base(pdf_path: Path, md_path: Path) -> dict[str, object]:
                content = pdf_path.read_bytes()
                calls.append(content)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(f"# policy\n\n{content.decode()}\n", encoding="utf-8")
                return {"markitdown_status": "test", "markitdown_chars": md_path.stat().st_size}

            def fake_repair_cross_check(pdf_path: Path, md_path: Path, **_: object) -> dict[str, object]:
                return {"pages": 1, "markitdown_status": "test"}

            with (
                patch.object(pdf_kb, "write_markitdown_base_markdown", fake_write_markitdown_base),
                patch.object(pdf_kb, "repair_markdown_with_cross_check", fake_repair_cross_check),
            ):
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

    def test_skill_requires_source_citations_for_kb_answers(self) -> None:
        skill_path = Path(__file__).resolve().parents[2] / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("Every response produced by this skill must include source citations.", skill_text)
        self.assertIn("Answers must include sources.", skill_text)
        self.assertIn("markdown_file", skill_text)
        self.assertIn("line", skill_text)
        self.assertIn("start_line", skill_text)

    def test_windows_installer_skips_existing_python_packages_and_fonts(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn("Get-MissingPythonRequirements", installer_text)
        self.assertIn("No missing Python dependencies", installer_text)
        self.assertIn("Install-MissingPythonRequirements", installer_text)
        self.assertNotIn("pip install --upgrade --target $TargetPath -r $requirements", installer_text)
        self.assertIn("Test-CjkFontAvailable", installer_text)
        self.assertIn("At least one common CJK font already exists", installer_text)
        self.assertIn("Install-WindowsCapabilityIfMissing", installer_text)

    def test_requirements_do_not_install_unused_reportlab(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1]
        requirements_text = (scripts_dir / "requirements.txt").read_text(encoding="utf-8")
        installer_text = (scripts_dir / "install_windows_dependencies.ps1").read_text(encoding="utf-8")

        self.assertNotIn("reportlab", requirements_text)
        self.assertNotIn('"reportlab"', installer_text)

    def test_windows_installer_passes_target_path_via_environment(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn("PDF_KB_INSTALL_TARGET", installer_text)
        self.assertIn("PDF_KB_INSTALL_PATHS", installer_text)
        self.assertIn("os.environ.get('PDF_KB_INSTALL_PATHS'", installer_text)
        self.assertNotIn('os.environ["PDF_KB_INSTALL_TARGET"]', installer_text)
        self.assertNotIn('sys.path.insert(0, r"$TargetPath")', installer_text)

    def test_windows_installer_validates_rapidocr_engine_symbol(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1]
        installer_text = (scripts_dir / "install_windows_dependencies.ps1").read_text(encoding="utf-8")
        requirements_text = (scripts_dir / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("rapidocr_onnxruntime", requirements_text)
        self.assertIn('"rapidocr_onnxruntime" = @("rapidocr:RapidOCR|rapidocr_onnxruntime:RapidOCR")', installer_text)
        self.assertNotIn("spec_in_target", installer_text)
        self.assertIn("getattr(module, part)", installer_text)

    def test_windows_installer_checks_combined_dependency_sources(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn("PDF_KB_INSTALL_PATHS", installer_text)
        self.assertIn("Get-DependencySearchPaths", installer_text)
        self.assertIn("Get-PythonSystemSearchPaths", installer_text)
        self.assertIn("Add-ToolRootAndChildren", installer_text)
        self.assertIn("site.getsitepackages", installer_text)
        self.assertIn(r"D:\ai_tools", installer_text)
        self.assertIn("Get-ChildItem -LiteralPath $ToolRoot -Directory", installer_text)
        self.assertIn("AI_TOOLS_HOME", installer_text)

    def test_windows_installer_defaults_to_skill_owned_tools_directory(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn('[string]$TargetPath = ""', installer_text)
        self.assertIn('Join-Path $skillRoot "tools"', installer_text)
        self.assertNotIn("Assert-OwnedToolsPath", installer_text)
        self.assertNotIn("TargetPath must be the skill-owned tools directory", installer_text)
        self.assertNotIn('[string]$TargetPath = "D:\\ai_tools"', installer_text)

    def test_windows_installer_uninstall_only_removes_skill_owned_tools(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn("[switch]$Uninstall", installer_text)
        self.assertIn("Uninstall-OwnedTools", installer_text)
        self.assertIn("Remove-UserPathEntry", installer_text)
        self.assertIn('Join-Path $skillRoot "tools"', installer_text)
        self.assertIn("PDF_KB_TOOLS_HOME", installer_text)
        self.assertNotIn("Remove-Item -LiteralPath $TargetPath -Recurse", installer_text)

    def test_windows_installer_updates_pdf_kb_tools_home_and_user_path_only(self) -> None:
        installer_path = Path(__file__).resolve().parents[1] / "install_windows_dependencies.ps1"
        installer_text = installer_path.read_text(encoding="utf-8")

        self.assertIn('SetEnvironmentVariable("PDF_KB_TOOLS_HOME"', installer_text)
        self.assertIn("Add-UserPathEntry", installer_text)
        self.assertIn("Path", installer_text)
        self.assertNotIn('SetEnvironmentVariable("AI_TOOLS_HOME"', installer_text)

    def test_runtime_uses_skill_tools_ai_tools_and_global_packages(self) -> None:
        runtime_path = Path(__file__).resolve().parents[1] / "pdf_kb.py"
        runtime_text = runtime_path.read_text(encoding="utf-8")

        self.assertIn("DEFAULT_TOOLS_HOME", runtime_text)
        self.assertIn("PDF_KB_TOOLS_HOME", runtime_text)
        self.assertIn("pdf_kb_tools_home_exists", runtime_text)
        self.assertIn("DEFAULT_AI_TOOLS_HOME", runtime_text)
        self.assertIn(r'D:\ai_tools', runtime_text)
        self.assertIn("add_tool_root_and_children", runtime_text)
        self.assertIn("iterdir()", runtime_text)
        self.assertIn("system_dependency_paths", runtime_text)
        self.assertIn("site.getsitepackages", runtime_text)
        self.assertIn("SYSTEM_DEPENDENCY_PATHS", runtime_text)
        self.assertIn("ai_tools_home_exists", runtime_text)

    def test_runtime_supports_rapidocr_onnxruntime_fallback(self) -> None:
        runtime_path = Path(__file__).resolve().parents[1] / "pdf_kb.py"
        runtime_text = runtime_path.read_text(encoding="utf-8")

        self.assertIn("from rapidocr_onnxruntime import RapidOCR", runtime_text)

    def test_dependency_docs_allow_explicit_target_and_bound_uninstall(self) -> None:
        skill_root = Path(__file__).resolve().parents[2]
        docs = "\n".join(
            [
                (skill_root / "README.md").read_text(encoding="utf-8"),
                (skill_root / "SKILL.md").read_text(encoding="utf-8"),
                (skill_root / "references" / "dependencies.md").read_text(encoding="utf-8"),
            ]
        )

        self.assertIn("Explicit -TargetPath may be used", docs)
        self.assertIn("system/global Python packages, D:\\ai_tools, all direct child directories", docs)
        self.assertIn("all direct child directories under D:\\ai_tools and AI_TOOLS_HOME", docs)
        self.assertIn("system/global site-packages", docs)
        self.assertIn("-Uninstall", docs)
        self.assertIn("only removes the skill-owned default tools directory", docs)
        self.assertIn("do not overwrite AI_TOOLS_HOME", docs)
        self.assertIn("Fresh install verification must delete the skill-owned tools directory", docs)

    def test_dependency_status_reports_windows_ocr_runtime_api(self) -> None:
        status = pdf_kb.dependency_status()

        self.assertIn("windows_ocr_runtime_api", status)
        runtime = status["windows_ocr_runtime_api"]
        self.assertIsInstance(runtime, dict)
        self.assertIn("zh-Hant-HK", runtime)
        self.assertIn("zh-Hant-TW", runtime)
        self.assertIn("zh-Hans-CN", runtime)
        self.assertIn("profile_engine", runtime)

    def test_skill_bundles_ocr_and_font_assets_for_installer(self) -> None:
        skill_root = Path(__file__).resolve().parents[2]
        installer_text = (skill_root / "scripts" / "install_windows_dependencies.ps1").read_text(encoding="utf-8")

        rapidocr_models = skill_root / "assets" / "rapidocr" / "models"
        self.assertTrue((rapidocr_models / "PP-OCRv6_det_small.onnx").exists())
        self.assertTrue((rapidocr_models / "PP-OCRv6_rec_small.onnx").exists())
        self.assertTrue((rapidocr_models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx").exists())
        self.assertTrue((skill_root / "assets" / "fonts" / "NotoSansSC-VF.ttf").exists())
        self.assertTrue((skill_root / "assets" / "windows-ocr" / "capabilities.json").exists())

        self.assertIn("Install-BundledRapidOcrModels", installer_text)
        self.assertIn("Install-BundledFonts", installer_text)
        self.assertIn("Test-WindowsOcrRuntime", installer_text)
        self.assertIn("Windows OCR runtime is available through Windows OCR API", installer_text)
        self.assertIn("Get-BundledWindowsOcrCapabilities", installer_text)
        self.assertIn("Skipping existing bundled RapidOCR model", installer_text)
        self.assertIn("Skipping existing bundled font", installer_text)


if __name__ == "__main__":
    unittest.main()
