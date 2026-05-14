# claude-local-api

<p align="center">
  <img src="https://img.shields.io/badge/Claude-Opus%20%7C%20Sonnet%20%7C%20Haiku-blueviolet?style=for-the-badge&logo=anthropic&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey?style=for-the-badge&logo=apple&logoColor=white" />
  <img src="https://img.shields.io/badge/Zero%20Dependencies-stdlib%20only-success?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Auth-Claude%20Code%20Login-orange?style=for-the-badge" />
</p>

<p align="center">
  <strong>Run Opus. Run Sonnet. Run Haiku. No API key. No cloud bill. Just your machine.</strong>
</p>

<p align="center">
  Zero-config local Claude API — no key, no port, just a socket.
</p>

`claude-local-api` turns the [Claude Code CLI](https://claude.ai/code) into a local API server. It listens on a Unix socket, accepts prompts from any script on the machine, and returns Claude's response. No Anthropic API key needed — auth is handled by your existing Claude Code login. No HTTP server, no extra dependencies.

---

## Prerequisites

- **macOS or Linux** (Unix socket required)
- **Python 3.11+**
- **Claude Code CLI** installed and authenticated

```bash
npm install -g @anthropic-ai/claude-code
claude auth login
```

---

## Start the Server

```bash
python server.py
```

```
[pool] ready — model=haiku, concurrency=3
[server] listening on /tmp/claude_api.sock
```

Set env vars to change the default model or concurrency:

```bash
CLAUDE_API_MODEL=sonnet CLAUDE_API_POOL_SIZE=5 python server.py
```

---

## Usage

This is a drop-in replacement for any LLM SDK call in your local scripts. The pattern is identical to how you'd use the Anthropic SDK, OpenAI SDK, or Bedrock — call it once, call it in a loop, call it concurrently. The server handles the rest.

### The one function you need

Copy this into any script. No installs, no imports beyond stdlib:

```python
import socket, json

def ask_claude(prompt: str, model: str = None, timeout: int = 60) -> str:
    req = {"prompt": prompt}
    if model:
        req["model"] = model
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect("/tmp/claude_api.sock")
        s.sendall(json.dumps(req).encode() + b"\n")
        chunks = []
        while True:
            data = s.recv(4096)
            if not data or b"\n" in data:
                chunks.append(data)
                break
            chunks.append(data)
    resp = json.loads(b"".join(chunks).decode().strip())
    if "error" in resp:
        raise RuntimeError(f"claude error: {resp['error']}")
    return resp["result"]
```

### Single call

```python
answer = ask_claude("Summarise the risks of this portfolio in two sentences.")
print(answer)
```

### Choose your model

```python
# Fast, cheap — classification, extraction, short answers
answer = ask_claude("Is this headline bullish or bearish?", model="haiku")

# Balanced — summaries, structured output, moderate reasoning
report = ask_claude("Write a one-page analysis of Q3 earnings.", model="sonnet")

# Most capable — complex analysis, long-form generation, hard reasoning
deep = ask_claude("Do a deep multi-factor analysis of this balance sheet.", model="opus")
```

### Call it in a loop — process a list of items

```python
headlines = [
    "Reliance surges 4% on strong refining margins",
    "Infosys misses Q3 estimates, stock falls 6%",
    "RBI holds repo rate, markets rally",
]

for headline in headlines:
    sentiment = ask_claude(
        f"Classify as bullish, bearish, or neutral. Reply with one word only.\n\n{headline}",
        model="haiku"
    )
    print(f"{sentiment.strip():10s}  {headline}")
```

### Structured JSON output

```python
import json

def ask_json(prompt: str, model: str = "sonnet") -> dict:
    raw = ask_claude(prompt + "\n\nRespond with valid JSON only. No markdown.", model=model)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

result = ask_json(
    "Analyse: 'Infosys beats Q3 estimates by 8%'. "
    "Return JSON with keys: sentiment, score (0.0–1.0), reason."
)
# {'sentiment': 'positive', 'score': 0.87, 'reason': '...'}
```

### Concurrent calls — process many items at once

```python
import asyncio, socket, json

async def ask_claude_async(prompt: str, model: str = "haiku") -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: ask_claude(prompt, model))

async def main():
    stocks = ["RELIANCE", "INFY", "TCS", "HDFC", "WIPRO"]
    prompts = [f"Give a one-line technical outlook for {s} stock." for s in stocks]

    results = await asyncio.gather(*[ask_claude_async(p) for p in prompts])

    for stock, result in zip(stocks, results):
        print(f"{stock}: {result}\n")

asyncio.run(main())
```

The server queues requests beyond the concurrency limit automatically — you don't need to throttle.

### With retry on failure

```python
import time

def ask_with_retry(prompt: str, model: str = "haiku", retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            return ask_claude(prompt, model=model)
        except RuntimeError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
```

---

## Model Reference

| Alias | Model | Best for |
|---|---|---|
| `haiku` | claude-haiku-4-5 | Classification, extraction, short answers — fastest |
| `sonnet` | claude-sonnet-4-6 | Summaries, structured output, moderate reasoning |
| `opus` | claude-opus-4-7 | Complex analysis, long-form generation, hard reasoning |

Start with `haiku`. Upgrade only if the output quality isn't good enough.

---

## Run as a Background Service

**macOS — launchd:**

Create `~/Library/LaunchAgents/com.claude-local-api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>        <string>com.claude-local-api</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/claude-local-api/server.py</string>
  </array>
  <key>RunAtLoad</key>    <true/>
  <key>KeepAlive</key>    <true/>
  <key>StandardOutPath</key> <string>/tmp/claude-local-api.log</string>
  <key>StandardErrorPath</key> <string>/tmp/claude-local-api.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.claude-local-api.plist
```

**Linux — systemd:**

```ini
[Unit]
Description=claude-local-api Unix socket server

[Service]
ExecStart=/usr/bin/python3 /path/to/claude-local-api/server.py
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now claude-local-api
```

---

## Benchmarks

Measured on macOS (Apple M-series), model: `claude-haiku-4-5`, concurrency: 3.

### Sequential — 10 prompts, one after another

| Metric | Value |
|---|---|
| Requests | 10 / 10 succeeded |
| Total wall time | 98.9 s |
| Avg latency | 9,892 ms |
| p50 latency | 10,262 ms |
| p95 latency | 11,936 ms |
| Min / Max | 6,153 ms / 12,739 ms |

### Concurrent — 3 users × 5 prompts in parallel

| Metric | Value |
|---|---|
| Requests | 15 / 15 succeeded |
| Total wall time | 62.2 s |
| Sequential equivalent | 172.9 s |
| **Speedup** | **2.78×** |
| Throughput | 0.24 req/s |
| p50 latency | 11,451 ms |
| p95 latency | 13,274 ms |
| Min / Max | 8,103 ms / 14,303 ms |

> Latency is dominated by model inference time, not socket or server overhead. The socket round-trip adds < 5 ms.

---

## Limitations

- Local machine only — the Unix socket is not accessible over a network.
- Each call is stateless — no conversation memory between requests. Concatenate history into the prompt yourself if you need multi-turn context.
- No streaming — the server returns the full response once inference is complete.
- Requires an active Claude Code session (`claude auth login`).
