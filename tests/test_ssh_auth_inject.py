"""ssh 凭据注入 单元测试"""
from backend.service.host_whitelist_service import inject_ssh_auth


class TestInjectSshAuth:
    def test_password_injection(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service.get_host_auth",
                            lambda host: {"access_user": "root", "auth_method": "password", "auth_secret": "s3cret"})
        cmd = inject_ssh_auth("ssh root@db01 ls -la", "db01")
        assert cmd.startswith("sshpass -p")
        assert "s3cret" in cmd
        assert "ssh root@db01 ls" in cmd

    def test_key_injection(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service.get_host_auth",
                            lambda host: {"access_user": "", "auth_method": "key", "auth_secret": "/home/u/.ssh/id_rsa"})
        cmd = inject_ssh_auth("ssh db01 uptime", "db01")
        assert "ssh -i '/home/u/.ssh/id_rsa' db01" in cmd

    def test_none_passthrough(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service.get_host_auth",
                            lambda host: {"access_user": "", "auth_method": "none", "auth_secret": ""})
        assert inject_ssh_auth("ssh db01 uptime", "db01") == "ssh db01 uptime"

    def test_no_record_passthrough(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service.get_host_auth", lambda host: {})
        assert inject_ssh_auth("ssh db01 uptime", "db01") == "ssh db01 uptime"

    def test_invalid_key_path_ignored(self, monkeypatch):
        monkeypatch.setattr("backend.service.host_whitelist_service.get_host_auth",
                            lambda host: {"access_user": "", "auth_method": "key", "auth_secret": "rm -rf /"})
        assert inject_ssh_auth("ssh db01 uptime", "db01") == "ssh db01 uptime"