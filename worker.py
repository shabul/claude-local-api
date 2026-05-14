"""
Claude subprocess worker.

Claude CLI has no persistent-process mode when stdout is a pipe (no TTY).
Each request spawns a dedicated claude process: prompt on stdin → close → read
stream-json until the result event.  Concurrency is handled by the pool's
asyncio semaphore — N requests run in parallel, each in its own process.

Latency breakdown: ~150 ms process spawn + model inference.  The pool
semaphore prevents thundering-herd and keeps resource usage bounded.
"""
import asyncio
import json


BASE_CMD = [
    "claude",
    "--output-format", "stream-json",
    "--verbose",               # required alongside stream-json
    "--no-session-persistence",
    "--tools", "",             # no tools — pure Q&A
]


async def _run_one(prompt: str, model: str) -> str:
    """Spawn a single claude -p process, stream-json, return the result text."""
    proc = await asyncio.create_subprocess_exec(
        *BASE_CMD,
        "--model", model,
        "-p", prompt,          # -p = print mode; prompt as CLI arg
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if proc.stdout is None:
        raise RuntimeError("failed to open stdout pipe to claude process")

    result = ""
    async for raw in proc.stdout:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event.get("result", "")
            break

    await proc.wait()

    if not result:
        err = (await proc.stderr.read()).decode().strip()
        raise RuntimeError(err or "empty result from claude")

    return result


class WorkerPool:
    """
    Concurrency-limited pool.  `size` controls how many claude processes
    run simultaneously.  Requests beyond that queue and wait.
    """

    def __init__(self, model: str = "haiku", size: int = 3):
        self.model = model
        self.size = size
        self._sem: asyncio.Semaphore | None = None

    async def start(self):
        self._sem = asyncio.Semaphore(self.size)
        print(f"[pool] ready — model={self.model}, concurrency={self.size}", flush=True)

    async def ask(self, prompt: str, model: str | None = None) -> str:
        if self._sem is None:
            raise RuntimeError("WorkerPool.start() must be called before ask()")
        effective_model = model or self.model
        async with self._sem:
            return await _run_one(prompt, effective_model)

    async def stop(self):
        pass  # no persistent processes to clean up
