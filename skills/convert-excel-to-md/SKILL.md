---
name: "convert-excel-to-md"
description: "将 Excel (.xlsx) 工作簿转换为 Markdown 格式，以便精准进行内容分析、总结、检索或数据提取。只要用户提供、引用或咨询 .xlsx 文件，无论是否明确提及“转换”或“Markdown”，均须使用此技能。这包括对电子表格、工作簿、预算表、导出数据或追踪表执行“读取”、“总结”、“审查”、“提取数据”、“对比”、“绘图”或“分析”等指令。必须优先运行内置转换脚本生成 Markdown，严禁直接解析 .xlsx 文件或临时编写提取代码。本技能同样适用于整组或整个文件夹的 Excel 批量转换。重要提示：若用户提供的文件夹或文档集中混合了多种文件类型（.pdf、.docx、.xlsx），请务必同时调用三项关联技能（convert-pdf-to-md、convert-word-to-md 及 convert-excel-to-md），确保不遗漏任何文件。"
version: "1.0.0"
license: "MIT"
---
# Convert Excel to Markdown

## When to use this skill

Trigger this skill any time there is a `.xlsx` file that needs to be
understood or processed — for example, a user attaches a spreadsheet and
asks questions about it, wants a summary of the data, wants specific rows or
values pulled out, or wants multiple workbooks in a folder processed
together. Excel's native `.xlsx` format is a zipped XML bundle that is not
reliably readable as plain text, so always convert it to Markdown first
using the script in this skill rather than trying to open or parse the file
directly.

This skill only supports `.xlsx`. If asked to convert a legacy `.xls` file,
tell the user it isn't supported and ask them to re-save it as `.xlsx`
(Excel: File > Save As > Excel Workbook (.xlsx)) first.

**Mixed file types:** When the user references a folder or set of documents
containing multiple supported file types (`.pdf`, `.docx`, `.xlsx`), this
skill handles only `.xlsx` files. The agent MUST also invoke the sibling
skills in parallel:
- `convert-pdf-to-md` for any `.pdf` files
- `convert-word-to-md` for any `.docx` files

Never process a folder and silently skip a supported file type. All three
skills must be invoked together when mixed types are present.

## Setup (once per environment)

Before the first conversion in a given environment, follow
[`references/setup.md`](references/setup.md) step by step to ensure Python,
pip, and the `markitdown` package are installed. Do this proactively rather
than guessing whether the environment is ready — the script itself will
also fail with a clear pointer back to that file if `markitdown` turns out
to be missing, so it's safe to just try the conversion first if you're
reasonably confident setup was already done.

## Usage

The conversion script lives at `scripts/convert_excel_to_md.py`.

**Output structure:** MarkItDown's XLSX converter renders each sheet as its
own `## <SheetName>` Markdown table — it has no support for embedded images
at all. This script separately extracts real embedded images (raster
pictures, not charts) and maps them to the sheet they belong to, writing a
self-contained folder per document:

```
<name>/
    img/
        sheet001_<sheetname>_img001.<ext>
        sheet002_<sheetname>_img001.<ext>
        ...
    <name>.md          (each sheet's images appear right after its table,
                         under a "#### Images in this sheet" heading)
```

This is per-sheet placement, not exact cell position — the finest
granularity MarkItDown's stable output anchors (the `## <SheetName>`
headings) allow. If a workbook has no embedded images, no `img/` folder or
image sections are created. Native Excel **charts** are not extracted as
images (only actual embedded pictures are — charts would need to be
rendered by Excel/LibreOffice, which this lightweight skill does not do).

**Single file:**

```powershell
python scripts\convert_excel_to_md.py "C:\path\to\workbook.xlsx"
```

This creates a `workbook\` folder next to the source file (containing
`workbook.md` and, if present, `workbook\img\`). To control the destination
folder explicitly:

```powershell
python scripts\convert_excel_to_md.py "C:\path\to\workbook.xlsx" -o "C:\path\to\output_folder"
```

**A folder of workbooks (batch mode):**

```powershell
python scripts\convert_excel_to_md.py "C:\path\to\folder"
```

Add `--recursive` to also include subfolders:

```powershell
python scripts\convert_excel_to_md.py "C:\path\to\folder" --recursive
```

Each `.xlsx` found gets its own `<name>\` output folder next to it by
default. Pass `-o "C:\path\to\output_parent"` to collect all the generated
`<name>\` folders under a separate parent directory instead (subfolder
structure is preserved when combined with `--recursive`).

After conversion, read the resulting `.md` file(s) to perform the actual
analysis the user asked for — the script's job is only to produce accurate
Markdown (and images), not to interpret the content.

## Deciding where output goes

**Default — always output next to the source file.** The `<name>/` folder
is created in the same directory as the source `.xlsx`. This is the required
default for every case. Do NOT override it unless the user explicitly asks
for a different location.

**Only use `-o` when** the user explicitly provides an output path (e.g.,
"save the output to `C:\output`", "put the results in `D:\work`"). Do NOT
pass `-o` based on the agent's current working directory, the session state
folder, or any implied location.

**If the source file path cannot be fully resolved** — for example, the
user provides only a filename with no directory, or the path is ambiguous —
use `ask_user` to confirm the full absolute path before running the
conversion. Never guess or assume the directory.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'markitdown'` / exit code 2 | MarkItDown not installed | Follow `references/setup.md` |
| `ERROR: Unsupported file type '.xls'` / exit code 3 | Legacy `.xls`, not `.xlsx` | Ask the user to re-save as `.xlsx` |
| `ERROR: Input path not found` / exit code 3 | Wrong path, or file moved | Confirm the correct path with the user |
| `FAILED <file> -> ...` in batch output | That specific file is corrupt, password-protected, or otherwise unreadable | Report which file(s) failed; other files in the batch still succeed |
| `NOTE: skipped N non-.xlsx file(s)` | Folder contains non-Excel files | Expected — those files are intentionally ignored |
| A sheet's charts don't appear as images | Charts are chart objects, not embedded pictures — this skill only extracts real embedded raster images | Expected; mention this limitation if the user specifically needs chart images |

