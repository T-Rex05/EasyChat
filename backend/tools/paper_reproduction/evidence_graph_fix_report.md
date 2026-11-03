# 证据图谱问题修复报告

**修复时间**: 2026-10-02 19:02
**问题**: 论文复现成功但证据图谱全为 0，验证报告无法滚动

---

## 🔍 问题分析

### 1. 数据流断裂

**问题**：前端没有保存代码调试结果，导致证据图谱缺少执行数据

```javascript
// 之前
execution_results: {}  // 空对象！

// 修复后
executionResults.value = JSON.parse(response)  // 保存调试结果
```

### 2. 后端处理不完整

**问题**：没有实际执行结果时，证据图谱节点为空

**修复**：添加 "pending" 状态，即使没有执行结果也能生成图谱结构

```python
# 修复后
if not has_execution:
    evidence["status"] = "pending"
    evidence["message"] = "等待代码执行以收集证据"
```

### 3. 置信度缺少 pending 字段

**问题**：置信度只统计 verified/failed/inconclusive

**修复**：添加 pending 计数

```python
return {
    "overall": overall,
    "verified": verified,
    "failed": failed,
    "inconclusive": inconclusive,
    "pending": pending,  # 新增
    "total": total
}
```

### 4. 前端滚动问题

**问题**：验证报告 Tab 无法滚动

**修复**：修复 el-tabs 的高度布局

```css
.content-area {
  display: flex;
  flex-direction: column;
}

:deep(.el-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.el-tab-pane) {
  height: 100%;
  overflow: auto;
}
```

---

## 📝 修改文件

### 后端

| 文件 | 修改内容 |
|------|---------|
| `build_evidence_graph.py` | 1. 支持 pending 状态证据<br>2. 支持 pending 状态判定<br>3. 置信度增加 pending 字段<br>4. Claim 状态增加 pending 判断 |

### 前端

| 文件 | 修改内容 |
|------|---------|
| `PaperReproductionView.vue` | 1. 添加 `executionResults` 变量<br>2. `debugCode` 保存执行结果<br>3. `buildEvidence` 使用保存的结果<br>4. 修复 Tab 滚动布局 |

---

## ✅ 测试结果

```json
{
  "confidence": {
    "overall": 0.0,
    "verified": 0,
    "failed": 0,
    "inconclusive": 0,
    "pending": 1,
    "total": 1
  },
  "graph": {
    "nodes": 4,  // 1 claim + 1 criterion + 1 evidence + 1 judgment
    "edges": 3
  }
}
```

---

## 🎯 用户体验改进

### 修复前

```
整体置信度: 0%
已验证: 0 / 0
失败: 0 / 0
待定: 0 / 0
证据图谱: 空白
验证报告: 无法滚动
```

### 修复后

```
整体置信度: 0%（等待执行）
已验证: 0 / 1
失败: 0 / 1
待定: 1 / 1  ← 新增
证据图谱: 显示完整结构（状态为 pending）
验证报告: 可以滚动查看
```

---

## 🔄 下一步

1. **重启后端服务**以应用修改
2. **刷新前端页面**重新测试
3. **验证完整流程**：
   - 解析论文
   - 提取主张
   - 发现仓库
   - 搭建环境（如有仓库）
   - 调试代码（如有仓库）
   - 构建证据图谱（现在应该有数据了）

---

**修复人**: Claude Fable 5
**状态**: 已修复，待用户验证