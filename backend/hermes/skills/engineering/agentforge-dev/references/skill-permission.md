# Skill Permission Architecture

## Tables

```sql
skill_meta (
  name         VARCHAR(100) UNIQUE,
  owner_id     BIGINT,          -- who created it
  category     VARCHAR(50),
  status       VARCHAR(20) DEFAULT 'approved',  -- pending/approved/rejected
  locked       TINYINT DEFAULT 0,
  reviewed_by  BIGINT,
  reviewed_at  DATETIME
)
```

## Visibility matrix

| Role | Own skill | Other's non-AI public | AI生成 category | Locked |
|------|-----------|----------------------|----------------|--------|
| super_admin | ✅ | ✅ | ✅ | ✅ (bypass lock) |
| admin | ✅ | ✅ | ✅ | ✅ (bypass lock) |
| user | ✅ | ✅ | ❌ hidden | ❌ blocked |

- "Public non-AI" = owner_id==1 (admin-owned) AND category != "AI生成"
- "AI生成" is the magic category: only visible to super_admin

## Lock enforcement (TWO layers required)

Lock is useless unless enforced at BOTH layers:

1. **API layer** — `get_skill()` raises `ValueError("已被锁定")` for non-super_admin callers. Also `list_skills()` returns `locked=True` field so UI can show 🔒 icon.

2. **Hermes agent layer** — `_find_all_skills()` in `backend/hermes/tools/skills_tool.py` MUST filter locked skills. Otherwise the Agent's system prompt still lists them. Apply `_filter_locked_skills()` on BOTH cache hit AND cache miss returns. Also `skill_view()` must check `_meta_get(name).locked` and refuse.

Lock check is on every turn (no restart needed) because it queries `skill_meta` table live.

## Ownership enforcement

`update_skill(name, ..., user_id, role)` and `delete_skill(name, user_id, role)` must check:
- `role == "super_admin"` → allowed
- `meta.owner_id == user_id` → allowed (own skill)
- else → `ValueError("只能修改自己创建的技能")`

Also `delete_skill` must search sub-category directories (not just root), because skills live at `skills/<category>/<name>/SKILL.md`:
```python
skill_dir = skills_dir / name
if not skill_dir.exists():
    for category_dir in skills_dir.iterdir():
        if (category_dir / name).exists():
            skill_dir = category_dir / name
            break
```

## Controller layer

Controller endpoints MUST pass `user_id` and `role` to service:
```python
@router.put("/{name}")
async def update_skill(name: str, req, user: dict = Depends(get_current_user)):
    result = skill_service.update_skill(..., user_id=user["user_id"], role=user["role"])

@router.delete("/{name}")
async def delete_skill(name: str, user: dict = Depends(get_current_user)):
    skill_service.delete_skill(name, user_id=user["user_id"], role=user["role"])
```

ValueError → 403 (permission), FileNotFoundError → 404 (not found).

## AI-created skills auto-approved

In `skill_manager_tool.py::_create_skill()`, after writing SKILL.md, call:
```python
from backend.service.skill_service import _meta_insert
_meta_insert(name, owner_id=1, category=final_category, status="approved")
```
owner_id=1 means admin-owned, so all users see it (unless it's AI生成 category, then only super_admin).

## Logout must clear chat state

`auth.ts` logout function must call `useChatStore().resetAll()` — otherwise next user sees previous user's conversation. Chat state is in memory (`messages.value`), `currentChatId` in sessionStorage. The chat store's `resetAll()` must:
- Clear `currentChatId`
- Clear `messages.value`
- Clear `streamingSessions` map
- Remove `currentChatId` from sessionStorage
