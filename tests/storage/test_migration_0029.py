"""角色迁移保留旧角色含义并恢复可验证的微信会话来源。"""
from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing

import pytest

from backend.modules.channels.repository import ChannelRepository
from backend.platform.migrations import MIGRATIONS_DIR
from backend.platform.sqlite import Database, run_migrations


def test_persona_upgrade_restores_verified_routes_and_preserves_legacy_default(tmp_path):
    before_dir = tmp_path / "before"
    before_dir.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if source.name < "0029":
            shutil.copy2(source, before_dir / source.name)

    before = Database(tmp_path / "before.db")
    run_migrations(before, migrations_dir=before_dir)
    timestamp = "2026-11-20T00:00:00+00:00"
    with before.transaction() as conn:
        conn.executemany(
            "INSERT INTO users(id, username, password, created_at, updated_at) VALUES(?,?,'unused',?,?)",
            [(1, "old_owner", timestamp, timestamp), (2, "other_owner", timestamp, timestamp)],
        )
        conn.execute(
            "INSERT INTO channel_accounts(id, platform, account_id, created_at, updated_at) "
            "VALUES('account', 'wechat', 'bot', ?, ?)",
            (timestamp, timestamp),
        )
        conn.executemany(
            "INSERT INTO sessions(id, owner_id, source, channel_account_id, created_at, updated_at) "
            "VALUES(?, 1, 'wechat', 'account', ?, ?)",
            [(sid, timestamp, timestamp) for sid in ("previous", "current", "unproven")],
        )
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, source, channel_account_scope, "
            "client_message_id, status, created_at) VALUES('run', 1, 'previous', 'wechat', "
            "'account', 'msg', 'completed', ?)", (timestamp,),
        )
        conn.execute(
            "INSERT INTO channel_session_cursors(platform, account_id, external_user_id, external_chat_id, "
            "session_id, updated_at, context_token) VALUES('wechat','bot','wx_user','chat','current',?,'current-token')",
            (timestamp,),
        )
        conn.execute(
            "INSERT INTO channel_events(id, platform, account_id, external_event_id, received_at, "
            "session_id, run_id, state, envelope_json) "
            "VALUES('event','wechat','bot','msg',?,'previous','run','processed',?)",
            (timestamp, json.dumps({
                "account_pk": "account", "external_user_id": "wx_user",
                "external_chat_id": "chat", "context_token": "original-token",
            })),
        )

    restored = Database(tmp_path / "restored.db")
    with closing(before.connect()) as source, closing(restored.connect()) as target:
        source.backup(target)
    assert "0029" in restored.migrate()
    assert not restored.migrate()

    channels = ChannelRepository(restored)
    assert channels.find_session_route("previous")["context_token"] == "original-token"
    assert channels.find_session_route("current")["context_token"] == "current-token"
    assert channels.find_session_route("unproven") is None
    with closing(restored.connect()) as conn:
        assert all(row["persona_id"] is None for row in conn.execute("SELECT persona_id FROM sessions"))
        assert conn.execute("SELECT persona_id FROM runs WHERE id='run'").fetchone()["persona_id"] is None

    with restored.transaction() as conn:
        conn.execute(
            "INSERT INTO persona_catalog(id, owner_id, name, name_key, instruction, created_at, updated_at) "
            "VALUES('persona', 2, 'Other', 'other', 'Use examples', ?, ?)", (timestamp, timestamp),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sessions(id, owner_id, persona_id, created_at, updated_at) "
                "VALUES('invalid', 1, 'persona', ?, ?)", (timestamp, timestamp),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE sessions SET persona_id='persona' WHERE id='previous'")
