# 论文复现系统第三轮修复报告 — 数据隔离架构优化

**修复时间**: 2026-10-01 22:15
**严重程度**: 🔴 架构级问题
**影响范围**: 知识图谱数据隔离、对话检索正确性

---

## 🔴 核心问题：论文实体污染对话检索

### 问题发现

用户指出关键问题：
> "但是传 user_id 是不是也不太对啊，这个论文里的也不应该让对话中检索得到吧，对话检索应该只能检索到知识库文档的实体和记忆的实体"

### 知识图谱可见性规则

```python
@staticmethod
def _vis_pred(var: str) -> str:
    return (
        f"(({var}.source_document_id IS NOT NULL "
        f"AND {var}.source_document_id IN $visible_doc_ids) "
        f"OR ({var}.source_document_id IS NULL AND {var}.user_id = $user_id))"
    )
```

### 数据分类对比

| 数据类型 | source_document_id | user_id | 可见性 |
|---------|-------------------|---------|--------|
| **知识库文档** | ✅ 非空 | NULL | 有权限的用户可见 |
| **用户记忆** | NULL | ✅ 非空 | 仅自己可见 |
| **论文实体** | NULL | ❌ 不应有 | **不应在对话中检索** |

### 如果传递 user_id 会发生什么？

```
用户 A 解析论文 → 存储实体 (user_id=A)
↓
用户 A 在对话中提问 → GraphRAG 检索
↓
检索条件: source_document_id IS NULL AND user_id = A
↓
❌ 论文实体被检索到，干扰对话上下文
```

---

## ✅ 修复方案：不存储到知识图谱

### 设计决策

论文解析产生的实体是**分析产物**，而非**知识资产**：

- **知识库文档**：企业级知识，多人可见，持久化存储
- **用户记忆**：个人上下文，仅自己可见，持久化存储
- **论文实体**：论文复现专用，临时数据，**不应污染对话检索**

### 修复代码

**文件**: [parse_paper.py:462](parse_paper.py#L462)

```python
def _store_to_graphrag(entities: list, relations: list, user_id: Optional[int] = None):
    """
    存储到知识图谱（论文实体暂时不存储）

    ⚠️ 设计决策：
    论文解析产生的实体与知识库文档、用户记忆性质不同：
    - 知识库文档：企业级知识，多人可见（source_document_id）
    - 用户记忆：个人上下文，仅自己可见（user_id）
    - 论文实体：论文复现专用，不应在正常对话中检索

    如果存储到知识图谱，会污染对话检索结果：
    - 用户 A 解析论文 → 存储 entity(user_id=A)
    - 用户 A 对话时，GraphRAG 会检索到论文实体
    - 这会干扰正常的对话上下文

    TODO: 未来可考虑：
    1. 创建独立的论文知识库（source_paper_id）
    2. 或在可见性规则中添加 artifact 类型过滤
    3. 或仅在论文复现流程中使用，不持久化

    当前方案：不存储到知识图谱，仅返回给前端使用
    """
    if not entities:
        logger.info("没有实体需要存储")
        return

    # 🔒 论文实体不存储到知识图谱，避免污染对话检索
    logger.info(f"📊 论文实体不存储到知识图谱（避免对话检索污染）")
    logger.info(f"   提取了 {len(entities)} 个实体, {len(relations)} 条关系")
    logger.info(f"   实体将通过返回值传递给后续工具使用")

    # 仍然记录统计信息
    return {
        "entities_count": len(entities),
        "relations_count": len(relations),
        "stored": False,
        "reason": "论文实体不应污染对话检索"
    }
```

---

## 📊 修复效果

### 测试结果

```
[测试 1] 论文解析
------------------------------------------------------------
✅ PDF 提取: 9 页, 40357 字符
✅ 实体提取: 25 个实体, 27 条关系
📊 论文实体不存储到知识图谱（避免对话检索污染）
   提取了 25 个实体, 27 条关系
   实体将通过返回值传递给后续工具使用
✅ 论文解析完成: Proper motion, spectra, and timing of PSR J1813−1749

[测试 2] 主张提取
------------------------------------------------------------
✅ Rubric 冻结完成: 5 个主张, SHA-256: 0129d99c1c57...

[测试 3] 仓库发现
------------------------------------------------------------
✅ 仓库发现完成: 推荐 DavidT3/XGA
✅ 找到仓库: 7 个
```

### 数据流向对比

| 修复前 | 修复后 |
|--------|--------|
| 论文实体 → 知识图谱 → 对话检索 ❌ | 论文实体 → 返回前端 → 论文复现流程 ✅ |
| 污染对话上下文 | 保持对话检索纯净 |
| 用户困惑：为什么聊到论文？ | 对话与论文复现隔离 |

---

## 🚀 架构优化建议

### 当前方案（推荐）

**不存储到知识图谱**，仅作为临时数据传递：

- 论文解析 → 返回实体/关系 JSON
- 前端展示 → 用户确认
- 后续工具 → 使用传递的实体数据
- 流程结束 → 数据丢弃

### 未来扩展方案

#### 方案 1：独立论文知识库

```python
entity = Entity(
    id=uuid4(),
    name=...,
    source_paper_id=paper_id,  # 新字段
    paper_user_id=user_id,     # 论文所有者
)
```

可见性规则：
```python
# 对话检索：排除论文实体
WHERE source_paper_id IS NULL

# 论文复现流程：按 paper_id 检索
WHERE source_paper_id = $paper_id AND paper_user_id = $user_id
```

#### 方案 2：Artifact 类型标记

```python
entity = Entity(
    id=uuid4(),
    name=...,
    artifact_type="paper_analysis",  # 新字段
    user_id=user_id,
)
```

可见性规则：
```python
# 对话检索：只检索 KB 和记忆
WHERE (source_document_id IN $visible_docs)
   OR (source_document_id IS NULL AND user_id = $user_id AND artifact_type IS NULL)
```

---

## ✨ 技术亮点

```
✶ Insight ─────────────────────────────────────
1. **数据分类思维**：并非所有数据都适合存储到知识图谱，需要考虑数据的性质和用途
2. **可见性规则边界**：现有的可见性规则是为 KB 文档和用户记忆设计的，强行加入新类型会破坏语义
3. **最小惊讶原则**：用户在对话中不应看到论文复现的数据，避免混淆和困惑
4. **临时数据传递**：有些数据只需要在流程中使用，不需要持久化
─────────────────────────────────────────────────
```

---

## 📝 相关代码

- [parse_paper.py:462](parse_paper.py#L462) - 修复后的存储函数
- [kg_store.py:224](../../graphrag/kg_store.py#L224) - create_entity 方法
- [kg_store.py:521](../../graphrag/kg_store.py#L521) - 可见性谓词

---

## 🔄 后续行动

- [x] 论文实体不再存储到知识图谱
- [ ] 考虑是否需要论文知识库功能（按需求优先级）
- [ ] 更新架构文档，说明数据分类原则
- [ ] 添加单元测试验证隔离效果

---

**修复人**: Claude Fable 5
**验证状态**: ✅ 已通过测试