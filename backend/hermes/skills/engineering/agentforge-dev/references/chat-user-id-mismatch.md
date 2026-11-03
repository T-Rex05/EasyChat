# chatUserId 存储位置导致的 user_id=0 会话丢失

## 症状
- 新建对话后刷新页面，历史记录列表里看不到刚创建的对话
- 历史列表只显示旧对话，新对话"消失"

## 根因链
```
authStore.userId → sessionStorage.getItem('chatUserId')
  → sessionStorage 按标签页隔离/被清空
  → 返回 null
  → fallback: '0'
  → 新对话 thread_id = '0_...timestamp'
  → DB: user_id=0 入库
  → 刷新后 /api/data/sessions 通过 Token 取 user_id=1
  → WHERE user_id=1 → 查不到 user_id=0 的记录
  → 前端历史列表为空（只有旧 user_id=1 的会话显示）
```

## 诊断 SQL（MySQL）
```sql
-- 确认有 user_id=0 的记录
SELECT user_id, COUNT(*) FROM conversations GROUP BY user_id;

-- 查看 user_id=0 的具体会话
SELECT id, session_id, user_id, LEFT(user_question,50) as q, status 
FROM conversations WHERE user_id=0 ORDER BY id DESC;

-- 查看当前用户
SELECT id, username, role FROM users;
```

## 修复 SQL（将 user_id=0 归正到 user_id=1）
```sql
UPDATE conversations 
SET user_id = 1, 
    session_id = REPLACE(session_id, '0_', '1_')
WHERE user_id = 0;
```

## 前端修复（agent_frontend/src/stores/auth.ts）

### userId computed — 优先级调整
```ts
// 修复前（错误）
return sessionStorage.getItem('chatUserId') || localStorage.getItem('chatUserId') || '0'

// 修复后
return localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId') || '1'
// ↑ localStorage 优先（跨标签页持久）  ↑ fallback 用 '1' 不是 '0'
```

### login/register — 双写
```ts
const uid = String(response.user_id || '1')
localStorage.setItem('chatUserId', uid)   // ← 新增：持久化
sessionStorage.setItem('chatUserId', uid)  // 保留兼容
```

## 根本教训
- `sessionStorage` 是 tab-scoped，新标签页/某些浏览器行为会清空
- 用户身份相关的状态必须持久化到 `localStorage`
- fallback 值绝不能用 `'0'`——它会在 DB 中形成孤儿记录
- 前后端 user_id 的一致性链路：`localStorage → thread_id.split('_')[0] → DB user_id → Token uid → WHERE user_id=X`，任何一环断裂都会导致"数据写入成功但查不回来"
