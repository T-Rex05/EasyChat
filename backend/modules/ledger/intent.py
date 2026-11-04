"""意图路由：自然语言 → 受控动作（导入预览 / 查询 / 修正 / 报告 / 退款核对）。

边界（架构 §账本）：
- 模型只用于“理解用户要什么”和“把话翻成结构化参数”，绝不算金额、不生成 SQL；
- 查询一律产出一份 QueryPlan，交给 `LedgerService.analyze` 做白名单校验与参数化编译；
- 规则解析器不依赖模型也能工作（离线可测），模型失败时给出澄清问题而不是猜。
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Protocol
from zoneinfo import ZoneInfo

from backend.modules.ledger.contracts import (
    BASIS_CONSUMPTION_NET,
    BASIS_PERIOD_CASH_OUTFLOW,
    BASIS_STATEMENT_FLOW,
    GROUP_BY_CATEGORY,
    GROUP_BY_MERCHANT,
    GROUP_BY_MONTH,
    METRIC_EXPENSE,
    METRIC_INCOME,
    METRIC_NET,
    METRIC_REFUND_RECEIVED,
)
from backend.shared.errors import InvalidInputError

INTENT_IMPORT = "import"
INTENT_QUERY = "analyze"
INTENT_CORRECT = "correct"
INTENT_REPORT = "report"
INTENT_REVIEW_REFUND = "review_refund"
INTENT_UNKNOWN = "unknown"

ALL_INTENTS = frozenset(
    {INTENT_IMPORT, INTENT_QUERY, INTENT_CORRECT, INTENT_REPORT, INTENT_REVIEW_REFUND, INTENT_UNKNOWN}
)

_IMPORT_WORDS = ("导入", "上传", "收录", "存一下", "保存这张")
_IMPORT_OBJECTS = ("账单", "流水", "xlsx", "csv", "截图", "excel", "对账单")
_REPORT_WORDS = ("报告", "pdf", "导出", "生成一份", "发我一份")
_CORRECT_WORDS = ("改成", "改为", "记错", "修正", "纠正", "分类到", "归到", "备注")
_REFUND_WORDS = ("退款", "退回", "退我")
_REFUND_ACTIONS = ("核对", "确认", "匹配", "关联", "对上")
_QUERY_WORDS = (
    "花了", "花费", "支出", "收入", "消费", "多少", "统计", "分析", "净额",
    "账单情况", "一共", "总共", "对比", "排名", "占比",
)

_DATE_RANGE_DAYS = re.compile(r"(?:最近|近|过去)\s*(\d{1,3})\s*天")
_YEAR_MONTH = re.compile(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*月?")
_NUMBER_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9, "十": 10}


class PlannerPort(Protocol):
    """把用户话翻成 QueryPlan 的模型端口；实现方必须只返回结构化 JSON。"""

    async def plan(self, text: str, *, schema_hint: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: str
    confidence: float
    reason: str
    plan: Mapping[str, Any] | None = None
    needs_clarification: bool = False
    question: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_range(year: int, month: int, tz: ZoneInfo) -> tuple[str, str]:
    start = date(year, month, 1)
    end = start + timedelta(days=_days_in_month(year, month))
    return start.isoformat(), end.isoformat()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def plan_from_text(text: str, *, now: datetime, timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    """确定性规则：把常见中文时间/口径说法翻成 QueryPlan（未知部分用默认值）。"""
    tz = ZoneInfo(timezone)
    local_now = now.astimezone(tz)
    today = local_now.date()
    lowered = text.lower()

    period: tuple[str, str] | None = None
    days_match = _DATE_RANGE_DAYS.search(text)
    if days_match:
        days = max(1, min(int(days_match.group(1)), 3660))
        start = today - timedelta(days=days - 1)
        period = (start.isoformat(), (today + timedelta(days=1)).isoformat())
    elif "上个月" in text or "上月" in text:
        year, month = _shift_month(today.year, today.month, -1)
        period = _month_range(year, month, tz)
    elif "本月" in text or "这个月" in text:
        period = _month_range(today.year, today.month, tz)
    elif "去年" in text:
        period = (date(today.year - 1, 1, 1).isoformat(), date(today.year, 1, 1).isoformat())
    elif "今年" in text or "年初至今" in text:
        period = (date(today.year, 1, 1).isoformat(), (today + timedelta(days=1)).isoformat())
    else:
        matched = _YEAR_MONTH.search(text)
        if matched:
            year, month = int(matched.group(1)), int(matched.group(2))
            if 1 <= month <= 12:
                period = _month_range(year, month, tz)
    if period is None:
        # 没有明确时间：默认本月，但明确标注为默认值，由上层提示用户
        period = _month_range(today.year, today.month, tz)

    basis = BASIS_CONSUMPTION_NET
    if "流水" in text or "账单金额" in text:
        basis = BASIS_STATEMENT_FLOW
    elif "现金" in text or "实际支出" in text:
        basis = BASIS_PERIOD_CASH_OUTFLOW

    metrics: list[str] = []
    if any(word in text for word in ("花", "支出", "消费")):
        metrics.append(METRIC_EXPENSE)
    if "收入" in text or "进账" in text:
        metrics.append(METRIC_INCOME)
    if "退款" in lowered:
        metrics.append(METRIC_REFUND_RECEIVED)
    if not metrics:
        metrics = [METRIC_EXPENSE, METRIC_INCOME]
    if METRIC_NET not in metrics:
        metrics.append(METRIC_NET)

    group_by: list[str] = []
    if "分类" in text or "类别" in text:
        group_by.append(GROUP_BY_CATEGORY)
    if "商户" in text or "商家" in text:
        group_by.append(GROUP_BY_MERCHANT)
    if "每月" in text or "月度" in text or "每个月" in text:
        group_by.append(GROUP_BY_MONTH)

    return {
        "version": 1,
        "basis": basis,
        "metrics": metrics,
        "period": {"start": period[0], "end_exclusive": period[1]},
        "group_by": group_by[:2],
        "output": "table" if group_by else "summary",
        "top_n": 10,
    }


def classify(text: str, *, has_files: bool = False) -> IntentDecision:
    """纯规则分类；顺序即优先级（退款核对 > 导入 > 报告 > 修正 > 查询）。"""
    raw = (text or "").strip()
    if not raw:
        return IntentDecision(
            intent=INTENT_UNKNOWN, confidence=0.0, reason="空输入",
            needs_clarification=True, question="请说明要做什么：导入账单、查花销、修正记录或生成报告。",
        )
    lowered = raw.lower()
    if any(word in raw for word in _REFUND_WORDS) and any(word in raw for word in _REFUND_ACTIONS):
        return IntentDecision(intent=INTENT_REVIEW_REFUND, confidence=0.8, reason="提到退款核对/关联")
    if any(word in raw for word in _IMPORT_WORDS) and (
        any(obj in lowered for obj in _IMPORT_OBJECTS) or has_files
    ):
        return IntentDecision(intent=INTENT_IMPORT, confidence=0.85, reason="提到导入/上传账单")
    if any(word in lowered for word in _REPORT_WORDS):
        return IntentDecision(intent=INTENT_REPORT, confidence=0.75, reason="提到报告/导出")
    if any(word in raw for word in _CORRECT_WORDS):
        return IntentDecision(intent=INTENT_CORRECT, confidence=0.7, reason="提到修正/改分类")
    if any(word in raw for word in _QUERY_WORDS):
        return IntentDecision(intent=INTENT_QUERY, confidence=0.7, reason="提到金额/统计/分析")
    return IntentDecision(
        intent=INTENT_UNKNOWN, confidence=0.2, reason="没有识别出账本相关意图",
        needs_clarification=True, question="你是想导入账单、查某段时间的花销、修正某笔记录，还是生成报告？",
    )


async def route(
    service,
    principal,
    text: str,
    *,
    file_ids: tuple[str, ...] = (),
    planner: PlannerPort | None = None,
) -> IntentDecision:
    """分类 + （可选）模型补全计划；模型输出非法时抛错，不静默降级为乱猜。"""
    decision = classify(text, has_files=bool(file_ids))
    if decision.intent != INTENT_QUERY:
        return decision
    now = service.now()
    if planner is not None:
        try:
            raw_plan = await planner.plan(
                text, schema_hint={"type": "object", "required": ["version", "basis", "metrics", "period"]},
            )
        except InvalidInputError:
            raise
        except Exception as exc:  # noqa: BLE001  模型调用失败要让用户知道
            raise InvalidInputError(f"查询计划生成失败: {exc}") from exc
        if not isinstance(raw_plan, Mapping):
            raise InvalidInputError("查询计划必须是 JSON 对象")
        plan = dict(raw_plan)
    else:
        plan = plan_from_text(text, now=now, timezone=service.timezone)
    return IntentDecision(
        intent=INTENT_QUERY, confidence=decision.confidence,
        reason=decision.reason, plan=plan,
    )
