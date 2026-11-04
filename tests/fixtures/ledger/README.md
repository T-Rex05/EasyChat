# 合成账单夹具（F0）

本目录只存放**人工合成**的账单/截图/识别结果说明，不含任何真实用户账单、支付凭证或运行数据。

- 生成器：`tests/support/ledger_fixtures.py`（纯标准库写 XLSX/CSV/PNG；不读取桌面文件）。
- 商户、订单号、金额全部虚构；订单号刻意使用超长字符串验证“ID 不能经 float/科学计数法截断”。
- 需要在测试运行时临时生成文件，不把生成的二进制提交进 Git：
  - `write_wechat_xlsx()` — 说明行 + 移动表头 + 多 sheet 变体
  - `write_wechat_csv()` — BOM/GB18030、逗号/制表符、引号内换行
  - `write_png()` — 纯 zlib 生成的支付截图占位图（带像素尺寸参数）
  - `fake_vision_payload()` — 假视觉模型的候选字段/置信度/原文

覆盖场景（见各测试文件）：

| 场景 | 生成器 |
|---|---|
| 原消费 100 / 部分退款 30 / 转账 50 / 充值 200 | `standard_scenario()` |
| 全额退款 100（不能用 -100 计算消费净额） | `full_refund_scenario()` |
| 原单与退款共用同一交易单号 | `same_id_refund_scenario()` |
| 重叠区间导出（同一交易出现在两个文件） | `overlap_export_scenario()` |
| 状态更新（早导出“支付成功” → 晚导出“已全额退款”） | `status_update_scenario()` |
| 控制总额不符（笔数/金额被篡改） | `mismatched_control_totals()` |
| 缺金额/方向/日期的识别候选 | `fake_vision_payload()` |

禁止在此目录放入真实 `.xlsx`/`.csv`/`.png` 文件；如确实需要固定样本，必须确认内容完全虚构并在 PR 说明来源。
