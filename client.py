"""
Thin client for claude_api Unix socket server.

Usage:
  python -m claude_api.client "your prompt"
  python -m claude_api.client "your prompt" --model sonnet
  python -m claude_api.client "your prompt" --model opus

From anywhere on the machine:
  python /path/to/claude_api/client.py "hello"
"""
import argparse
import json
import socket
import sys
import time

SOCKET_PATH = "/tmp/claude_api.sock"


def ask(prompt: str, model: str | None = None, timeout: int = 60) -> dict:
    req = {"prompt": prompt}
    if model:
        req["model"] = model

    t0 = time.perf_counter()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect(SOCKET_PATH)
        except FileNotFoundError:
            return {"error": f"server not running (socket not found: {SOCKET_PATH})"}
        except ConnectionRefusedError:
            return {"error": "server not running (connection refused)"}

        s.sendall(json.dumps(req).encode() + b"\n")

        chunks = []
        try:
            while True:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            return {"error": f"Connection lost: {e}"}

    raw = b"".join(chunks).decode().strip()
    if not raw:
        return {"error": "Empty response from server (worker may have crashed)"}
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"Bad JSON from server: {e} — got: {raw[:120]}"}
    resp["round_trip_ms"] = int((time.perf_counter() - t0) * 1000)
    return resp


def main():
    parser = argparse.ArgumentParser(description="claude_api client")
    parser.add_argument("prompt", help="Prompt to send")
    parser.add_argument("--model", default=None, help="Model override (haiku/sonnet/opus)")
    parser.add_argument("--json", action="store_true", help="Print full JSON response")
    args = parser.parse_args()

    resp = ask(args.prompt, model=args.model)

    if args.json:
        print(json.dumps(resp, indent=2))
    elif "error" in resp:
        print(f"ERROR: {resp['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        print(resp["result"])
        print(f"\n[{resp.get('round_trip_ms')}ms round-trip, {resp.get('worker_ms')}ms worker]",
              file=sys.stderr)


if __name__ == "__main__":
    main()
