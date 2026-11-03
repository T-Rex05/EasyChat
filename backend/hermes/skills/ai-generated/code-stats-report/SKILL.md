---
name: code-stats-report
category: ai-generated
description: "统计 AgentForge 项目代码量并生成 PDF 报告。触发：定时任务代码统计、项目代码量分析。"
version: 1.0.0

author: qqq
metadata:
  hermes:
    requires_toolsets:
      - file
      - terminal
---
# /code-stats-report — AgentForge 代码量统计报告

## 概述
递归遍历 AgentForge 项目目录，统计各子目录的代码文件数和行数，排除 node_modules、__pycache__、.git、venv、dist、.vite 等非源码目录，生成排版良好的 PDF 报告。

## 前置条件
```bash
pip install reportlab
```

## 执行
```bash
cd E:/PythonCode/AgentForge
python scripts/generate_report.py
```

PDF 报告保存到：`%TEMP%/AgentForge_代码量统计报告_2026-08-11.pdf`
