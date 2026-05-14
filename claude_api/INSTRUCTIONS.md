# Instructions for Agents — How to Use claude_api as a Free LLM Backend

This document is written for AI agents and Claude instances. If you are an agent reading this to understand how to add LLM capability to a project, this is the right file.

---

## What This Gives You

A running `claude_api` server on this machine exposes a **Unix socket** at `/tmp/claude_api.sock`. You can send any text prompt to it and receive a response from a Claude model (haiku by default, sonnet or opus on request).

- **No API key needed in your code** — auth is handled by the host machine's Claude Code login.
- **No HTTP server, no port, no firewall** — pure Unix socket, local machine only.
- **No extra Python packages** — stdlib only (`socket`, `json`).
- **Concurrent-safe** — the server handles multiple callers at the same time.

---

## Step 1 — Check the Server is Running

Before writing any code, verify the socket exists:

```bash
python3 -c "
import socket
s = socket.socket(socket.AF_UNIX)
s.connect('/tmp/claude_api.sock')
s.sendall(b'{\"prompt\": \"ping\"}\n')
print(s.recv(4096).decode())
s.close()
"
```

Expected output:
```json
{"result": "...", "worker_ms": 8200}
```

If you get `FileNotFoundError` or `ConnectionRefusedError`, the server is not running. Tell the user to start it:

```bash
# From the MarketCruise repo root
python -m claude_api.server
```

---

## Step 2 — Call It From Your Code

### Minimal Python (copy-paste this, no imports beyond stdlib)

```python
import socket
import json

def ask_claude(prompt: str, model: str = None, timeout: int = 60) -> str:
    """
    Send a prompt to the local claude_api server.
    Returns the response text, or raises RuntimeError on failure.
    """
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
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break

    resp = json.loads(b"".join(chunks).decode().strip())
    if "error" in resp:
        raise RuntimeError(f"claude_api error: {resp['error']}")
    return resp["result"]


# Usage
answer = ask_claude("Summarise the risks of this portfolio in two sentences.")
answer = ask_claude("Write a Python function to compute RSI.", model="sonnet")
answer = ask_claude("Do a deep analysis of this earnings report.", model="opus")
```

### If you have the claude_api package on the Python path

```python
from claude_api import ask

resp = ask("Your prompt here")
print(resp["result"])       # the text answer
print(resp["worker_ms"])    # how long the model took (ms)
```

---

## Wire Protocol

Everything is **newline-delimited JSON** over the Unix socket.

**Request** (you send):
```json
{"prompt": "your question or instruction", "model": "haiku"}
```

`model` is optional. Omit it to use the server default (haiku).

**Response** (you receive):
```json
{"result": "The full response text", "worker_ms": 9400}
```

**Error response**:
```json
{"error": "description of what went wrong"}
```

Always check for the `"error"` key before reading `"result"`.

---

## Model Choice

| Model | Alias | When to use |
|---|---|---|
| claude-haiku-4-5 | `haiku` | Default. Fast, cheap, good for classification, extraction, short answers |
| claude-sonnet-4-6 | `sonnet` | Balanced. Use for summaries, structured output, moderate reasoning |
| claude-opus-4-7 | `opus` | Most capable. Use for complex analysis, long-form generation, hard reasoning |

Pass the alias — full model IDs also work.

**Rule of thumb:** start with haiku. Only upgrade the model if the output quality is insufficient for the task.

---

## Async Usage (asyncio projects)

The socket call blocks the thread. In an async project, run it in an executor so you don't block the event loop:

```python
import asyncio
import socket
import json

async def ask_claude_async(prompt: str, model: str = None) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: ask_claude(prompt, model)   # ask_claude from the snippet above
    )

# Fire multiple prompts concurrently
results = await asyncio.gather(
    ask_claude_async("Summarise stock A"),
    ask_claude_async("Summarise stock B"),
    ask_claude_async("Summarise stock C"),
)
```

The server has a concurrency semaphore (default 3). Requests beyond that queue automatically — you do not need to throttle manually.

