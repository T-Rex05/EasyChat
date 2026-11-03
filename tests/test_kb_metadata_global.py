"""
测试 Metadata 全局共享方案

验证超长主题切分后，关键信息（表关联、约束条件、表选择原则）是否全局共享。
"""
import pytest
from backend.service.kb.kb_topic_splitter import (
    TopicSection,
    _extract_table_refs_from_section,
    _extract_constraints_from_section,
    _extract_key_rules_from_section,
)
from backend.service.kb.kb_parent_child_splitter import (
    build_parent_child_chunks,
    ParentChunk,
)


class TestMetadataExtraction:
    """测试 metadata 提取功能"""

    def test_extract_table_refs(self):
        """测试提取表关联"""
        section_text = """
### 六、【数据库表关联】

#### MySQL表

| 表名 | 说明 | 数据维度 |
|------|------|----------|
| map_config_msg | 业务MAP图配置表（核心表） | **业务级别** |
| business_map_data_level | 业务主机的等保和密评等级表 | **主机级别** |

**重要：表选择原则**
- 查询"各业务的密评/等保/数据分级等级" → 使用 `map_config_msg`（业务级别，每个业务唯一）
- 查询"业务主机的等级"或"文件数据分级明细" → 使用 `business_map_data_level`（主机级别）

**约束条件**
- ⚠️ 需要先在系统管理-业务库数据源配置中配置好数据源并点击同步
- 查询 `map_config_msg` 时需排除4个占位业务：
  ```sql
  WHERE map_cfg_id NOT IN (9901, 9902, 9903, 9904)
  ```
"""
        table_refs = _extract_table_refs_from_section(section_text)
        assert "map_config_msg" in table_refs
        assert "business_map_data_level" in table_refs

    def test_extract_constraints(self):
        """测试提取约束条件"""
        section_text = """
### 功能描述

这是一个测试功能。

### 约束条件

- ⚠️ 需要先在系统管理-业务库数据源配置中配置好数据源并点击同步
- 查询 `map_config_msg` 时需排除4个占位业务：
  ```sql
  WHERE map_cfg_id NOT IN (9901, 9902, 9903, 9904)
  ```

### 其他内容

其他内容...
"""
        constraints = _extract_constraints_from_section(section_text)
        assert len(constraints) >= 2
        assert any("配置好数据源" in c for c in constraints)
        assert any("排除" in c and "占位业务" in c for c in constraints)

    def test_extract_key_rules(self):
        """测试提取表选择原则"""
        section_text = """
### 六、【数据库表关联】

| 表名 | 说明 |
|------|------|
| map_config_msg | 业务MAP图配置表 |
| business_map_data_level | 业务主机的等保和密评等级表 |

**重要：表选择原则**
- 查询"各业务的密评/等保/数据分级等级" → 使用 `map_config_msg`（业务级别，每个业务唯一）
- 查询"业务主机的等级"或"文件数据分级明细" → 使用 `business_map_data_level`（主机级别）
- **常见错误**：使用 `business_map_data_level` 做"各业务等级统计"会导致一个业务出现多个等级
"""
        key_rules = _extract_key_rules_from_section(section_text)
        assert len(key_rules) >= 2
        assert any("map_config_msg" in r for r in key_rules)
        assert any("business_map_data_level" in r for r in key_rules)


