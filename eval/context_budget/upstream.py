"""A real pinned MCP subprocess per run, not a local BM25 imitation."""
import asyncio
from concurrent.futures import Future
import os
from pathlib import Path
import threading


class MCPBridge:
    def __init__(self, upstream, home):
        self.upstream = Path(upstream).resolve()
        self.home = Path(home).resolve()
        self.ready = Future()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.job = asyncio.run_coroutine_threadsafe(self._serve(), self.loop)
        self.tools = self.ready.result(timeout=45)

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.home.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home),
               "CONTEXT_MODE_HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data")}
        try:
            async with stdio_client(StdioServerParameters(
                command="node", args=[str(self.upstream / "server.bundle.mjs")], env=env)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    self.stop = asyncio.Event()
                    self.ready.set_result((await session.list_tools()).tools)
                    await self.stop.wait()
        except BaseException as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            raise

    def call(self, name, payload):
        result = asyncio.run_coroutine_threadsafe(self.session.call_tool(name, payload), self.loop).result(timeout=120)
        return "\n".join(item.text for item in result.content if hasattr(item, "text"))

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        self.job.result(timeout=15)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
