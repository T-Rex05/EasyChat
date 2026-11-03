"""主机白名单服务 — 终端远程执行安全拦截（借鉴 Eyes host_whitelist）

白名单为空或主机不在名单内时，ssh/scp 等远程执行命令一律拦截（secure-by-default）。
"""
import re
from datetime import datetime
from typing import List, Optional

from backend.utils.log_utils import log

logger = log

_SSH_TOKEN_RE = re.compile(r"(?:^|\s)(ssh|scp)\s+")
_OPT_RE = re.compile(r"^-[^\s]*$")
# 带值的 ssh 选项：命中后跳过其后的值 token（防把端口/密钥路径误判为目标主机）
_FLAGS_WITH_VALUE = {"p", "i", "o", "l", "F", "c", "m", "b", "e", "J", "S", "w", "D", "L", "R", "E", "I"}


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def _encrypt_secret(secret: str) -> str:
    """AES-256-GCM 加密凭据（与邮箱密码同机制）；空串原样返回。"""
    secret = (secret or "").strip()
    if not secret:
        return ""
    try:
        from backend.utils.crypto_utils import encrypt
        return encrypt(secret)
    except Exception:
        return secret  # 加密不可用时明文兜底（与项目其他凭据行为一致）


def _decrypt_secret(secret: str) -> str:
    secret = secret or ""
    if not secret:
        return ""
    try:
        from backend.utils.crypto_utils import decrypt
        return decrypt(secret)
    except Exception:
        return secret  # 明文兼容


