# 论文复现系统"没有找到可用仓库"问题修复报告

**修复时间**: 2026-10-02 00:10
**严重程度**: 🟡 中等
**影响范围**: 论文复现流程

---

## 🔴 问题分析

### 错误信息

```
00:01:13复现失败: 环境搭建失败: 没有找到可用仓库
```

### 问题根因

**前端代码硬性要求仓库存在**：

```typescript
// 修复前
if (repos.value.length === 0) {
  throw new Error('没有找到可用仓库')  // ❌ 直接抛出错误
}
```

**问题**：
1. 不是所有论文都有公开的代码实现
2. GitHub API 搜索可能找不到相关仓库
3. 没有提供"跳过"或"手动输入"选项
4. 整个流程因为缺少仓库而失败

---

## ✅ 修复方案

### 1. 后端改进：更友好的错误信息

**文件**: [discover_repo.py](backend/tools/paper_reproduction/discover_repo.py)

```python
# 检查是否找到仓库
if not top_repos:
    logger.warning(f"⚠️ 未找到匹配的仓库，建议：")
    logger.warning(f"   1. 论文可能没有公开的代码实现")
    logger.warning(f"   2. 尝试使用更通用的搜索词")
    logger.warning(f"   3. 手动提供仓库 URL")
    result["warning"] = "未找到匹配的仓库，可以尝试手动提供仓库 URL 或使用代码生成模式"
    result["suggestions"] = [
        "在 GitHub 上搜索论文标题",
        "查看论文是否提供了代码链接",
        "使用 '代码生成' 模式而非 '仓库复现' 模式"
    ]
```

### 2. 前端改进：允许跳过仓库发现

**文件**: [PaperReproductionView.vue](agent_frontend/src/views/paper-reproduction/PaperReproductionView.vue)

#### 修改 1：discoverRepo 函数

```typescript
if (repos.value.length === 0) {
  // 没有找到仓库，提供选项
  updateTaskStatus('repo', 'warning')  // ✅ 标记为警告而非失败
  addLog('warning', '未找到匹配的仓库')
  addLog('info', '建议：在 GitHub 上搜索论文标题，或查看论文是否提供了代码链接')

  ElMessage.warning('未找到匹配的仓库，您可以手动输入仓库 URL 或跳过此步骤')
} else {
  updateTaskStatus('repo', 'completed')
  addLog('success', `找到 ${repos.value.length} 个仓库`)
}
```

#### 修改 2：setupEnvironment 函数

```typescript
if (repos.value.length === 0) {
  // 没有找到仓库，跳过环境搭建
  updateTaskStatus('setup', 'skipped')  // ✅ 标记为跳过
  addLog('warning', '没有找到可用仓库，跳过环境搭建')
  addLog('info', '建议：手动在 GitHub 搜索论文代码，或使用代码生成模式')
  return  // ✅ 返回而非抛出错误
}
```

#### 修改 3：debugCode 函数

```typescript
// 检查是否有仓库
if (repos.value.length === 0) {
  updateTaskStatus('debug', 'skipped')  // ✅ 标记为跳过
  addLog('warning', '没有可用仓库，跳过代码调试')
  return
}
```

#### 修改 4：buildEvidence 函数

```typescript
confidence.value = evidenceGraph.value.confidence || {
  overall: 0,
  verified: 0,
  failed: 0,
  inconclusive: 0,
  total: 0
}

// 检查是否有错误
if (evidenceGraph.value.error) {
  updateTaskStatus('verify', 'warning')  // ✅ 标记为警告
  addLog('warning', `证据图谱构建警告: ${evidenceGraph.value.error}`)
} else {
  updateTaskStatus('verify', 'completed')
  addLog('success', `证据图谱构建完成: 置信度 ${(confidence.value.overall * 100).toFixed(0)}%`)
}
```

---

## 📊 修复对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| **未找到仓库** | ❌ 抛出错误，流程失败 | ✅ 显示警告，继续执行 |
| **环境搭建** | ❌ 强制要求仓库 | ✅ 跳过，提供建议 |
| **代码调试** | ❌ 强制要求仓库 | ✅ 跳过，提供建议 |
| **证据图谱** | ❌ 可能崩溃 | ✅ 优雅处理错误 |
| **用户体验** | ❌ 阻断性错误 | ✅ 引导性建议 |

---

## 🚀 用户体验改进

### 修复前

```
用户：开始复现
系统：❌ 复现失败: 环境搭建失败: 没有找到可用仓库
用户：（无法继续）
```

### 修复后

```
用户：开始复现
系统：⚠️ 未找到匹配的仓库
系统：💡 建议：在 GitHub 上搜索论文标题，或查看论文是否提供了代码链接
系统：✅ 论文解析完成
系统：✅ 主张提取完成
系统：⏭️  仓库发现：跳过
系统：⏭️  环境搭建：跳过
系统：⏭️  代码调试：跳过
系统：✅ 证据图谱构建完成
用户：（可以查看论文解析和主张提取的结果）
```

---

## 💡 未来增强

### 短期

- [ ] 添加"手动输入仓库 URL"输入框
- [ ] 添加"在 GitHub 搜索"按钮（打开新窗口）
- [ ] 显示论文中可能包含的代码链接

### 中期

- [ ] 支持"代码生成模式"（不依赖现有仓库）
- [ ] 集成 Papers with Code API
- [ ] 提供相似论文的仓库推荐

### 长期

- [ ] 自动从论文 PDF 中提取代码链接
- [ ] 支持多个仓库对比
- [ ] 提供代码质量评估

---

## ✨ 技术亮点

```
✶ Insight ─────────────────────────────────────
1. **优雅降级**：当非关键步骤失败时，允许流程继续，而非直接崩溃
2. **用户引导**：提供具体的建议和操作指引，而非简单的错误信息
3. **状态区分**：区分 failed（失败）、warning（警告）、skipped（跳过）状态
4. **防御性编程**：确保 `confidence` 对象始终存在，避免前端崩溃
─────────────────────────────────────────────────
```

---

**修复人**: Claude Fable 5
**验证状态**: 待用户测试