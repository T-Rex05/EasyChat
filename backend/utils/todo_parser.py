"""
任务解析工具 - 从工具输出中提取任务清单
参考故障诊断项目的 parse_todos_from_tool_output 实现
"""
import json
import ast
import re
from typing import Any, Dict, List, Optional


def _normalize_status(value: Any) -> str:
    if not value:
        return "pending"
    text = str(value).strip().lower()
    mapping = {
        "pending": "pending",
        "todo": "pending",
        "not_started": "pending",
        "not-started": "pending",
        "wait": "pending",
        "in-progress": "in_progress",
        "in_progress": "in_progress",
        "doing": "in_progress",
        "working": "in_progress",
        "running": "in_progress",
        "active": "in_progress",
        "completed": "completed",
        "complete": "completed",
        "done": "completed",
        "finished": "completed"
    }
    return mapping.get(text, "completed" if "complete" in text or "done" in text else ("in_progress" if "progress" in text else "pending"))


def _extract_bracket_content(text: str, marker: str) -> Optional[str]:
    """
    从包含 marker 的字符串中提取第一个完整的方括号内容。
    """
    idx = text.find(marker)
    if idx == -1:
        return None
    start = text.find("[", idx)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        char = text[i]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _normalize_todo_items(raw_todos: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for idx, item in enumerate(raw_todos):
        if isinstance(item, dict):
            # 处理LangChain内置write_todos工具的格式（只有content和status字段）
            normalized.append({
                "id": str(item.get("id") or f"todo_{idx}"),
                "title": item.get("content") or item.get("title") or item.get("task") or item.get("description") or f"任务 {idx + 1}",
                "description": item.get("description") or item.get("detail") or item.get("notes") or "",
                "status": _normalize_status(item.get("status")),
            })
        else:
            normalized.append({
                "id": f"todo_{idx}",
                "title": str(item),
                "description": "",
                "status": "pending"
            })
    return normalized


def _extract_todo_list_from_output(output: Any):
    if output is None:
        return None

    # 处理LangChain内置write_todos工具返回的Command对象
    if hasattr(output, 'update') and isinstance(output.update, dict):
        if 'todos' in output.update and isinstance(output.update['todos'], list):
            return output.update['todos']
    
    if isinstance(output, dict):
        if "todos" in output and isinstance(output["todos"], list):
            return output["todos"]
        if "content" in output:
            nested = _extract_todo_list_from_output(output["content"])
            if nested:
                return nested
        return None

    if isinstance(output, list):
        return output

    if isinstance(output, str):
        text = output.strip()
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
                nested = _extract_todo_list_from_output(parsed)
                if nested:
                    return nested
            except Exception:
                pass
        bracket_snippet = None
        # 尝试匹配 todos 字段
        match = re.search(r'["\']?todos["\']?\s*:\s*(\[[\s\S]*\])', text)
        if match:
            bracket_snippet = match.group(1)
        else:
            # 尝试匹配 "任务详情：" 后面的JSON数组（支持中英文冒号）
            match = re.search(r'任务详情\s*[:：]\s*(\[[\s\S]*\])', text)
            if match:
                bracket_snippet = match.group(1)
            else:
                # 尝试匹配任何JSON数组
                match = re.search(r'(\[[\s\S]*\])', text)
                if match:
                    bracket_snippet = match.group(1)
                else:
                    # 使用标记提取
                    for marker in ("'todos'", '"todos"', "任务详情"):
                        bracket_snippet = _extract_bracket_content(text, marker)
                        if bracket_snippet:
                            break
        if bracket_snippet:
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(bracket_snippet)
                    nested = _extract_todo_list_from_output(parsed)
                    if nested:
                        return nested
                except Exception:
                    pass
    return None


def parse_todos_from_tool_output(output: Any):
    """
    从工具输出中解析任务清单
    支持多种格式：JSON字符串、字典、列表、LangChain Command对象等
    """
    raw_todos = _extract_todo_list_from_output(output)
    if not raw_todos:
        return None
    return _normalize_todo_items(raw_todos)
