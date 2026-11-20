"""内置示例技能模板目录（P3）。

来源固定：anthropics/skills @ 2c5958ecac7c（Apache-2.0，许可头随内容保留）。
资源为 EasyChat 适配改写版（自包含 Markdown，声明支持/不支持范围）；
模板本体只读，导入经 SkillService.import_template 走真实版本流程——
默认不激活（避免无选择地批量启用）。
"""
from __future__ import annotations

import functools
from pathlib import Path

from backend.shared.errors import InvalidInputError, NotFoundError

_ORIGIN = "anthropics/skills"
_COMMIT = "2c5958ecac7c"
_SOURCE_PUBLISHED_AT = "2026-11-06T22:32:28Z"
_ROOT = Path(__file__).resolve().parent / "templates"

_CATALOG: tuple[dict, ...] = (
    {
        "key": "pdf",
        "name": "pdf",
        "title": "PDF 处理",
        "purpose": "读取/抽取文本与表格、合并拆分、旋转水印、表单填写、生成新 PDF（含中文）",
        "license": "Apache-2.0",
        "dependencies": ["pypdf==6.15.0", "fpdf2"],
        "resources": "文件处理依赖可访问正文的工具；普通聊天上传目前只提供附件元数据。中文 PDF 需要中文字体",
        "file": "pdf-processing.md",
    },
    {
        "key": "xlsx",
        "name": "xlsx",
        "title": "表格处理",
        "purpose": "读取/创建 .xlsx：公式、格式、数据校验；输出可用 openpyxl 复核",
        "license": "Apache-2.0",
        "dependencies": ["openpyxl"],
        "resources": "自包含；无外部字体/模板资源",
        "file": "xlsx-processing.md",
    },
    {
        "key": "docx",
        "name": "docx",
        "title": "Word 文档",
        "purpose": "读取普通 Word 文件、生成带标题和表格的会议纪要或工作报告",
        "license": "Apache-2.0",
        "dependencies": ["python-docx"],
        "resources": "处理附件依赖当前会话可访问文件内容的文档工具；也可输出 Markdown 草稿",
        "file": "docx-processing.md",
    },
    {
        "key": "daily-brief",
        "name": "daily-brief",
        "title": "日常整理与会议纪要",
        "purpose": "把聊天、个人计划、会议记录或工作进展整理成摘要和行动清单",
        "license": "Apache-2.0",
        "dependencies": [],
        "resources": "使用用户提供的文字，可直接在 Web 和微信回复",
        "source_name": "internal-comms",
        "file": "daily-brief.md",
    },
    {
        "key": "skill-creator",
        "name": "skill-creator",
        "title": "技能编写",
        "purpose": "从零起草与迭代技能：意图捕捉、SKILL.md 编写、测试提示设计、评审循环",
        "license": "Apache-2.0",
        "dependencies": [],
        "resources": "官方附带脚本/eval-viewer 不在 EasyChat 内容模型内，改写版已声明替代步骤",
        "file": "skill-creator.md",
    },
)

TEMPLATE_KEYS = frozenset(item["key"] for item in _CATALOG)


def templates_catalog() -> list[dict]:
    """模板清单（含用途/来源/固定 commit/许可/依赖/资源状态），不含正文。"""
    return [_catalog_entry(item) for item in _CATALOG]


def _catalog_entry(item: dict) -> dict:
    return {
        "key": item["key"],
        "name": item["name"],
        "title": item["title"],
        "purpose": item["purpose"],
        "origin": _ORIGIN,
        "commit": _COMMIT,
        "license": item["license"],
        "dependencies": list(item["dependencies"]),
        "resources": item["resources"],
    }


def _provenance(key: str, item: dict) -> dict:
    return {
        "author": "Anthropic · EasyChat 适配",
        "origin": _ORIGIN,
        "commit": _COMMIT,
        "source_published_at": _SOURCE_PUBLISHED_AT,
        "source_url": f"https://github.com/{_ORIGIN}/tree/{_COMMIT}/skills/{item.get('source_name', key)}",
    }


def template_detail(key: str) -> dict:
    if key not in TEMPLATE_KEYS:
        raise NotFoundError("内置技能不存在")
    item = template_meta(key)
    return {
        **_catalog_entry(item),
        **_provenance(key, item),
        "content": load_template_content(key),
    }


def matching_template_provenance(name: str, content: str | None) -> dict | None:
    """只为与本次分发的内置技能完全一致的正文返回来源。"""
    if not content or name not in TEMPLATE_KEYS:
        return None
    item = template_meta(name)
    try:
        return _provenance(name, item) if content == load_template_content(name) else None
    except (InvalidInputError, OSError, UnicodeError):
        return None  # 读取个人技能独立于模板文件的可用性。


def template_meta(key: str) -> dict:
    for item in _CATALOG:
        if item["key"] == key:
            return item
    raise InvalidInputError(f"未知技能模板: {key}")


@functools.lru_cache(maxsize=8)
def _read(file_name: str) -> str:
    path = _ROOT / file_name
    if not path.is_file():
        raise InvalidInputError("模板资源缺失，请联系部署完整性检查")
    return path.read_text(encoding="utf-8")


def load_template_content(key: str) -> str:
    """模板正文（含来源与许可头）。"""
    return _read(template_meta(key)["file"])
