# 论文解析与 Rubric 冻结

> [返回目录](./README.md)

---

## 什么是 Rubric 冻结

Rubric（评分细则）冻结是指在论文复现开始前，先将论文的主张、判定准则、验收标准固定下来，形成一个不可变的评分框架。

**为什么需要冻结？**

| 问题 | 不冻结的后果 | 冻结的好处 |
|------|-------------|-----------|
| **标准漂移** | 根据实验结果修改验收标准 | 标准客观、可审计 |
| **选择性验收** | 只验收成功的指标 | 全面覆盖、无遗漏 |
| **主观判断** | "看起来差不多就行" | 明确准则、可量化 |

`✶ Insight ─────────────────────────────────────`
**Rubric 冻结的核心价值：**
1. **客观性** - 验收标准在看到结果前就已确定
2. **可审计** - 每个主张都有独立的判定准则
3. **可追溯** - 准则与证据一一绑定
`─────────────────────────────────────────────────`

---

## Librarian Agent 职责

Librarian Agent 负责论文解析、主张提取和 Rubric 冻结。

### 核心任务

```
┌─────────────────────────────────────────────────────────────────┐
│                    Librarian Agent 工作流                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   输入：论文 PDF / URL / 上传文件                               │
│                                                                 │
│   步骤 1：解析论文结构                                          │
│     - 提取标题、摘要、方法、实验、结论                          │
│     - 识别关键表格、图表                                        │
│                                                                 │
│   步骤 2：提取论文主张                                          │
│     - 量化指标主张（准确率、F1、延迟等）                        │
│     - 方法论主张（创新点、对比优势等）                          │
│     - 消融主张（模块贡献、参数敏感性等）                        │
│                                                                 │
│   步骤 3：生成分层 Rubric                                       │
│     - 每个主张拆解为多个独立准则                                │
│     - 每个准则定义所需证据类型                                  │
│     - 规范化 ID、字段、容差                                     │
│                                                                 │
│   输出：Frozen Claim Rubric                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 论文解析

### 解析流程

```mermaid
flowchart LR
    P["论文输入"] --> E["提取结构"]
    E --> S["分段摘要"]
    S --> C["识别主张"]
    C --> R["构建 Rubric"]
    R --> F["冻结签名"]
