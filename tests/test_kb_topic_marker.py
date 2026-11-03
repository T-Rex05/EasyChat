"""主题标记切分 + 数据库表关联提取 单元测试"""
import pytest

from backend.service.kb.kb_topic_splitter import (
    _from_md_topic_markers,
    _extract_table_refs_from_section,
    detect_topic_sections,
)
from backend.service.database_semantic_index import (
    format_table_schema_context,
    resolve_table_schema_context,
)

# Eyes 风格文档示例
_SAMPLE_DOC = """## 【主题：文档概述】

### 一、【目的】
本手册旨在指导用户正确使用监控系统。

### 四、【检索关键词】
文档概述、术语定义

---

## 【主题：库表查询-数据库合规】

### 一、【功能模块定义】
- **名称：** 库表查询
- **核心功能：** 查看库表信息

### 五、【检索关键词】
库表查询、数据分级

### 六、【数据库表关联】

#### MySQL表

| 表名 | 说明 | 数据维度 |
|------|------|----------|
| map_config_msg | 业务MAP图配置表（核心表） | **业务级别** - 每个业务唯一一行 |
| business_map_data_level | 业务主机的等保和密评等级表 | **主机级别** - 一个业务可能多行 |

#### 表关联关系
```
map_config_msg.map_cfg_id = business_map_data_level.map_id
```

---

## 【主题：主机TCP会话报表-主机TCP会话可视化】

### 三、【检索关键词】
TCP会话报表、主机TCP

### 四、【数据库表关联】

#### ClickHouse表

| 表名 | 说明 |
|------|------|
| sessions_tcp_msg | 非容器TCP会话原始数据 |
| sessions_tcp_msg_local_sessions_agg | 非容器本地TCP会话聚合数据 |

---
"""


class TestTopicMarkerSplit:
    def test_detect_topic_markers(self):
        """应识别出 3 个【主题：xxx】主题。"""
        sections = _from_md_topic_markers(_SAMPLE_DOC)
        assert len(sections) == 3
        assert sections[0].title == "文档概述"
        assert sections[1].title == "库表查询-数据库合规"
        assert sections[2].title == "主机TCP会话报表-主机TCP会话可视化"
        assert sections[0].source == "marker"

    def test_topic_marker_priority(self):
        """detect_topic_sections 应优先使用主题标记。"""
        sections, warnings = detect_topic_sections(".md", "", _SAMPLE_DOC, [])
        assert len(sections) == 3
        assert all(s.source == "marker" for s in sections)

    def test_extract_table_refs(self):
        """应提取【数据库表关联】区块中的表名。"""
        body = """### 六、【数据库表关联】

#### MySQL表

| 表名 | 说明 | 数据维度 |
|------|------|----------|
| map_config_msg | 业务MAP图配置表 | **业务级别** |
| business_map_data_level | 业务主机的等保等级表 | **主机级别** |
"""
        refs = _extract_table_refs_from_section(body)
        assert "map_config_msg" in refs
        assert "business_map_data_level" in refs
        assert "表名" not in refs  # 表头不应被提取

    def test_table_refs_in_sections(self):
        """主题章节应携带 table_refs。"""
        sections = _from_md_topic_markers(_SAMPLE_DOC)
        assert sections[0].table_refs == []  # 无表关联的主题为空
        assert "map_config_msg" in sections[1].table_refs
        assert "business_map_data_level" in sections[1].table_refs
        assert "sessions_tcp_msg" in sections[2].table_refs

    def test_parent_child_chunks_with_refs(self):
        """父子切片（sections 输入）：父片携带 table_refs，子片通过 parent_index 关联父片。"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        sections = _from_md_topic_markers(_SAMPLE_DOC)
        result = build_parent_child_chunks([], sections=sections)
        parents = result["parents"]
        assert len(parents) == 3
        assert parents[1]["table_refs"] == [
            "map_config_msg", "business_map_data_level"
        ]
        assert "table_refs" not in parents[0]
        # 子片不继承父片 table_refs，通过 parent_index 关联
        for c in result["children"]:
            assert "parent_index" in c
            assert "table_refs" not in c  # 子片不存储 table_refs


class TestDedup:
    def test_table_refs_dedup(self):
        """同一表名多次出现应去重。"""
        body = """### 四、【数据库表关联】

| 表名 | 说明 |
|------|------|
| alert_info | 告警信息表 |
| alert_info | 重复出现 |
| host_main | 主机表 |
"""
        refs = _extract_table_refs_from_section(body)
        assert refs.count("alert_info") == 1
        assert refs == ["alert_info", "host_main"]


class TestSchemaCard:
    def test_format_schema_context(self):
        """应能按表名查到 Schema Card。"""
        ctx = format_table_schema_context("mysql", ["users"])
        assert "users" in ctx
        assert "用户" in ctx

    def test_format_schema_unknown_table(self):
        """不存在的表应返回空。"""
        ctx = format_table_schema_context("mysql", ["no_such_table_xyz"])
        assert ctx == ""

    def test_resolve_from_table_refs(self):
        """根据 table_refs 列表拼装 Schema 上下文。"""
        ctx = resolve_table_schema_context(["users", "traces", "nonexistent_zzz"])
        assert "users" in ctx
        assert "traces" in ctx
        assert "nonexistent_zzz" not in ctx

    def test_resolve_empty(self):
        """空 table_refs 应返回空字符串。"""
        assert resolve_table_schema_context(None) == ""
        assert resolve_table_schema_context([]) == ""