---

## Dropping It Into a LangChain / LangGraph Project

If your project uses LangChain or LangGraph and needs an LLM node, wrap `ask_claude` as a custom LLM:

```python
from langchain_core.language_models.llms import LLM
from typing import Any, List, Optional
import socket, json

class ClaudeAPILLM(LLM):
    model: str = "haiku"
    socket_path: str = "/tmp/claude_api.sock"

    @property
    def _llm_type(self) -> str:
        return "claude_api"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        req = {"prompt": prompt, "model": self.model}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(120)
            s.connect(self.socket_path)
            s.sendall(json.dumps(req).encode() + b"\n")
            chunks = []
            while True:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break
        resp = json.loads(b"".join(chunks).decode().strip())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp["result"]

# Use it anywhere a LangChain LLM is accepted
llm = ClaudeAPILLM(model="sonnet")
result = llm.invoke("What is the current sentiment on NIFTY?")
```

---

## Common Patterns

### Structured output (JSON from the model)

```python
import json

def ask_json(prompt: str, model: str = "sonnet") -> dict:
    full_prompt = f"""{prompt}

Respond with valid JSON only. No explanation, no markdown, no code block. Raw JSON."""
    raw = ask_claude(full_prompt, model=model)
    # strip any accidental markdown fences
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

data = ask_json("Return a JSON object with keys: sentiment, score (0-1), reason. Analyse: 'Infosys beats Q3 estimates by 8%'")
# {'sentiment': 'positive', 'score': 0.85, 'reason': '...'}
```

### Classify into fixed categories

```python
def classify(text: str, categories: list[str]) -> str:
    cats = ", ".join(categories)
    prompt = f"Classify the following into exactly one of [{cats}]. Reply with the category name only.\n\n{text}"
    return ask_claude(prompt, model="haiku").strip()

label = classify("Reliance surges 4% on strong refining margins", ["bullish", "bearish", "neutral"])
```

### Retry on transient errors

```python
import time

def ask_with_retry(prompt: str, model: str = "haiku", retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            return ask_claude(prompt, model=model)
        except RuntimeError as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
```

---

## What the Server Does Not Support

Be aware of these limits before designing around it:

- **No conversation memory** — each call is stateless. The model has no memory of previous calls. If you need multi-turn context, concatenate the history into the prompt yourself.
- **No streaming to your code** — the server waits for the full response before returning it. Perceived latency is the full model inference time.
- **Local machine only** — the Unix socket is not accessible over a network. Do not try to tunnel it unless you know what you are doing.
- **No function/tool calling** — the server starts claude with `--tools ""`. It is a pure text-in / text-out interface.
- **Rate limits still apply** — the underlying Claude Code account has a usage quota. If you hit it, requests will fail with a rate-limit error from the server.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: /tmp/claude_api.sock` | Server not started | Run `python -m claude_api.server` |
| `{"error": "Connection lost"}` | Server crashed or restarting | Check server logs; restart it |
| `{"error": "empty result from claude"}` | claude process failed internally | Check if claude auth is still valid (`claude auth status`) |
| Response takes >30s | Model overloaded or large output | Switch to haiku, or increase socket timeout |
| `RuntimeError: rate limit` | Claude account quota hit | Wait and retry, or check usage at claude.ai |

---

## File Reference

```
claude_api/
├── server.py        # Start this to run the service
├── worker.py        # Subprocess management and concurrency semaphore
├── client.py        # CLI client + importable ask() function
├── __init__.py      # Exports ask() at package level
├── README.md        # Human-facing setup and usage guide
├── INSTRUCTIONS.md  # This file — for agents integrating the API
└── tests/
    ├── test_sequential.py   # 10-prompt sequential benchmark
    ├── test_parallel.py     # 3-user × 5-prompt parallel benchmark
    └── README.md            # Benchmark results and instructions
```

The only file you need to read to use the API is this one. The only function you need is `ask_claude` above.
