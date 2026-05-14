"""
Unix socket server for claude_api.

Protocol (newline-delimited JSON):
  Request:  {"prompt": "...", "model": "haiku"}   # model is optional
  Response: {"result": "...", "worker_ms": 123}   # or {"error": "..."}

Socket: /tmp/claude_api.sock
"""
import asyncio
import json
import os
import signal
import sys
import time

from worker import WorkerPool

SOCKET_PATH = "/tmp/claude_api.sock"
DEFAULT_MODEL = os.environ.get("CLAUDE_API_MODEL", "haiku")
POOL_SIZE = int(os.environ.get("CLAUDE_API_POOL_SIZE", "3"))


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, pool: WorkerPool):
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10)
        if not raw:
            return
        req = json.loads(raw.decode().strip())
        prompt = req.get("prompt", "")
        model = req.get("model") or None

        if not prompt:
            writer.write(json.dumps({"error": "empty prompt"}).encode() + b"\n")
            await writer.drain()
            return

        t0 = time.perf_counter()
        result = await pool.ask(prompt, model=model)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        writer.write(json.dumps({"result": result, "worker_ms": elapsed_ms}).encode() + b"\n")
        await writer.drain()

    except asyncio.TimeoutError:
        writer.write(json.dumps({"error": "request timeout"}).encode() + b"\n")
        await writer.drain()
    except Exception as e:
        writer.write(json.dumps({"error": str(e)}).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()


async def main():
    pool = WorkerPool(model=DEFAULT_MODEL, size=POOL_SIZE)
    await pool.start()

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = await asyncio.start_unix_server(
        lambda r, w: handle(r, w, pool),
        path=SOCKET_PATH,
    )
    os.chmod(SOCKET_PATH, 0o600)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)

    print(f"[server] listening on {SOCKET_PATH}", flush=True)
    async with server:
        await stop

    print("[server] shutting down …")
    await pool.stop()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    asyncio.run(main())
