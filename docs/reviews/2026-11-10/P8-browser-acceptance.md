# P8 记录:真实浏览器全功能验收(2026-11-10)

方式:后端 8001+Vite 3000 实起、注册专用测试用户(p8_accept_user id3/p8_accept_admin id4,admin+superagent 三键经 AccessRepository),真实输入事件驱动(IAB 坐标点击/键盘 dispatch;Playwright locator click 在 IAB 桥接偶发超时,已标注)。截图存本会话 artifacts 目录。

## 验收矩阵结果

| 场景 | 结果 | 证据 |
|---|---|---|
| 登录→聊天首屏 | ✅ | 三列布局截图;503 history 优雅降级("加载中"+不阻塞) |
| 拒绝态(普通用户→#/admin) | ✅ 弹回 /chat | 探针 hash/route 双读 |
| 后端 API 拒绝(普通用户 model-configs) | ✅ 403 | curl+服务日志 |
| 账单页(admin/user 允许态) | ✅ 渲染完整(导入/统计/最近交易/退款候选) | 截图 |
| 超级代理页 | ✅ 间距/卡片/表单/失败任务轨迹(443 历史失败记录如实显示,runner 未就绪横幅正确) | 截图 |
| 系统管理→用户管理 | ✅ 角色下拉/有效权限/禁用入口齐备 | 截图 |
| 角色卡 | ✅ role-card 整卡 role=button tabindex=0(编辑入口可键盘聚焦) | a11y 树 |
| 权限弹窗(编辑角色) | ✅ 9 功能项模式卡+依赖说明文案("文件能力…已随功能自动包含")+admin 账单显示"使用"(模式识别修复生效) | 截图+DOM 探针 |
| 聊天三列拖动 | ✅ 即时生效(280→380,边界 max 钳制)+键盘 ArrowRight±16 | 坐标拖拽+dispatch 探针 |
| 拖动刷新恢复 | ❌→✅ **缺陷③已修**(见下) | 修复前后对照 |
| 路由切换 | ❌→✅ **缺陷②已修** | 修复前后对照 |
| 登录后菜单 | ❌→✅ **缺陷①已修** | After 截图 |

## 三个实测缺陷与修复(提交 2c7b2e5/714d4c8)

1. **缺陷①(已修)**:登录响应不含 capabilities(后端契约 `/api/auth/login` 无此字段,实测 keys)→前端菜单首帧走权限回退,回退表无 `ledger` →账单入口消失至刷新。修复=回退表补一行(caps 就绪后仍以 caps 为准)。
2. **缺陷②(已修)**:router-view 的 `<transition mode="out-in">` 在 leave 被中断的导航下冻结组件替换——**登录后路由切换全部失效**(currentRoute 已=Ledger、URL=#/ledger,main 内仍 ChatView;修复后同一探针 main 子节点唯一=ledger-page,双向切换正常)。ChatView 模板为单根(div.chat-view),冻结与根数无关(修正中途误判)。
3. **缺陷③(已修)**:历史/导航栏宽度仅存内存,刷新回弹(验收项"刷新恢复"缺口)。修复=localStorage 读写+初值钳制(312→刷新 312;999→钳 420;键盘/拖动/双击 reset 全链走同一 handler,已实测)。

## 前端检查覆盖口径(如实)

- `npm test` 22 passed:纯逻辑(node --test,.mjs/.cjs)——含 role-modes 行为回归,**不含**上述三个 UI 缺陷的自动化回归(无 DOM 测试框架,登记为未验证项:本次修复由浏览器端到端证据支撑,未来若引入 vitest+DOM 应补)。
- `type-check` 0 错误;`build` 通过(退出码 0)。

## 遗留与未验证

- 触摸拖拽(touch)未测(桌面环境无 touch 模拟;键盘替代路径已验证)。
- 微信/邮件等真实外发页:渠道默认关闭,配置页按拒绝/引导态显示,实单归 P9 阶段 F。
- 暗色模式切换按钮存在未逐项验证。
- 测试用户 id3/id4 保留在 dev 库 `data/app.db`(非生产),记录归属:验收专用,可随时禁用。
- 验收完成后两服务已停(端口释放实测)。
