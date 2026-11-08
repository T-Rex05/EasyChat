"""T2 凭证与仓库解析回归：严格 parser、脱敏出口、credential helper 无泄漏。"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from backend.modules.superagent.credentials import (
    ALLOWED_HOSTS,
    RepoUrlError,
    credential_helper_gitconfig,
    credential_helper_source,
    git_auth_env,
    parse_repo_url,
    sanitize_text,
)


@pytest.mark.parametrize("url", [
    "https://github.com/foo/bar.git",
    "https://github.com/foo/bar",
])
def test_parse_repo_url_accepts_normalized_https(url: str) -> None:
    ref = parse_repo_url(url)
    assert ref.full_name == "foo/bar"
    assert ref.origin_url == "https://github.com/foo/bar.git"
    assert ref.host in ALLOWED_HOSTS


@pytest.mark.parametrize("url", [
    "https://www.github.com/foo/bar.git",             # www 变体（严格白名单外）
    "https://token@github.com/foo/bar.git",           # userinfo
    "https://user:pass@github.com/foo/bar.git",       # userinfo 完整
    "git@github.com:foo/bar.git",                     # SSH 形式
    "http://github.com/foo/bar.git",                  # 非 https
    "https://gitee.com/foo/bar",                      # 非 GitHub（第一版白名单外）
    "https://github.com/foo/bar?token=x",             # 查询串
    "https://github.com/foo/bar#frag",                # 片段
    "https://github.com:8443/foo/bar.git",            # 自定义端口
    "https://github.com/foo/bar/extra",               # 路径深度
    "https://github.com/justone",                     # 路径不足
    "https://evil.com\\@github.com/foo/bar",          # 反斜杠（不安全字符）
    "https://github.com/foo/bar\n",                   # 控制字符
    "https://github.com/.foo/bar.git",                # 段以点开头
    "",                                                # 空
])
def test_parse_repo_url_rejects_unsafe_forms(url: str) -> None:
    with pytest.raises(RepoUrlError):
        parse_repo_url(url)


def test_sanitize_text_strips_userinfo_tokens_and_auth_headers() -> None:
    text = (
        "clone https://ghp_abc123@github.com/foo/bar.git failed; "
        "https://user:secret@github.com/x/y.git; "
        "Authorization: Bearer ghp_real_token; "
        "plain ghp_mention_here"
    )
    out = sanitize_text(text, tokens=("ghp_real_token", "ghp_mention_here"))
    assert "ghp_abc123" not in out
    assert "user:secret" not in out
    assert "ghp_real_token" not in out
    assert "ghp_mention_here" not in out
    assert "***" in out


def test_credential_helper_source_contains_no_token_and_responds_by_host() -> None:
    source = credential_helper_source()
    assert "ghp_" not in source  # 脚本本身不含任何密钥
    # 真实执行 helper：github.com 响应，其他 host 不响应
    env = dict(os.environ)
    env["EASYCHAT_GIT_CRED"] = "ghp_synthetic_token_abcdef"
    result = subprocess.run(
        [sys.executable, "-c", source],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert result.returncode == 0
    assert "username=x-access-token" in result.stdout
    assert "password=ghp_synthetic_token_abcdef" in result.stdout
    other = subprocess.run(
        [sys.executable, "-c", source],
        input="protocol=https\nhost=gitlab.com\n\n",
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert other.stdout.strip() == ""


def test_git_auth_args_never_carry_token(tmp_path) -> None:
    helper = tmp_path / "cred_helper.py"
    helper.write_text(credential_helper_source(), encoding="utf-8")
    key, value = credential_helper_gitconfig(str(helper))
    assert key == "-c"
    assert "ghp_" not in value
    assert "cred_helper.py" in value
    env = git_auth_env("ghp_synthetic")
    assert env == {"EASYCHAT_GIT_CRED": "ghp_synthetic"}
    assert git_auth_env("") == {}
