# WP-A 记录:聊天连接归属与历史竞争(2026-11-13)

## 复现(红证据)

对 HEAD 原始 useChat.ts 跑与修复后完全相同的断言集（`evidence/wp-a-red-proof.mjs`，读 git show 导出的原文件）：

```
✖ A 完成只清理自己,不误关 B 的连接(B 流继续)
  AssertionError: A 完成只关自己的连接            ← A 完成时 streams[0] 未关、B 被误关
✖ 晚到历史不覆盖流式内容与新消息(缺陷②)
  AssertionError: 晚到历史不得覆盖流式内存数据     ← 挂起历史返回后覆盖流式中间态
✔ 同一会话流式期间禁止重复发送(不同会话互不影响)  ← 原行为正确,无需变更
✔ 停止只作用于当前浏览会话                        ← 原语义正确
```

源码定位（与方案 §1 证据一致）：实例级单例槽 `currentEventSource/currentCloseFn` 被后发会话覆盖，先完成方 cleanup 关掉的是后发会话连接并按**当时浏览会话**清状态；`loadChatHistory` 完成后 `setMessages(history)` **不带 chatId**（写进当时 currentChatId）且无晚到校验。

## 最小修复

1. **连接归属**：单例槽 → `activeStreams: Map<chatId, {eventSource, closeFn}>`（4 个写入点：GET/POST 发送、GET/POST 重连）；
2. **清理归属**：`cleanupStream(chatId)` 取代全局 `cleanup()`——关闭并删除**发起会话**的槽与流式/待恢复状态；`onComplete/onError` 用回调闭包捕获的 `cid`（6 处调用点全部迁移）；旧 `cleanup` 从返回对象移除（grep 证实无外部消费方，教训：导出面即 API）；
3. **历史归属与晚到防护**：`loadChatHistory` 完成后**按请求 chatId** 校验——目标会话出现流式/新消息则丢弃晚到历史；写入改显式 `setMessages(historyMessages, chatId)`；reconnectStream 同样显式归属；
4. **stopStream** 按当前浏览会话的槽操作（停止语义保留：用户点停=停正在看的流，后台其他流不动）。

## 回归矩阵（已覆盖子集）

`tests/use-chat-stream.test.mjs` 4 项全绿（进 npm test：27 passed）：A完成/B不误关+B结果落对会话+状态不被清、晚到历史不覆盖流式、同会话流式防重复/跨会话并行、停止只作用当前浏览会话。
方案矩阵中**断流恢复/刷新重连/GET与POST附件路径**：机制同源（activeStreams 键一致），重连 GET/POST 写点已迁移并静态复核；真实 SSE 断流恢复需活模型长任务，列浏览器待验证（见未验证项）。

## 浏览器操作证据

真实操作双会话长文重叠（《秋》→《春》，BEFORE 部分注入构建下 B 正常完成 pageLen=3259——注意：注入仅回退清理层，连接覆盖缺陷由 red/green 脚本证严格性，视觉证据不能证明旧缺陷故不采用误导截图；修复后终态历史列表两条 17:02 新会话并存=AFTER 截图在 artifacts）。

## 评审

自评修复：cleanupStream 补 `if (!chatId) return` 防护（空 id 早期返回，避免误清 ''会话键）；catch 清理异常吞并注释原因；`closeFn?.()` 对 GET 路径会重复 close EventSource——EventSource.close 幂等且 POST 才有 close 语义，双保险无害（评审记录在案）。

## 未验证项

1. 真实网络断流→自动重连（reconnectStream 路径在活模型长任务下未演练）；续作条件：一次人为断网试验或真实长任务；
2. 附件 POST 路径的双会话并行（同机制未单独实操）；
3. A 报错/B 继续、A历史晚到/B当前两个矩阵子项由同构断言覆盖，真实 SSE error 事件注入未做。

## 回滚

revert 本提交；useChat.ts 纯前端、无数据迁移。
