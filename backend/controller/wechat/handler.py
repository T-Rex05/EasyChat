"""微信监听器 - 消息处理主逻辑"""
import asyncio
import time
import re
import os
from pathlib import Path
from typing import Optional

from backend.controller.wechat.config import (
    _get_conn, _dedup, _dedup_ttl, _pending_images, _pending_files, 
    _session_files, _PENDING_TIMEOUT
)
from backend.controller.wechat.session import (
    _get_active_session, _set_active_session, _get_user_sessions, 
    _new_session_key, _skey
)
from backend.controller.wechat.reply import (
    _reply_wechat_text, _reply_wechat_chunks, _fetch_typing_ticket, 
    _send_typing_indicator
)
from backend.controller.wechat.text import _strip_md, _split_text_for_weixin
from backend.controller.wechat.file import _read_file_content
from backend.controller.wechat.hermes import run_wechat_hermes, persist_wechat_conversation
from backend.wechat import (
    aes128_ecb_decrypt, _parse_aes_key, ITEM_IMAGE, ITEM_FILE, ITEM_VOICE,
    download_and_decrypt_file, ALLOWED_FILE_EXTENSIONS
)
from backend.utils.image_safety import process_image_safe
from backend.utils.log_utils import log as logger


async def _monitor_process(proc, label: str):
    """监控子进程完成并清理资源"""
    try:
        # 等待进程完成，设置超时防止无限等待
        # proc.wait() 返回 int（退出码），需要用 asyncio.to_thread 包装
        exit_code = await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=300)
        logger.info(f"系统进程完成: {label}, 退出码: {exit_code}")
    except asyncio.TimeoutError:
        logger.warning(f"系统进程超时，强制终止: {label}")
        proc.terminate()
        try:
            await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
    except Exception as e:
        logger.error(f"监控系统进程失败: {label}, 错误: {e}")
    finally:
        # 从全局列表中移除已完成的进程
        from backend.controller.wechat.config import _system_processes
        _system_processes[:] = [(p, t, l) for p, t, l in _system_processes if p != proc]


