# 论文复现系统安全隔离修复报告

**修复时间**: 2026-10-01 21:10
**严重程度**: 🔴 高危
**影响范围**: 数据隔离、隐私保护

---

## 🔴 安全漏洞描述

### 漏洞类型：跨租户数据泄露

**原问题**：论文解析存储到知识图谱时**没有传递 user_id**，导致：

1. **无隔离**：所有用户可能看到所有论文实体
2. **数据泄露风险**：用户 A 的论文解析结果，用户 B 可能检索到
3. **实体对齐冲突**：不同用户的同名实体会被错误合并

---

## 📊 技术分析

### KGStore 可见性规则

```python
# 知识图谱可见性谓词
(source_document_id IS NOT NULL AND source_document_id IN $visible_doc_ids)
OR
(source_document_id IS NULL AND user_id = $user_id)
```

### 论文实体的字段状态

| 字段 | 值 | 说明 |
|------|-----|------|
| `source_document_id` | NULL | 不是从 KB 文档提取 |
| `user_id` | NULL | **没有传递** |

**问题**：
- 论文实体两个条件都不满足
- 可能导致查询时不可见，或实体对齐时泄露

---

## ✅ 修复方案

### 修复内容

1. **添加 user_id 参数**：
   ```python
   def _store_to_graphrag(entities, relations, user_id=None):
   ```

2. **自动获取当前用户 ID**：
   ```python
   from backend.hermes_adapter import _CURRENT_USER_ID_CTX
   user_id = _CURRENT_USER_ID_CTX.get()
   ```

3. **传递给 KGStore**：
   ```python
   kg_store.create_entity(entity, user_id=user_id)
   kg_store.create_relation(relation, user_id=user_id)
   ```

---

## 🧪 验证方法

### 测试步骤

1. **用户 A 解析论文**：
   ```bash
   # 用户 A 登录
   # 解析论文 https://arxiv.org/abs/2009.00031
   ```

2. **用户 B 尝试检索**：
   ```bash
   # 用户 B 登录
   # 在对话中询问论文内容
   # 应该检索不到用户 A 的论文实体
   ```

3. **验证日志**：
   ```
   ✅ 存储到知识图谱: 26 个实体, 34 条关系 (user_id=123)
   ```

---

## 📋 影响评估

### 修复前

| 场景 | 风险 |
|------|------|
| 多租户环境 | 🔴 高风险：数据可能泄露 |
| 单租户环境 | 🟡 中风险：实体对齐可能冲突 |
| 公有云部署 | 🔴 高风险：严重隐私问题 |

### 修复后

| 场景 | 风险 |
|------|------|
| 多租户环境 | ✅ 低风险：按 user_id 隔离 |
| 单租户环境 | ✅ 低风险：实体对齐隔离 |
| 公有云部署 | ✅ 低风险：符合隐私要求 |

---

## 🛡️ 防御措施

### 1. 数据库层面

确保所有实体都有 `user_id` 字段：

```cypher
# 查找没有 user_id 的实体
MATCH (n)
WHERE n.user_id IS NULL
  AND n.source_document_id IS NULL
RETURN count(n)
```

### 2. 监控告警

添加日志监控：

```python
if not user_id:
    logger.warning(f"⚠️ 知识图谱存储缺少 user_id，可能存在隔离问题")
```

### 3. 代码审查

检查所有 `create_entity` 调用是否传递了 `user_id`。

---

## ✨ 最佳实践

```
✶ Insight ─────────────────────────────────────
1. **租户隔离原则**：所有用户数据必须标记 owner（user_id）
2. **contextvars 应用**：在异步环境中传递用户上下文
3. **防御性编程**：假设调用方可能忘记传参，自动获取默认值
4. **安全审计**：定期检查数据库中的孤立实体（无 user_id）
─────────────────────────────────────────────────
```

---

## 📝 相关代码

- [parse_paper.py:462](parse_paper.py#L462) - 修复后的存储函数
- [kg_store.py:224](../../graphrag/kg_store.py#L224) - create_entity 方法
- [hermes_adapter.py:179](../../hermes_adapter.py#L179) - 用户上下文

---

## 🔄 后续行动

- [ ] 验证修复效果（不同用户测试）
- [ ] 检查其他工具是否有类似问题
- [ ] 添加自动化测试覆盖隔离场景
- [ ] 更新开发文档，强调租户隔离

---

**修复人**: Claude Fable 5
**验证状态**: 待测试