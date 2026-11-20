<!-- Reference: anthropics/skills @ 2c5958ecac7c, skills/docx (Apache-2.0).
     https://github.com/anthropics/skills/blob/2c5958ecac7c/skills/docx/LICENSE.txt
     EasyChat 适配：用 python-docx 处理普通 Word 文件。 -->

---
name: docx
description: 读取或制作 Word 文档、会议纪要、报告和清单。
license: Apache-2.0
---

# Word 文档

当用户明确要求读取或生成 Word 文档时使用。读取时先检查附件是否可访问，用 `python-docx` 提取有内容的段落和表格。将来源明确的文本和提取工具无法读取的内容分别说明。

生成时明确标题、受众和用途。使用标题级别区分正文，使用表格呈现重复结构。对负责人和日期保留原始信息，缺失项标记为「待确认」。编辑已有文件时将结果另存为新文件。

输出前用 `docx.Document` 重新打开文件，核对标题、关键段落和表格内容。布局是否正确以实际渲染结果为准。该流程涵盖常规段落和表格。复杂 Word 修订、宏和旧版 `.doc` 格式需要专用工具。

工具或依赖不可用时，可以输出可复制的 Markdown 草稿，并明确告知文件生成状态。只有实际得到文件或下载链接时才报告已交付附件。
