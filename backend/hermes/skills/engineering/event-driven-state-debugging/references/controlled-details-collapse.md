# Vue 受控组件坑:手动展开被下一轮状态更新强制折叠

## 症状(用户原话)

「思考完一轮放到折叠块,我点开之后,下一轮思考完就又折叠上,而且页面上下跳。」

## 根因:`<details :open="...">` 是受控组件

```html
<!-- ❌ 坏代码:受控式绑定,reactive 值一变就覆盖用户的 DOM 手动操作 -->
<details :open="!message.content">
```

- `:open="!message.content"` 的值由 Vue 响应式派生。
- 用户手动点 `<summary>` 展开时,浏览器改的是 **DOM 的 `open` 属性**,Vue 的响应式 `:open` 值没变。
- 下一轮思考开始/结束 → `message.content` 变化(清空→再填充)→ Vue 重新 patch `:open` 属性 → 把用户手动展开的 `<details>` **强制重置**回表达式算出的值(`false`)。
- 「页面上下跳」:折叠的高度突变 + 流式期间每 500ms 拉滚底部,两者竞争。

## 正确修法:非受控 + 本地开关 + 「用户是否手动干预」标志

核心是:一旦用户手动 toggle 过,后续 `message.content` 变化**不得再覆盖**。用 `@toggle` 同步真实 DOM 状态,并用一个 `userToggled` 标志区分「用户手动」vs「自动跟随」。

```vue
<details :open="isOpen" @toggle="onToggle">
  <summary>🧠 思考过程（{{ n }} 步）</summary>
  <!-- ...内容... -->
</details>
```

```ts
const isOpen = ref<boolean>(!props.message.content)   // 初始:无正文(思考中)→展开
const userToggled = ref<boolean>(false)

function onToggle(e: Event) {
  isOpen.value = (e.target as HTMLDetailsElement).open  // 同步真实开合
  userToggled.value = true                              // 标记用户已手动干预
}

watch(
  () => props.message.content,
  (val) => {
    if (!userToggled.value) isOpen.value = !val   // 仅未手动干预时自动跟随
  },
)
```

效果:
- 思考阶段默认展开(`!content`)。
- 用户点开后,后续 content 更新**保持用户的选择**(`userToggled` 挡住自动覆盖)。
- 用户没动过时,仍自动「有正文折叠、无正文展开」。

## 页面上下跳的另一诱因:流式期间无脑拉到底

`setInterval(fn, 500)` 里若无条件 `smartScrollToBottom()`,每当折叠块开合改变容器高度后,`nearBottom` 突然变真 → 又 smooth 拉到底 → 视觉跳动。

修法:只在实际**有新内容长度变化**时才滚动:

```ts
let lastStreamedLength = 0
function watchStreaming() {
  const last = messages.value[lastIndex]
  const len = (last?.content?.length||0) + (last?.thinkingProcesses?.reduce((s,t)=>s+(t?.content?.length||0),0)||0)
  if (len !== lastStreamedLength) { lastStreamedLength = len; smartScrollToBottom() }
}
```

## 通用结论

- Vue 里对**浏览器自带交互组件**(`<details>`、`<input>` 的受控 value、`<select>`)做响应式绑定前,先想清楚:用户 DOM 手动操作会不会被 reactive 值覆盖?
- 需要兼顾「默认自动」与「用户手动优先」时,用一个独立 `ref` 记录状态 + 一个 `userToggled`/`userInteracted` 布尔挡住自动逻辑。
- 流式/高频更新组件,滚动、重渲染务必做「变化才触发」守门,否则轻微高度抖动都会被放大成反复跳动。
