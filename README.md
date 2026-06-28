# PDF KB Builder

將指定目錄下的 PDF 文件轉換成可檢索的本地知識庫。第一次建庫時，流程固定為：先用 MarkItDown 產生 Markdown 基底，再用 PyMuPDF、pdfplumber、Windows OCR、RapidOCR 逐頁交叉補漏。

## 目錄結構

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

## 安裝依賴

Windows 建議把工具依賴安裝到 `D:\ai_tools`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -UpdateUserEnv
```

如果不想安裝 Windows OCR/字體能力，只安裝 Python 套件：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_dependencies.ps1 -TargetPath D:\ai_tools -SkipWindowsCapabilities
```

## 建立知識庫

```powershell
$env:AI_TOOLS_HOME = "D:\ai_tools"
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --recursive
```

建庫流程：

1. MarkItDown 先把每份 PDF 轉成 Markdown。
2. PyMuPDF 和 pdfplumber 再逐頁抽取文字，檢查 MarkItDown 是否漏頁或漏段。
3. 若原生文字抽不到，先跑 Windows OCR。
4. Windows OCR 沒有結果時，才回落 RapidOCR。
5. 漏抽出的內容會補到 `.pdf_kb/markdown/*.md` 的 `PDF 第 N 頁補漏` 區段。

再次執行同一條 `build` 命令即可同步更新：

- 新增 PDF：自動產生新的 Markdown，並重建索引。
- 刪除 PDF：自動移除之前生成的 Markdown，並從索引中移除。
- 修改 PDF：根據檔案 hash 自動重新轉換。
- 未修改 PDF：直接複用既有 Markdown，只重建索引。

預設輸出到 PDF 目錄下的 `.pdf_kb`：

```text
.pdf_kb/
  markdown/
  markdown_chunks.jsonl
  manifest.json
  catalog.md
  coverage_report.json
  qa_overrides.jsonl        # 可選
```

## 搜索知識庫

```powershell
python .\scripts\pdf_kb.py search "查詢內容" --kb-dir "D:\path\to\pdf-folder\.pdf_kb"
```

如果有 `qa_overrides.jsonl`，預設會優先返回精確問答：

```powershell
python .\scripts\pdf_kb.py search "查詢內容" --kb ".pdf_kb\markdown_chunks.jsonl" --qa ".pdf_kb\qa_overrides.jsonl"
```

建議優先使用 `--kb-dir`，讓搜索能力和知識庫內容解耦；更新知識庫時只改 `.pdf_kb` 產物，不需要修改技能包或搜索腳本。

## 回答來源規則

凡是用這個技能產生的回覆都必須附來源：

- 命中 `qa_override`：附 `sources[].markdown_file`、`sources[].line` 和簡短 `quote`。
- 命中普通 chunk：附 `markdown_file`、`start_line`、`end_line`，可同時附 `pdf_file`。
- 建庫、更新、修補或驗證時：附 `.pdf_kb/manifest.json`、`.pdf_kb/catalog.md`、`.pdf_kb/coverage_report.json`、`markdown_chunks.jsonl` 或命令輸出作為依據。
- 如果沒有來源欄位，不應直接給確定答案；先重新搜索或打開 Markdown 核對。

## 補充內容

- `qa_overrides.jsonl`：放在 `.pdf_kb/`，用於高優先級標準答案。
- `00_*.md`：放在 `.pdf_kb/markdown/`，會作為補充 Markdown 索引加入 chunks。
- 修改補充內容後，執行：

```powershell
python .\scripts\pdf_kb.py build "D:\path\to\pdf-folder" --resume
```

## 驗證

```powershell
python -m unittest discover -s .\scripts\tests
python .\scripts\pdf_kb.py deps
```

建庫後檢查：

- `catalog.md` 是否列出全部 PDF。
- `coverage_report.json` 中 `markitdown_status` 是否為 `ok`。
- `coverage_report.json` 中 `supplemented_pages`、`windows_ocr_pages`、`rapidocr_pages` 是否符合預期。
- 新增/刪除 PDF 後重新執行 `build`，確認 `.pdf_kb/markdown` 和 `markdown_chunks.jsonl` 已同步。
- `no_ocr_text_pages` 是否主要為封面、照片、分隔頁或空白頁。
- 用已知問題搜索一次，確認能命中正確來源。

## 說明

`SKILL.md` 是給 Codex 使用的技能入口；`README.md` 是給人快速上手的說明文件。若兩者有衝突，以 `SKILL.md` 和腳本實際參數為準。
