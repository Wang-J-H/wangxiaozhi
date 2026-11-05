---
name: document-export
slug: document-export
description: "将 Markdown 内容导出为 Word (.docx)、PowerPoint (.pptx)、PDF (.pdf)、Excel (.xlsx) 等格式。当用户要求生成或导出文档为 Office 格式时使用此技能。"
---

# 文档导出技能

当用户要求将内容输出为 Word 文档、PPT 演示文稿、PDF 文件或 Excel 表格时使用此技能。

## 可用工具

- `convert_document`：将 Markdown 文件转换为 docx/pptx/pdf/xlsx 格式
- `present_artifacts`：展示生成的交付物文件

## 重要约束（必须遵守）

**绝对禁止：** 不要用 `execute`（Python 脚本）或任何编程方式生成 Office 文档。

无论你当前上下文中是否已有全部数据，都要按以下流程操作：

1. 先用 `write_file` 将数据写出为 Markdown 文件到 outputs 目录
2. **唯一允许的方式：** 调用 `convert_document` 转换格式
3. 调用 `present_artifacts` 展示生成的交付物文件
4. 在回复中告知用户生成结果和文件路径

> 原因：`convert_document` 已内置 python-docx、python-pptx、openpyxl、LibreOffice 等全部依赖，比手写 Python 脚本更稳定、更省上下文 token，避免超时问题。

## 操作流程

1. 用 `write_file` 写出 Markdown 内容到 outputs 目录
2. 调用 `convert_document` 转换格式
   - 参数 `file_path`：刚才写出的 Markdown 文件路径
   - 参数 `output_format`：docx / pptx / pdf / xlsx
   - 参数 `title`（可选）：文档标题
3. 调用 `present_artifacts` 展示生成的交付物文件
4. 在回复中告知用户生成结果和文件路径

## 格式说明

| 格式 | 适用场景 | 说明 |
|------|---------|------|
| docx | 正式报告、文档 | 保留标题、列表、表格、引用样式 |
| pptx | 演示文稿 | 适合汇报场景 |
| pdf | 不可编辑的正式文档 | 通用分发格式 |
| xlsx | 数据表格 | 自动提取 Markdown 表格生成真正 .xlsx，支持多表格多 Sheet，带格式化表头 |

## 使用示例

用户："帮我生成一份项目报告，导出为 Word 文档"

1. 用 write_file 写出报告内容的 Markdown 文件
2. convert_document(file_path="/home/gem/user-data/outputs/report.md", output_format="docx", title="项目报告")
3. present_artifacts(filepaths=["/home/gem/user-data/outputs/report.docx"])

用户："把这个表格数据导出为 Excel"

1. 先写出带 Markdown 表格的 .md 文件
2. convert_document(file_path="/home/gem/user-data/outputs/data.md", output_format="xlsx")
3. present_artifacts(filepaths=["/home/gem/user-data/outputs/data.xlsx"])
