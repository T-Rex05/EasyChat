# ToT 消融设计

> [返回目录](./README.md)

---

## 什么是 ToT 消融设计

ToT（Tree of Thoughts）消融设计是指在论文复现过程中，使用受限的思维树搜索自动生成消融实验候选、评估信息增益与成本，并只保留预算内的少量方案的机制。

**核心特点**：

| 特性 | 说明 |
|------|------|
| **受限搜索** | 搜索深度固定为 2，候选分支最多 8 |
| **多维度覆盖** | 参数、模块、数据规模、随机种子、运行成本 |
| **预算控制** | 最大实验数、GPU 时间、总耗时上限 |
| **确定性兜底** | 模型失败时使用内置候选和评分 |

`✶ Insight ─────────────────────────────────────`
**为什么需要 ToT？**
1. **自动化** - 不需要人工设计消融实验
2. **有边界** - 不会无限展开思维树
3. **多维度** - 自动覆盖不同类型的消融
4. **预算受限** - 只选择高价值、低成本的组合
`─────────────────────────────────────────────────`

---

## 设计目标

### 问题背景

论文复现中，用户可能要求：
- "做参数敏感性分析"
- "验证模块贡献"
- "测试数据规模影响"
- "检查随机种子稳定性"
- "对比运行成本"

传统方式需要人工设计实验组合，ToT 可以自动生成候选并选择最优组合。

### 核心价值

| 传统方式 | ToT 方式 |
|----------|----------|
| ❌ 人工设计实验组合 | ✅ 自动生成候选 |
| ❌ 可能遗漏重要维度 | ✅ 五类维度自动覆盖 |
| ❌ 无成本预算控制 | ✅ 预算内选择最优 |
| ❌ 主观判断价值 | ✅ 信息增益评分 |

---

## ToT 设计

### 两个阶段

```
┌─────────────────────────────────────────────────────────────────┐
│                    ToT 消融设计流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   阶段 1：候选扩展                                              │
│   ┌─────────────┐                                              │
│   │  LLM 扩展   │ 最多生成 8 个实验分支                         │
│   └──────┬──────┘                                              │
│          │                                                       │
│          ├─→ 参数消融 (parameter)                               │
│          ├─→ 模块消融 (module)                                  │
│          ├─→ 数据规模消融 (data_scale)                          │
│          ├─→ 随机种子消融 (seed_stability)                      │
│          └─→ 运行成本消融 (runtime_cost)                        │
│                                                                 │
│   阶段 2：分支评估                                              │
│   ┌─────────────┐                                              │
│   │  LLM 评估   │ 为每个候选评估信息增益、相关性、风险          │
│   └──────┬──────┘                                              │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                              │
│   │  确定性选择 │ Go 代码重新打分并选择预算内最优组合           │
│   └──────┬──────┘                                              │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                              │
│   │  输出       │ ablation_plan + selected_configs              │
│   └─────────────┘                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 允许的候选类别

| 类别 | 用途 | 示例 |
|------|------|------|
| `parameter` | 参数或结构敏感性 | heads: 1/2/4/8 |
| `module` | 模块移除或开关 | 关闭 attention scaling |
| `data_scale` | 数据量、序列长度等规模变化 | sequence length: 8/32/64 |
| `seed_stability` | 固定多随机种子重复 | seed: 17/47/123 |
| `runtime_cost` | 延迟、吞吐和内存成本 | batch size: 1/4/16 |

---

## 评分公式

### 多维度评分

```text
score = 0.40 * information_gain
      + 0.30 * relevance
      + 0.20 * reproducibility
      - 0.07 * normalized_time_cost
      - 0.03 * risk
