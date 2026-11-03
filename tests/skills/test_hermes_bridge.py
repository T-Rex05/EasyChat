"""Hermes Skills 桥接：只用 skills 公开接口、仅 owner 快照、无 backend.hermes 导入。"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.modules.skills.contracts import SOURCE_USER
from backend.runtime.hermes import skills_bridge
from backend.runtime.hermes.skills_bridge import SkillsBridge
from backend.shared.errors import ConflictError, InvalidInputError
from tests.skills.helpers import (
    make_skill_rig,
    make_user,
    version_file,
)

BRIDGE_PATH = Path(skills_bridge.__file__)


@pytest.fixture
def env(tmp_path):
    rig, service, root = make_skill_rig(tmp_path)
    alice = make_user(rig, tag="alice")
    bob = make_user(rig, tag="bob")
    yield rig, service, root, alice, bob
    rig.db.close()


def _seed(service, user, name: str, content: str):
    version = service.propose(user, name, content)
    return service.activate(user, version.skill_id, version.version_id, None), version


def test_bridge_only_returns_owner_snapshots(env):
    _, service, _, alice, bob = env
    _seed(service, alice, "alpha", "# alpha")
    _seed(service, bob, "beta", "# beta")

    bridge = SkillsBridge(service, alice)
    snapshots = bridge.list_for_runtime()
    assert [s.name for s in snapshots] == ["alpha"]
    assert all(s.owner_id == alice.user_id for s in snapshots)
    assert snapshots[0].content == "# alpha"
    assert snapshots[0].version_id

    # 显式传入另一个 Principal 时仍按该 owner 过滤（不按 name 混淆）
    assert [s.name for s in bridge.list_for_runtime(bob)] == ["beta"]


def test_bridge_propose_and_activate_flow(env):
    _, service, _, alice, _ = env
    bridge = SkillsBridge(service, alice)
    version = bridge.propose("alpha", "# v1")
    assert version.source == "web"
    assert version.status == "validated"

    skill = bridge.activate(version.skill_id, version.version_id, None)
    assert skill.active_version_id == version.version_id
    assert bridge.list_for_runtime()[0].content == "# v1"

    v2 = bridge.propose("alpha", "# v2", source=SOURCE_USER)
    with pytest.raises(ConflictError):
        bridge.activate(version.skill_id, v2.version_id, None)
    assert bridge.list_for_runtime()[0].content == "# v1"


def test_bridge_fails_explicitly_when_active_file_missing(env):
    _, service, root, alice, _ = env
    _, version = _seed(service, alice, "alpha", "# alpha")
    bridge = SkillsBridge(service, alice)
    version_file(root, version).unlink()
    with pytest.raises(InvalidInputError):
        bridge.list_for_runtime()


def test_bridge_imports_only_public_skills_api():
    tree = ast.parse(BRIDGE_PATH.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

    assert not any(
        mod == "backend.hermes" or mod.startswith("backend.hermes.") for mod in modules
    ), "skills_bridge 不得导入 backend.hermes"
    skills_imports = [mod for mod in modules if mod.startswith("backend.modules.skills")]
    assert skills_imports, "桥接应通过 skills 公开接口工作"
    assert set(skills_imports) <= {
        "backend.modules.skills.api",
        "backend.modules.skills.contracts",
    }, f"桥接只能使用 api/contracts: {skills_imports}"
