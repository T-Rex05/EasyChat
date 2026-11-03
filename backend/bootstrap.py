"""显式装配与启动顺序（架构 §2/A01、§10）。

本模块 import 无任何副作用：不连接数据库、不启动监听、不加载 .env。
所有真实启动发生在 lifespan 阶段显式调用 run_startup。
"""
from dataclasses import dataclass
from typing import Any

from backend.platform.settings import AppSettings, default_settings, settings_from_environment

__all__ = [
    "AppSettings",
    "ModuleRegistry",
    "default_settings",
    "run_shutdown",
    "run_startup",
    "settings_from_environment",
]


@dataclass(slots=True)
class ModuleRegistry:
    """bootstrap 显式构造出的模块集合；任务推进时逐个加入。

    各字段在对应任务完成后才有真实类型；未完成的任务不创建占位实现。
    """

    settings: AppSettings
    db: Any | None = None  # Task 2 (platform.sqlite.Database)
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

    Task 2 起：执行版本化迁移，失败明确终止启动。模块构造、调度器恢复
    随后续任务在此函数中按固定顺序加入。
    """
    from backend.platform.sqlite import Database

    registry.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    db = Database(registry.settings.data_db_path)
    db.migrate()  # 迁移失败抛 MigrationError → 启动终止
    registry.db = db

    # Task 6：统一 Assistant（runtime 缺省时不装配——最小工厂仅存活/就绪）
    if registry.runtime is not None and registry.access is not None:
        from backend.modules.assistant.api import AssistantService

        registry.assistant = AssistantService(
            db, runtime=registry.runtime, models=registry.models, access=registry.access,
        )
        registry.access.seed()
        await registry.assistant.start()


async def run_shutdown(registry: ModuleRegistry) -> None:
    """lifespan 关闭序列：停止接收→停任务→关Runtime→最终刷计量→释放连接。

    后续任务按逆序补充；整个流程保持幂等。
    """
    if registry.assistant is not None:
        await registry.assistant.aclose()
        registry.assistant = None
    if registry.runtime is not None:
        aclose = getattr(registry.runtime, "aclose", None)
        if aclose is not None:
            await aclose()
        registry.runtime = None
    if registry.db is not None:
        registry.db.close()
        registry.db = None
