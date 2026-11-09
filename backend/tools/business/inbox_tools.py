"""收件箱四工具：URL/附件保存、搜索、列表、归档；owner 只来自 ToolContext。"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.shared.tool_context import resolve


class SaveInput(BaseModel):
    url: str = Field(default="", description="http/https 链接")
    attachment_id: str = Field(default="", description="消息附件 ID，可留空")
    note: str = Field(default="", description="备注，可留空")
    title: str = Field(default="", description="标题，可留空")
    tags: list[str] = Field(default_factory=list, description="最多 12 个小标签")


class SearchInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=10)


class ListInput(BaseModel):
    status: str = Field(default="unread", description="unread/read/archived，空为全部")
    limit: int = Field(default=10, ge=1, le=20)


class ItemInput(BaseModel):
    item_id: str


def _ctx(config: RunnableConfig = None):
    context = resolve(config)
    if context is None:
        raise RuntimeError("缺少可信用户身份，拒绝访问收件箱")
    return context


def _line(item) -> str:
    state = "未读" if item.status == "unread" else item.status
    return f"• {item.title or item.url}（{item.item_id}，{state}）"


def build_inbox_tools(*, inbox: Any, assistant: Any = None) -> list[Any]:
    if inbox is None:
        return []

    @tool(args_schema=SaveInput)
    async def inbox_save(
        url: str = "",
        attachment_id: str = "",
        note: str = "",
        title: str = "",
        tags: list[str] | None = None,
        config: RunnableConfig = None,
    ) -> str:
        """保存链接或当前消息附件到稍后读；同 URL 去重更新备注。"""
        try:
            context = _ctx(config)
            file_id = ""
            if attachment_id:
                if assistant is None:
                    return "附件保存未启用。"
                attachment = await assistant.get_attachment(
                    context.principal, attachment_id
                )
                file_id = str(attachment.get("stored_file_id") or "")
                if not file_id:
                    return "这个附件还没有持久化，暂时不能存。"
            item = inbox.save(
                context.principal, url=url, file_id=file_id, note=note,
                title=title, tags=tags or [], source="wechat",
            )
            return f"已存：{item.title or item.url}（{item.item_id}）"
        except Exception as exc:  # noqa: BLE001
            return f"保存失败：{exc}"

    @tool(args_schema=SearchInput)
    async def inbox_search(
        query: str, limit: int = 5, config: RunnableConfig = None
    ) -> str:
        """按标题/摘要/备注/标签搜索收件箱。"""
        try:
            context = _ctx(config)
            items = inbox.search(context.principal, query, limit=limit)
            if not items:
                return "没找到相关收藏。"
            return "找到：\n" + "\n".join(_line(item) for item in items)
        except Exception as exc:  # noqa: BLE001
            return f"搜索失败：{exc}"

    @tool(args_schema=ListInput)
    async def inbox_list(
        status: str = "unread", limit: int = 10, config: RunnableConfig = None
    ) -> str:
        """列出未读/归档条目。"""
        try:
            context = _ctx(config)
            items = inbox.list(context.principal, status=status, limit=limit)
            if not items:
                return "收件箱是空的。"
            return "收件箱：\n" + "\n".join(_line(item) for item in items)
        except Exception as exc:  # noqa: BLE001
            return f"读取失败：{exc}"

    @tool(args_schema=ItemInput)
    async def inbox_archive(item_id: str, config: RunnableConfig = None) -> str:
        """归档一条收藏，保留内容。"""
        try:
            context = _ctx(config)
            item = inbox.archive(context.principal, item_id)
            return f"已归档：{item.title or item.url}"
        except Exception as exc:  # noqa: BLE001
            return f"归档失败：{exc}"

    tools = [inbox_save, inbox_search, inbox_list, inbox_archive]
    for item in tools:
        item._toolset = "__always_available__"
    return tools
