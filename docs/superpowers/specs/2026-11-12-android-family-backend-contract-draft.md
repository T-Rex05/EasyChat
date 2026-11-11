# 升级简报:小暖客户端所需后端读取契约增强(草稿,等待人工决策)

日期 2026-11-12,分支 `feature/android-family-client`,基线 WP3/WP4 客户端记录。**本文档只提案,未改动任何后端代码。**

## 停止原因

以下变更涉及受保护路径(公共契约 `contracts.py`/路由响应、`scheduling`、`assistant` 读取路径),按 AGENTS.md 自主会话必须停在草稿 + 升级简报,等待人工决策。客户端当前**不依赖**这些增强即可运行(P0 基本查看版已交付),增强属于 P1「微信来源精确回看」。

## 背景与证据(源码核对,基线 2d4311e)

| # | 缺口 | 客户端受限行为 | 证据 |
| --- | --- | --- | --- |
| 1 | 历史消息响应仅 `{role, content, created_at}` | 无法稳定去重、无法精确定位原文、无法展示附件 | `backend/modules/assistant/routes.py::history_messages` |
| 2 | schedule 无 `origin_session_id`/`origin_message_id` | 「微信里记下的」来源标签不能显示(P0 客户端已避免虚构) | `backend/modules/scheduling/routes.py::_schedule_dict` |
| 3 | inbox item 响应无 `source` 字段(写入有 source,读取不返回) | 无法区分微信收藏与网页收藏 | `backend/modules/inbox/routes.py::item_as_dict`(对照 `commands.py::_inbox_save` 写入 source="wechat") |
| 4 | history 列表无 `has_more`/`next_cursor`,过滤后短页使 offset 分页提前终止 | 长会话列表可能漏页 | `backend/modules/assistant/routes.py::history_list`(对照 `assistant/repository.py::list_sessions`) |

## 提案(全部为只读响应扩展,不改写路径与表结构语义)

1. **history message 读取响应补**:`message_id`(messages 表主键即可)、`run_id`、`attachment_ids`(runs.attachment_ids)、`status`。风险低:纯读取字段追加;客户端已按「整段快照替换」兼容缺失场景,字段出现后自动升级为按 ID 去重。
2. **schedule 读取响应补**:`origin_session_id`、`origin_message_id`(可空)。需要写入链路在工具创建 schedule 时携带来源(涉及 `backend/tools/business/reminder_tools.py` 与 scheduling 写入),建议拆两步:先读取字段(可空),再补写入落列(需追加迁移,单独评审)。
3. **inbox item 响应补**:`source`(行内已有该值,纯透传)。零迁移。
4. **history 列表补**:`has_more`(按 active 过滤后是否还有下一页)。零迁移。

## 已完成(客户端侧,均已验证)

- WP0~WP4 客户端全部交付,真实后端联调通过(见 wp0/wp1/wp2/wp34 四份记录);
- 客户端 DTO 对缺失字段全部容错(ignoreUnknownKeys + 默认值),后端增强上线后无需客户端发版即可获得增强显示;
- 契约测试建议:后端实施时在 `tests/` 增加 history/schedules/inbox 读取响应的字段快照断言。

## 剩余工作(人工批准后)

1. 按 #1/#3/#4 顺序实施(零迁移,半天级);#2 第一步同步;
2. 客户端按新字段接入来源标签与原文定位(预留代码位已就绪:`XnSourceChip`、会话详情跳转);
3. 微信命令(`/存`、语音、图片)的原始事件 ID 落列核查(`channels/commands.py` 写入路径)——若命令直接执行导致来源缺失,需要「命令结果投影」小设计,另行评审。

## 续作步骤建议

批准后从一个独立小 PR 开始(仅 #3 inbox source 透传 + 测试),逐项验证客户端显示,再逐项推进 #4/#1/#2。
