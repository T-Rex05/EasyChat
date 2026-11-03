# 多模态图片问答 — 全栈实现参考

## 架构总览

```
用户 ──┬── Web 前端 (ChatView.vue) ── POST /chat/stream + data_url ──► FastAPI
       │       ├─ 按钮上传 → /api/chat/upload-images → data_url 数组
       │       ├─ Ctrl+V 粘贴 → FileReader → data_url
       │       └─ 拖拽 → FileReader → data_url
       │
       └── 微信 (wechat_listener.py) ── iLink type=2/3 → CDN 下载 → base64 ──►
                                         _call_llm_multimodal()
```

**核心设计决策**：图片全部转为 data_url（base64）传输，不依赖服务端文件持久化。上传端点只做转码，返回 data_url 给前端直接使用。

## 文件地图

| 层 | 文件 | 角色 |
|---|---|---|
| 模型检测 | `backend/utils/multimodal_detect.py` | 名称模式匹配，判断模型是否多模态 |
| DB | `model_configs.is_multimodal` | 新增 TINYINT 列 |
| 后端控制器 | `backend/controller/model_config_controller.py` | 创建/更新时自动检测 + 手动切换端点 |
| 后端控制器 | `backend/controller/chat_controller.py` | `POST /chat/stream`（图片流式）、`POST /api/chat/upload-images`（上传）、多模态 content 构建 |
| 前端 API | `agent_frontend/src/api/chat.ts` | `uploadChatImages()`、`sendMessageStreamPost()`、fetch+ReadableStream SSE |
| 前端类型 | `agent_frontend/src/types/chat.ts` | `ChatImage` 接口、`Message.images` 字段 |
| 前端 composable | `agent_frontend/src/composables/useChat.ts` | `attachedImages`、`addImagesFromFiles/addImageFromDataUrl`、POST/GET 双路由 |
| 前端视图 | `agent_frontend/src/views/ChatView.vue` | 图片预览条、粘贴/拖拽处理、上传按钮 |
| 前端配置 | `agent_frontend/src/views/ConfigView.vue` | 🖼️ badge、toggleMultimodal 按钮 |
| 微信 | `backend/controller/wechat_listener.py` | 图片消息检测(type=2/3)、CDN 下载、`_call_llm_multimodal()` |

## 1. 模型多模态检测

**文件**: `backend/utils/multimodal_detect.py`

通过正则模式匹配模型名称，判断是否支持图片输入。覆盖 30+ 主流模型厂商。

**核心函数**:
```python
is_multimodal_model(model_name: str) -> bool
check_model_multimodal(model_config: dict) -> bool  # 优先读 is_multimodal 字段
```

**检测优先级**: DB `is_multimodal` 字段 > 名称模式匹配 > 默认 False。

**模式覆盖**: gpt-4o/v/turbo, claude-3/3.5/4, gemini-1.5/2/2.5, o1/o3, deepseek-vl, qwen-vl, glm-4v, internvl, llama-vision, llava, pixtral, phi-vision, molmo 等。

**排除规则**: gpt-3.5, text-embedding, dall-e, tts, whisper 等明确非视觉模型即使含模糊关键词也排除。

**自动注入**: 模型配置创建/更新时自动调 `is_multimodal_model()` 写入 `is_multimodal` 列。管理员可通过 `PUT /{id}/multimodal` 手动覆盖。

## 2. DB 改动

```sql
ALTER TABLE model_configs ADD COLUMN is_multimodal TINYINT DEFAULT 0 AFTER model_name;
```

`schema.py` 同步更新建表语句。

## 3. 图片上传端点

**端点**: `POST /api/chat/upload-images`
**输入**: multipart/form-data, `files` 字段（可多张）
**输出**: `{ ok, images: [{mime, data_url, filename}], count }`

行为：
- 校验 Content-Type 为 `image/*`
- 限制单张 20MB
- 读取文件内容 → base64 编码 → `data:image/xxx;base64,...` 格式
- **不持久化到磁盘**（data_url 足够大可直接使用）

## 4. 双路 SSE 流式架构

### GET /chat/stream — 纯文本（保持兼容）
现有 `EventSource` 方式不变。仅纯文本时使用。

### POST /chat/stream — 图片+文本（新增）
**输入 JSON**:
```json
{
  "message": "这张图片里有什么？",
  "thread_id": "1_1234567890",
  "mode": "normal",
  "client_msg_id": "...",
  "images": [{"data_url": "data:image/png;base64,...", "mime": "image/png"}]
}
```

**前端消费**: `fetch()` + `ReadableStream` + `TextDecoder` + 行分割解析 SSE `data:` 事件。不能用 `EventSource`（不支持 POST 和自定义请求体）。

