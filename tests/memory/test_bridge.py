"""Hermes MemoryProvider 桥接测试：只走公开接口、无结果不编造、来源可见。"""
from __future__ import annotations

from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.runtime.hermes.memory_bridge import MemoryBridge
from tests.memory.helpers import make_memory_rig, owner_a


def test_prefetch_without_memory_says_no_result(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    bridge = MemoryBridge(service, user)
    text = bridge.prefetch("我喜欢什么")
    assert "无相关记忆" in text
    assert "喜欢" not in text.replace("无相关记忆", "")
    rig.db.close()


def test_prefetch_includes_content_and_sources(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    service.remember(user, MemoryCandidate(
        kind="preference", content="喜欢黑咖啡，不加糖", confidence=0.9,
        source_refs=(SourceRef(kind="message", ref="msg-coffee"),),
    ))
    text = MemoryBridge(service, user).prefetch("咖啡")
    assert "黑咖啡" in text
    assert "message:msg-coffee" in text
    assert "【相关记忆】" in text
    rig.db.close()


def test_bridge_remember_goes_through_service(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    bridge = MemoryBridge(service, user)
    record = bridge.remember(MemoryCandidate(
        kind="fact", content="每周三晚上健身",
        source_refs=(SourceRef(kind="message", ref="msg-gym"),),
    ))
    assert record.memory_id
    assert service.repo.get(record.memory_id).content == "每周三晚上健身"
    rig.db.close()
