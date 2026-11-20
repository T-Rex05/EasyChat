# Web 记忆与对话角色复验

截图使用同一本机 Chrome、1440 × 1000 视口和同一组合成记忆。记忆页和聊天页分别保存开发前后的画面。页面从实现工作树的 Vite 服务加载，Playwright 拦截认证、业务接口和 SSE，夹具只使用虚构数据。

| 场景 | Before | After |
| --- | --- | --- |
| 账号打开记忆管理的默认列表 | [before-memory.png](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/before-memory.png) | [after-memory.png](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-memory.png) |
| 账号打开聊天页并看到历史会话 | [before-chat.png](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/before-chat.png) | [after-chat.png](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-chat.png) |

- [按类型分组的星图与记忆详情](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-starmap.png)
- [只读账号在 430 × 860 视口登录后定位记忆](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-mobile-read-only.png)
- [历史答案的本轮记忆](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-answer-memory.png)
- [角色设置与新会话入口](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/after-personas.png)

## 复验步骤

在本工作树的 `agent_frontend` 目录运行 `npm run dev -- --host 127.0.0.1 --port 31879 --strictPort`，随后在另一个终端执行 `node "<本地脚本路径>"`。脚本读取本机已安装的 Chrome 和 npm 缓存中的 Playwright，移至其他机器时需调整脚本顶部的安装路径。[本地浏览器夹具](C:/Users/SWQ/.codex/visualizations/2026/11/20/01a1f70d-30b7-70e2-8d8a-7c9c34a663d4/memory-personas/browser-fixture.cjs)

- 从列表切换到星图，通过键盘选中记忆，检查来源与修订。制造 409 并确认草稿仍在，核对服务器新版本后重交。验证范围筛选、文字检索、模拟召回和遗忘。
- 从未登录和过期令牌两种状态打开指定记忆及版本。登录后核对落点和所选版本，检查只读账号在窄屏可查看详情，且看不到写操作。
- 打开历史答案的「本轮记忆」并沿链接定位。创建对话角色和绑定的新会话，发送首条消息并断言 SSE 使用服务端返回的会话 ID。从 SSE 开始帧取得 run ID，确认终帧没有重复携带 run ID 时也能读取本轮记忆。编辑、归档角色。
- 本次 Playwright 通过合成 HTTP 与 SSE 响应复验交互。真实微信、真实 Hermes 和外部部署需要独立验收。
