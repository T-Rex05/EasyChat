"""主机白名单 + ssh 目标提取 单元测试"""
import pytest

from backend.service.host_whitelist_service import extract_ssh_targets, is_host_allowed


class TestExtractSshTargets:
    def test_simple_ssh(self):
        assert extract_ssh_targets("ssh 192.168.1.10") == ["192.168.1.10"]

    def test_user_at_host(self):
        assert extract_ssh_targets("ssh root@db01.internal") == ["db01.internal"]

    def test_with_options(self):
        assert extract_ssh_targets("ssh -p 2222 -i key.pem root@web01") == ["web01"]

    def test_scp(self):
        assert extract_ssh_targets("scp file.txt root@10.0.0.5:/tmp/") == ["10.0.0.5"]

    def test_no_ssh(self):
        assert extract_ssh_targets("ls -la") == []
        assert extract_ssh_targets("") == []

    def test_multiple(self):
        assert extract_ssh_targets("ssh a.com && ssh b.com") == ["a.com", "b.com"]


class TestHostAllowedWithPerm:
    """用户维度：白名单通过后还需 system.manage 权限（免密门槛）。"""

    def _conn_with_row(self):
        class Cur:
            @staticmethod
            def fetchall():
                return [{"id": 1}]

        class Conn:
            def execute(self, sql, params):
                return Cur()

            def close(self):
                pass

        return Conn()

    def test_no_perm_denied(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: self._conn_with_row())
        monkeypatch.setattr("backend.service.host_whitelist_service.user_has_whitelist_perm", lambda uid: False)
        assert is_host_allowed("db01", user_id=5) is False

    def test_with_perm_allowed(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: self._conn_with_row())
        monkeypatch.setattr("backend.service.host_whitelist_service.user_has_whitelist_perm", lambda uid: True)
        assert is_host_allowed("db01", user_id=5) is True

    def test_host_missing_denied_even_with_perm(self, monkeypatch):
        class Cur:
            @staticmethod
            def fetchall():
                return []

        class Conn:
            def execute(self, sql, params):
                return Cur()

            def close(self):
                pass

        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: Conn())
        monkeypatch.setattr("backend.service.host_whitelist_service.user_has_whitelist_perm", lambda uid: True)
        assert is_host_allowed("ghost", user_id=5) is False


class TestHostAllowed:
    def test_empty_whitelist_denies(self, monkeypatch):
        class Conn:
            def execute(self, sql, params):
                class Cur:
                    @staticmethod
                    def fetchall():
                        return []
                return Cur()

            def close(self):
                pass

        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: Conn())
        assert is_host_allowed("db01") is False

    def test_allowed_host(self, monkeypatch):
        class Cur:
            @staticmethod
            def fetchall():
                return [{"id": 1}]

        class Conn:
            def execute(self, sql, params):
                return Cur()

            def close(self):
                pass

        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: Conn())
        assert is_host_allowed("db01") is True

    def test_db_error_denies(self, monkeypatch):
        class Conn:
            def execute(self, sql, params):
                raise RuntimeError("db down")

            def close(self):
                pass

        monkeypatch.setattr("backend.service.host_whitelist_service._conn", lambda: Conn())
        assert is_host_allowed("db01") is False