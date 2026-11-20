# 五包整改独立验收

日期为2026-11-17，范围为`579db03...03b41ee`及当前工作区验证。结论为整改已有实质进展，整轮验收仍需返修下列缺陷。（代码核查、隔离复现）

## Standards　规范与实现正确性

### S1　P2　网络读流异常未进入恢复流程

位置为`agent_frontend/src/api/chat.ts:226–230`。`reader.read()`抛异常时直接onError并return，只有正常EOF进入recoverFromDrop。通过转译实际chat.ts，ReadableStream先输出partial，再controller.error(TypeError('network terminated'))，结果请求次数1、保留partial、显示连接中断，没有重连。（内存harness实测）

修复时让可恢复读流异常进入现有有界恢复，保留手动停止、代次失效和终态守卫。补controller.error、读取部分内容后断网、游标恢复、重试耗尽与不重复执行的行为测试。（返修要求）

### S2　P2　总笔数格式兼容回退

位置为`backend/modules/ledger/normalization.py:298`。新正则不接受冒号并强制末尾“笔”，`总笔数：99笔`、`交易笔数: 99`等原支持输入变为None。真实CSV入口四条明细配“总笔数：99笔”，control.checked=false、ok=true，普通提交成功四条，数量差异守卫被跳过。（临时账本完整导入实测）

保留明确总笔数标签后的合法分隔符和可选单位，限制“共”的语义以排除金额。增加总数不符阻止普通提交的完整入口回归。（返修要求）

### S3　P2　同一摘要行多个分类会串金额

位置为`backend/modules/ledger/normalization.py:329–334`。对`支出：20.00元 收入：1笔 10.00元`，解析expense_minor为1000，应为2000。当前函数搜索标签后全部余文中的笔数，再丢弃其前文本，读入下一分类金额。（实际parse_control_totals实测）

先限定当前分类片段边界，再分离笔数和金额，补同一行多分类、不同顺序和金额直接出现的回归。（返修要求）

新增模块状态接口存在认证检查，静态返回状态与固定原因，没有找到凭据值泄露证据。此次diff未修改WAL/迁移，也未新增事务内外呼。（源码核查）

## Spec　需求实现与验收缺口

### R1　P1　用量详情没有补动作权限检查

位置为`backend/modules/usage/api.py:142–148`，对应新测试`tests/access/test_action_revocation.py:197–198`。get_call仍只检查owner。临时SQLite建立真实本人调用并撤销trace.view/manage，HTTP列表403、日报403，按真实ID读详情200。（ASGITransport实测）

新测试用不存在的call_nope，并允许NotFoundError，无法证明已存在记录被撤权拒绝。给详情加相同动作闸，改为真实记录先有权200、撤权403、授回200，并补他人记录边界。（返修要求）

### R2　P2　聊天业务403被误报为登录过期

位置为`agent_frontend/src/api/chat.ts:156–158`。真实聊天路由对撤chat.use的有效用户返回403及message“缺少权限: chat.use”，同token仍可认证。实际chat.ts转译harness处理该响应后logoutCalls=1、清token、跳/login、提示登录过期。（真实HTTP与前端harness实测）

认证失败与动作禁止分别处理。403保留有效身份并显示服务端原因，同时补GET/POST及恢复探测的状态一致性测试。（返修要求）

WP-A的原385/33/10笔数误作金额、WP-D技能固定/归档与提醒动作闸、WP-E重复下拉去除等已有对应实现。上述S2/S3、R1/R2使WP-A/C/D仍存在待修复项。（源码与复现）

## UI与交付证据

- 本地evidence目录存在7张PNG。已打开after-role-edit与after-upgrade-panel，两张均出现横向/纵向重复画面和裁切，难以据此判断完整弹窗与窄屏布局。需要重录完整视口Before/After，并附视口、账号类型、主题及滚动位置。该现象是证据质量问题，尚不能据此断言页面实现同样平铺。（文件与图像核查）
- 图片受gitignore排除，当前提交未包含这些PNG。若需从双远程复现验收，使用明确授权的证据附件或仓库允许的提交方式提供。（git check-ignore及提交树核查）
- RoleListPanel空列表仍为未定位观察项。组件本轮未改不能证明问题来源，也不能替代角色列表到编辑保存完整路径的验收。（报告与源码核查）
- 本地提交范围实际6个提交，其中5个实现提交和1个文档提交，与消息“七个提交”需校对；两个remote-tracking分支均包含HEAD，未在本轮重新查询远端服务器。（git实测与验证范围）
- 交付报告的权限矩阵把evolution.manage混入active组，其属于deprecated，应修正文档并逐项挂接真实测试节点；现有描述不能单独证明22项权限所有通道和撤权组合均覆盖。（contracts.py与报告核查）
- 模型密钥及激活模型变更属于报告记录的运维变更。本轮未调用真实模型、发送微信或更换凭据，真实对话、微信链路及旧密文可用性仍需按报告边界验收。（范围）

## 独立运行记录

- `npm test`为65 passed，退出码0。（本轮实测）
- `npm run type-check`退出码0，`npm run build`退出码0，构建有chunk体积警告。（本轮实测）
- 全量后端命令`python -m pytest tests -q -m "not integration and not resources"`为1247 passed、2 skipped、3 deselected，耗时378.15秒，退出码0。（本轮实测）

本轮只新增本验收文档，现有产品源码与主题工作未修改。返修建议依仓库protected paths要求交付，人工验收前保留具体失败证据与回归结果。（范围与仓库要求）
