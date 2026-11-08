"""强类型配置与能力开关（架构 §3 platform/settings.py）。

显式加载：import 本模块无副作用；`settings_from_environment()` 仅在
lifespan 启动阶段显式调用。能力开关默认全部关闭（R10/R13/R16 约束）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AppSettings:
    """应用配置。测试与部署都通过显式构造。"""

    data_db_path: Path
    state_db_path: Path
    artifacts_dir: Path
    project_timezone: str = "Asia/Shanghai"
    # 能力开关：默认关闭，由部署配置显式启用
    email_enabled: bool = False
    pdf_enabled: bool = False
    script_runner_enabled: bool = False
    wechat_enabled: bool = False
    mcp_enabled: bool = False
    # 语音输入（A1）：总开关默认关闭；auto=云端优先、本地兜底；off 关闭
    voice_enabled: bool = False
    stt_provider: str = "auto"
    stt_model: str = "whisper-1"
    stt_model_local: str = "small"
    stt_language: str = "zh"
    stt_timeout_seconds: float = 20.0
    voice_echo: bool = False
    # 部署密钥：模型密钥与渠道凭证的 AES-GCM 加密来源；空值表示未配置（能力保持关闭）
    encryption_secret: str = ""
    # JWT 签名密钥；空值时启动生成进程内随机密钥（重启后旧 token 失效）
    jwt_secret: str = ""
    # GitHub webhook 验签密钥（T7）；空值 = webhook 路由一律 403
    github_webhook_secret: str = ""
    # 登录/注册限流（审计 #5）：default_settings（测试/工厂）默认关闭，
    # 生产入口 settings_from_environment 默认开启，EASYCHAT_AUTH_RATE_LIMIT 可显式关闭
    auth_rate_limit_enabled: bool = False
    # 是否在启动时构造真实 Hermes Runtime（默认关闭，便于无模型的最小启动）
    hermes_enabled: bool = False
    # 额外部署参数（各能力 Adapter 自行读取所需键）
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.data_db_path:
            raise ValueError("data_db_path 不能为空")
        if not self.state_db_path:
            raise ValueError("state_db_path 不能为空")
        if not self.artifacts_dir:
            raise ValueError("artifacts_dir 不能为空")

    @property
    def files_root(self) -> Path:
        """文件权威根目录：与 app.db 同目录（staging 与最终位置需同文件系统）。"""
        return Path(self.data_db_path).parent


def default_settings() -> AppSettings:
    """显式默认配置：相对路径常量，不做任何文件系统访问。仅用于工厂缺省与测试。"""
    data_dir = Path("data")
    return AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
    )


def settings_from_environment() -> AppSettings:
    """从进程环境构造配置——仅在 lifespan 启动时显式调用，不允许 import 期调用。"""
    import os

    root = Path(os.environ.get("EASYCHAT_ROOT", Path.cwd()))
    data_dir = Path(os.environ.get("EASYCHAT_DATA_DIR", root / "data"))
    flag = lambda name: os.environ.get(name, "").lower() in {"1", "true", "yes"}  # noqa: E731
    off_flag = lambda name: os.environ.get(name, "").lower() in {"0", "false", "no", "off"}  # noqa: E731
    return AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
        email_enabled=flag("EASYCHAT_EMAIL_ENABLED"),
        pdf_enabled=flag("EASYCHAT_PDF_ENABLED"),
        script_runner_enabled=flag("EASYCHAT_RUNNER_ENABLED"),
        wechat_enabled=flag("EASYCHAT_WECHAT_ENABLED"),
        mcp_enabled=flag("EASYCHAT_MCP_ENABLED"),
        voice_enabled=flag("EASYCHAT_VOICE_ENABLED"),
        stt_provider=os.environ.get("EASYCHAT_STT_PROVIDER", "auto"),
        stt_model=os.environ.get("EASYCHAT_STT_MODEL", "whisper-1"),
        stt_model_local=os.environ.get("EASYCHAT_STT_MODEL_LOCAL", "small"),
        stt_language=os.environ.get("EASYCHAT_STT_LANGUAGE", "zh"),
        stt_timeout_seconds=float(os.environ.get("EASYCHAT_STT_TIMEOUT", "20")),
        voice_echo=flag("EASYCHAT_VOICE_ECHO"),
        encryption_secret=os.environ.get("EASYCHAT_ENCRYPTION_SECRET", ""),
        jwt_secret=os.environ.get("EASYCHAT_JWT_SECRET", ""),
        github_webhook_secret=os.environ.get("EASYCHAT_GITHUB_WEBHOOK_SECRET", ""),
        hermes_enabled=flag("EASYCHAT_HERMES_ENABLED"),
        auth_rate_limit_enabled=not off_flag("EASYCHAT_AUTH_RATE_LIMIT"),
    )
