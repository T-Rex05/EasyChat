"""内置示例技能模板目录（P3）。

来源固定：anthropics/skills @ 2c5958ecac7c（Apache-2.0，许可头随内容保留）。
资源为 EasyChat 适配改写版（自包含 Markdown，声明支持/不支持范围）；
模板本体只读，导入经 SkillService.import_template 走真实版本流程——
默认不激活（避免无选择地批量启用）。
"""
from __future__ import annotations

import functools
from pathlib import Path

from backend.shared.errors import InvalidInputError

_ORIGIN = "anthropics/skills"
_COMMIT = "2c5958ecac7c"
_ROOT = Path(__file__).resolve().parent / "templates"

_CATALOG: tuple[dict, ...] = (
    {
        "key": "pdf",
        "name": "pdf",
        "title": "PDF 处理",
        "purpose": "读取/抽取文本与表格、合并拆分、旋转水印、表单填写、生成新 PDF（含中文）",
        "license": "Apache-2.0",
        "dependencies": ["pypdf==6.15.0", "fpdf2"],
        "resources": "自包含；中文字体使用本机 simhei.ttf（Windows），其他环境需自备等价字体",
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
    return [
        {
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
        for item in _CATALOG
    ]


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
