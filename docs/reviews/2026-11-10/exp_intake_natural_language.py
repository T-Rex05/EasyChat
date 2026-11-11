"""② 定性实验：同一装配下，两种措辞是否会触发 superagent_submit_task。

复用 ① 的真实工作区（base sha 取自任务快照），仅换用户消息观察 tool_calls。
不写 app.db，不调业务 service（工具函数不实际执行）。
用法: python docs/reviews/2026-11-10/exp_intake_natural_language.py <workspace_path> <base_sha>
"""
import sys

sys.path.insert(0, ".")

from backend.config.paths import get_hermes_dir
from backend.runtime.hermes.paths import ensure_hermes_environment
from pathlib import Path

ensure_hermes_environment(Path(get_hermes_dir()))

from langchain_core.messages import HumanMessage  # noqa: E402
from tools.registry import registry  # noqa: E402
from backend.tools.tools_decorator import get_project_tools  # noqa: E402

# 用 bootstrap 同一构建函数拿业务工具（stub service：仅观察调用决策，不执行 handler）
from backend.tools.business.superagent_tools import build_superagent_tools  # noqa: E402

class _Stub:
    def create_task(self, *a, **k):
        raise AssertionError("handler must not execute in observation experiment")

submit = build_superagent_tools(superagent=_Stub())[0]
print("submit tool:", submit.name, "| toolset:", submit._toolset)

# 模型（走 backend 配置读取,与运行实例同源）
from backend.modules.models.repository import ModelsRepository  # noqa: E402
import os, sqlite3  # noqa: E402

db = sqlite3.connect("file:data/app.db?mode=ro", uri=True)
row = db.execute(
    "SELECT provider, model, api_key_encrypted, base_url FROM model_configs WHERE is_active=1"
).fetchone()
db.close()
if not row:
    print("NO ACTIVE MODEL"); sys.exit(1)
provider, model_name, key_enc, base_url = row
secret = os.environ.get("EASYCHAT_ENCRYPTION_SECRET", "")
if not secret:
    print("需要 EASYCHAT_ENCRYPTION_SECRET 环境变量——用 start-local.bat 同款方式运行"); sys.exit(2)
from backend.shared.crypto import decrypt_secret  # noqa: E402

api_key = decrypt_secret(key_enc, secret)

from langchain_openai import ChatOpenAI  # noqa: E402

llm = ChatOpenAI(model=model_name, api_key=api_key,
                 base_url=base_url if base_url.endswith("/v1") else base_url.rstrip("/") + "/v1",
                 temperature=0.3, timeout=120)
llm_with_tools = llm.bind_tools([submit])

CASES = {
    "隐式指令(用户②原话)": "帮我创建一个开发任务：在 README 文件的最后追加一行 natural language intake test，然后提交",
    "点名工具(对照)": "请调用 superagent_submit_task 工具，创建一个编码任务：在 README 末尾追加一行 natural language intake test",
    "闲聊(对照组)": "今天天气不错",
}

for label, text in CASES.items():
    resp = llm_with_tools.invoke([HumanMessage(content=text)])
    calls = getattr(resp, "tool_calls", []) or []
    print(f"[{label}] tool_calls={len(calls)}", end=" ")
    if calls:
        print("→", calls[0]["name"], str(calls[0]["args"])[:80])
    else:
        print("(纯文本回复:", (resp.content or "")[:60].replace("\n", " "), ")")
