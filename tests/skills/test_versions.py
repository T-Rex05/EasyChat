"""个人技能不可变版本、激活/回滚、pin/权限与重启恢复测试（Task 10）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.modules.skills.contracts import VERSION_ACTIVE, VERSION_VALIDATED
from backend.shared.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
)
from tests.skills.helpers import (
    make_skill_rig,
    make_user,
    new_service,
    version_file,
)


@pytest.fixture
def env(tmp_path):
    rig, service, root = make_skill_rig(tmp_path)
    user = make_user(rig, tag="owner")
    yield rig, service, root, user
    rig.db.close()


def _propose_and_activate(service, user, name="alpha", content="# alpha\n"):
    version = service.propose(user, name, content)
    skill = service.activate(user, version.skill_id, version.version_id, None)
    return skill, version


def test_version_files_are_immutable_and_activation_is_explicit(env):
    _, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)
    assert skill.active_version_id == v1.version_id
    assert version_file(root, v1).read_text(encoding="utf-8") == "# alpha\n"
    assert service.read_active_content(user, skill.skill_id) == "# alpha\n"

    v2 = service.propose(user, "alpha", "# alpha v2\n")
    assert v2.version_seq == 2
    # 提出新候选不改变旧文件，也不改变 active 指针
    assert version_file(root, v1).read_text(encoding="utf-8") == "# alpha\n"
    assert service.read_active_content(user, skill.skill_id) == "# alpha\n"
    assert service.get(user, skill.skill_id).active_version_id == v1.version_id

    activated = service.activate(user, skill.skill_id, v2.version_id, v1.version_id)
    assert activated.active_version_id == v2.version_id
    assert service.read_active_content(user, skill.skill_id) == "# alpha v2\n"
    # 旧 active 保留为 validated，不删除内容
    assert service.repo.get_version(v1.version_id).status == VERSION_VALIDATED
    assert service.repo.get_version(v2.version_id).status == VERSION_ACTIVE
    assert version_file(root, v1).read_text(encoding="utf-8") == "# alpha\n"


def test_stale_expected_pointer_conflict_does_not_overwrite(env):
    rig, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)
    v2 = service.propose(user, "alpha", "# v2\n")
    v3 = service.propose(user, "alpha", "# v3\n")

    # 第二个进程在切换前读到的期望指针（v1）
    other = new_service(rig, root)
    expected_seen = service.get(user, skill.skill_id).active_version_id
    service.activate(user, skill.skill_id, v2.version_id, expected_seen)

    with pytest.raises(ConflictError):
        other.activate(user, skill.skill_id, v3.version_id, expected_seen)

    assert service.get(user, skill.skill_id).active_version_id == v2.version_id
    assert service.read_active_content(user, skill.skill_id) == "# v2\n"


def test_rollback_restores_old_content(env):
    _, service, _, user = env
    skill, v1 = _propose_and_activate(service, user)
    v2 = service.propose(user, "alpha", "# v2\n")
    service.activate(user, skill.skill_id, v2.version_id, v1.version_id)

    rolled = service.rollback(user, skill.skill_id, v1.version_id)
    assert rolled.active_version_id == v1.version_id
    assert service.read_active_content(user, skill.skill_id) == "# alpha\n"
    assert service.repo.get_version(v2.version_id).status == VERSION_VALIDATED

    with pytest.raises(NotFoundError):
        service.rollback(user, skill.skill_id, "skv_" + "0" * 32)


@pytest.mark.parametrize("bad_name", ["../x", "a/b", "a\\b", "..", ".", "x..y", ""])
def test_path_traversal_names_rejected(env, bad_name):
    _, service, _, user = env
    with pytest.raises(InvalidInputError):
        service.propose(user, bad_name, "# x")


def test_content_path_is_derived_from_ids_not_name(env):
    _, service, root, user = env
    version = service.propose(user, "safe_name", "# x")
    assert version.content_path == f"{version.skill_id}/{version.version_id}.md"
    assert "safe_name" not in version.content_path
    assert version.content_path.startswith(version.skill_id + "/")
    stored = version_file(root, version)
    assert stored.is_file()
    assert stored.resolve().is_relative_to(Path(root).resolve())


def test_tampered_content_blocks_read_and_activation(env):
    _, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)
    v2 = service.propose(user, "alpha", "# v2\n")
    version_file(root, v2).write_text("tampered", encoding="utf-8")

    with pytest.raises(InvalidInputError):
        service.activate(user, skill.skill_id, v2.version_id, v1.version_id)
    assert service.get(user, skill.skill_id).active_version_id == v1.version_id

    version_file(root, v1).write_text("tampered active", encoding="utf-8")
    with pytest.raises(InvalidInputError):
        service.read_active_content(user, skill.skill_id)


def test_missing_version_file_does_not_destroy_active_pointer(env):
    _, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)
    v2 = service.propose(user, "alpha", "# v2\n")
    version_file(root, v2).unlink()

    with pytest.raises(InvalidInputError):
        service.activate(user, skill.skill_id, v2.version_id, v1.version_id)
    assert service.get(user, skill.skill_id).active_version_id == v1.version_id
    assert service.read_active_content(user, skill.skill_id) == "# alpha\n"


def test_out_of_root_content_path_rejected(env):
    rig, service, _, user = env
    skill, v1 = _propose_and_activate(service, user)
    outside = rig.tmp_path / "outside.md"
    outside.write_text("outside-secret", encoding="utf-8")
    with service.db.transaction() as conn:
        conn.execute(
            "UPDATE skill_versions SET content_path=? WHERE id=?",
            ("../../../outside.md", v1.version_id),
        )
    with pytest.raises(InvalidInputError):
        service.read_active_content(user, skill.skill_id)


def test_symlinked_version_file_rejected(env):
    rig, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)
    target = rig.tmp_path / "outside-target.md"
    target.write_text("outside", encoding="utf-8")
    link = version_file(root, v1)
    link.unlink()
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")
    with pytest.raises(InvalidInputError):
        service.read_active_content(user, skill.skill_id)


def test_pinned_blocks_automated_sources_but_allows_owner(env):
    _, service, _, user = env
    skill, v1 = _propose_and_activate(service, user)
    pinned = service.set_pinned(user, skill.skill_id, True)
    assert pinned.pinned is True

    for source in ("background", "evolution"):
        with pytest.raises(ForbiddenError):
            service.propose(user, "alpha", "# automated\n", source=source)

    v2 = service.propose(user, "alpha", "# owner edit\n", source="user")
    assert v2.version_seq == 2
    current = service.get(user, skill.skill_id)
    assert current.pinned is True
    assert current.active_version_id == v1.version_id


def test_permissions_owner_and_other_owner(env):
    rig, service, _, user = env
    skill, v1 = _propose_and_activate(service, user)

    nobody = make_user(rig, revokes=("skill.create",))
    with pytest.raises(ForbiddenError):
        service.propose(nobody, "beta", "# beta")

    outsider = make_user(rig, tag="outsider")
    with pytest.raises(ForbiddenError):
        service.get(outsider, skill.skill_id)
    with pytest.raises(ForbiddenError):
        service.activate(outsider, skill.skill_id, v1.version_id, None)
    with pytest.raises(ForbiddenError):
        service.set_pinned(outsider, skill.skill_id, True)
    with pytest.raises(ForbiddenError):
        service.read_active_content(outsider, skill.skill_id)
    assert service.list(outsider) == ()

    manager = make_user(rig, role="admin", tag="manager")
    assert [s.skill_id for s in service.list(manager, all_owners=True)] == [skill.skill_id]
    assert service.get(manager, skill.skill_id).owner_id == user.user_id
    assert service.set_pinned(manager, skill.skill_id, True).pinned is True


def test_restart_recovery_and_missing_file_failure(env):
    rig, service, root, user = env
    skill, v1 = _propose_and_activate(service, user)

    restarted = new_service(rig, root)
    snapshots = restarted.list_for_runtime(user)
    assert [(s.skill_id, s.version_id) for s in snapshots] == [
        (skill.skill_id, v1.version_id),
    ]
    assert snapshots[0].content == "# alpha\n"
    assert restarted.read_active_content(user, skill.skill_id) == "# alpha\n"

    version_file(root, v1).unlink()
    with pytest.raises(InvalidInputError):
        restarted.read_active_content(user, skill.skill_id)
    with pytest.raises(InvalidInputError):
        restarted.list_for_runtime(user)


def test_archive_excludes_runtime_but_keeps_content(env):
    _, service, _, user = env
    skill, _ = _propose_and_activate(service, user)

    service.archive(user, skill.skill_id)
    assert service.list_for_runtime(user) == ()
    assert service.read_active_content(user, skill.skill_id) == "# alpha\n"
    assert service.list(user) == ()
    service.unarchive(user, skill.skill_id)
    assert [s.skill_id for s in service.list_for_runtime(user)] == [skill.skill_id]


def test_empty_and_oversized_content_rejected(env):
    _, service, _, user = env
    with pytest.raises(InvalidInputError):
        service.propose(user, "empty", "   ")
    too_big = "x" * (200 * 1024 + 1)
    with pytest.raises(InvalidInputError):
        service.propose(user, "big", too_big)
    version = service.propose(user, "limit", "x" * (200 * 1024))
    assert version.version_seq == 1


def test_parent_version_and_activation_require_same_skill(env):
    _, service, _, user = env
    skill_a, v_a = _propose_and_activate(service, user, name="alpha", content="# a\n")
    _, v_b = _propose_and_activate(service, user, name="beta", content="# b\n")

    with pytest.raises(InvalidInputError):
        service.propose(user, "alpha", "# child\n", parent_version_id=v_b.version_id)
    with pytest.raises(InvalidInputError):
        service.activate(user, skill_a.skill_id, v_b.version_id, v_a.version_id)
