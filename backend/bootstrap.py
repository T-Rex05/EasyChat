"""显式装配与启动顺序（架构 §2/A01、§10）。

本模块 import 无任何副作用：不连接数据库、不启动监听、不加载 .env。
所有真实启动发生在 lifespan 阶段显式调用 run_startup。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AppSettings:
    """强类型应用配置。测试与部署都通过显式构造；不从 import 期读环境。"""

    data_db_path: Path
    state_db_path: Path
    artifacts_dir: Path
    project_timezone: str = "Asia/Shanghai"
    # 能力开关：默认全部关闭，由部署配置显式启用（R10/R13 约束）
    email_enabled: bool = False
    pdf_enabled: bool = False
    script_runner_enabled: bool = False
    wechat_enabled: bool = False
    mcp_enabled: bool = False
    # 额外部署参数（能力 Adapter 自行读取自身所需的键）
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.data_db_path:
            raise ValueError("data_db_path 不能为空")
        if not self.artifacts_dir:
            raise ValueError("artifacts_dir 不能为空")


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
    return AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
        email_enabled=os.environ.get("EASYCHAT_EMAIL_ENABLED", "").lower() in {"1", "true", "yes"},
        pdf_enabled=os.environ.get("EASYCHAT_PDF_ENABLED", "").lower() in {"1", "true", "yes"},
        script_runner_enabled=os.environ.get("EASYCHAT_RUNNER_ENABLED", "").lower() in {"1", "true", "yes"},
        wechat_enabled=os.environ.get("EASYCHAT_WECHAT_ENABLED", "").lower() in {"1", "true", "yes"},
        mcp_enabled=os.environ.get("EASYCHAT_MCP_ENABLED", "").lower() in {"1", "true", "yes"},
    )


@dataclass(slots=True)
class ModuleRegistry:
    """bootstrap 显式构造出的模块集合；任务推进时逐个加入。

    各字段在对应任务完成后才有真实类型；未完成的任务不创建占位实现。
    """

    settings: AppSettings
    access: Any | None = None  # Task 3
    models: Any | None = None  # Task 4
    usage: Any | None = None  # Task 4
    runtime: Any | None = None  # Task 5 (ExecutionRuntime)
    assistant: Any | None = None  # Task 6
    channels: Any | None = None  # Task 7
    delivery: Any | None = None  # Task 8
    scheduling: Any | None = None  # Task 8
    memory: Any | None = None  # Task 9
    skills: Any | None = None  # Task 10
    evolution: Any | None = None  # Task 11


async def run_startup(registry: ModuleRegistry) -> None:
    """lifespan 启动序列（架构 §10）。

    Task 1 阶段：仅确保产物目录存在。迁移、模块构造、调度器恢复
    随后续任务在此函数中按固定顺序加入；失败必须让启动明确失败。
    """
    registry.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)


async def run_shutdown(registry: ModuleRegistry) -> None:
    """lifespan 关闭序列：停止接收→停任务→关Runtime→最终刷计量→释放连接。

    Task 1 阶段无资源需要释放；后续任务按逆序补充，整个流程保持幂等。
    """
    return None
