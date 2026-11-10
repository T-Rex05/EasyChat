# P1 GitHub 仓库规则 owner 操作清单(权限不足,移交人类)

**现状(本轮 gh-agent 实测,api.github.com)**：`GET branches/main` → `protected:false`;`GET rules/branches/main` → `[]`。与 REVIEW-2026-11-10 记录一致,今天重新证实：**main 无任何合并门禁,CI 此前从未入库(本轮已入库,见 3de6a9c)——push 即触发**。

**为何移交**：rulesets/CODEOWNERS 配置需仓库 admin 权限;当前凭据只有 add-05(write)。**必须用 T-Rex05 本人登录操作**——按仓库约束,agent 不进入 bypass,也不应持有 admin。

## 操作一:main ruleset(T-Rex05 本人凭据;网页 Settings → Rules → Rulesets 亦可)

保存下面 JSON 为 `ruleset.json`(字段按 GitHub 官方 rulesets schema;规则来源见执行计划 §2 引用的官方文档)：

```json
{
  "name": "protect-main",
  "target": "branch",
  "source_type": "Repository",
  "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": ["refs/heads/main"] } },
  "rules": [
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true,
        "require_last_push_approval": true,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": ["squash"] } },
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "update",
      "parameters": { "updated_branch": false,
        "require_thread_resolution": true,
        "allowed_merge_methods": ["squash"] } }
  ],
  "bypass_actors": []
}
```

执行:`gh api repos/T-Rex05/EasyChat/rulesets -X POST --input ruleset.json`(`require_signatures` 暂未纳入,可后续按需加)。

## 操作二:required status checks

1. 先等一次真实 push(本轮已推 `feature/permission-remediation` 含 .github/workflows/ci.yml)在 Actions 页确认三个 job 全绿,记录其**实际 job 名**(`backend-test`/`lint`/`frontend-build`)。
2. 在上面 PR 规则 parameters 中加 `"required_status_checks":[{"context":"backend-test"},{"context":"lint"},{"context":"frontend-build"}]`(通过 `PUT /repos/{repo}/rulesets/{id}` 更新)。
3. 验证场景(计划 A2 验收):开测试 PR ①无审批 → 合并禁用;②CI 失败 → 合并禁用;③审批后 force-push 新 commit → 旧审批失效。全部截图/`gh pr view --json mergeStateStatus` 记录。

## 操作三:CODEOWNERS(新增 `.github/CODEOWNERS`)

```
# 受保护路径——对应 AGENTS.md 风险清单
backend/modules/access/       @T-Rex05
backend/platform/             @T-Rex05
backend/modules/delivery/     @T-Rex05
backend/modules/scheduling/   @T-Rex05
backend/runtime/              @T-Rex05
backend/modules/superagent/   @T-Rex05
docker/                       @T-Rex05
.github/                      @T-Rex05
```

并启用规则里的 `require_code_owner_review`(已在操作一 JSON 中)。**拥有者本人是唯一 owner**:agent 账号 add-05 故意不进 bypass、不进 CODEOWNERS——它的 PR 必须人工评审后合并,这正是分层设计的人工层。

## 操作四(可选但建议):仓库可见性

T-Rex05/EasyChat 当前 public。若源码不便公开:Settings → General → Danger Zone → Change visibility → Private(镜像与 agent 工作不受影响)。

## agent 侧待办(权限就绪后我方可续作)

- ruleset 创建后:gh-agent 读回核对(`GET /rulesets` 输出与本文档比对)。
- 破坏性推送试验(禁非快进验证)需在一次性测试仓库做,计划 A2 已注明。
