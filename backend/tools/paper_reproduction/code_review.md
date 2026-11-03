# 论文复现系统代码审查报告

**审查时间**: 2026-10-02 21:10
**审查范围**: 前端数据流、后端逻辑、错误处理

---

## 🔴 严重问题

### 问题 1：数据流断裂（已修复）

**位置**: `PaperReproductionView.vue`

**问题描述**:
- `setupEnvironment` 调用 `debug_paper_code (setup)` 但没有保存返回的 `container_id`
- `debugCode` 调用 `debug_paper_code (debug)` 但没有传递 `container_id`
- 导致 `debug` action 失败：`"必须提供 container_id"`

**修复**:
```javascript
// 1. 添加 containerId 变量
const containerId = ref<string | null>(null)

// 2. setupEnvironment 保存 container_id
const setupResult = JSON.parse(response)
if (setupResult.container_id) {
  containerId.value = setupResult.container_id
}

// 3. debugCode 传递 container_id
const response = await invokeTool('debug_paper_code', {
  action: 'debug',
  container_id: containerId.value,  // 传递容器 ID
  rubric: claimRubric.value
})
```

---

### 问题 2：错误处理中断流程（已修复）

**位置**: `PaperReproductionView.vue`

**问题描述**:
- `setupEnvironment` 失败时抛出异常，中断整个流程
- `debugCode` 失败时抛出异常，阻止证据图谱构建

**修复**:
```javascript
// setupEnvironment 失败时设置 executionResults
executionResults.value = {
  results: [],
  metrics: {},
  status: 'setup_failed',
  error: error.message
}

// debugCode 失败时不抛出异常
catch (error: any) {
  executionResults.value = {
    results: [],
    metrics: {},
    status: 'failed',
    error: error.message
  }
  // 不抛出异常，让流程继续
}
```

---

### 问题 3：后端错误导致空图谱（已修复）

**位置**: `build_evidence_graph.py`

**问题描述**:
- `execution_results` 包含 `error` 字段时，返回空图谱
- 导致前端显示全为 0

**修复**:
```python
# 不直接返回空图谱，而是继续构建
execution_error = None
if execution_results.get("error"):
    execution_error = execution_results.get("error")
    logger.warning(f"⚠️ 执行结果包含错误: {execution_error}")
    # 继续构建，状态会标记为 pending

# 构建图谱
graph = _build_graph(rubric, execution_results, metrics_data or {})
```

---

## ⚠️ 中等问题

### 问题 4：`_generate_summary` 缺少 pending 统计（已修复）

**位置**: `build_evidence_graph.py`

**问题描述**:
- `summary` 没有统计 `pending` 状态的 claims

**修复**:
```python
pending = sum(1 for c in claims if c.get("status") in ["pending", "partially_pending"])

return {
    "total_claims": len(claims),
    "fully_verified": fully_verified,
    "partially_verified": partially_verified,
    "pending": pending,  # 新增
    "failed": failed,
    ...
}
```

---

### 问题 5：调试日志未移除

**位置**: `PaperReproductionView.vue:442-457`

**问题描述**:
- 生产环境应该移除调试日志

**建议**:
```javascript
// 使用环境变量控制
if (import.meta.env.DEV) {
  console.log('=== 构建证据图谱参数 ===')
  console.log('claimRubric:', JSON.stringify(claimRubric.value, null, 2))
}
```

---

## 📝 代码质量改进建议

### 1. 类型定义不完整

**建议**: 使用 TypeScript 接口定义数据结构

```typescript
interface Claim {
  id: string
  title: string
  statement: string
  criteria: Criterion[]
}

interface Criterion {
  id: string
  description: string
  metric_name?: string
  expected_value?: any
}

interface ExecutionResults {
  status: string
  results: any[]
  metrics: Record<string, any>
  error?: string
}
```

### 2. 错误处理不一致

**建议**: 统一错误处理策略

```javascript
// 创建统一的错误处理工具
function handleToolError(step: string, error: any) {
  executionResults.value = {
    results: [],
    metrics: {},
    status: `${step}_failed`,
    error: error.message
  }
  addLog('error', `${step}失败: ${error.message}`)
}
```

### 3. 状态管理分散

**建议**: 考虑使用 Pinia 管理论文复现状态

```typescript
// stores/paperReproduction.ts
export const usePaperReproductionStore = defineStore('paperReproduction', {
  state: () => ({
    currentPaper: null,
    claimRubric: null,
    repos: [],
    containerId: null,
    executionResults: null,
    evidenceGraph: null
  }),
  actions: {
    async parsePaper(url: string) { ... },
    async extractRubric() { ... },
    // ...
  }
})
```

---

## ✅ 修复总结

| 问题 | 严重程度 | 状态 |
|------|----------|------|
| 数据流断裂 | 🔴 严重 | ✅ 已修复 |
| 错误处理中断 | 🔴 严重 | ✅ 已修复 |
| 空图谱返回 | 🔴 严重 | ✅ 已修复 |
| pending 统计缺失 | ⚠️ 中等 | ✅ 已修复 |
| 调试日志未移除 | 📝 建议 | ⏸️ 待处理 |

---

## 🔄 测试验证

修复后，完整流程应该：

1. **论文解析**: ✅ 提取实体和主张
2. **主张提取**: ✅ 生成结构化 rubric
3. **仓库发现**: ✅ 找到相关仓库
4. **环境搭建**: ✅ 创建 Docker 容器，保存 `container_id`
5. **代码调试**: ✅ 传递 `container_id`，保存执行结果
6. **证据图谱**: ✅ 基于 rubric 生成图谱（即使调试失败）

---

**审查人**: Claude Fable 5
**状态**: 关键问题已修复，建议刷新前端重新测试