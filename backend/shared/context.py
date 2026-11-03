"""身份与执行上下文值对象。

所有渠道（Web/微信/定时任务）产生可信 Principal 后才能进入业务模块；
外部请求参数不能指定任意 owner（架构 §4）。
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """已通过认证的操作主体。

    user_id 是 app.db users 表主键；role 为角色名字符串；
    permission_revision 在角色/授权变更时递增，用于缓存失效判断。
    """

    user_id: int
    role: str
    permission_revision: int


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """一次 run 执行的完整上下文快照，随 RuntimeRequest 传给 Runtime。

    source: web / wechat / schedule / memory / evolution
    """

    run_id: str
    session_id: str
    principal: Principal
    source: str
    channel_account_id: str | None
    model_profile_id: str
    policy_revision: int
