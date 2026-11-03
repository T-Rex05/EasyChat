# 模型配置"测试连接"端点的多轮迭代模式

## 场景

用户需要 CRUD 管理多条 LLM 模型配置（Base URL / API Key / 模型名）并在保存前验证可达性。测试端点调 `urllib.request` 向远程 API 发探测请求。

## 实测的四轮迭代

### 第 1 轮：只查 `/models` → DeepSeek/Anthropic 端点返回 404

```python
# ❌ 仅此一条路径
test_url = f"{base}/models"
```

报错：`404 NOT FOUND`，但 DeepSeek Anthropic 兼容端点根本没有 `/models` 接口。

### 第 2 轮：加 `/v1/models` 做双路径试探 → 仍然 404

```python
# 仍然不够
for test_url in (f"{base}/v1/models", f"{base}/models"):
```

`https://api.deepseek.com/anthropic/v1/models` 和 `/models` 全都 404。

### 第 3 轮：三阶段探测 + SSL 绕过 → 还是 404

加了 `ssl._create_unverified_context()` 解决 Windows SSL 问题，加根路径连通性检查，但 DeepSeek Anthropic 端点**所有 GET 请求都返回 404**，因为它只接受 POST。

### 第 4 轮（最终）：Anthropic 端点专属 POST 分支

`https://api.deepseek.com/anthropic` 这样的 Anthropic 兼容端点**根本不接受 GET 请求**。必须对 Anthropic 端点专门处理：

```python
is_anthropic = "/anthropic" in base or base.endswith("/messages")

if is_anthropic:
    # 发一个最小的 POST 验证连通性
    body = json.dumps({
        "model": model_name,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }).encode()
    headers["anthropic-version"] = "2023-06-01"
    # Bearer + x-api-key 双保险（不同兼容实现用不同 header）
    if api_key and "x-api-key" not in headers:
        headers["x-api-key"] = api_key

    req = Request(test_url, data=body, headers=headers, method="POST")
    resp = urlopen(req, context=ctx, timeout=15)
    # HTTP 200 → 连通成功
    # HTTP 401/403 → 服务器通了但 Key 被拒（区分连通 vs 鉴权）
    # 其他 HTTP 状态码 → 也算连通，只是端点行为特殊
    # URLError（DNS/网络不通）→ 明确说「无法连接」
```

## 关键原则

1. **分层探测**：先试"列模型"（最理想），失败再降级到"只要能连通"。不要一个 404 就判死刑。
2. **区分「连通」与「鉴权」**：401/403 说明网络是通的但 Key 错，和"网络不通"是完全不同的两类问题。错误消息必须说清楚。
3. **Windows SSL 坑**：`urllib.request` 在 Windows 下调用 HTTPS 经常报 SSL 证书验证错（系统 CA 不全/企业代理），加上 `ssl._create_unverified_context()` 旁路。
4. **API 风格必须分支**：OpenAI 兼容用 GET `/v1/models`，Anthropic 兼容用 POST 根路径 + `anthropic-version`/`x-api-key` header。根据 URL 特征（含 `/anthropic` 或 `/messages`）分叉。
5. **返回丰富错误信息**：失败时返回 `tested_urls` 列表和具体错误描述，让用户在浏览器里直接看到。用 `last_error_detail` 保留最后一次尝试的原始错误。
6. **HTTP vs URLError 含义完全不同**：`HTTPError(404)` = 服务器有响应但该路径不存在（网络是通的）；`URLError` = DNS 解析失败或 TCP 连接被拒（网络不通）。前者可以继续试下一条，后者基本是终点。