**关键实现** (`api/chat.ts` — `sendMessageStreamPost`):
```typescript
fetch(url, { method: 'POST', body: JSON.stringify(body), signal: abortController.signal })
  .then(resp => {
    const reader = resp.body.getReader()
    // 逐块读 → TextDecoder → 按行分割 → 解析 data: {...}
  })
```

## 5. 聊天控制器多模态处理

`token_stream_events()` 新增 `images` 参数。处理流程：

1. 获取模型配置 → 检查 `is_multimodal`（`check_model_multimodal`）
2. 不支持多模态 → 立即返回错误提示 "⚠️ 当前模型不支持图片解析"
3. 支持 → 构建 OpenAI Vision 格式 content:
   ```python
   [{"type": "text", "text": message}, {"type": "image_url", "image_url": {"url": "data:..."}}]
   ```
4. `effective_message` 被改写为 list，但 `text_message` 跟踪原始文本用于 DB 存储

**⚠️ 陷阱**: `effective_message` 从字符串变为 `list[dict]` 后，`save_message()`, `_persist_conversation_answer()`, 历史比较 `cached[-1].get("content") == effective_message` 都会受影响 → 必须用 `text_message` 跟踪原始文本。

## 6. 前端图片输入

### ChatView.vue 改动
- `.input-area` 改为 `flex-direction: column`（图片预览条在上，输入框+按钮在下）
- `@paste` → `handlePaste`：检测剪贴板 `image/*` → FileReader → `addImageFromDataUrl`
- `@drop` → `handleDrop`：取 `dataTransfer.files` → `addImagesFromFiles`
- `<label class="upload-btn">` + `<input type="file" accept="image/*" multiple hidden>` → `onFileInput`
- `.image-preview-strip`：64×64 缩略图 + × 删除按钮 + 虚线添加框

### useChat.ts 改动
- `attachedImages: ref<ChatImage[]>` — 当前附件图片
- `addImagesFromFiles(files)` → 调 `uploadChatImages()` API → push data_url
- `addImageFromDataUrl(dataUrl, mime)` → 直接 push（粘贴/拖拽走客户端 FileReader，不上传）
- `sendMessage()` 判断 `hasImages` → 选 POST 还是 GET 路径
- `newChat()` 同时清空 `clearImages()`

### 发送按钮禁用条件变更
```html
:disabled="!inputMessage.trim() && attachedImages.length === 0"
```
纯图片（无文字）也可发送。

## 7. 微信图片支持

### 消息检测
iLink `item_list` 中 `type` 为 2 或 3 的是图片：
```python
image_items = [item for item in msg.get("item_list") or [] if item.get("type") in (2, 3)]
has_image = len(image_items) > 0
```

### 处理流程
1. 检查当前模型 `is_multimodal` → 不支持则回复 "⚠️ 当前模型不支持图片识别"
2. 下载图片：`session.get(img_url)` → `resp.read()` → `base64.b64encode()` → data_url
3. 调用 `_call_llm_multimodal(text, images)` 发多模态请求
4. 回复走正常的 `_strip_md` + `_reply_wechat_chunks` 流程

### `_call_llm_multimodal()` 函数
独立于 `_call_llm()`，处理两种端点格式：
- **OpenAI**: content 为 `[{type:"text",text:...}, {type:"image_url",image_url:{url:"data:..."}}]`
- **Anthropic**: content 为 `[{type:"text",text:...}, {type:"image",source:{type:"base64",media_type:"image/jpeg",data:"..."}}]` — 需从 data_url 中分离出纯 base64 和 media_type

## 8. 微信陷阱

- **iLink 图片字段结构**: 实际 URL 在 `img_data.media.full_url`，不是 `img_data.url` 或 `img_data.cdn_url`。提取时必须按优先级尝试：`img_data.get("url") or img_data.get("cdn_url") or img_data.get("full_url") or (img_data.get("media") or {}).get("full_url")`
- **⚠️ iLink 图片是 AES-128-ECB 加密的**: 下载到的数据不是原始图片，是 AES-128-ECB + PKCS#7 填充加密的密文。文件头不会是标准 JPEG/PNG 魔数。**必须先解密**：
  ```python
  from Crypto.Cipher import AES
  from Crypto.Util.Padding import unpad
  aeskey = img_data.get("aeskey")  # 32 字符 hex 字符串
  key = bytes.fromhex(aeskey)  # 16 bytes = AES-128
  cipher = AES.new(key, AES.MODE_ECB)  # ⚠️ ECB 模式，无 IV
  decrypted = unpad(cipher.decrypt(img_content), AES.block_size)
  ```
  **常见错误**：不要用 AES-CBC（无论 IV=0 还是 IV=key[:16]），解密后前两个字节碰巧是 `ffd8` 但实际数据损坏，API 会报 "The image format is illegal and cannot be opened"。**依赖**: `pip install pycryptodome`
