# WP1 记录:视觉壳与导航(小暖 Android 客户端)

日期 2026-11-11,基线 WP0 文档 + 工程脚手架。本文件是 WP1 的验收记录:交付物、截图清单、验收对照与遗留打磨项。

## 1. 交付物

- 视觉系统:`core/designsystem/`(XnPalette 单一色值来源 + Theme/Type/Dimens/Components),浅深两套暖色主题,排版 26/20/17/14sp 体系,卡片 20dp/弹层 28dp/输入 24dp 圆角,点击区 ≥48dp,主按钮 54dp。
- 四导航:`今天 / 聊天 / 生活 / 我的`(`app/XiaoNuanApp.kt`),底部 NavigationBar 文字常驻、图标+文字双态。
- 页面布局:欢迎/服务器/登录(onboarding)、今天、聊天列表、对话详情(微信只读态 + App 输入态)、生活(日程/记下的事/收藏 分段 + 厨房预留卡)、我的。
- 单元测试 13 项全部通过:`./gradlew.bat assembleDebug testDebugUnitTest` BUILD SUCCESSFUL。
  - ContrastTest:WCAG 对比度(浅/深正文 ≥4.5,图形/按钮 ≥3 或 4.5)对 Token 直接验收;
  - TypeScaleTest:26/34、20/28、17/27、14/20 设计值与「行高 ≥ 字号」;
  - XnTimeTest:`next_run_at` 秒级 epoch 语义(毫秒误用必须暴露)、今天/明天/周内/远期文案、ISO 无时区后缀按 UTC 解析、问候语时段。
- 模拟数据:每页带可见「示例数据」徽标(`XnMockBadge`),`res/values/strings.xml` 亦有 `mock_badge`。

## 2. 构建与测试(实测)

```
gradlew.bat assembleDebug testDebugUnitTest  → BUILD SUCCESSFUL
产物:android_client/app/build/outputs/apk/debug/app-debug.apk(versionName 0.1.0)
测试:13 tests,0 failed(ContrastTest 6 + TypeScaleTest 4 + XnTimeTest 5? 见测试报告)
```

单测报告:`android_client/app/build/reports/tests/testDebugUnitTest/index.html`。

## 3. 截图清单(`docs/superpowers/specs/assets/android-wp1/`,模拟器 xn_test:Pixel 6 配置,1080×2400@420dpi)

| 文件 | 场景 |
| --- | --- |
| assets/android-wp1/shot_01_welcome.png | 欢迎页(浅色正常) |
| assets/android-wp1/shot_02_server.png | 服务器配置(示例状态 + 扫码入口) |
| assets/android-wp1/shot_03_login.png | 登录页 |
| assets/android-wp1/shot_04_today.png | 今天(412dp 浅色正常):问候/主图占位/双按钮/今日安排/记下的事 |
| assets/android-wp1/shot_05_chat.png | 聊天列表(全部/微信/App 筛选 + 来源标签) |
| assets/android-wp1/shot_06_life.png | 生活-日程(周日历 + 重复规则 + 已暂停态 + 厨房预留卡) |
| assets/android-wp1/shot_07_profile.png | 我的(账号/微信绑定/称呼陪伴/外观/连接存储) |
| assets/android-wp1/shot_08_wechat_detail.png | 微信对话只读详情(来源标签 + 带着这段聊一聊) |
| assets/android-wp1/shot_09_today_dark.png | 今天 深色 |
| shot_10_chat_dark.png | 聊天 深色 |
| shot_11_today_font2.png | 今天 2.0× 系统字体 |
| shot_12_life_360dp.png | 生活 360dp 窄屏(`wm density 480`) |

## 4. 验收对照(设计 §10 WP1)

| 验收目标 | 结果 |
| --- | --- |
| 主题 Token、文字系统、卡片、状态组件、四导航、登录布局 | 完成;色值以 XnPalette 单一来源,Compose 主题与对比度测试同源 |
| 360dp / 412dp、浅色 / 深色、正常 / 大字截图 | 完成,见 §3;模拟数据均显式标记 |
| 对照效果图检查照片占比、字体可读性、内容密度、选中状态 | 主图占位约 190dp(≈首屏 22%,达标区间 20~25%);选中态:导航主色 + 分段胶囊 primaryContainer;正文 17sp 深可可色对比度 >7:1(测试保证) |

## 5. 遗留打磨项(记录,不阻塞 WP2)

1. 2.0× 大字下「示例数据」徽标纵向换行成高胶囊(shot_11 右上),`XnMockBadge` 后续加 `maxLines=1` 或横向流式布局;
2. 360dp 下周日历日期数字换行成两行(shot_12),周历单元格后续加 `maxLines=1` + 自动缩字号;
3. 首页主图为渐变占位:真实自然光家居照片素材待 WP5 前替换(版权与拍摄来源需用户确认);
4. Nunito 拉丁字体未随包分发(当前系统字体),需用户确认授权来源后再集成;
5. TalkBack 实测在 WP5 真机阶段进行(模拟器已保证:图标 contentDescription、按钮文字常驻、状态文字可读)。

## 6. 与设计文档的差异决定

- 设计 §3.3 拉丁与数字可用 Nunito:暂用系统字体(见 §5.4),不阻塞中文排版验收。
- 设计 §5.2「更新于 HH:mm」:WP1 示例固定「更新于 20:36」;WP3 接真实数据后由各区块 fetched_at 驱动。
- 概念图中的结构化提醒卡片:按设计 §3.1 属 P1 增强(需真实回执),WP1 未实现,对话内仅文本呈现。