def get_host_auth(host: str) -> dict:
    """取主机的认证配置：{auth_method, auth_secret(已解密), access_user}；无记录返回空。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT access_user, auth_method, auth_secret FROM host_whitelist "
            "WHERE host_identifier = %s AND status = 1 AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1",
            (host,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else [r for r in (cur or [])]
        if not rows:
            return {}
        row = dict(rows[0])
        return {
            "access_user": row.get("access_user") or "",
            "auth_method": (row.get("auth_method") or "none").strip().lower(),
            "auth_secret": _decrypt_secret(row.get("auth_secret") or ""),
        }
    finally:
        conn.close()


def inject_ssh_auth(command: str, host: str) -> str:
    """把白名单主机的凭据注入 ssh/scp 命令（审批通过后执行前调用，密码不进审批卡片）。

    password → 每个 ssh/scp 前注入 sshpass -p；key → 注入 -i 参数；none → 原样。
    需要主机安装 sshpass（password 模式）。"""
    try:
        auth = get_host_auth(host)
    except Exception:
        return command
    if not auth:
        return command
    method = auth.get("auth_method") or "none"
    secret = auth.get("auth_secret") or ""
    if method == "password" and secret:
        esc = secret.replace("\\", "\\\\").replace("'", "'\\''")
        return re.sub(r"(^|\s)(ssh|scp)\s+", r"\1sshpass -p '" + esc + r"' \2 ", command)
    if method == "key" and secret:
        key_arg = secret if re.match(r"^[A-Za-z0-9_./\\~-]+$", secret) else ""
        if key_arg:
            return re.sub(r"(^|\s)(ssh|scp)\s+", r"\1\2 -i '" + key_arg + r"' ", command)
    return command


def execute_ssh_via_paramiko(command: str, host: str, timeout: int = 60) -> Optional[dict]:
    """使用 paramiko 直接执行 SSH 命令（跨平台，不依赖 sshpass）。

    解析 ssh user@host "command" 格式，用 paramiko 连接并执行，返回 {"output": ..., "exit_code": ...}。
    如果不是 ssh 命令或解析失败，返回 None（让调用方回退到原始执行路径）。
    """
    # 解析 ssh 命令：ssh [options] user@host "command"
    # 简化处理：提取 user@host 和要执行的远程命令
    ssh_match = re.match(r"ssh\s+(?:-[^\s]+\s+(?:[^\s]+\s+)?)*(\S+?@)?(\S+)\s+(.+)", command)
    if not ssh_match:
        return None

    user_host = (ssh_match.group(1) or "root@") + ssh_match.group(2)
    remote_cmd = ssh_match.group(3).strip().strip('"').strip("'")

    # 解析 user 和 host
    if "@" in user_host:
        user, hostname = user_host.split("@", 1)
    else:
        user, hostname = "root", user_host

    # 获取认证信息
    try:
        auth = get_host_auth(hostname)
    except Exception:
        auth = None

    if not auth:
        return None

    method = auth.get("auth_method") or "none"
    secret = auth.get("auth_secret") or ""
    port = auth.get("access_port") or 22

    try:
        import paramiko
    except ImportError:
        logger.warning("paramiko 未安装，无法执行 SSH 命令")
        return None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        connect_kwargs = {
            "hostname": hostname,
            "port": port,
            "username": user,
            "timeout": timeout,
            "banner_timeout": timeout,
            "auth_timeout": timeout,
        }

        if method == "password" and secret:
            connect_kwargs["password"] = secret
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        elif method == "key" and secret:
            import os
            key_path = secret.strip()
            if not os.path.isfile(key_path):
                return {"output": f"私钥文件不存在: {key_path}", "exit_code": 1}
            try:
                pkey = paramiko.RSAKey.from_private_key_file(key_path)
            except Exception:
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
                except Exception:
                    try:
                        pkey = paramiko.ECDSAKey.from_private_key_file(key_path)
                    except Exception:
                        return {"output": f"无法解析私钥文件: {key_path}", "exit_code": 1}
            connect_kwargs["pkey"] = pkey
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False

        client.connect(**connect_kwargs)
        stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=timeout)
        output = stdout.read().decode("utf-8", errors="replace")
        err_output = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()

        if err_output:
            output = output + "\n" + err_output if output else err_output

        return {"output": output.strip(), "exit_code": exit_code}

    except paramiko.AuthenticationException:
        return {"output": f"SSH 认证失败：用户名/密码/密钥不正确（{user}@{hostname}）", "exit_code": 1}
    except paramiko.SSHException as e:
        return {"output": f"SSH 协议错误：{e}", "exit_code": 1}
    except Exception as e:
        return {"output": f"SSH 执行失败：{type(e).__name__}: {e}", "exit_code": 1}
    finally:
        try:
            client.close()
        except Exception:
            pass


def _host_from_token(token: str) -> str:
    """token → 主机名：去掉 user@ 前缀与远程路径冒号。"""
    host = token.split("@")[-1]
    host = host.split(":", 1)[0]
    return host.rstrip(".").strip()


def extract_ssh_targets(command: str) -> List[str]:
    """从命令中提取 ssh/scp 的目标主机（user@host 取 host 部分）。

    ssh：跳过选项及其取值，第一个非选项 token 为目标；
    scp：取含「:」的远程路径 token（即最后一个参数）中的主机部分。
    """
    targets: List[str] = []
    if not command:
        return targets
    for m in _SSH_TOKEN_RE.finditer(command):
        cmd_kind = m.group(1)
        tokens = [t for t in re.split(r"[\s&|;]+", command[m.end():]) if t]
        if cmd_kind == "scp":
            for token in tokens:
                if ":" in token:
                    host = _host_from_token(token)
                    if host and re.match(r"^[A-Za-z0-9_.-]+$", host):
                        targets.append(host)
                    break
            continue
        skip_next_value = False
        for token in tokens:
            if skip_next_value:
                skip_next_value = False
                continue
            if _OPT_RE.match(token):
                flag = token.lstrip("-").split("=", 1)[0]
                if flag in _FLAGS_WITH_VALUE and "=" not in token:
                    skip_next_value = True
                continue
            if token.startswith("=") or token.startswith(":"):
                continue
            host = _host_from_token(token)
            if host and re.match(r"^[A-Za-z0-9_.-]+$", host):
                targets.append(host)
            break  # 每段 ssh 只取目标
    return targets


def user_has_whitelist_perm(user_id) -> bool:
    """用户是否有主机白名单权限（需要 system.manage 权限）。"""
    try:
        from backend.permission.checker import has_permission
        return has_permission(int(user_id), "system.manage")
    except Exception:
        return False


def is_host_allowed(host: str, user_id=None) -> bool:
    """主机是否在白名单（status=1 且未过期），且用户持有 system.manage 权限。
    白名单为空或用户无权限 → False。user_id=None 时仅检查白名单（管理场景）。"""
    host = (host or "").strip()
    if not host:
        return False
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT id FROM host_whitelist WHERE host_identifier = %s AND status = 1 "
            "AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1",
            (host,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else [r for r in (cur or [])]
        if not rows:
            return False
    except Exception:
        return False  # DB 异常时拒绝（secure-by-default）
    finally:
        conn.close()
    if user_id is None:
        return True
    return user_has_whitelist_perm(user_id)


def list_hosts() -> list:
    """列出白名单（凭据脱敏：只返回是否已配置）。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT id, host_identifier, access_user, access_port, remark, status, auth_method, created_at, updated_at FROM host_whitelist ORDER BY id DESC")
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        result = []
        for r in rows:
            item = dict(r)
            secret_configured = bool(_get_secret_configured(item.get("id")))
            item["auth_configured"] = secret_configured
            result.append(item)
        return result
    finally:
        conn.close()