```

### 指标说明

| 指标 | 权重 | 说明 |
|------|------|------|
| **information_gain** | 0.40 | 信息增益，是否能提供新见解 |
| **relevance** | 0.30 | 相关性，与论文主张的关联程度 |
| **reproducibility** | 0.20 | 可复现性，实验是否容易重复 |
| **normalized_time_cost** | -0.07 | 标准化时间成本（越高越差） |
| **risk** | -0.03 | 风险，实验失败的可能性 |

---

## 预算配置

### 默认预算

```text
最大实验数：3
最大 GPU 时间：30 分钟
最大总耗时：60 分钟
搜索深度：2
候选上限：8
```

### 用户覆盖

用户可以在指令中覆盖部分预算：

```text
复现 Transformer，并做最多 2 组轻量消融，总耗时 30 分钟。
```

支持的表达：
- "最多 N 组消融/实验"
- "总耗时 N 分钟"
- "GPU 时间 N 分钟"

---

## Attention Smoke 执行

### 入选类别映射

| 入选类别 | 运行配置 |
|----------|----------|
| `parameter` | heads: 1/2/8，与 4-head baseline 对照 |
| `module` | 关闭 attention scaling、关闭 residual |
| `data_scale` | sequence length: 8/32 |
| `seed_stability` | seed: 17/47 |
| `runtime_cost` | batch size: 1/4 |

### 执行结果记录

每个结果记录：
- 类别、配置
- 延迟、注意力熵、输出 L2
- 参数量
- 相对 baseline 的变化百分比

---

## 结构化产物

### Ablation Plan

```json
{
  "version": "ablation.plan/v1",
  "strategy": "bounded_tree_of_thoughts",
  "budget": {
    "max_experiments": 3,
    "max_gpu_minutes": 30,
    "max_total_minutes": 60
  },
  "candidates": [
    {
      "id": "cand-001",
      "category": "parameter",
      "description": "Test different number of attention heads",
      "config": {
        "heads": [1, 2, 8]
      },
      "scores": {
        "information_gain": 0.9,
        "relevance": 0.8,
        "reproducibility": 0.9,
        "time_cost": 10,
        "risk": 0.1
      },
      "total_score": 0.82,
      "selected": true
    },
    {
      "id": "cand-002",
      "category": "module",
      "description": "Remove attention scaling",
      "config": {
        "disable_scaling": true
      },
      "scores": {
        "information_gain": 0.7,
        "relevance": 0.9,
        "reproducibility": 0.8,
        "time_cost": 5,
        "risk": 0.2
      },
      "total_score": 0.78,
      "selected": true
    }
  ],
  "selected_count": 2,
  "pruned_count": 5
}
```

### Selected Configs

```json
{
  "version": "ablation.configs/v1",
  "experiments": [
    {
      "id": "exp-001",
      "category": "parameter",
      "name": "heads_1",
      "config": {
        "heads": 1
      },
      "baseline_ref": "baseline_heads_4"
    },
    {
      "id": "exp-002",
      "category": "parameter",
      "name": "heads_2",
      "config": {
        "heads": 2
      },
      "baseline_ref": "baseline_heads_4"
    }
  ]
}
```

---

## 代码实现

### ToT Agent

```go
// backend/internal/agent/ablation_tot.go

type AblationToTAgent struct {
    chatModel ChatModel
    budget    AblationBudget
}

type AblationBudget struct {
    MaxExperiments   int
    MaxGPUMinutes   int
    MaxTotalMinutes int
    SearchDepth      int
    CandidateLimit   int
}

func (a *AblationToTAgent) Design(ctx context.Context, parsedPaper ParsedPaper) (*AblationPlan, error) {
    // 阶段 1：候选扩展
    candidates, err := a.expandCandidates(ctx, parsedPaper)
    if err != nil {
        // 模型失败时使用内置候选
        candidates = a.buildinCandidates()
    }

    // 补齐缺失类别
    candidates = a.ensureCategoryCoverage(candidates)

    // 阶段 2：分支评估
    evaluated, err := a.evaluateCandidates(ctx, candidates)
    if err != nil {
        // 模型失败时使用确定性评分
        evaluated = a.deterministicScoring(candidates)
    }

    // 确定性选择
    selected := a.selectWithinBudget(evaluated)

    // 构建计划
    plan := &AblationPlan{
        Version:    "ablation.plan/v1",
        Strategy:   "bounded_tree_of_thoughts",
        Budget:     a.budget,
        Candidates: evaluated,
        Selected:   selected,
    }

    return plan, nil
}

func (a *AblationToTAgent) expandCandidates(ctx context.Context, paper ParsedPaper) ([]AblationCandidate, error) {
    prompt := fmt.Sprintf(`
你是一个实验设计助手。请为以下论文设计消融实验候选。

论文标题：%s
论文方法：%s
论文实验：%s

请按以下格式输出：

1. 候选 ID
2. 类别 (parameter / module / data_scale / seed_stability / runtime_cost)
3. 描述
4. 具体配置（JSON 格式）

最多生成 8 个候选，覆盖 5 个类别。
`, paper.Title, paper.Methods, paper.Experiments)

    response, err := a.chatModel.Generate(ctx, prompt)
    if err != nil {
        return nil, err
    }

    return parseCandidates(response)
}

