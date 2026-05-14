# claude-local-api

> Zero-config local Claude API — no key, no port, just a socket.

`claude-local-api` turns the [Claude Code CLI](https://claude.ai/code) into a local API server. It listens on a Unix socket, accepts newline-delimited JSON prompts from any script on the machine, and returns Claude's response. No Anthropic API key needed — auth is handled by your existing Claude Code login. No HTTP server, no dependencies beyond the Python standard library.

---

## The Problem

Running `claude "your prompt"` from a shell script works, but every call:

- Spawns a brand-new process (~1–3 s startup before any inference)
- Loads MCP servers, hooks, memory, and CLAUDE.md from scratch
- Writes session state to disk
- Is synchronous — concurrent calls queue up

If you're calling Claude programmatically — from automation, pipelines, or other tools — this overhead adds up fast.

---

## The Solution

`claude_api` exposes a Unix socket server that accepts prompts and dispatches them to `claude` subprocesses. A semaphore limits how many processes run simultaneously, preventing resource exhaustion under load.

```
your script  ──►  Unix socket (/tmp/claude_api.sock)  ──►  concurrency semaphore (N slots)
                                                              └─ claude subprocess per request
```

Each subprocess uses flags that minimise startup overhead:

| Flag | What it skips |
|---|---|
| `--no-session-persistence` | Disk writes per request |
| `--tools ""` | Tool enumeration and loading |

The result: **minimal startup cost per request**, nothing else.

---

## Prerequisites

- **macOS or Linux** (Unix socket required)
- **Python 3.11+**
- **Claude Code CLI** installed and authenticated

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Authenticate (one-time)
claude auth login
```

No extra Python packages required — the server and client use only the standard library.

---

## Quick Start

### 1. Start the server

```bash
cd claude_api
python -m claude_api.server
```

You'll see:

```
[pool] ready — model=haiku, concurrency=3
[server] listening on /tmp/claude_api.sock
```

### 2. Send a prompt

**From the CLI:**

```bash
python -m claude_api.client "What is 2 + 2?"
python -m claude_api.client "Explain RSI" --model sonnet
python -m claude_api.client "Write a market summary" --model opus
```

**From Python (anywhere on the machine):**

```python
import sys
sys.path.insert(0, "/path/to/claude_api")
from claude_api import ask

resp = ask("What is MACD?")
print(resp["result"])        # the answer
print(resp["round_trip_ms"]) # total latency including socket
```

**Raw socket (zero dependencies):**

```bash
echo '{"prompt": "hello"}' | socat - UNIX-CONNECT:/tmp/claude_api.sock
```

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `CLAUDE_API_MODEL` | `haiku` | Default model for all pool workers |
| `CLAUDE_API_POOL_SIZE` | `3` | Number of warm workers to keep alive |

```bash
# Example: use sonnet with 2 workers
CLAUDE_API_MODEL=sonnet CLAUDE_API_POOL_SIZE=2 python -m claude_api.server
```

---

## Model Options

Pass `--model` on any request to override the pool default for that call. Spawns a temporary worker (one-off, not pooled).

| Alias | Model |
|---|---|
| `haiku` | claude-haiku-4-5 — fastest, lowest cost |
| `sonnet` | claude-sonnet-4-6 — balanced |
| `opus` | claude-opus-4-7 — most capable |

Full model IDs also accepted (e.g. `claude-haiku-4-5-20251001`).

---

## Wire Protocol

The socket speaks newline-delimited JSON.

**Request:**
```json
{"prompt": "your question", "model": "haiku"}
```
`model` is optional — omit to use the pool default.

**Response:**
```json
{"result": "The answer text", "worker_ms": 412}
```

**Error:**
```json
{"error": "description of what went wrong"}
```

---

## File Structure

```
claude_api/
├── server.py     # asyncio Unix socket server + request handler
├── worker.py     # WorkerPool — concurrency semaphore + claude subprocess per request
├── client.py     # CLI + importable Python client
└── README.md
```

---

## Run as a Background Service (optional)

To keep the server running across terminal sessions, use a launchd plist (macOS) or a systemd unit (Linux).

**macOS — launchd:**

Create `~/Library/LaunchAgents/com.claude_api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>        <string>com.claude_api</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string>
    <string>claude_api.server</string>
  </array>
  <key>WorkingDirectory</key> <string>/path/to/MarketCruise</string>
  <key>RunAtLoad</key>    <true/>
  <key>KeepAlive</key>    <true/>
  <key>StandardOutPath</key> <string>/tmp/claude_api.log</string>
  <key>StandardErrorPath</key> <string>/tmp/claude_api.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.claude_api.plist
```

**Linux — systemd:**

```ini
[Unit]
Description=claude_api Unix socket server

[Service]
ExecStart=/usr/bin/python3 -m claude_api.server
WorkingDirectory=/path/to/MarketCruise
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now claude_api
```

---

## Limitations

- Unix socket only — not accessible over a network by design (local machine only).
- Workers share no conversation context between requests (each prompt is stateless).
- Model override requests (`--model` different from the pool default) spawn a temporary process and pay the full startup cost for that single call.
- Requires an active Claude Code authentication session (`claude auth login`).
