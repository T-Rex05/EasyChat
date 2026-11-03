"""S2 SSE 解耦 step2：把 GET 流式端点接到 RunRegistry 的传输适配器。

只依赖纯 backend.service.run_registry；生成器（token_stream_events）由端点以
producer_factory 注入（依赖反转，避免与 chat_controller 循环 import）。生成在后台
asyncio.Task 里跑到底并落库，与 HTTP 订阅者是否在场无关——这就是 detach 白拿的根因。

权威设计：docs/refactor/S2-SSE解耦-设计裁决-20260614.md（§6 step2）
"""
from __future__ import annotations

import asyncio
import hashlib
import logging

from backend.service.run_registry import RunRegistry

logger = logging.getLogger(__name__)

_REGISTRY = RunRegistry()  # 进程内单例（单进程假设，见设计 §5.2；多副本另引外部存储）


def cancel_run(thread_id: str, client_msg_id: str) -> bool:
    """用户主动暂停/停止：取消 registry 中的后台 run，阻止后续重连重放。
    返回 True 表示找到并取消了活跃 run；False 表示 run 不存在或已终结。"""
    return _REGISTRY.user_cancel(thread_id, client_msg_id)


def transitional_client_msg_id(thread_id: str, message: str) -> str:
    """前端尚未下发 client_msg_id 期间的过渡键：对 (thread_id, message) 稳定。

    设计 §6 step2 字面写「缺省=thread_id」，但 GET url 含 message，纯 thread_id 会让同 thread
    的连续不同消息共用键、第二条命中第一条已完成 run 重放旧答案——破坏多轮对话。改对
    (thread_id, message) 取哈希：连续不同消息→不同键→各自新 run（与现状等价）；EventSource 断线
    重连同一 url（message 不变）→同键→续传同一 run（detach/e3 生效）。step6 前端下发真 client_msg_id
    后退役本函数。不记明文：哈希本身即可作 run.created 日志的 msg 指纹。"""
    digest = hashlib.sha256(f"{thread_id}\x00{message}".encode("utf-8")).hexdigest()
    return digest[:16]


def resolve_client_msg_id(explicit, thread_id, message):
    """端点幂等键选择：前端下发的 client_msg_id 优先（前端可控、与消息文本解耦——
    『重复发同一句话』可被前端判成有意新一轮：新 uuid→新 run）；缺省/空白（None/空串/
    纯空白，含 url 里 client_msg_id=）回退过渡键，与 step2 等价，绝不拿空串当键。
    前端在 step6 才下发真键，故 step3 后端先按可选参收、安全回退。"""
    if explicit and explicit.strip():
        return explicit
    return transitional_client_msg_id(thread_id, message)


def resume_from_seq(last_event_id):
    """把 EventSource 重连自动带的 Last-Event-ID 头换算成续传游标 from_seq。
    客户端最后看到 id:N（registry 给 buffered 帧前置的 SSE id 行）→ 要 N 之后的帧 →
    from_seq=N+1（replay_from 含起点，故 +1 排除已看过的 N）。缺省（首连无头）/ 空 /
    非数字 / 负数 → 0 全量重放兜底，缺口由 subscribe 的 stream_reset 收。"""
    if not last_event_id:
        return 0
    try:
        seq = int(str(last_event_id).strip())
    except (TypeError, ValueError):
        return 0
    return seq + 1 if seq >= 0 else 0


async def subscribe_stream(thread_id, client_msg_id, producer_factory, *,
                           from_seq=0, registry=None):
    """按幂等键 (thread_id, client_msg_id) 拿到/启动后台 run，把 ring buffer 的帧
    （重放 + live 续传）透传给 HTTP 消费者。生成由后台 task 驱动，订阅者断开不打断它。
    解析 run（get_or_create）后委托 _subscribe_run 这个单一订阅原语。"""
    reg = registry if registry is not None else _REGISTRY
    run, _created = reg.get_or_create(thread_id, client_msg_id, producer_factory)
    async for frame in _subscribe_run(reg, run, from_seq):
        yield frame


def open_request_stream(thread_id, message, client_msg_id, last_event_id,
                        producer_factory, *, registry=None):
    """请求级 SSE 投递入口：把一次 GET 的原始入参（含 EventSource 重连自动带的 Last-Event-ID
    头）收敛成 ring buffer 的订阅流——解析幂等键 + 续传游标后【急切】get_or_create、再返回订阅流。
    端点与 e4 集成测试共用此单一真源、杜绝接线漂移；step6 前端下发真 client_msg_id 时此处零改动
    （resolve 内部优先显式键）。返回 async generator，交给 StreamingResponse。

    急切（非惰性）get_or_create 是为 F-SAMETHREAD-SERIAL 的干净 409：同 thread 有 active run 时
    get_or_create 同步抛 ThreadBusyError，在【返回订阅流之前】传到端点——端点得以在流开始前回 409；
    若留到首帧迭代才抛（惰性），200 头已发、只能 500 兜底。busy 抛错时不创建生成器、无资源泄漏。"""
    reg = registry if registry is not None else _REGISTRY
    run_key = resolve_client_msg_id(client_msg_id, thread_id, message)
    from_seq = resume_from_seq(last_event_id)
    logger.info("open_request_stream thread_id=%s client_msg_id=%s run_key=%s from_seq=%d last_event_id=%s",
                thread_id, client_msg_id, run_key, from_seq, last_event_id)
    run, _created = reg.get_or_create(thread_id, run_key, producer_factory)  # 同步、busy 即时抛
    return _subscribe_run(reg, run, from_seq)


async def _subscribe_run(reg, run, from_seq):
    """订阅一个【已解析】的 run，把 ring buffer 的帧（重放 + live 续传）透传给 HTTP 消费者。
    run 由调用方急切 get_or_create 拿到（见 open_request_stream），故本协程只管订阅、不再建 run。"""
    async for frame in reg.subscribe(run, from_seq=from_seq):
        yield frame


async def run_periodic_sweep(registry=None, *, interval_s=60, sleep=None):
    """登记表的周期内存守卫：每 interval_s 调一次 registry.sweep()，回收挂死 RUNNING（取消）、
    TTL 终结 run、超 max_runs 的 LRU。由 app startup 钩子起一个常驻后台 task 驱动（main.py）。

    没有它 sweep 永不被调用——挂死的 RUNNING run 既漏内存，又让该 thread 被 F-SAMETHREAD-SERIAL
    的 409 永久卡死（busy 判定看 is_active，never-swept 的挂死 run 永远 active）。故 sweeper 是
    best-effort 守卫：单轮 sweep 抛错只吞掉记日志、绝不停摆（停了等于守卫消失）。被 cancel
    （app shutdown）时让 CancelledError 穿过、干净退出。sleep 可注入以便确定性单测。"""
    reg = registry if registry is not None else _REGISTRY
    _sleep = sleep if sleep is not None else asyncio.sleep
    while True:
        await _sleep(interval_s)        # 取消点：shutdown 时 CancelledError 由此穿出
        try:
            reg.sweep()
        except Exception:               # noqa: BLE001 守卫绝不能因单轮异常停摆
            logger.exception("run.sweep_failed (周期 sweep 单轮异常，已吞、下一轮照常)")
