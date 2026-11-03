# IDE 模式全栈开发模式

## 三面板布局（splitpanes）
- `npm install splitpanes` → 在 `IdeLayout.vue` 中使用 `<Splitpanes><Pane>...`
- `Pane` 的 `min-size` 和 `size` 是百分比，三个面板合计 100
- `.ide-layout { height: 100%; width: 100%; position: relative; }` — 必须有 `position: relative` 为退出按钮提供定位锚点

## Monaco Editor 陷阱

### 1. vite-plugin-monaco-editor 不要用
Monaco 0.56 + Vite 6 下 `vite-plugin-monaco-editor` 会导致 `?worker` 导入路径解析失败。直接 `import * as monaco from 'monaco-editor'` 即可，基础语法高亮和代码显示正常。

### 2. 容器必须渲染完成再初始化
```ts
// ❌ 错误：容器被 v-show/v-if 隐藏时 create 会静默失败
editor = monaco.editor.create(container, { ... })

// ✅ 正确：用 v-if 控制可见性，初始化前用 setTimeout 等 layout
editorReady.value = true
await nextTick()
setTimeout(() => {
  const container = editorContainer.value
  if (!container || container.offsetHeight === 0) {
    setTimeout(() => createEditor(), 100)  // 重试
    return
  }
  editor = monaco.editor.create(container, { ... })
}, 100)
```

### 3. 切换文件/Tab 必须 dispose 再重建
```ts
if (editor) { editor.dispose(); editor = null }
editorReady.value = false
await nextTick()
editorReady.value = true
setTimeout(() => createEditor(), 100)
```

### 4. 主题
- `theme: 'vs'` → 白色背景（推荐）
- `theme: 'vs-dark'` → 深色背景

## 递归文件树组件
- 任意深度目录需要递归组件 → 抽离 `TreeNode.vue`
- `TreeNode` 用 `name: 'TreeNode'` 自引用
- `depth * 16 + 8` px 计算缩进
- 子目录按需懒加载：`handleClick` 中检查 `item.children`，为空时 `loadTree(item.path)`
- `expandedDirs` 用 `Set<string>` 管理展开状态

## Markdown 预览切换
- `CodeEditor.vue` 对 `.md` 文件显示「预览/源码」按钮
- 预览用 `v-html="renderMarkdown(content)"` 渲染
- 源码/预览两个 div 用 `v-if` 互斥，切回源码时要 watch `mdPreview` 重建编辑器

## 聊天面板嵌入 IDE
- `IdeChatPanel.vue` 复用 `useChat('ide')`，传 `chatMode='ide'`
- SSE URL 带 `mode=ide` → 后端 `_insert_running_conversation(chat_mode=mode)`
- IDE 会话历史：`/api/data/sessions?session_type=ide` → 后端 WHERE `c.chat_mode='ide'`
- 数据库 `conversations.chat_mode VARCHAR(32) DEFAULT 'normal'`

## 后端 IDE API (`ide_controller.py`)
- `POST /api/ide/root` → 设置工作根目录，存内存 `_ide_roots[user_id]`
- `GET /api/ide/tree?path=` → 递归 3 层返回文件树 JSON
- `GET /api/ide/file?path=` → 读取文件内容（拒绝 >2MB 和二进制）
- `PUT /api/ide/file?path=` → 保存文件内容（路径穿越防护）
- 安全：`_safe_path()` 校验 `os.path.realpath` 必须在 root 内