func (a *AblationToTAgent) buildinCandidates() []AblationCandidate {
    return []AblationCandidate{
        {
            ID:          "builtin-001",
            Category:    "parameter",
            Description: "Test different parameter settings",
            Config:      map[string]interface{}{"param": "value"},
        },
        {
            ID:          "builtin-002",
            Category:    "module",
            Description: "Remove key modules",
            Config:      map[string]interface{}{"module": "disable"},
        },
        // ... 其他内置候选
    }
}

func (a *AblationToTAgent) ensureCategoryCoverage(candidates []AblationCandidate) []AblationCandidate {
    categories := map[string]bool{
        "parameter":       false,
        "module":          false,
        "data_scale":      false,
        "seed_stability":  false,
        "runtime_cost":    false,
    }

    // 标记已有类别
    for _, cand := range candidates {
        categories[cand.Category] = true
    }

    // 补齐缺失类别
    for category, exists := range categories {
        if !exists {
            candidates = append(candidates, a.buildinCandidateForCategory(category))
        }
    }

    return candidates
}

func (a *AblationToTAgent) evaluateCandidates(ctx context.Context, candidates []AblationCandidate) ([]AblationCandidate, error) {
    prompt := fmt.Sprintf(`
你是一个实验评估助手。请为以下消融实验候选打分。

候选列表：
%s

请为每个候选评估：
1. information_gain (0-1)
2. relevance (0-1)
3. reproducibility (0-1)
4. time_cost (分钟)
5. risk (0-1)
`, formatCandidates(candidates))

    response, err := a.chatModel.Generate(ctx, prompt)
    if err != nil {
        return nil, err
    }

    return parseEvaluations(response, candidates)
}

func (a *AblationToTAgent) deterministicScoring(candidates []AblationCandidate) []AblationCandidate {
    for i := range candidates {
        // 简单确定性评分
        candidates[i].Scores = AblationScores{
            InformationGain: 0.5,
            Relevance:       0.5,
            Reproducibility: 0.8,
            TimeCost:        10,
            Risk:            0.2,
        }

        // 计算总分
        candidates[i].TotalScore = a.computeScore(candidates[i].Scores)
    }

    return candidates
}

func (a *AblationToTAgent) computeScore(scores AblationScores) float64 {
    normalizedTime := float64(scores.TimeCost) / float64(a.budget.MaxTotalMinutes)

    return 0.40*scores.InformationGain +
        0.30*scores.Relevance +
        0.20*scores.Reproducibility -
        0.07*normalizedTime -
        0.03*scores.Risk
}

func (a *AblationToTAgent) selectWithinBudget(candidates []AblationCandidate) []AblationCandidate {
    // 按总分排序
    sort.Slice(candidates, func(i, j int) bool {
        return candidates[i].TotalScore > candidates[j].TotalScore
    })

    var selected []AblationCandidate
    totalGPU := 0
    totalTime := 0

    for _, cand := range candidates {
        // 检查预算
        if len(selected) >= a.budget.MaxExperiments {
            break
        }
        if totalGPU+cand.EstimatedGPUMinutes > a.budget.MaxGPUMinutes {
            continue
        }
        if totalTime+cand.EstimatedTimeMinutes > a.budget.MaxTotalMinutes {
            continue
        }

        // 确保类别多样性
        if a.hasCategory(selected, cand.Category) {
            // 降低同类别候选的优先级
            continue
        }

        selected = append(selected, cand)
        totalGPU += cand.EstimatedGPUMinutes
        totalTime += cand.EstimatedTimeMinutes
    }

    return selected
}
```

---

## 实际示例

### 输入

```
论文：Attention Is All You Need
预算：最多 2 组消融，总耗时 30 分钟，GPU 时间 10 分钟
```

### 阶段 1：候选扩展

```
候选 1：parameter - heads: 1/2/8
候选 2：module - 关闭 attention scaling
候选 3：data_scale - sequence length: 8/32
候选 4：seed_stability - seed: 17/47
候选 5：runtime_cost - batch size: 1/4
```

### 阶段 2：评分

| 候选 | 信息增益 | 相关性 | 可复现性 | 时间成本 | 风险 | 总分 |
|------|----------|--------|----------|----------|------|------|
| 1 | 0.9 | 0.8 | 0.9 | 10min | 0.1 | 0.82 |
| 2 | 0.7 | 0.9 | 0.8 | 5min | 0.2 | 0.78 |
| 3 | 0.6 | 0.7 | 0.7 | 15min | 0.3 | 0.61 |
| 4 | 0.5 | 0.6 | 0.9 | 8min | 0.1 | 0.66 |
| 5 | 0.4 | 0.5 | 0.8 | 3min | 0.1 | 0.52 |

### 选择结果

```
选择：
1. 候选 1 (parameter) - 分数 0.82，GPU 10min，总耗时 10min
2. 候选 2 (module) - 分数 0.78，GPU 5min，总耗时 5min