- **下载用 aiohttp**: 不能混用 `urllib.request.urlopen`（同步阻塞事件循环）
- **内容类型**: 图片响应头 `Content-Type` 取 `image/jpeg` 等真实类型；微信 CDN 实际不返回 Content-Type，需通过解密后魔数检测：JPEG=`ffd8ff`、PNG=`89504e47`、GIF=`GIF87a/GIF89a`、WebP=`RIFF...WEBP`
- **模型检查在下载前**: 避免下载完图片才发现模型不支持
- **多模态检测优先级**: `is_multimodal_model(model_name)` 自动检测 > DB `is_multimodal` 字段。微信监听器中用 `is_multi = is_multimodal_model(model_name) or bool(db_multimodal)`，确保即使 DB 未更新也能正确识别
- **纯图片消息先缓存再提示**: 微信无法同时发图片和文字。收到纯图片时先下载解密缓存到 `_pending_images[pending_key]`，回复"📷 已收到 N 张图片，请在 30 秒内发送文字描述"。后续收到文字时检查缓存合并发送。`/send` 命令直接发送（无文字描述时用"请描述这张图片"）

## 9. 图片持久化（metadata JSON 字段）

图片 data_url 通过 `conversations.metadata` JSON 字段持久化，确保刷新/重新加载历史后图片仍然可见。

**DB 层** (`mysql_impl.py`):
- `insert_conversation()` 新增 `metadata: Optional[Dict[str, Any]] = None` 参数
- `get_conversations_by_session()` SELECT 必须包含 `metadata` 列
- metadata 用 `json.dumps()` 序列化存入，读取时 `json.loads()` 反序列化

**后端保存** (`chat_controller.py`):
```python
# 在 token_stream_events() 入口落库前
metadata = None
if images:
    metadata = {"images": images}  # images = [{data_url, mime, filename}, ...]
running_conversation_id = _insert_running_conversation(
    thread_id, user_id, effective_message, chat_mode=mode, metadata=metadata
)
```

**后端读取** (`chat_controller.py` `get_chat_messages`):
```python
metadata = conv.get("metadata")
images = None
if metadata:
    try:
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if isinstance(metadata, dict) and "images" in metadata:
            images = metadata["images"]
    except (json.JSONDecodeError, TypeError):
        pass
# ...
if images:
    msg["images"] = images
```

**前端类型** (`types/chat.ts`): `Message.images?: ChatImage[]` 已有定义。

**前端渲染** (`MessageBubble.vue`): 用户消息区域先渲染图片再渲染文字：
```html
<div v-if="message.role === 'user'" class="message-content">
  <div v-if="message.images?.length" class="message-images">
    <img v-for="(img, idx) in message.images" :key="idx"
         :src="img.data_url" class="message-image"
         @click="openImagePreview(img.data_url)" />
  </div>
  <div v-text="message.content"></div>
</div>
```

## 10. 图片预览模态框

点击图片放大查看，使用 `<Teleport to="body">` 确保 z-index 不受父容器限制。

**模式**:
```html
<Teleport to="body">
  <div v-if="previewImage" class="image-preview-modal" @click="closeImagePreview">
    <div class="image-preview-content" @click.stop>
      <img :src="previewImage" class="image-preview-img" />
      <button class="image-preview-close" @click="closeImagePreview">×</button>
    </div>
  </div>
</Teleport>
```

**关键 CSS**:
- `.image-preview-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 9999; }`
- `.image-preview-img { max-width: 90vw; max-height: 90vh; object-fit: contain; }`
- 关闭按钮 `position: absolute; top: -40px; right: 0;` 悬浮在图片右上角
- 点击 backdrop 关闭，`@click.stop` 阻止冒泡到 backdrop

**状态管理**: 组件内 `const previewImage = ref<string | null>(null)`，`openImagePreview(url)` / `closeImagePreview()` 方法。

## 11. 前端关键陷阱

- **发送按钮禁用**: 原来 `!inputMessage.trim()` 改为 `!inputMessage.trim() && attachedImages.length === 0`，允许纯图发送
- **清空时机**: 必须在 `sendMessage()` 内先快照 `currentImages`，再 `clearImages()`，最后放 userMessage 里
- **文件 input 重置**: `onFileInput` 后必须 `input.value = ''`，否则选择同一文件不触发 change
- **粘贴只取首张**: `handlePaste` 遍历 `clipboardData.items`，只处理第一个 `image/*`
- **图片必须持久化到 metadata**: 仅存内存的 `images` 数组在刷新后丢失，必须写入 `conversations.metadata` JSON 字段
- **metadata 可能是字符串或 dict**: 从 DB 读出时需 `isinstance(metadata, str)` 判断是否需要 `json.loads()`
