"""文档格式转换工具 - 将 Markdown 转换为 Word/PPT/PDF/Excel"""

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from langchain.tools import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field

from xiaozhi.agents.backends.sandbox.paths import resolve_virtual_path, get_virtual_path_prefix
from xiaozhi.agents.toolkits.registry import tool

SUPPORTED_FORMATS = {
    "docx": "Word 文档 (.docx)",
    "pptx": "PowerPoint 演示文稿 (.pptx)",
    "pdf": "PDF 文档 (.pdf)",
    "xlsx": "Excel 表格 (.xlsx)",
}

CONVERT_DESCRIPTION = """将 Markdown 文件转换为 Office 文档格式（Word/PPT/PDF/Excel）。

支持格式：
- docx：Word 文档
- pptx：PowerPoint 演示文稿
- pdf：PDF 文档
- xlsx：Excel 表格（适用于表格数据）

使用步骤：
1. 先用 write_file 写出 Markdown 内容到 outputs 目录
2. 调用此工具转换格式
3. 再调用 present_artifacts 展示给用户
"""


class ConvertDocumentInput(BaseModel):
    """文档转换输入参数"""

    file_path: str = Field(description="需要转换的 Markdown 文件路径")
    output_format: str = Field(
        description="输出格式：docx（Word）、pptx（PPT）、pdf（PDF）、xlsx（Excel）"
    )
    title: Optional[str] = Field(
        default=None,
        description="文档标题（用于 PPT 幻灯片标题或文档标题页，可选）",
    )