def _get_secret_configured(host_id: int) -> bool:
    conn = _conn()
    try:
        cur = conn.execute("SELECT auth_secret FROM host_whitelist WHERE id = %s", (int(host_id),))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else [r for r in (cur or [])]
        return bool(rows and rows[0].get("auth_secret"))
    except Exception:
        return False
    finally:
        conn.close()


def add_host(host_identifier: str, access_user: str = "", access_port: int = 22,
             remark: str = "", auth_method: str = "none", auth_secret: str = "",
             created_by: Optional[int] = None) -> dict:
    host_identifier = (host_identifier or "").strip()
    if not host_identifier:
        raise ValueError("主机标识不能为空")
    method = (auth_method or "none").strip().lower()
    if method not in ("password", "key", "none"):
        method = "none"
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO host_whitelist (host_identifier, access_user, access_port, remark, auth_method, auth_secret, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (host_identifier, access_user, int(access_port), remark, method, _encrypt_secret(auth_secret), created_by),
        )
        conn.commit()
        return {"id": cur.lastrowid, "host_identifier": host_identifier}
    finally:
        conn.close()


def update_host(host_id: int, **fields) -> bool:
    allowed = {"host_identifier", "access_user", "access_port", "remark", "status", "auth_method"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    # 凭据独立处理：仅当传入非空 auth_secret 时更新（空串=保持不变）
    if fields.get("auth_secret"):
        updates["auth_secret"] = _encrypt_secret(fields["auth_secret"])
    if fields.get("auth_method") and fields["auth_method"] not in ("password", "key", "none"):
        updates.pop("auth_method", None)
    if not updates:
        return False
    sets = ", ".join(f"{k} = %s" for k in updates)
    conn = _conn()
    try:
        cur = conn.execute(f"UPDATE host_whitelist SET {sets} WHERE id = %s", list(updates.values()) + [int(host_id)])
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_host(host_id: int) -> bool:
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM host_whitelist WHERE id = %s", (int(host_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_user_accessible_hosts(user_id: int) -> list:
    """获取用户可访问的白名单主机列表（脱敏，不返回密码）。
    
    返回格式：[{host_identifier, access_user, access_port, auth_method, remark}]
    """
    if not user_has_whitelist_perm(user_id):
        return []
    
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT host_identifier, access_user, access_port, auth_method, remark "
            "FROM host_whitelist WHERE status = 1 "
            "AND (expires_at IS NULL OR expires_at > NOW()) "
            "ORDER BY host_identifier"
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


def format_hosts_for_prompt(hosts: list) -> str:
    """将主机列表格式化为系统提示词片段。"""
    if not hosts:
        return ""
    
    lines = [
        "\n\n## 可访问的服务器（主机白名单）",
        "你可以通过 SSH 连接以下服务器执行命令。每条命令仍需用户审批。",
        "",
        "| 主机 | 端口 | 登录用户 | 认证方式 | 备注 |",
        "|------|------|----------|----------|------|"
    ]
    
    for h in hosts:
        host = h.get("host_identifier", "")
        port = h.get("access_port", 22)
        user = h.get("access_user", "root") or "root"
        auth = h.get("auth_method", "none")
        remark = h.get("remark", "") or "-"
        
        auth_label = {"password": "密码", "key": "私钥", "none": "免密"}.get(auth, auth)
        lines.append(f"| {host} | {port} | {user} | {auth_label} | {remark} |")
    
    lines.extend([
        "",
        "**使用方式：** 执行 `ssh user@host \"command\"` 或 `scp` 命令。",
        "**注意：** 只能访问上述列表中的主机，其他主机会被安全拦截。"
    ])
    
    return "\n".join(lines)


def test_ssh_connection(host_identifier: str, access_user: str = "",
                        access_port: int = 22, auth_method: str = "none",
                        auth_secret: str = "", timeout: int = 10) -> dict:
    """测试 SSH 连通性（paramiko），返回 {"ok": bool, "message": str}。"""
    host_identifier = (host_identifier or "").strip()
    if not host_identifier:
        return {"ok": False, "message": "主机标识不能为空"}
    access_user = (access_user or "").strip() or "root"
    access_port = int(access_port) or 22
    method = (auth_method or "none").strip().lower()

    # 如果 auth_secret 为空且是已有主机，从数据库取已保存的凭据
    if not auth_secret and method != "none":
        try:
            stored = get_host_auth(host_identifier)
            if stored:
                auth_secret = stored.get("auth_secret", "")
                if not access_user:
                    access_user = stored.get("access_user", "") or "root"
        except Exception:
            pass

    try:
        import paramiko
    except ImportError:
        return {"ok": False, "message": "服务端未安装 paramiko，无法执行 SSH 测试"}

    import time
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    t0 = time.time()
    try:
        connect_kwargs = {
            "hostname": host_identifier,
            "port": access_port,
            "username": access_user,
            "timeout": timeout,
            "banner_timeout": timeout,
            "auth_timeout": timeout,
        }
        if method == "password" and auth_secret:
            connect_kwargs["password"] = auth_secret
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        elif method == "key" and auth_secret:
            # auth_secret 是私钥文件路径
            import os
            key_path = auth_secret.strip()
            if not os.path.isfile(key_path):
                return {"ok": False, "message": f"私钥文件不存在: {key_path}"}
            try:
                pkey = paramiko.RSAKey.from_private_key_file(key_path)
            except Exception:
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
                except Exception:
                    try:
                        pkey = paramiko.ECDSAKey.from_private_key_file(key_path)
                    except Exception:
                        return {"ok": False, "message": f"无法解析私钥文件: {key_path}（不支持的密钥格式）"}
            connect_kwargs["pkey"] = pkey
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False
        # method == "none": 依赖系统默认密钥 / ssh-agent

        client.connect(**connect_kwargs)
        t_connect = time.time()
        # 连接成功 → 尝试执行一个简单命令确认权限
        stdin, stdout, stderr = client.exec_command("echo __AGENTFORGE_SSH_TEST__", timeout=5)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        t_total = time.time()
        connect_ms = round((t_connect - t0) * 1000)
        total_ms = round((t_total - t0) * 1000)
        if "__AGENTFORGE_SSH_TEST__" in output:
            return {"ok": True, "message": f"连接成功 ✓ （{access_user}@{host_identifier}:{access_port}）命令执行正常 | 握手 {connect_ms}ms，总耗时 {total_ms}ms"}
        else:
            return {"ok": True, "message": f"SSH 连接成功 ✓，但命令执行异常（exit={exit_code}）| 握手 {connect_ms}ms，总耗时 {total_ms}ms"}
    except paramiko.AuthenticationException:
        return {"ok": False, "message": f"认证失败：用户名/密码/密钥不正确（{access_user}@{host_identifier}）"}
    except paramiko.SSHException as e:
        return {"ok": False, "message": f"SSH 协议错误：{e}"}
    except OSError as e:
        msg = str(e)
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            return {"ok": False, "message": f"连接超时：无法在 {timeout}s 内到达 {host_identifier}:{access_port}"}
        if "refused" in msg.lower():
            return {"ok": False, "message": f"连接被拒绝：{host_identifier}:{access_port} 可能未开放 SSH 服务"}
        if "no route" in msg.lower() or "unreachable" in msg.lower():
            return {"ok": False, "message": f"网络不可达：无法路由到 {host_identifier}"}
        return {"ok": False, "message": f"网络错误：{msg}"}
    except Exception as e:
        return {"ok": False, "message": f"测试失败：{type(e).__name__}: {e}"}
    finally:
        try:
            client.close()
        except Exception:
            pass