class TestMetadataGlobalSharing:
    """测试 metadata 全局共享"""

    def test_long_topic_metadata_shared(self):
        """测试超长主题切分后，metadata 全局共享"""
        # 构造一个超长主题（3000 字）
        long_topic_text = """
## 【主题：等保/密评/数据分级库表查询】

### 一、【功能模块定义】
- **名称：** 等保/密评/数据分级库表查询
- **核心功能：** 根据业务MAP图，查询相关库表数据分级列表
- **适用范围：** 安全管理员、合规负责人、数据管理员
- **前置条件：** ⚠️ 需要先在业务库数据源配置里配置好

### 二、【操作步骤】

1. **选择查询条件**（任选其一）
   - 业务MAP图名称 / 文件数据分级 / 等保等级 / 密评定级 / 业务分组 / 部门

2. **选择时间范围**

3. **点击查询按钮**

### 三、【查询结果字段】

| 字段名 | 说明 |
|--------|------|
| 数据源名称 | 数据库连接名称 |
| 库/Schema | 数据库或Schema名称 |
| 表名 | 数据库表名 |
| 表字段 | 字段详情（点击查看） |
| 主机IP | 数据库主机IP |

### 四、【约束条件】

⚠️ **注意：** 需要先在系统管理-业务库数据源配置中配置好数据源并点击同步

查询 `map_config_msg` 时需排除4个占位业务：
```sql
WHERE map_cfg_id NOT IN (9901, 9902, 9903, 9904)
-- 9901=恶意外联告警专用, 9902=恶意文件告警专用, 9903=关键文件告警专用, 9904=反弹shell告警专用
```

### 五、【检索关键词】
库表查询、数据分级、等保库表、密评库表、数据库合规、表字段、数据源、业务MAP图

### 六、【数据库表关联】

#### MySQL表

| 表名 | 说明 | 数据维度 |
|------|------|----------|
| map_config_msg | 业务MAP图配置表（核心表） | **业务级别** - 每个业务唯一一行 |
| business_map_data_level | 业务主机的等保和密评等级表 | **主机级别** - 一个业务可能多行 |

**重要：表选择原则**
- 查询"各业务的密评/等保/数据分级等级" → 使用 `map_config_msg`（业务级别，每个业务唯一）
- 查询"业务主机的等级"或"文件数据分级明细" → 使用 `business_map_data_level`（主机级别）
- **常见错误**：使用 `business_map_data_level` 做"各业务等级统计"会导致一个业务出现多个等级（如"2级、4级"），这是错误的

#### 表关联关系
```
map_config_msg.map_cfg_id = business_map_data_level.map_id
```

#### 占位业务排除
查询 `map_config_msg` 时需排除4个占位业务：
```sql
WHERE map_cfg_id NOT IN (9901, 9902, 9903, 9904)
```

### 七、【补充说明】

这是补充内容，用于让主题超过 2000 字，触发三级降级切分。

补充内容1：关于数据分级的详细说明...
补充内容2：关于等保等级的详细说明...
补充内容3：关于密评定级的详细说明...
"""
        # 创建 TopicSection（需要先提取 metadata）
        from backend.service.kb.kb_topic_splitter import (
            _extract_table_refs_from_section,
            _extract_constraints_from_section,
            _extract_key_rules_from_section,
        )
        
        section = TopicSection(
            title="等保/密评/数据分级库表查询",
            text=long_topic_text,
            page_start=1,
            page_end=5,
            source="marker",
            table_refs=_extract_table_refs_from_section(long_topic_text),
            constraints=_extract_constraints_from_section(long_topic_text),
            key_rules=_extract_key_rules_from_section(long_topic_text),
        )

        # 构建父子分片（父片大小设为 1000，强制切分）
        result = build_parent_child_chunks(
            pages=[],
            parent_chunk_size=1000,  # 强制切分
            child_chunk_size=200,
            child_overlap=50,
            sections=[section],
        )

        parents = result["parents"]
        
        # 验证：切分成了多个父片
        assert len(parents) > 1, "应该切分成多个父片"

        # 验证：所有父片的 metadata 都包含相同的 table_refs
        all_table_refs = [p.get("table_refs", []) for p in parents]
        assert all(len(refs) > 0 for refs in all_table_refs), "所有父片都应该有 table_refs"
        assert all(refs == all_table_refs[0] for refs in all_table_refs), "所有父片的 table_refs 应该相同"

        # 验证：所有父片的 metadata 都包含相同的 constraints
        all_constraints = [p.get("constraints", []) for p in parents]
        assert all(len(c) > 0 for c in all_constraints), "所有父片都应该有 constraints"
        assert all(c == all_constraints[0] for c in all_constraints), "所有父片的 constraints 应该相同"

        # 验证：所有父片的 metadata 都包含相同的 key_rules
        all_key_rules = [p.get("key_rules", []) for p in parents]
        assert all(len(r) > 0 for r in all_key_rules), "所有父片都应该有 key_rules"
        assert all(r == all_key_rules[0] for r in all_key_rules), "所有父片的 key_rules 应该相同"

        # 验证：关键信息确实被提取到了
        assert "map_config_msg" in all_table_refs[0]
        assert "business_map_data_level" in all_table_refs[0]
        assert any("配置好数据源" in c for c in all_constraints[0])
        assert any("map_config_msg" in r for r in all_key_rules[0])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