def _md_to_html(markdown_text: str) -> str:
    """将 Markdown 文本转为带样式的 HTML"""
    import re

    lines = markdown_text.split("\n")
    html_parts = []
    in_list = False
    in_code_block = False
    code_content = []
    in_table = False
    table_rows = []

    for line in lines:
        # 代码块
        if line.startswith("```"):
            if in_code_block:
                html_parts.append(
                    f"<pre style='background:#f5f5f5;padding:12px;border-radius:6px;"
                    f"overflow-x:auto;font-size:13px;'><code>{''.join(code_content)}</code></pre>"
                )
                code_content = []
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_content.append(line.replace("<", "&lt;").replace(">", "&gt;") + "\n")
            continue

        # 表格
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(cells)
            continue
        elif in_table and ("|" not in line or not line.strip().startswith("|")):
            if len(table_rows) >= 2:
                header = table_rows[0]
                body = table_rows[2:] if len(table_rows) > 2 else []
                html_parts.append(
                    "<table style='border-collapse:collapse;width:100%;margin:12px 0;'>"
                )
                html_parts.append("<thead><tr>")
                for h in header:
                    html_parts.append(
                        f"<th style='border:1px solid #ddd;padding:8px;"
                        f"background:#f5f7fa;text-align:left;font-weight:600;'>{h}</th>"
                    )
                html_parts.append("</tr></thead><tbody>")
                for row in body:
                    html_parts.append("<tr>")
                    for cell in row:
                        html_parts.append(
                            f"<td style='border:1px solid #ddd;padding:8px;'>{cell}</td>"
                        )
                    html_parts.append("</tr>")
                html_parts.append("</tbody></table>")
            in_table = False
            table_rows = []

        if in_table and table_rows:
            continue

        if not line.strip():
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<br>")
            continue

        if line.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2 style='color:#333;margin:24px 0 12px;'>{line[3:]}</h2>")
        elif line.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<h3 style='color:#444;margin:20px 0 10px;'>{line[4:]}</h3>"
            )
        elif line.startswith("#### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<h4 style='color:#555;margin:16px 0 8px;'>{line[5:]}</h4>"
            )
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_parts.append("<ul style='padding-left:24px;margin:8px 0;'>")
                in_list = True
            html_parts.append(f"<li style='margin:4px 0;'>{line[2:]}</li>")
        elif line.startswith("> "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<blockquote style='border-left:4px solid #667eea;"
                f"padding:8px 16px;margin:12px 0;"
                f"background:#f8f9ff;color:#555;'>{line[2:]}</blockquote>"
            )
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            text = line
            text = re.sub(
                r"\*\*(.+?)\*\*",
                r"<strong>\1</strong>",
                text,
            )
            text = re.sub(
                r"\*(.+?)\*",
                r"<em>\1</em>",
                text,
            )
            text = re.sub(
                r"`(.+?)`",
                r"<code style='background:#f4f4f4;padding:2px 6px;"
                r"border-radius:3px;font-size:0.9em;'>\1</code>",
                text,
            )
            html_parts.append(f"<p style='margin:4px 0;line-height:1.7;'>{text}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "".join(html_parts)


def _generate_xlsx(markdown_text: str, output_path: str) -> str:
    """从 Markdown 表格生成真正的 Excel (.xlsx) 文件，支持多表格多 Sheet"""
    import re
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    lines = markdown_text.strip().split("\n")
    wb = Workbook()
    wb.remove(wb.active)

    # Parse all tables from the Markdown
    tables = []
    current_table = None

    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if current_table is None:
                current_table = {"title": "", "rows": [cells]}
            else:
                if all(
                    c and all(ch == "-" for ch in c.strip("-").strip())
                    for c in cells if c
                ):
                    continue
                current_table["rows"].append(cells)
        else:
            if current_table is not None:
                tables.append(current_table)
                current_table = None

    if current_table is not None:
        tables.append(current_table)

    # Extract section headings as potential sheet names
    headings = []
    for line in lines:
        m = re.match(r"^#{1,4}\s+(.+)", line.strip())
        if m:
            headings.append(m.group(1).strip())

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_align = Alignment(vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    for idx, table in enumerate(tables):
        # Excel sheet name max 31 chars
        if idx == 0:
            sheet_name = "经费总表"
        elif idx - 1 < len(headings):
            candidate = headings[idx - 1][:28]
            sheet_name = candidate
        else:
            sheet_name = f"表{idx + 1}"

        ws = wb.create_sheet(title=sheet_name)
        header_row = table["rows"][0] if table["rows"] else []
        data_rows = table["rows"][1:] if len(table["rows"]) > 1 else []

        for col_idx, header_val in enumerate(header_row, 1):
            cell = ws.cell(row=1, column=col_idx, value=header_val)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        for row_idx, row_data in enumerate(data_rows, 2):
            for col_idx, cell_val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=cell_val)
                cell.alignment = cell_align
                cell.border = thin_border

        # Auto-adjust column widths (cap at 40)
        for col in ws.columns:
            col_letter = col[0].column_letter
            max_len = 0
            for cell in col:
                val = str(cell.value or "")
                cjk_count = sum(1 for c in val if "\u4e00" <= c <= "\u9fff")
                display_len = len(val) + cjk_count
                if display_len > max_len:
                    max_len = display_len
            ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    wb.save(output_path)
    return output_path


def _generate_docx(markdown_text: str, output_path: str, title: str | None = None) -> str:
    """从 Markdown 生成 Word 文档 (python-docx)"""
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # 设置默认字体
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Microsoft YaHei"
    font.size = Pt(11)

    if title:
        heading = doc.add_heading(title, level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    lines = markdown_text.split("\n")
    in_list = False
    in_code_block = False
    code_lines = []
    in_table = False
    table_data = []

    for line in lines:
        # 代码块
        if line.startswith("```"):
            if in_code_block:
                text = "\n".join(code_lines)
                p = doc.add_paragraph()
                run = p.add_run(text)
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
                p.paragraph_format.left_indent = Inches(0.3)
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(line)
            continue

        # 表格
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not in_table:
                in_table = True
                table_data = [cells]
            else:
                if all(c.strip() and all(ch == "-" for ch in c.strip()) for c in cells):
                    continue
                table_data.append(cells)
            continue
        else:
            if in_table and table_data:
                if len(table_data) > 0:
                    ncols = max(len(row) for row in table_data)
                    nrows = len(table_data)
                    table = doc.add_table(rows=nrows, cols=ncols)
                    table.style = "Light Grid Accent 1"
                    for i, row_data in enumerate(table_data):
                        for j, cell_text in enumerate(row_data):
                            if j < ncols:
                                cell = table.cell(i, j)
                                cell.text = cell_text
                                if i == 0:
                                    for paragraph in cell.paragraphs:
                                        for run in paragraph.runs:
                                            run.bold = True
                in_table = False
                table_data = []
                doc.add_paragraph()  # spacing

        if in_table:
            continue

        if not line.strip():
            if in_list:
                doc.add_paragraph()  # spacing
                in_list = False
            continue

        # Headers
        if line.startswith("# "):
            if in_list:
                in_list = False
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            if in_list:
                in_list = False
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            if in_list:
                in_list = False
            doc.add_heading(line[4:], level=3)
        elif line.startswith("#### "):
            if in_list:
                in_list = False
            doc.add_heading(line[5:], level=4)
        elif line.startswith("- ") or line.startswith("* "):
            in_list = True
            p = doc.add_paragraph(line[2:], style="List Bullet")
        elif line.startswith("> "):
            if in_list:
                in_list = False
            p = doc.add_paragraph(line[2:])
            p.paragraph_format.left_indent = Inches(0.3)
            # Make it italic to indicate quote
            for run in p.runs:
                run.italic = True
        else:
            if in_list:
                in_list = False
            p = doc.add_paragraph(line)

    doc.save(output_path)
    return output_path


def _generate_pptx(markdown_text: str, output_path: str, title: str | None = None) -> str:
    """从 Markdown 生成 PPT (python-pptx)"""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slide_layout = prs.slide_layouts[1]  # title + content

    if title:
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title

    lines = markdown_text.split("\n")
    slide = prs.slides.add_slide(slide_layout)
    body = slide.shapes.placeholders[1]
    tf = body.text_frame
    tf.word_wrap = True
    current_heading = ""
    text_frame_content = []

    for line in lines:
        if line.startswith("## "):
            if text_frame_content:
                _populate_text_frame(tf, text_frame_content)
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = line[3:]
            body = slide.shapes.placeholders[1]
            tf = body.text_frame
            tf.word_wrap = True
            text_frame_content = []
        elif line.startswith("### "):
            if text_frame_content:
                _populate_text_frame(tf, text_frame_content)
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = line[4:]
            body = slide.shapes.placeholders[1]
            tf = body.text_frame
            tf.word_wrap = True
            text_frame_content = []
        elif line.startswith("- ") or line.startswith("* "):
            text_frame_content.append(("bullet", line[2:]))
        elif line.strip():
            text_frame_content.append(("text", line.strip()))

    if text_frame_content:
        _populate_text_frame(tf, text_frame_content)

    prs.save(output_path)
    return output_path


def _populate_text_frame(tf, items):
    """填充 PPT 文本框"""
    from pptx.util import Pt

    for i, (style, text) in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = text
        p.space_after = Pt(6)
        if style == "bullet":
            p.level = 0
            pPr = p._pPr
            if pPr is None:
                from pptx.oxml.ns import qn
                pPr = p._p.get_or_add_pPr()
            from pptx.oxml.ns import qn
            buChar = pPr.makeelement(qn("a:buChar"), {"char": "\u2022"})
            # remove existing buNone
            for child in list(pPr):
                if child.tag == qn("a:buNone"):
                    pPr.remove(child)
            pPr.append(buChar)


def _generate_pdf(markdown_text: str, output_path: str, title: str | None = None) -> str:
    """从 Markdown 生成 PDF (借助 libreoffice)"""
    output_dir = Path(output_path).parent
    html_content = _md_to_html(markdown_text)
    full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif;
font-size: 14px; line-height: 1.7; color: #333; padding: 24px; }}
</style>
</head><body>
{html_content}
</body></html>"""

    tmp_html = tempfile.NamedTemporaryFile(mode="w", suffix=".html", encoding="utf-8", delete=False)
    tmp_html.write(full_html)
    tmp_html.close()

    try:
        # 创建临时 profile 目录避免 Docker 中 libreoffice 静默失败
        profile_dir = Path(tempfile.mkdtemp())
        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    f"-env:UserInstallation=file://{profile_dir.as_posix()}",
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(output_dir),
                    tmp_html.name,
                ],
                capture_output=True, text=True, timeout=120,
            )
        finally:
            import shutil
            shutil.rmtree(profile_dir, ignore_errors=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        generated = list(output_dir.glob("*.pdf"))
        if generated:
            return str(max(generated, key=lambda p: p.stat().st_mtime))
        return output_path
    finally:
        Path(tmp_html.name).unlink(missing_ok=True)


@tool(
    category="buildin",
    tags=["文件", "导出"],
    display_name="导出文档",
    description=CONVERT_DESCRIPTION,
    args_schema=ConvertDocumentInput,
)
def convert_document(
    file_path: str,
    output_format: str,
    title: Optional[str] = None,
    runtime: ToolRuntime = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> dict:
    """将 Markdown 文件转换为指定格式的 Office 文档"""

    if output_format not in SUPPORTED_FORMATS:
        return {
            "error": f"不支持的格式: {output_format}，支持: {', '.join(SUPPORTED_FORMATS.keys())}",
        }

    source_path = Path(file_path)
    if not source_path.exists():
        if runtime is not None:
            try:
                config = getattr(runtime, "config", {}) or {}
                configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
                ctx = runtime.context if hasattr(runtime, "context") else None
                thread_id = (
                    configurable.get("file_thread_id")
                    or configurable.get("thread_id")
                    or (getattr(ctx, "file_thread_id", None) if ctx else None)
                    or (getattr(ctx, "thread_id", None) if ctx else None)
                )
                uid = configurable.get("uid") or (getattr(ctx, "uid", None) if ctx else None)
                if thread_id and uid:
                    resolved = resolve_virtual_path(thread_id, file_path, uid=uid)
                    # 验证文件是否存在
                    import os as _os
                    if _os.path.exists(str(resolved)):
                        source_path = resolved
                    else:
                        return {"error": f"路径解析成功但文件不存在: {resolved}"}
                else:
                    return {"error": f"无法获取运行时上下文(thread_id={thread_id}, uid={uid}), 跳过路径解析"}
            except Exception as exc:
                return {"error": f"路径解析异常: {type(exc).__name__}: {exc}"}
        else:
            return {"error": f"runtime 为 None, 无法解析路径: {file_path}"}
        if not source_path.exists():
            return {"error": f"找不到文件: {file_path}"}

    with open(source_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    stem = source_path.stem
    output_dir = source_path.parent
    output_path = str(output_dir / f"{stem}.{output_format}")

    try:
        if output_format == "docx":
            result_path = _generate_docx(md_content, output_path, title)
            output_format_info = "Word 文档 (.docx)"
        elif output_format == "pptx":
            result_path = _generate_pptx(md_content, output_path, title)
            output_format_info = "PowerPoint 演示文稿 (.pptx)"
        elif output_format == "xlsx":
            result_path = _generate_xlsx(md_content, output_path)
            output_format_info = (
                "CSV (Excel 可打开)" if result_path.endswith(".csv") else "Excel"
            )
        elif output_format == "pdf":
            result_path = _generate_pdf(md_content, output_path, title)
            output_format_info = "PDF 文档 (.pdf)"
        else:
            return {"error": f"不支持的格式: {output_format}"}

        file_size = (
            Path(result_path).stat().st_size
            if Path(result_path).exists()
            else 0
        )
        size_str = (
            f"{file_size / 1024:.1f} KB"
            if file_size < 1024 * 1024
            else f"{file_size / 1024 / 1024:.1f} MB"
        )

        result = {                                                                                                                                                           
            "success": True,                                                                                                                                                 
            "output_path": result_path,                                                                                                                                      
            "format": output_format_info,                                                                                                                                    
            "file_size": size_str,                                                                                                                                           
            "message": f"已转换为 {output_format_info} 格式，文件路径: {result_path}",                                                                                       
        }                                                                                                                                                                    
                                                                                                                                                                               
        # 自动注册交付物（等价于调用 present_artifacts），确保前端展示                                                                                                       
        try:                                                                                                                                                                 
            if runtime is not None:                                                                                                                                          
                from xiaozhi.agents.toolkits.buildin.tools import _normalize_presented_artifact_path                                                                         
                normalized = _normalize_presented_artifact_path(result_path, runtime)                                                                                        
                import json as _json                                                                                                                                         
                return Command(                                                                                                                                              
                    update={                                                                                                                                                 
                        "artifacts": [normalized],                                                                                                                           
                        "messages": [                                                                                                                                        
                            ToolMessage(                                                                                                                                     
                                content=_json.dumps(result, ensure_ascii=False),                                                                                             
                                tool_call_id=tool_call_id,                                                                                                                   
                            )                                                                                                                                                
                        ],                                                                                                                                                   
                    }                                                                                                                                                        
                )                                                                                                                                                            
        except Exception as exc:                                                                                                                                             
            result["_auto_register_error"] = f"{type(exc).__name__}: {exc}"                                                                                                  
                                                                                                                                                                               
        return result

    except Exception as e:
        return {"error": f"转换失败: {str(e)}"}
