# 折叠侧边栏：收起后展开按钮被裁掉的布局坑

已在 AgentForge `agent_frontend/src/components/AppSidebar.vue` 遇到并修复。

## 症状

点击侧边栏左下角"折叠"按钮把它缩到窄宽度（本项目 64px）后，**"展开"按钮看不见/点不到**，侧边栏再也展不回来。UI 表现是"缩回去之后那个 → 被覆盖了"。

## 根因

- 侧边栏折叠态只把外层宽度变窄（如 `width: 240px → 64px`），**底部操作区里还是原来的多个按钮**（主题、退出、折叠）。
- 这些按钮是固定宽度（如 `width:30px`），3 个排一起 `3×30=90px > 64px`。
- 容器 `.sidebar-footer` 设了 `flex-wrap: nowrap; overflow: hidden` 时，**溢出的按钮被裁掉**——而"折叠/展开"按钮恰好在最右，第一个被推到可视区外，用户自然点不到。

```css
.sidebar-footer { flex-wrap: nowrap; overflow: hidden; }  /* ❌ 溢出被裁 */
```

关键点：**展开按钮被裁 = 用户被锁死在折叠态，无法恢复**，比"看着丑"严重得多。

## 正确修法

折叠态只保留「切换展开」这一个按钮，把其余按钮（主题/退出/用户信息）在 `collapsed` 时**不渲染**（而不是靠裁切）：

```html
<div class="sidebar-footer">
  <div v-if="!collapsed" class="user-info">…</div>
  <template v-if="!collapsed">
    <button @click="toggleTheme">…</button>
    <button @click="handleLogout">…</button>
  </template>
  <!-- 折叠/展开按钮始终渲染，是唯一存活的控制 -->
  <button class="sidebar-btn" @click="collapsed = !collapsed"
    :title="collapsed ? '展开侧边栏' : '折叠侧边栏'">
    <svg v-if="collapsed" …arrow-right…/>
    <svg v-else …arrow-left…/>
  </button>
</div>
```

配套细节：
- 用 `v-if="collapsed"` / `v-else` 让箭头**随方向翻转**（收→指向右，展→指向左），视觉更明确。
- 折叠态 CSS 保持 `.collapsed .sidebar-footer { justify-content: center }`，让只剩下的展开按钮居中。

## 可迁移原则

凡是「折叠 / 收起」类导航、工具栏：**宽度变窄的本质是空间不足，处理方式是「削减内容」（条件渲染），而不是靠 `overflow: hidden` 硬裁**。任何 `overflow:hidden` + 多个子项紧凑排列的地方，都要检查"裁掉的那个是不是用户唯一能恢复入口的按钮"。

## 排查步骤

1. 点折叠后是否还有按钮被裁？把 `.sidebar-footer` 的 `overflow:hidden` 临时改 `visible` 数一下有几个子项在宽度之外。
2. 收起态想要几个按钮？只留必须的（通常只有展开/折叠），其余 `v-if="!collapsed"` 不渲染。
3. 验证展开按钮永远是"最可靠触发态存在"的那个。
