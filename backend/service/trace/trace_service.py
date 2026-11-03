"""
LLM 链路可观测性 — 兼容入口层

本模块保留原有公共 API，实现已拆分到：
- trace_config.py: 配置管理（get_config / set_config / is_detail_enabled 等）
- trace_write.py:  数据写入（record_trace / update_trace / mark_trace_error 等）
- trace_query.py:  查询功能（list_traces / get_trace_detail / list_turns）
- trace_stats.py:  统计与清理（get_dashboard_stats / get_ranking / cleanup_old_traces 等）

外部调用方 `from backend.service.trace.trace_service import xxx` 保持兼容。
"""
from backend.service.trace.config import (
    get_config,
    get_all_config,
    set_config,
    is_detail_enabled,
    get_max_text_chars,
)
from backend.service.trace.write import (
    record_trace,
    update_trace,
    mark_trace_error,
    sync_trace_texts,
    record_span,
    _get_session_source,
)
from backend.service.trace.query import (
    list_traces,
    get_trace_detail,
    list_turns,
)
from backend.service.trace.stats import (
    get_dashboard_stats,
    get_user_ranking,
    cleanup_old_traces,
    get_ranking,
)

__all__ = [
    # 配置管理
    "get_config",
    "get_all_config",
    "set_config",
    "is_detail_enabled",
    "get_max_text_chars",
    # 数据写入
    "record_trace",
    "update_trace",
    "mark_trace_error",
    "sync_trace_texts",
    "record_span",
    # 查询
    "list_traces",
    "get_trace_detail",
    "list_turns",
    # 统计与清理
    "get_dashboard_stats",
    "get_user_ranking",
    "cleanup_old_traces",
    "get_ranking",
]