累计：
- 实验数：2/3 ✅
- GPU 时间：15/30min ✅
- 总耗时：15/60min ✅
```

---

## 文件上传集成

### 执行流程

```
上传文件
  -> POST /api/uploads
  -> 返回 upload ID
  -> POST /api/plan { intent, attachments }
  -> Parse Paper
  -> Repo Discovery -----------+
  -> Ablation Design (ToT) ----+-> Prepare Workspace
                                 -> Resolve Dependencies
                                 -> Prepare Runtime
                                 -> Install Dependencies
                                 -> Execute Selected Ablations
                                 -> Compare With Paper Claims
```

### API 示例

**上传文件**：

```bash
curl -X POST http://localhost:8080/api/uploads \
  -H 'X-User-Id: user-001' \
  -F 'file=@paper.pdf'
```

**创建计划**：

```bash
curl -X POST http://localhost:8080/api/plan \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user-001' \
  -d '{
    "intent": "复现 Attention Is All You Need，并做最多 2 组轻量消融，总耗时 30 分钟",
    "attachments": ["upload-id"]
  }'
```

---

## 验证与测试

```go
func TestToTCandidateCoverage(t *testing.T) {
    agent := &AblationToTAgent{
        budget: AblationBudget{
            MaxExperiments: 3,
        },
    }

    // 测试内置候选覆盖所有类别
    candidates := agent.buildinCandidates()
    categories := make(map[string]bool)

    for _, cand := range candidates {
        categories[cand.Category] = true
    }

    assert.True(t, categories["parameter"])
    assert.True(t, categories["module"])
    assert.True(t, categories["data_scale"])
    assert.True(t, categories["seed_stability"])
    assert.True(t, categories["runtime_cost"])
}

func TestToTBudgetSelection(t *testing.T) {
    agent := &AblationToTAgent{
        budget: AblationBudget{
            MaxExperiments:   2,
            MaxGPUMinutes:   10,
            MaxTotalMinutes: 30,
        },
    }

    candidates := []AblationCandidate{
        {ID: "1", Category: "parameter", TotalScore: 0.9, EstimatedGPUMinutes: 10, EstimatedTimeMinutes: 10},
        {ID: "2", Category: "module", TotalScore: 0.8, EstimatedGPUMinutes: 5, EstimatedTimeMinutes: 5},
        {ID: "3", Category: "data_scale", TotalScore: 0.7, EstimatedGPUMinutes: 20, EstimatedTimeMinutes: 20},
    }

    selected := agent.selectWithinBudget(candidates)

    // 只选择预算内的候选
    assert.Len(t, selected, 2)
    assert.Equal(t, "1", selected[0].ID)
    assert.Equal(t, "2", selected[1].ID)
}

func TestToTModelFailure(t *testing.T) {
    agent := &AblationToTAgent{
        chatModel: &mockChatModel{fail: true},
        budget:    AblationBudget{MaxExperiments: 3},
    }

    // 模型失败时使用内置候选
    plan, err := agent.Design(context.Background(), ParsedPaper{})

    assert.NoError(t, err)
    assert.Equal(t, "bounded_tree_of_thoughts", plan.Strategy)
    assert.GreaterOrEqual(t, len(plan.Candidates), 5) // 至少覆盖 5 个类别
}
```

---

## 相关文档

- [上一章：Claim-Evidence证据图](./06-Claim-Evidence证据图.md)
- [下一章：执行示例](./08-执行示例.md)
- [返回目录](./README.md)