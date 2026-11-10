"""Offline regressions for the proposed access fixes. Use replay_access_draft.py."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
import sqlite3

import pytest

from backend.modules.access.api import AccessService
from backend.modules.access.contracts import ALL_PERMISSION_KEYS
from backend.modules.access.policy import effective_permissions
from backend.platform.sqlite import Database
from backend.shared.errors import ForbiddenError


@pytest.fixture
def access(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    service = AccessService(db, jwt_secret="draft-offline-test-secret-0000000000")
    service.seed()
    yield service
    db.close()


def user(access, name, role="user"):
    registered = access.register(name, "offline-password")
    access.repo.set_user_role(registered["user_id"], role)
    access.invalidate_all()
    return access.snapshot_principal(registered["user_id"])


@pytest.mark.parametrize("operation", ["role", "status"])
def test_concurrent_owner_losses_leave_one_active_owner(access, operation):
    owners = [user(access, "owner-one", "super_admin"), user(access, "owner-two", "super_admin")]
    # Align callers at the transaction entry, after any preflight service checks.
    # The real BEGIN IMMEDIATE, SQL and commits are never replaced.
    original_transaction = access.repo.db.transaction
    barrier = Barrier(2)

    @contextmanager
    def simultaneous_transactions(*args, **kwargs):
        barrier.wait(timeout=10)
        with original_transaction(*args, **kwargs) as connection:
            yield connection

    access.repo.db.transaction = simultaneous_transactions

    def lose_owner(principal):
        try:
            if operation == "role":
                access.set_user_role(principal, principal.user_id, "user")
            else:
                access.set_user_status(principal, principal.user_id, 0)
            return "changed"
        except ForbiddenError:
            return "denied"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lose_owner, owners))
    finally:
        access.repo.db.transaction = original_transaction
    assert sorted(outcomes) == ["changed", "denied"]
    connection = access.repo.db.connect()
    try:
        remaining = connection.execute(
            "SELECT count(*) FROM users WHERE role='super_admin' AND status=1"
        ).fetchone()[0]
    finally:
        connection.close()
    assert remaining == 1


def test_role_rename_preserves_members_permissions_and_toolsets(access):
    owner = user(access, "role-owner", "super_admin")
    role_id = access.create_role(owner, name="before", display_name="Draft",
                                 permissions=["chat.use"], toolsets=["web"])
    member = user(access, "role-member", "before")
    assert access.effective_permissions(member.user_id) == frozenset({"chat.use"})
    assert access.hermes_toolsets(member.user_id) == ("web",)
    access.update_role(owner, role_id, name="after")
    assert access.snapshot_principal(member.user_id).role == "after"
    assert access.effective_permissions(member.user_id) == frozenset({"chat.use"})
    assert access.hermes_toolsets(member.user_id) == ("web",)


def test_renaming_to_existing_role_rolls_back_members_and_grants(access):
    owner = user(access, "collision-owner", "super_admin")
    role_id = access.create_role(owner, name="original", display_name="Draft", permissions=["chat.use"])
    member = user(access, "collision-member", "original")
    with pytest.raises(sqlite3.IntegrityError):
        access.update_role(owner, role_id, name="user", permissions=[])
    assert access.snapshot_principal(member.user_id).role == "original"
    assert access.effective_permissions(member.user_id) == frozenset({"chat.use"})


def test_unknown_keys_are_inert_from_role_and_user_override(access):
    member = user(access, "retired-member")
    access.repo.set_role_permissions_by_name("user", ["chat.use", "removed.permission"])
    access.repo.set_user_permission(member.user_id, "removed.grant", True)
    access.invalidate_all()
    assert access.effective_permissions(member.user_id) == frozenset({"chat.use"})
    assert effective_permissions(role_name="user", role_permissions=frozenset({"removed.permission"}),
                                 grants=frozenset(), revokes=frozenset()) == frozenset()
    # Preserve historical records for audit.
    assert "removed.permission" in access.repo.snapshot_role_permissions("user")
    assert "removed.grant" in access.repo.get_user_overrides(member.user_id)[0]


@pytest.mark.parametrize("permissions,read,use", [
    (["memory.edit"], False, True),
    (["memory.view"], True, False),
    (["memory.view", "memory.edit"], True, True),
    ([], False, False),
])
def test_memory_capabilities_match_actual_atomic_checks(access, permissions, read, use):
    member = user(access, "memory-member")
    access.repo.set_role_permissions_by_name("user", permissions)
    access.invalidate_all()
    capability = access.capabilities(member)["modules"]["memory"]
    assert capability["read"] is read
    assert capability["use"] is use
    assert access.has_permission(member, "memory.view") is read
    assert access.has_permission(member, "memory.edit") is use


def test_explicit_empty_registry_grants_nothing():
    assert effective_permissions(role_name="user", role_permissions=ALL_PERMISSION_KEYS,
                                 grants=ALL_PERMISSION_KEYS, revokes=frozenset(),
                                 all_registered_permissions=frozenset()) == frozenset()
