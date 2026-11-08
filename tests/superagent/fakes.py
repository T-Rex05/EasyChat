"""superagent 测试共享桩：FakeGit / FakeRunner / FakePRClient / FakeCanceller。

只替换外部 Seam（git 子进程、编码会话、GitHub REST、协作取消），
数据库/delivery/repository 全部走真实实现（TestRig 临时 SQLite）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.modules.superagent import github as gh
from backend.modules.superagent.runner import RunnerOutcome


@dataclass
class FakeGit:
    """有状态 git 替身：记录调用、按脚本应答 rev-parse/status/diff。

    fail_on：args 前缀匹配即失败（err 可携带合成 token 用于脱敏断言）。
    hooks：push 等边界可注入回调（模拟"push 期间用户取消"等竞态）。
    """

    status: str = ""
    diff: str = ""
    heads: list[str] = field(default_factory=lambda: ["b" * 40])
    fail_on: tuple[tuple[str, str], ...] = ()
    hooks: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.git_args_seen: tuple[str, ...] = ()
        self.env_seen: dict[str, str] = {}
        self.timeouts_seen: list[float] = []
        self._head_index = 0

    async def __call__(self, cwd, git_args, env_extra, timeout, *args):
        self.calls.append(tuple(args))
        self.git_args_seen = tuple(git_args or ())
        self.env_seen = dict(env_extra or {})
        self.timeouts_seen.append(timeout)
        joined = " ".join(args)
        for prefix, err in self.fail_on:
            if joined.startswith(prefix):
                return 1, "", err
        hook = self.hooks.get(joined.split(" ")[0])
        if hook is not None:
            await hook(joined)
        if args[0] == "rev-parse":
            value = self.heads[min(self._head_index, len(self.heads) - 1)]
            self._head_index += 1
            return 0, value, ""
        if args[0] == "status":
            return 0, self.status, ""
        if args[0] == "diff":
            return 0, self.diff, ""
        return 0, "", ""

    def argv_of(self, index: int) -> tuple[str, ...]:
        return self.calls[index]


class FakeRunner:
    """CodingRunner 替身：返回预置 RunnerOutcome；记录 request 与 interrupt。"""

    def __init__(self, outcome: RunnerOutcome | None = None) -> None:
        self.outcome = outcome or RunnerOutcome(completed=True, final_response="完成。")
        self.requests: list[object] = []
        self.interrupted: list[str] = []
        self.prepared: list[str] = []
        self.run_timeout_seconds = 4 * 3600

    async def prepare(self, request) -> None:
        self.prepared.append(str(request.workspace))
        self.requests.append(request)

    async def execute(self, request) -> RunnerOutcome:
        return self.outcome

    async def interrupt(self, run_id: str) -> None:
        self.interrupted.append(run_id)


class CancelMidRunRunner(FakeRunner):
    """在 execute 期间触发用户取消（模拟取消与编码并发）。"""

    def __init__(self, outcome, trigger) -> None:
        super().__init__(outcome)
        self._trigger = trigger

    async def execute(self, request) -> RunnerOutcome:
        await self._trigger()
        return self.outcome


class FakePRClient:
    """PRClient 替身：可预置已有 PR；记录 create 调用与 body。"""

    def __init__(self, *, existing: gh.PullRequest | None = None,
                 create_error: Exception | None = None,
                 register_on_create_error: gh.PullRequest | None = None) -> None:
        self.existing = existing
        self.create_error = create_error
        self.register_on_create_error = register_on_create_error
        self.created: list[dict] = []
        self._after_create: gh.PullRequest | None = None

    async def find_pr_for_head(self, *, ref, head_branch, base_branch):
        if self._after_create is not None:
            return self._after_create
        return self.existing

    async def create_draft_pr(self, *, ref, title, head, base, body):
        if self.create_error is not None:
            if self.register_on_create_error is not None:
                # 模拟"PR 实际已创建但响应丢失"（网络歧义）
                self._after_create = self.register_on_create_error
            raise self.create_error
        pr = gh.PullRequest(
            number=7 + len(self.created), api_url="https://api/pulls/x",
            html_url=f"https://github.com/{ref.full_name}/pull/{7 + len(self.created)}",
            state="open", draft=True, head_ref=head,
        )
        self.created.append({"ref": ref, "title": title, "head": head, "base": base, "body": body})
        self._after_create = pr
        return pr


class FakeCanceller:
    """service._run_canceller 替身：记录 run_id，证明 await 生效。"""

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def __call__(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def make_outcome(final_response: str = "修复了问题。", *, completed: bool = True) -> RunnerOutcome:
    return RunnerOutcome(completed=completed, final_response=final_response)