```

### 结构化输出

```json
{
  "version": "paper.parsed/v1",
  "title": "Attention Is All You Need",
  "abstract": "...",
  "sections": [
    {
      "id": "section-001",
      "title": "Introduction",
      "summary": "...",
      "claims": ["claim-001", "claim-002"]
    }
  ],
  "tables": [
    {
      "id": "table-001",
      "caption": "Table 1: BLEU scores on WMT 2014",
      "metrics": ["BLEU", "training time"]
    }
  ],
  "figures": [
    {
      "id": "figure-001",
      "caption": "Figure 1: The Transformer model architecture"
    }
  ]
}
```

### 主张识别

**量化指标主张**：
- 准确率提升 X%
- 训练时间减少 Y 倍
- F1 分数达到 Z

**方法论主张**：
- 引入了新的注意力机制
- 提出了新的架构设计
- 改进了训练策略

**消融主张**：
- 模块 A 贡献了 X% 的提升
- 参数 B 的敏感性分析
- 随机种子稳定性验证

---

## Claim Rubric 结构

### 数据契约

```json
{
  "version": "claim.rubric/v1",
  "paper_title": "Attention Is All You Need",
  "source_artifact": "parsed_paper",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "created_at": "2026-07-17T00:00:00Z",
  "claims": [
    {
      "id": "claim-001",
      "title": "Translation Quality on WMT 2014",
      "statement": "The Transformer achieves 28.4 BLEU on WMT 2014 English-to-German translation.",
      "source_locator": "Table 1, Row 'Transformer (big)'",
      "claim_type": "quantitative",
      "importance": 0.9,
      "criteria": [
        {
          "id": "claim-001.criterion-01",
          "description": "Evaluate BLEU score on WMT 2014 En-De test set using the big model configuration.",
          "metric_name": "BLEU",
          "expected_value": 28.4,
          "tolerance": 1.0,
          "required_evidence": ["run", "metrics", "benchmark"],
          "verification_method": "automatic"
        },
        {
          "id": "claim-001.criterion-02",
          "description": "Verify the model configuration matches the 'big' variant in the paper.",
          "metric_name": "model_config",
          "required_evidence": ["code", "config"],
          "verification_method": "manual"
        }
      ]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| **version** | string | 契约版本，固定为 `claim.rubric/v1` |
| **paper_title** | string | 论文标题 |
| **sha256** | string | 整个 Rubric 的哈希值 |
| **claims[]** | array | 论文主张列表 |
| **claims[].id** | string | 主张 ID，由后端生成 |
| **claims[].title** | string | 主张标题 |
| **claims[].statement** | string | 主张原文陈述 |
| **claims[].source_locator** | string | 论文中的位置（如表格、章节） |
| **claims[].claim_type** | string | 主张类型：`quantitative` / `qualitative` |
| **claims[].importance** | float | 重要性权重（0-1） |
| **claims[].criteria[]** | array | 判定准则列表 |
| **criteria[].id** | string | 准则 ID |
| **criteria[].metric_name** | string | 指标名称 |
| **criteria[].expected_value** | number | 期望值（可选） |
| **criteria[].tolerance** | number | 容差范围（可选） |
| **criteria[].required_evidence** | array | 所需证据类型 |
| **criteria[].verification_method** | string | 验证方法：`automatic` / `manual` |

---

## 冻结机制

### 为什么需要后端规范化？

**问题**：模型可能生成不规范的结构

```json
// ❌ 模型生成的原始输出
{
  "claims": [
    {
      "title": "BLEU Score",
      "metric": 28.4
    }
  ]
}
```

**解决方案**：Go 后端规范化

```json
// ✅ 后端规范化后的输出
{
  "version": "claim.rubric/v1",
  "sha256": "...",
  "claims": [
    {
      "id": "claim-001",           // 后端生成
      "title": "BLEU Score",
      "claim_type": "quantitative", // 后端推断
      "criteria": [                // 后端拆解
        {
          "id": "claim-001.criterion-01",
          "metric_name": "BLEU",
          "expected_value": 28.4
        }
      ]
    }
  ]
}
```

### 哈希签名

**目的**：防止 Rubric 被篡改

**流程**：
1. 后端规范化字段和 ID
2. 计算整个 Rubric 的 SHA-256
3. 保存哈希值到 `sha256` 字段
4. 后续引用时验证哈希

**验证逻辑**：

```go
func ValidateRubric(rubric ClaimRubric) error {
    // 1. 检查版本
    if rubric.Version != "claim.rubric/v1" {
        return errors.New("invalid version")
    }

    // 2. 验证哈希
    expectedHash := computeSHA256(rubric)
    if rubric.SHA256 != expectedHash {
        return errors.New("rubric tampered")
    }

    // 3. 验证 ID 格式
    for _, claim := range rubric.Claims {
        if !isValidClaimID(claim.ID) {
            return errors.New("invalid claim ID")
        }
        for _, criterion := range claim.Criteria {
            if !isValidCriterionID(criterion.ID) {
                return errors.New("invalid criterion ID")
            }
        }
    }

    return nil
}
```

---

## 代码实现

### 节点定义

```go
// backend/internal/planner/planner.go

func (p *Planner) buildPaperReproductionPlan(ctx context.Context, intent IntentContext) (*PlanGraph, error) {
    nodes := make(map[string]TaskNode)

    // 1. 论文解析节点
    nodes["paper_parse"] = TaskNode{
        ID:                "paper_parse",
        Type:              "paper_parse",
        AssignedTo:        "librarian",
        OutputArtifacts:   []string{"parsed_paper"},
        Status:            "pending",
    }

    // 2. Claim Rubric 提取节点
    nodes["claim_rubric_extract"] = TaskNode{
        ID:                "claim_rubric_extract",
        Type:              "claim_rubric_extract",
        AssignedTo:        "librarian",
        Dependencies:      []string{"paper_parse"},
        RequiredArtifacts: []string{"parsed_paper"},
        OutputArtifacts:   []string{"claim_rubric", "claim_rubric_report"},
        Status:            "pending",
    }

    // 3. 仓库发现节点（并行）
    nodes["repo_discovery"] = TaskNode{
        ID:                "repo_discovery",
        Type:              "repo_discovery",
        AssignedTo:        "coder",
        Dependencies:      []string{"paper_parse"},
        RequiredArtifacts: []string{"parsed_paper"},
        OutputArtifacts:   []string{"repo_url"},
        Status:            "pending",
    }

    // ... 其他节点

    return &PlanGraph{
        ID:     generatePlanID(),
        Nodes:  nodes,
        Status: "pending",
    }, nil
}
```

### Agent 实现

```go
// backend/internal/agent/librarian.go

func (a *LibrarianAgent) ExtractClaimRubric(ctx context.Context, task Task) (*TaskResult, error) {
    // 1. 获取解析后的论文
    parsedPaper, ok := task.Inputs["parsed_paper"].(ParsedPaper)
    if !ok {
        return nil, errors.New("missing parsed_paper")
    }

    // 2. 调用 LLM 提取主张
    prompt := fmt.Sprintf(`
你是一篇学术论文的研究助手。请从以下论文中提取可验证的主张和判定准则。

论文标题：%s
论文摘要：%s
方法部分：%s
实验结果：%s

请按以下格式输出：

1. 主张 ID
2. 主张标题
3. 主张陈述
4. 论文位置（表格/章节）
5. 主张类型（quantitative/qualitative）
6. 判定准则列表（每个准则包含描述、指标名、期望值、容差、所需证据）
`, parsedPaper.Title, parsedPaper.Abstract, parsedPaper.Methods, parsedPaper.Experiments)

    llmResponse, err := a.chatModel.Generate(ctx, prompt)
    if err != nil {
        return nil, err
    }

    // 3. 解析 LLM 输出
    rawClaims, err := parseClaims(llmResponse)
    if err != nil {
        return nil, err
    }

    // 4. 后端规范化
    rubric := a.normalizeRubric(rawClaims)

    // 5. 计算哈希
    rubric.SHA256 = computeSHA256(rubric)

    // 6. 返回结果
    return &TaskResult{
        Status: "completed",
        Artifacts: map[string]interface{}{
            "claim_rubric":        rubric,
            "claim_rubric_report": generateReport(rubric),
        },
    }, nil
}

func (a *LibrarianAgent) normalizeRubric(rawClaims []RawClaim) ClaimRubric {
    rubric := ClaimRubric{
        Version:   "claim.rubric/v1",
        PaperTitle: a.paperTitle,
        CreatedAt: time.Now(),
        Claims:    make([]Claim, 0, len(rawClaims)),
    }

    for i, raw := range rawClaims {
        claim := Claim{
            ID:             fmt.Sprintf("claim-%03d", i+1),
            Title:          raw.Title,
            Statement:      raw.Statement,
            SourceLocator:  raw.SourceLocator,
            ClaimType:      inferClaimType(raw),
            Importance:     raw.Importance,
            Criteria:       make([]Criterion, 0, len(raw.Criteria)),
        }

        for j, rawCrit := range raw.Criteria {
            criterion := Criterion{
                ID:                fmt.Sprintf("claim-%03d.criterion-%02d", i+1, j+1),
                Description:       rawCrit.Description,
                MetricName:        rawCrit.MetricName,
                ExpectedValue:     rawCrit.ExpectedValue,
                Tolerance:         rawCrit.Tolerance,
                RequiredEvidence:  rawCrit.RequiredEvidence,
                VerificationMethod: inferVerificationMethod(rawCrit),
            }
            claim.Criteria = append(claim.Criteria, criterion)
        }

        rubric.Claims = append(rubric.Claims, claim)
    }

    return rubric
}
```

---

## 实际示例

### 输入：论文

```
论文标题：Attention Is All You Need

摘要：
The dominant sequence transduction models are based on complex recurrent or
convolutional neural networks... We propose a new simple network architecture,
the Transformer, based solely on attention mechanisms...

Table 1: BLEU scores on WMT 2014

Model                    BLEU    Training Time
Transformer (base)       27.3    12 hours
Transformer (big)        28.4    3.5 days
```

### 输出：Claim Rubric

```json
{
  "version": "claim.rubric/v1",
  "paper_title": "Attention Is All You Need",
  "sha256": "...",
  "claims": [
    {
      "id": "claim-001",
      "title": "Translation Quality (Big Model)",
      "statement": "The Transformer (big) achieves 28.4 BLEU on WMT 2014 En-De.",
      "source_locator": "Table 1, Row 'Transformer (big)'",
      "claim_type": "quantitative",
      "importance": 0.9,
      "criteria": [
        {
          "id": "claim-001.criterion-01",
          "description": "Evaluate BLEU score on WMT 2014 En-De test set using the big model configuration.",
          "metric_name": "BLEU",
          "expected_value": 28.4,
          "tolerance": 1.0,
          "required_evidence": ["run", "metrics", "benchmark"],
          "verification_method": "automatic"
        }
      ]
    },
    {
      "id": "claim-002",
      "title": "Training Efficiency",
      "statement": "The Transformer (base) trains in 12 hours.",
      "source_locator": "Table 1, Row 'Transformer (base)'",
      "claim_type": "quantitative",
      "importance": 0.7,
      "criteria": [
        {
          "id": "claim-002.criterion-01",
          "description": "Measure training time for the base model.",
          "metric_name": "training_time",
          "expected_value": "12 hours",
          "tolerance": "2 hours",
          "required_evidence": ["run", "logs"],
          "verification_method": "automatic"
        }
      ]
    }
  ]
}
```

---

## 验证与测试

### 单元测试

```go
func TestClaimRubricNormalization(t *testing.T) {
    rawClaims := []RawClaim{
        {
            Title:     "BLEU Score",
            Statement: "28.4 BLEU",
        },
    }

    agent := &LibrarianAgent{paperTitle: "Test Paper"}
    rubric := agent.normalizeRubric(rawClaims)

    // 验证 ID 格式
    assert.Equal(t, "claim-001", rubric.Claims[0].ID)

    // 验证版本
    assert.Equal(t, "claim.rubric/v1", rubric.Version)

    // 验证哈希
    expectedHash := computeSHA256(rubric)
    rubric.SHA256 = expectedHash
    assert.NoError(t, ValidateRubric(rubric))
}

func TestRubricTamperDetection(t *testing.T) {
    rubric := createValidRubric()

    // 篡改主张
    rubric.Claims[0].Statement = "Modified statement"

    // 验证失败
    assert.Error(t, ValidateRubric(rubric))
}
```

---

## 相关文档

- [上一章：概述与架构](./01-概述与架构.md)
- [下一章：仓库发现与环境准备](./03-仓库发现与环境准备.md)
- [返回目录](./README.md)