def _find_user_by_wechat_id(wx_user_id: str) -> dict | None:
    """根据微信用户ID查找绑定的系统用户"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ub.user_id, u.username, u.status FROM user_bindings ub JOIN users u ON ub.user_id = u.id "
            "WHERE ub.platform = 'wechat' AND ub.enabled = 1 AND ub.open_id = %s", (wx_user_id,))
        row = cur.fetchone()
        if not row:
            return None
        # 禁用用户拒绝服务（防越权使用聊天/工具）
        if int(row.get("status") or 0) != 1:
            return {"user_id": row["user_id"], "username": row["username"], "disabled": True}
        return {"user_id": row["user_id"], "username": row["username"]}
    finally:
        conn.close()


async def _handle_message(msg: dict, token: str, account_id: str, base_url: str, session):
    """处理单条微信消息"""
    from_user_id = str(msg.get("from_user_id") or "").strip()
    if not from_user_id or from_user_id == account_id:
        return
    
    # 去重：优先使用 message_id，否则使用 from_user_id + 文本内容的哈希
    msg_id = str(msg.get("message_id") or "").strip()
    now = time.time()
    
    # 如果没有 message_id，使用内容哈希作为去重键
    if not msg_id:
        # 提取文本内容用于生成哈希键
        _text_preview = "".join(
            str((item.get("text_item") or {}).get("text") or "") 
            for item in (msg.get("item_list") or []) 
            if item.get("type") == 1
        )[:100]  # 只取前100字符避免哈希过长
        if _text_preview:
            import hashlib
            msg_id = f"content:{from_user_id}:{hashlib.md5(_text_preview.encode()).hexdigest()[:16]}"
            logger.debug(f"[微信去重] 无 message_id，使用内容哈希: {msg_id}")
        else:
            # 纯图片/文件消息，使用 from_user_id + 时间戳（分钟级）
            msg_id = f"media:{from_user_id}:{int(now // 60)}"
            logger.debug(f"[微信去重] 媒体消息，使用时间键: {msg_id}")
    
    if msg_id in _dedup and now - _dedup[msg_id] < _dedup_ttl:
        logger.info(f"[微信去重] 跳过重复消息: {msg_id}")
        return
    _dedup[msg_id] = now
    
    # 清理过期的去重缓存
    for k in [k for k, v in _dedup.items() if now - v > _dedup_ttl]:
        _dedup.pop(k, None)
    # 清理超时的缓存图片和文件
    for cache_dict in (_pending_images, _pending_files):
        for k in [k for k, v in cache_dict.items() if now - v.get("timestamp", 0) > _PENDING_TIMEOUT]:
            cache_dict.pop(k, None)
    
    text = "".join(str((item.get("text_item") or {}).get("text") or "") for item in (msg.get("item_list") or []) if item.get("type") == 1).strip()
    
    # 检测图片消息
    image_items = [item for item in (msg.get("item_list") or []) if item.get("type") in (ITEM_IMAGE, ITEM_VOICE)]
    has_image = len(image_items) > 0
    
    # 检测文件消息（type=4）
    file_items = [item for item in (msg.get("item_list") or []) if item.get("type") == ITEM_FILE]
    has_file = len(file_items) > 0
    
    if not text and not has_image and not has_file:
        return
    
    user = _find_user_by_wechat_id(from_user_id)
    if not user:
        return logger.info(f"微信消息来自未绑定用户 {from_user_id[:8]}: {text[:50]}...")
    
    # 禁用用户拒绝（账号被管理员停用后立即失效）
    if user.get("disabled"):
        return await _reply_wechat_text("⛔ 账号已被禁用，请联系管理员", token, account_id, base_url, from_user_id, session, str(msg.get("context_token") or ""))
    
    # RBAC: 检查 chat.use 权限
    from backend.permission.checker import has_permission
    if not has_permission(user["user_id"], "chat.use"):
        return await _reply_wechat_text("⛔ 你没有使用聊天的权限，请联系管理员", token, account_id, base_url, from_user_id, session, str(msg.get("context_token") or ""))
    
    logger.info(f"微信消息 from={user['username']}({from_user_id[:8]}): {text[:50]}...")
    ctx_token = str(msg.get("context_token") or "")
    cmd = text.strip().lower()
    uid = user["user_id"]
    
    # ── 斜杠命令 ──
    if cmd in ("/new", "/新对话", "/新会话"):
        old_sid = _get_active_session(uid, from_user_id)
        sid = _new_session_key(uid, from_user_id)
        _set_active_session(uid, from_user_id, sid)
        _session_files.pop(old_sid, None)  # 清理旧会话文件注册表
        return await _reply_wechat_text(f"✅ 已开启新对话\nID: {sid[:16]}...", token, account_id, base_url, from_user_id, session, ctx_token)
    
    if cmd in ("/history", "/历史", "/会话列表", "/list"):
        sessions = _get_user_sessions(uid, 10)
        if not sessions:
            return await _reply_wechat_text("📭 暂无微信对话记录", token, account_id, base_url, from_user_id, session, ctx_token)
        current = _get_active_session(uid, from_user_id)
        lines = ["**📋 微信对话列表**"]
        for i, s in enumerate(sessions, 1):
            cur = " **← 当前**" if s['session_id'] == current else ""
            lines.append(f"- **{s['title']}**{cur}  `{i}`")
        lines += ["", "回复序号切换，如 `/1`"]
        return await _reply_wechat_text("\n".join(lines), token, account_id, base_url, from_user_id, session, ctx_token)
    
    if cmd.startswith("/") and cmd[1:].isdigit():
        idx = int(cmd[1:])
        sessions = _get_user_sessions(uid, 10)
        if 1 <= idx <= len(sessions):
            _set_active_session(uid, from_user_id, sessions[idx - 1]["session_id"])
            return await _reply_wechat_text(f"✅ 已切换到：{sessions[idx - 1]['title']}", token, account_id, base_url, from_user_id, session, ctx_token)
        return await _reply_wechat_text(f"❌ 序号无效，范围 1-{len(sessions)}", token, account_id, base_url, from_user_id, session, ctx_token)
    
    if cmd in ("/status", "/当前"):
        sid = _get_active_session(uid, from_user_id)
        return await _reply_wechat_text(f"📌 当前会话: {sid[:20]}...", token, account_id, base_url, from_user_id, session, ctx_token)
    
    if cmd.startswith("/rename ") or cmd.startswith("/重命名 "):
        new_title = text[text.index(" ") + 1:].strip()
        if not new_title or len(new_title) > 30:
            return await _reply_wechat_text("❌ 标题不能为空且不超过 30 个字符", token, account_id, base_url, from_user_id, session, ctx_token)
        sid = _get_active_session(uid, from_user_id)
        from backend.controller.wechat.config import _wx_session_titles
        _wx_session_titles[sid] = {"title": new_title, "last_active": time.time()}
        return await _reply_wechat_text(f"✅ 已重命名为：{new_title}", token, account_id, base_url, from_user_id, session, ctx_token)
    
    # /rm [序号] — 删除当前或指定会话
    if cmd == "/rm" or cmd == "/删除" or cmd == "/删除会话" or cmd == "/delete":
        sid = _get_active_session(uid, from_user_id)
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET status = 0 WHERE session_id = %s", (sid,))
            affected = cur.rowcount
        finally:
            conn.close()
        from backend.controller.wechat.config import _wx_session_titles, _wx_active_session
        _wx_session_titles.pop(sid, None)
        _wx_active_session.pop(_skey(uid, from_user_id), None)
        return await _reply_wechat_text(
            f"🗑️ 已删除当前会话（{affected} 条消息）\n发送任意消息将自动开启新对话",
            token, account_id, base_url, from_user_id, session, ctx_token,
        )
    
    # /rm 数字 / /删除 数字 — 按序号删除
    _rm_idx = 0
    if cmd.startswith("/rm ") and cmd[4:].strip().isdigit():
        _rm_idx = int(cmd[4:].strip())
    elif cmd.startswith("/删除 ") and cmd[4:].strip().isdigit():
        _rm_idx = int(cmd[4:].strip())
    elif cmd.startswith("/删除会话 ") and cmd[6:].strip().isdigit():
        _rm_idx = int(cmd[6:].strip())
    
    if _rm_idx > 0:
        sessions = _get_user_sessions(uid, 10)
        if not (1 <= _rm_idx <= len(sessions)):
            return await _reply_wechat_text(f"❌ 序号无效，范围 1-{len(sessions)}", token, account_id, base_url, from_user_id, session, ctx_token)
        target = sessions[_rm_idx - 1]
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET status = 0 WHERE session_id = %s", (target["session_id"],))
            affected = cur.rowcount
        finally:
            conn.close()
        from backend.controller.wechat.config import _wx_session_titles, _wx_active_session
        _wx_session_titles.pop(target["session_id"], None)
        if _get_active_session(uid, from_user_id) == target["session_id"]:
            _wx_active_session.pop(_skey(uid, from_user_id), None)
        return await _reply_wechat_text(
            f"🗑️ 已删除会话「{target['title']}」（{affected} 条消息）",
            token, account_id, base_url, from_user_id, session, ctx_token,
        )
    
    if cmd in ("/help", "/帮助", "/?"):
        return await _reply_wechat_text(
            "**📋 可用命令**\n"
            "- `/new` — 新对话\n"
            "- `/history` — 历史列表\n"
            "- `/1` `/2` … — 切换会话\n"
            "- `/rename 标题` — 重命名\n"
            "- `/rm [序号]` — 删除会话\n"
            "- `/status` — 查看当前会话\n"
            "- `/model` — 查看/切换模型\n"
            "- `/restart` — 重启前后端\n"
            "- `/restart-all` — 重启全部服务\n"
            "- `/stop` — 停止前后端\n"
            "- `/stop-all` — 停止全部服务\n"
            "- `/help` — 帮助",
            token, account_id, base_url, from_user_id, session, ctx_token,
        )
    
    # ── 系统控制命令（仅超管可用）──
    _PROJECT_ROOT = r"E:\PythonCode\AgentForge"
    _sys_cmds = {
        "/restart": (os.path.join(_PROJECT_ROOT, "restart.bat"), "前后端"),
        "/restart-all": (os.path.join(_PROJECT_ROOT, "restart-all.bat"), "全部服务"),
        "/stop": (os.path.join(_PROJECT_ROOT, "stop.bat"), "前后端"),
        "/stop-all": (os.path.join(_PROJECT_ROOT, "stop-all.bat"), "全部服务"),
    }
    if cmd in _sys_cmds:
        # 权限检查：需要 system.manage 权限
        from backend.permission.checker import has_permission
        if not has_permission(uid, "system.manage"):
            return await _reply_wechat_text("⛔ 需要系统管理权限（system.manage）", token, account_id, base_url, from_user_id, session, ctx_token)
        bat_path, label = _sys_cmds[cmd]
        try:
            import subprocess
            # 安全执行：使用列表参数避免命令注入，不使用 shell=True
            if os.name == "nt":
                # Windows: 通过 cmd.exe /c start 启动 bat，参数列表传递
                proc = subprocess.Popen(
                    ["cmd.exe", "/c", "start", f"AgentForge-{label}",
                     "cmd", "/c", f"cd /d {_PROJECT_ROOT} && {bat_path}"],
                )
            else:
                proc = subprocess.Popen(
                    [bat_path],
                    cwd=_PROJECT_ROOT,
                )
            
            # 保存进程引用到全局变量，防止僵尸进程
            from backend.controller.wechat.config import _system_processes
            _system_processes.append((proc, time.time(), label))
            
            # 启动后台任务监控进程完成
            asyncio.create_task(_monitor_process(proc, label))
            
            return await _reply_wechat_text(
                f"🚀 正在执行 {label}重启...\n脚本: {os.path.basename(bat_path)}",
                token, account_id, base_url, from_user_id, session, ctx_token,
            )
        except Exception as e:
            return await _reply_wechat_text(f"❌ 执行失败: {e}", token, account_id, base_url, from_user_id, session, ctx_token)
    
    # ── /model — 查看/切换模型 ──
    if cmd == "/model" or cmd == "/模型" or cmd.startswith("/model ") or cmd.startswith("/模型 "):
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, config_name, model_name, is_current, is_multimodal "
                "FROM model_configs WHERE enabled = 1 ORDER BY is_current DESC, id ASC"
            )
            models = cur.fetchall()
        finally:
            conn.close()
        
        if not models:
            return await _reply_wechat_text("⚠️ 没有可用的模型配置", token, account_id, base_url, from_user_id, session, ctx_token)
        
        arg = text[text.index(" ") + 1:].strip() if " " in text else ""
        if not arg:
            lines = ["**🤖 可用模型**"]
            for i, m in enumerate(models, 1):
                cur = " **← 当前**" if m.get("is_current") else ""
                mm = "📷" if m.get("is_multimodal") else "💬"
                name = m.get("config_name") or m.get("model_name") or f"模型{i}"
                lines.append(f"- {mm} {name}{cur}  `{i}`")
            lines += ["", "回复 `/model 序号` 切换"]
            return await _reply_wechat_text("\n".join(lines), token, account_id, base_url, from_user_id, session, ctx_token)
        
        # /model N → 切换
        target = None
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(models):
                target = models[idx]
        else:
            for m in models:
                name = (m.get("config_name") or m.get("model_name") or "").lower()
                if arg.lower() in name:
                    target = m
                    break
        
        if not target:
            return await _reply_wechat_text(f"❌ 未找到模型: {arg}\n输入 /model 查看列表", token, account_id, base_url, from_user_id, session, ctx_token)
        
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = 'chat' AND is_current = 1")
            cur.execute("UPDATE model_configs SET is_current = 1 WHERE id = %s", (target["id"],))
            conn.commit()
        finally:
            conn.close()
        new_name = target.get("config_name") or target.get("model_name")
        return await _reply_wechat_text(
            f"✅ 已切换到: {new_name}\n下次对话生效。",
            token, account_id, base_url, from_user_id, session, ctx_token,
        )
    
    # ── 普通消息 → LLM ──
    session_id = _get_active_session(uid, from_user_id)
    
    # ── 图片消息处理 ──
    pending_key = f"{uid}:{from_user_id}"
    
    # ── 先检查是否有缓存图片/文件（纯文字消息时合并） ──
    merged_file_contents: list[str] = []
    images_for_llm: list = []
    if text and not has_image:
        # 检查缓存图片
        pending_img = _pending_images.get(pending_key)
        if pending_img and (time.time() - pending_img["timestamp"]) < _PENDING_TIMEOUT:
            logger.info(f"[微信合并] 合并缓存图片 {len(pending_img['images'])} 张 + 文字: {text[:50]}...")
            images_for_llm = pending_img.pop("images", [])
            has_image = True
            del _pending_images[pending_key]
            # /send 快捷发送：无需文字描述，用默认看图指令
            if text.strip().lower() == "/send":
                logger.info("[微信合并] /send 快捷发送：使用默认图片描述指令")
                text = "请描述这张图片的内容"
        elif pending_img:
            del _pending_images[pending_key]
        # /send 但无有效缓存图片：明确提示
        if text.strip().lower() == "/send" and not has_image:
            return await _reply_wechat_text(
                "⚠️ 当前没有待发送的图片，请先发送图片",
                token, account_id, base_url, from_user_id, session, ctx_token,
            )
        
        # 检查缓存文件
        pending_file = _pending_files.get(pending_key)
        if pending_file and (time.time() - pending_file["timestamp"]) < _PENDING_TIMEOUT:
            logger.info(f"[微信合并] 合并缓存文件 {len(pending_file['files'])} 个 + 文字: {text[:50]}...")
            for f_info in pending_file["files"]:
                if f_info.get("content"):
                    merged_file_contents.append(
                        f"【用户发送的文件: {f_info['name']}】\n{f_info['content']}"
                    )
                else:
                    merged_file_contents.append(
                        f"【用户发送了文件: {f_info['name']}】（无法读取内容，路径: {f_info['path']}）"
                    )
            del _pending_files[pending_key]
        elif pending_file:
            del _pending_files[pending_key]
    
    # ── 文件消息处理（type=4，缓存模式：等文字合并）──
    if has_file and not has_image:
        from backend.config.paths import get_chat_uploads_dir
        output_dir = str(get_chat_uploads_dir(uid))
        cached_files = []
        for fi in file_items:
            fd = fi.get("file_item") or {}
            fname = fd.get("file_name") or "unnamed.bin"
            ok, saved_path, _ = await download_and_decrypt_file(session, fd, output_dir)
            if ok:
                content = _read_file_content(saved_path)
                cached_files.append({"name": fname, "path": saved_path, "content": content})
                logger.info(f"[微信文件] 接收成功: {fname} content_len={len(content) if content else 0}")
            else:
                logger.warning(f"[微信文件] 接收失败: {fname}")
        
        if not cached_files:
            return await _reply_wechat_text("❌ 文件接收失败", token, account_id, base_url, from_user_id, session, ctx_token)
        
        # 缓存文件，等待文字消息合并（30 秒内）
        _pending_files[pending_key] = {
            "files": cached_files,
            "timestamp": time.time(),
            "session_id": session_id,
        }
        # 同时注册到会话级持久化表（后续消息也能引用）
        if session_id not in _session_files:
            _session_files[session_id] = {"files": [], "last_access": time.time()}
        _session_files[session_id]["files"].extend(cached_files)
        _session_files[session_id]["last_access"] = time.time()
        logger.info(f"[微信文件] 会话 {session_id[:16]} 累计 {len(_session_files[session_id]['files'])} 个文件")
        
        file_names = ", ".join(f["name"] for f in cached_files)
        return await _reply_wechat_text(
            f"📎 已收到 {len(cached_files)} 个文件: {file_names}\n请在 30 秒内输入你的问题，我会结合文件内容回答。",
            token, account_id, base_url, from_user_id, session, ctx_token,
        )
    
    if has_image:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT model_name, is_multimodal FROM model_configs WHERE is_current = 1 AND enabled = 1")
            row = cur.fetchone()
        finally:
            conn.close()
        
        if not row:
            await _reply_wechat_text("⚠️ 未配置模型，请先在系统配置中设置", token, account_id, base_url, from_user_id, session, ctx_token)
            return
        
        if not row.get("is_multimodal"):
            await _reply_wechat_text(
                "⚠️ 当前模型不支持图片识别。\n请发送文字描述，或在系统配置中切换到支持多模态的模型。",
                token, account_id, base_url, from_user_id, session, ctx_token,
            )
            return
        
        # 纯图片消息（没有文字或只有默认文本）：先缓存并提示用户输入文字描述
        default_texts = ["[图片]", "[image]", "[Image]", "图片", "image"]
        if not text or text.lower() in default_texts:
            # 下载图片并缓存
            import aiohttp as _aiohttp
            cached_images = []
            for img_item in image_items:
                img_data = img_item.get("image_item") or img_item.get("file_item") or {}
                img_url = (
                    img_data.get("url") 
                    or img_data.get("cdn_url") 
                    or img_data.get("full_url") 
                    or (img_data.get("media") or {}).get("full_url") 
                    or ""
                )
                aeskey = img_data.get("aeskey") or ""
                if not img_url:
                    continue
                try:
                    timeout = _aiohttp.ClientTimeout(total=30)
                    async with session.get(img_url, timeout=timeout) as img_resp:
                        if img_resp.status == 200:
                            img_content = await img_resp.read()
                            if isinstance(img_content, str):
                                img_content = img_content.encode('latin-1')
                            elif not isinstance(img_content, bytes):
                                continue
                            
                            # AES-128-ECB 解密（图片路径：先 hex 后 base64，兼容两种格式）
                            if aeskey:
                                try:
                                    if len(aeskey) == 32:
                                        try:
                                            key = bytes.fromhex(aeskey)
                                        except ValueError:
                                            key = _parse_aes_key(aeskey)
                                    else:
                                        key = _parse_aes_key(aeskey)
                                    img_content = aes128_ecb_decrypt(img_content, key)
                                except Exception as e:
                                    logger.error(f"[微信图片] AES 解密失败: {e}")
                                    continue

                            # 安全处理：检测格式 + 大小检查 + 归一化
                            safe_url, err = process_image_safe(img_content, "")
                            if err:
                                logger.warning(f"[微信图片] 安全检查不通过: {err}")
                                continue
                            cached_images.append({
                                "data_url": safe_url,
                                "mime": safe_url.split(":")[1].split(";")[0] if ":" in safe_url else "image/png",
                            })
                except Exception as e:
                    logger.opt(exception=True).error(f"[微信图片] 下载异常: {e}")
            
            if cached_images:
                _pending_images[pending_key] = {
                    "images": cached_images,
                    "timestamp": time.time(),
                    "session_id": _get_active_session(uid, from_user_id),
                }
                await _reply_wechat_text(
                    f"📷 已收到 {len(cached_images)} 张图片\n请在 {_PENDING_TIMEOUT} 秒内发送文字描述，或发送 /send 直接发送",
                    token, account_id, base_url, from_user_id, session, ctx_token,
                )
            else:
                await _reply_wechat_text("⚠️ 图片下载失败，请重试", token, account_id, base_url, from_user_id, session, ctx_token)
            return
        
        # 有文字描述或已有缓存图片：下载图片并转 base64
        # 注意：合并缓存路径下 images_for_llm 已由 _pending_images 填充，
        # 不能在此重新初始化为空（否则会把缓存图片丢弃并误报"下载失败"）
        import aiohttp as _aiohttp
        new_images = []
        for img_item in image_items:
            img_data = img_item.get("image_item") or img_item.get("file_item") or {}
            # 图片 URL 可能在多处：url, cdn_url, full_url（顶层或 media 嵌套中）
            img_url = (
                img_data.get("url") 
                or img_data.get("cdn_url") 
                or img_data.get("full_url") 
                or (img_data.get("media") or {}).get("full_url") 
                or ""
            )
            # 提取 AES 密钥
            aeskey = img_data.get("aeskey") or ""
            
            if not img_url:
                logger.warning(f"[微信图片] 图片项中没有 URL: {img_data}")
                continue
            logger.info(f"[微信图片] 尝试下载: {img_url[:100]}, 有aeskey={bool(aeskey)}")
            try:
                timeout = _aiohttp.ClientTimeout(total=30)
                async with session.get(img_url, timeout=timeout) as img_resp:
                    logger.info(f"[微信图片] HTTP 状态: {img_resp.status}, Content-Type: {img_resp.headers.get('Content-Type')}")
                    if img_resp.status == 200:
                        # 确保读取的是二进制数据
                        img_content = await img_resp.read()
                        logger.info(f"[微信图片] 读取到 {len(img_content)} 字节, 类型: {type(img_content)}")
                        if isinstance(img_content, str):
                            # 如果返回字符串，转为 bytes
                            img_content = img_content.encode('latin-1')
                            logger.info(f"[微信图片] 字符串转字节后: {len(img_content)} 字节")
                        elif not isinstance(img_content, bytes):
                            logger.error(f"[微信图片] 未知的数据类型: {type(img_content)}")
                            continue
                        
                        # AES-128-ECB 解密（图片路径：先 hex 后 base64，兼容两种格式）
                        if aeskey:
                            try:
                                if len(aeskey) == 32:
                                    try:
                                        key = bytes.fromhex(aeskey)
                                    except ValueError:
                                        key = _parse_aes_key(aeskey)
                                else:
                                    key = _parse_aes_key(aeskey)
                                img_content = aes128_ecb_decrypt(img_content, key)
                                logger.info(f"[微信图片] AES-128-ECB 解密成功, 解密后 {len(img_content)} 字节")
                            except ImportError:
                                logger.error("[微信图片] 需要安装 pycryptodome: pip install pycryptodome")
                                continue
                            except Exception as e:
                                logger.opt(exception=True).error(f"[微信图片] AES 解密失败: {e}")
                                continue

                        # 安全处理：检测格式 + 大小检查 + 归一化
                        safe_url, err = process_image_safe(img_content, "")
                        if err:
                            logger.warning(f"[微信图片] 安全检查不通过: {err}")
                            continue
                        logger.info(f"[微信图片] 处理成功, data_url 长度: {len(safe_url)}")
                        new_images.append({
                            "data_url": safe_url,
                            "mime": safe_url.split(":")[1].split(";")[0] if ":" in safe_url else "image/png",
                        })
                    else:
                        logger.warning(f"[微信图片] 下载失败 HTTP {img_resp.status}: {img_url[:80]}")
            except Exception as e:
                logger.opt(exception=True).error(f"[微信图片] 下载异常: {e}")
        
        # 本消息新下载的图片并入 images_for_llm（合并缓存路径下为缓存图片）
        if new_images:
            images_for_llm = new_images
        
        if not images_for_llm:
            await _reply_wechat_text("⚠️ 图片下载失败，请重试", token, account_id, base_url, from_user_id, session, ctx_token)
            return
        
        logger.info(f"[微信图片] 下载了 {len(images_for_llm)} 张图片")
    elif not text:
        return
    
    # ── 将缓存文件 + 会话历史文件注入到提示词 ──
    effective_text = text or ""
    # 从会话文件注册表获取历史文件（排除已在 merged_file_contents 中的）
    session_file_entry = _session_files.get(session_id)
    session_file_list = session_file_entry["files"] if session_file_entry else []
    if session_file_entry:
        session_file_entry["last_access"] = time.time()
    if session_file_list:
        merged_names = set()
        for mc in merged_file_contents:
            # 提取已合并的文件名
            m = re.match(r"【用户发送的文件: (.+?)】", mc)
            if m:
                merged_names.add(m.group(1))
        hist_parts = []
        for f_info in session_file_list:
            if f_info["name"] in merged_names:
                continue  # 已在 pending 合并中，不重复
            if f_info.get("content"):
                hist_parts.append(f"【之前收到的文件: {f_info['name']}】\n{f_info['content']}")
            else:
                hist_parts.append(f"【之前收到的文件: {f_info['name']}】（无法读取内容）")
        if hist_parts:
            merged_file_contents = hist_parts + merged_file_contents
    
    if merged_file_contents:
        file_prefix = "\n\n".join(merged_file_contents)
        effective_text = f"{file_prefix}\n\n用户问题: {effective_text}"
        logger.info(f"[微信文件] 文件内容已注入, total_len={len(effective_text)}")
    
    # ── 发送「正在输入…」──
    typing_ticket = await _fetch_typing_ticket(session, base_url, token, from_user_id, ctx_token)
    await _send_typing_indicator(session, base_url, token, from_user_id, 1, typing_ticket)
    try:
        # 走 Hermes Agent（与 Web 一致：支持工具/技能/多轮记忆/多模态）
        # 调用 Hermes Agent
        result = await run_wechat_hermes(
            user_id=uid,
            thread_id=session_id,
            message=effective_text,
            images=images_for_llm if has_image else None,
            username=user["username"],
        )
        answer = result.get("final_response", "") or ""
        error = result.get("error", "") or ""
    finally:
        await _send_typing_indicator(session, base_url, token, from_user_id, 2, typing_ticket)

    if error and not answer:
        answer = f"⚠️ {error}"

    # ── 落库（source='wechat'，与 Web 同走 conversation_mapper）──
    persist_wechat_conversation(session_id, uid, text, answer)

    # ── 回填 trace 文本（与 Web 一致：用户问题 + AI 最终回复）──
    if answer:
        try:
            from backend.service.trace.trace_service import sync_trace_texts
            sync_trace_texts(session_id, text, answer)
        except Exception:
            pass

    if not answer:
        await _reply_wechat_text("⚠️ 未能生成回复，请稍后重试", token, account_id, base_url, from_user_id, session, ctx_token)
        return

    stripped = _strip_md(answer)
    chunks = _split_text_for_weixin(stripped)
    logger.info(f"[微信MD] raw={repr(answer[:800])}")
    logger.info(f"[微信MD] stripped={repr(stripped[:800])}")
    logger.info(f"[微信回复] answer_len={len(answer)} chunks={len(chunks)}")
    await _reply_wechat_chunks(chunks, token, account_id, base_url, from_user_id, session, ctx_token)
