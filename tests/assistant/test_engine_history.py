"""引擎历史恢复测试：真实临时 state.db，验证归属映射、恢复顺序、压缩容忍。

UI 投影（conversations）不得被当作第二套模型历史拼接（架构 §5.1）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.platform.sqlite import Database
from backend.runtime.hermes.sessions import SessionMapper
from backend.shared.errors import NotFoundError


@pytest.fixture
def env(tmp_path):
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    db = Database(tmp_path / "app.db")
    db.migrate()
    mapper = SessionMapper(db, hermes_home=hermes_home)
    yield mapper, db, hermes_home
    db.close()


def _engine_db(hermes_home: Path):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "hermes"))
    from hermes_state import SessionDB

    return SessionDB(db_path=hermes_home / "state.db")


def test_bind_and_resolve_with_owner_isolation(env):
    mapper, db, _ = env
    now = "2026-01-01T00:00:00Z"
    with db.transaction() as conn:
        conn.execute("INSERT INTO users(id, username, password, created_at, updated_at) VALUES(1,'u1','p',?,?)", (now, now))
        conn.execute("INSERT INTO users(id, username, password, created_at, updated_at) VALUES(2,'u2','p',?,?)", (now, now))
        conn.execute("INSERT INTO sessions(id, owner_id, created_at, updated_at) VALUES('sess_a', 1, ?, ?)", (now, now))
    assert mapper.resolve(1, "sess_a") is None  # 尚未绑定
    mapper.bind("sess_a", "engine-abc")
    assert mapper.resolve(1, "sess_a") == "engine-abc"
    with pytest.raises(NotFoundError):
        mapper.resolve(2, "sess_a")  # 他人会话不可解析（owner条件）


def test_recover_conversation_order_from_state_db(env):
    mapper, db, hermes_home = env
    engine = _engine_db(hermes_home)
    sid = "recover-test-1"
    engine.create_session(sid, source="test")
    engine.append_message(sid, "user", "上周担心什么来着")
    engine.append_message(sid, "assistant", "你上周担心直播的数据")
    engine.append_message(sid, "user", "对，后来呢")
    engine.append_message(sid, "assistant", "后来你决定复盘")
    engine.close()

    history = mapper.recover_conversation(sid)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "上周担心什么来着"),
        ("assistant", "你上周担心直播的数据"),
        ("user", "对，后来呢"),
        ("assistant", "后来你决定复盘"),
    ]


def test_compaction_old_session_id_still_resolvable(env):
    """压缩轮换后，旧 id 前缀仍解析到当前会话（不拼接重复历史）。"""
    mapper, db, hermes_home = env
    engine = _engine_db(hermes_home)
    sid = "compact-test-1"
    engine.create_session(sid, source="test")
    engine.append_message(sid, "user", "第一条")
    engine.append_message(sid, "assistant", "第一条回复")
    # 模拟压缩：旧消息软归档，追加压缩后的新消息
    compacted = [
        {"role": "user", "content": "第一条"},
        {"role": "assistant", "content": "第一条回复"},
    ]
    engine.archive_and_compact(sid, compacted)
    engine.append_message(sid, "user", "压缩后的新消息")
    engine.close()

    candidates = mapper.session_id_candidates(sid)
    assert sid in candidates
    history = mapper.recover_conversation(sid)
    contents = [m["content"] for m in history]
    assert contents.count("第一条") == 1  # 软归档消息不被重复计入（active=1过滤）
    assert "压缩后的新消息" in contents


def test_unknown_session_returns_empty_not_error(env):
    mapper, db, hermes_home = env
    assert mapper.recover_conversation("") == []
    assert mapper.recover_conversation("no-such-engine-session") == []


def test_state_db_unavailable_raises_storage_error(tmp_path):
    """state.db 不可打开（如被目录占位）→ 明确 StorageUnavailableError。

    文件缺失是合法的新安装状态（无历史），不在此测试范围。
    """
    hermes_home = tmp_path / "broken_home"
    hermes_home.mkdir()
    (hermes_home / "state.db").mkdir()  # state.db 被目录占位 → sqlite 打不开
    mapper = SessionMapper(Database(tmp_path / "app.db"), hermes_home=hermes_home)
    from backend.shared.errors import StorageUnavailableError

    with pytest.raises(StorageUnavailableError):
        mapper.recover_conversation("whatever")
