"""superagent 凭证与仓库地址（T2，方案 §6 Git 发布）。

原则：
- 同一个 parser 服务于保存、prepare、publish 三个边界；只接受规范 HTTPS，
  拒绝 userinfo/控制字符/查询串/选项式分支注入；
- git 远端一律无凭证 URL；push/fetch 认证经 credential helper（脚本不含
  密钥，token 经 git 子进程环境变量注入、进程结束即回收），token 不进
  URL、不进 .git/config、不进命令参数；
- 所有错误文本出口统一过 sanitize_text，URL userinfo、token、authorization 头脱敏。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# host 白名单：第一版只支持 GitHub HTTPS（Gitee/SSH 保留策略见方案 §3 P1）
ALLOWED_HOSTS = frozenset({"github.com"})
REPO_URL_RE = re.compile(r"^https://github\.com/", re.I)
_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REPO_SUFFIX_RE = re.compile(r"\.git$", re.I)
# 控制字符与 shell 元字符（URL 里出现即拒绝）
_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f\s`$;&|<>\\!'\"^~*?\[\]{}]")

CRED_ENV = "EASYCHAT_GIT_CRED"


@dataclass(frozen=True, slots=True)
class RepoRef:
    """规范化仓库引用；origin URL 一律无凭证。"""

    host: str
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def origin_url(self) -> str:
        return f"https://{self.host}/{self.full_name}.git"


class RepoUrlError(ValueError):
    """仓库地址非法（统一错误文本，不回显原始输入）。"""


def parse_repo_url(repo_url: str) -> RepoRef:
    """严格解析 HTTPS 仓库地址；任何不合规形式抛 RepoUrlError。

    只容忍首尾空格（配置手误）；换行/制表等控制字符出现在任何位置都拒绝。
    """
    raw = (repo_url or "").strip(" ")
    if not raw or len(raw) > 300 or _UNSAFE_RE.search(raw):
        raise RepoUrlError("仓库地址非法：为空、过长或包含不安全字符")
    parts = urlsplit(raw)
    if parts.scheme != "https":
        raise RepoUrlError("仓库地址必须是 https://（SSH/git@ 形式不再支持）")
    if parts.username or parts.password:
        raise RepoUrlError("仓库地址不得携带用户名/密码（凭证经受控 helper 注入）")
    if parts.query or parts.fragment:
        raise RepoUrlError("仓库地址不得携带查询串或片段")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise RepoUrlError("仓库 host 仅支持 github.com")
    if parts.port is not None:
        raise RepoUrlError("仓库地址不得携带自定义端口")
    path = _REPO_SUFFIX_RE.sub("", parts.path.rstrip("/"))
    segments = [s for s in path.split("/") if s]
    if len(segments) != 2 or not _REPO_PATH_RE.match("/".join(segments)):
        raise RepoUrlError("仓库路径必须是 owner/repo 形式")
    owner, repo = segments
    if owner.startswith(".") or repo.startswith("."):
        raise RepoUrlError("仓库路径段不得以点开头")
    return RepoRef(host=host, owner=owner, repo=repo)


def sanitize_text(text: str, *, tokens: tuple[str, ...] = ()) -> str:
    """统一脱敏出口：URL userinfo、已 token 化的凭证明文、authorization 头。"""
    out = text or ""
    # URL userinfo：scheme://user:pass@host → scheme://***:***@
    out = re.sub(r"(https?://)([^/\s:@]+):([^/\s:@]+)@", r"\1***:***@", out)
    out = re.sub(r"(https?://)([^/\s:@]+)@", r"\1***@", out)
    # authorization 头
    out = re.sub(r"(?i)(authorization\s*[:=]\s*)(\S+)", r"\1***", out)
    for token in tokens:
        if token:
            out = out.replace(token, "***")
    return out


# ---- credential helper -------------------------------------------------------
#
# helper 脚本本身不含任何密钥；git 调用它时经 stdin 发送协议请求（host=...），
# 脚本从环境变量 CRED_ENV 读取 token 输出 username/password。token 只存在于
# git 子进程（及其 helper 子进程）的环境里，进程结束即回收。


def credential_helper_source() -> str:
    """返回 helper 脚本源码（无密钥；调用方写到私有临时目录并按需删除）。"""
    return (
        "import os, sys\n"
        "host = ''\n"
        "for line in sys.stdin.read().splitlines():\n"
        "    key, _, value = line.partition('=')\n"
        "    if key == 'host':\n"
        "        host = value.strip().lower()\n"
        f"token = os.environ.get({CRED_ENV!r}, '')\n"
        "if token and host in {'github.com', 'www.github.com'}:\n"
        "    sys.stdout.write('username=x-access-token\\npassword=' + token + '\\n')\n"
        "sys.stdout.flush()\n"
    )


def credential_helper_gitconfig(helper_path: str) -> tuple[str, str]:
    """git -c 参数：credential.helper=python <helper_path>（argv 不含密钥）。"""
    from pathlib import Path

    quoted = str(Path(helper_path).resolve()).replace('"', '')
    return ("-c", f"credential.helper=python {quoted}")


def git_auth_env(token: str) -> dict[str, str]:
    """git 子进程环境：附加 CRED_ENV；空 token 时返回空覆盖表。"""
    if not token:
        return {}
    return {CRED_ENV: token}


class TokenCredentialProvider:
    """worker 内存中的 token 持有者；只向 git 子进程环境与 helper 供给。"""

    def __init__(self, token: str) -> None:
        self._token = token

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    @property
    def token(self) -> str:
        return self._token
