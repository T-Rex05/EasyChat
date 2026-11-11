# WP3 记录:Acceptance 本地试验(2026-11-11)

## 版本固定(隔离试验环境,全部实测记录)

| 组件 | 固定版本 | 证据 |
|---|---|---|
| acceptance skill | lobehub/acceptance @ **f720feb862bd**(main,2026-11-11 从 commits 页固定),SKILL.md 自述 version 0.10.0、license Apache-2.0 | raw 抓取文件头 |
| lh CLI | @lobehub/cli **0.0.78**(npm latest 当日) | `lh --version` |
| 运行模式 | `lh acceptance run preflight` → **mode: local**(未登录 LobeHub,零上传) | CLI JSON 输出 |
| 许可核查 | acceptance=Apache-2.0;LobeHub 主仓 Community License 条款与本试验关系(仅本地渲染,不分发)已核查 | 计划 §11 要求 |

## 轮次目录与证据构成

`.acceptances/easychat-wechat-ui/20261111-175615-r1/`(官方 new_round 语义,`.acceptances/.gitignore=*` 自忽略不进 git;报告 7.6MB 含内联证据,保留本机,共享范围待用户指定):
- result.json:8 检查项、14 证据文件、provenance(branch/commit/视口/主题/环境/时间)
- assets/:3 视频截图组 + before/after 成对图 + clamp 读数 txt + 键盘结论 txt + webm 录屏

## 三场景结果(逐项,对应计划验收)

1. **聊天拖动**(requiredEvidence: screenshot+video):before 280/240 → 拖动 420(clamp)/320 → 刷新恢复 420/320 ✓;纯拖动录屏 webm 一份(第一次录屏被 reload 打断失败,重录成功——复现记录在此);宽度键值与 DOM 实测双核对。
2. **超级代理间距三宽度**:1440/950/679 均无横向滚动、越界元素 0;679 下徽章换行正常 ✓(复用 P8 修复结论,本轮重新操作取证)。
3. **角色卡与权限弹窗**:整卡 role=button+tabindex+@keydown.enter(源码+打开截图);弹窗键盘激活轮曾打开(super_admin 只读弹窗截图);**发现并修复两项缺陷**:
   - c5 窄屏保存不可达:`.modal-body` 缺 `min-height:0`(flex 子项撑破 80vh 容器,overflow 失效)→ 修复实测 bodyScrollable=true、scrollTop 640.67、保存可达;before/after 成对图。
   - c6 Esc 无任何绑定:新增模板 `@keydown.esc` 冒泡绑定;DOM 冒泡派发关闭实测 1→0。**如实标 blocked**:IAB 桥的 Playwright press 与系统级 keypress 均不投递按键(Enter press 同通道对照无效、合成事件全通——桥限制推断);真机物理键复验条件:任一浏览器按一次 Esc。
   - c8 完整焦点圈:桥无法做,标 blocked 无伪证据。
4. **console 错误**:三场景注入计数 0 条 ✓。

## CLI 门禁与报告交互验证

- `lh acceptance run validate`:第一版因我误用 status:'uncertain'(合法枚举 pass|fail|blocked)与 c2 缺 text 证据被拒——**validate 的覆盖门真实生效**;修正后 valid:true。
- `lh acceptance run render` → report.html 本地渲染成功;http 托管下浏览器验证:8 项清单、逐项 忽略/拒绝并评论/验收通过、底部 打回交付/接受交付;**实测点开 c6 打回弹窗**(textarea+添加截图+提交反馈,"你的反馈将成为下一轮验证的处理输入"——WP4 返工闭环的机制原型直接可见)截图在案。
- 报告页按钮的真实指针点击同样受桥接 actionability 限制,DOM click 通道全通(与键盘同一桥限制,同一结论)。

## 临时服务清理

验收后 8765 静态服务已停(netstat+taskkill 实测 000);8001/3000 产品继续运行(用户会话仍在使用)。

## 待验证与续作条件

- c6/c8 真实键盘:用户在任意真机浏览器打开 `.acceptances/.../report.html`(或直接产品页)物理按 Esc/Tab 各一次即可关闭。
- 报告共享范围:本地保留;需团队评审时用户 `lh login` 后 `lh acceptance publish`。
- 环境注意(操作教训):nohup 起的服务随会话回收,已改用 `Start-Process` 独立进程;vite 曾被误发的 ^C 终止一次。
