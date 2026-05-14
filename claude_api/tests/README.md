# claude_api — Test Suite

Two benchmarks that verify correctness and measure real-world performance of the `claude_api` Unix socket server.

---

## Prerequisites

The server must be running before you execute either test.

```bash
# From the repo root
python -m claude_api.server
```

Wait for:
```
[pool] ready — model=haiku, concurrency=4
[server] listening on /tmp/claude_api.sock
```

---

## Tests

### 1. Sequential — `test_sequential.py`

Fires **10 prompts one after another** through the socket and records per-request metrics.

**What it measures:**
- Per-request round-trip latency (ms)
- Estimated prompt and output token counts (~4 chars per token)
- p50 / p95 / min / max latency
- Total wall time and total tokens across all requests

**Run:**
```bash
# Default model (haiku)
python -m claude_api.tests.test_sequential

# Override model
python -m claude_api.tests.test_sequential --model sonnet
python -m claude_api.tests.test_sequential --model opus
```

**Sample output:**
```
============================================================
  SEQUENTIAL TEST — 10 prompts — model: haiku
============================================================

[01/10] What is the difference between a stock and a bond?…
       latency: 10652ms | tokens est: 12p + 335o = 347 total
       preview: **Stocks** and **bonds** are two different types…

...

────────────────────────────────────────────────────────────
  SUMMARY
────────────────────────────────────────────────────────────
  Requests        : 10/10 succeeded
  Total wall time : 107179ms
  Latency p50     : 11014ms
  Latency p95     : 13059ms
  Latency min/max : 7711ms / 13386ms
  Avg latency     : 10717ms
  Avg output tok  : 269 (est)
  Total tokens    : 2803 (est)
────────────────────────────────────────────────────────────
```

**Saved report:** `claude_api/tests/results_sequential_<model>.json`

---

### 2. Parallel — `test_parallel.py`

Simulates **3 concurrent users** (Alice, Bob, Carol), each sending **5 prompts simultaneously**. All 15 requests race through the pool at the same time.

**What it measures:**
- Per-user wall time and per-request latency
- Aggregate throughput (requests/second)
- Speedup vs sequential equivalent (parallelism efficiency)
- p50 / p95 latency under concurrent load
- Pool pressure and cross-user interference

**Run:**
```bash
# Default: 3 users × 5 prompts, haiku
python -m claude_api.tests.test_parallel

# Override model or scale
python -m claude_api.tests.test_parallel --model sonnet
python -m claude_api.tests.test_parallel --users 2 --prompts 3
```

**Sample output:**
```
============================================================
  PARALLEL TEST — 3 users × 5 prompts — model: haiku
============================================================

  [Alice] starting 5 prompts …
  [Bob] starting 5 prompts …
  [Carol] starting 5 prompts …
  [Bob]   #1  9560ms | ~210 out tokens | What is the Nifty 50 index?…
  [Carol] #1 11106ms | ~290 out tokens | What is a dividend yield…
  ...
  [Carol] done in 56057ms
  [Alice] done in 58363ms
  [Bob]   done in 60524ms

────────────────────────────────────────────────────────────
  AGGREGATE
────────────────────────────────────────────────────────────
  Users / prompts each  : 3 / 5
  Total requests        : 15
  Total wall time       : 60526ms  (60.5s)
  Sequential equiv      : 174937ms (174.9s)
  Speedup vs sequential : 2.89x
  Throughput            : 0.25 req/s
  Latency p50           : 11106ms
  Latency p95           : 14046ms
  Latency min/max       : 9048ms / 15247ms
  Avg output tokens     : 305 (est)
  Total tokens          : 4747 (est)
────────────────────────────────────────────────────────────
```

**Saved report:** `claude_api/tests/results_parallel_<model>.json`

---

## Benchmark Results (haiku, 2026-05-15)

### Sequential
| Metric | Value |
|---|---|
| Requests | 10 / 10 succeeded |
| Avg latency | 10,717 ms |
| p50 latency | 11,014 ms |
| p95 latency | 13,059 ms |
| Min / Max | 7,711 ms / 13,386 ms |
| Avg output tokens | ~269 |
| Total tokens (est) | 2,803 |

### Parallel (3 users × 5 prompts)
| Metric | Value |
|---|---|
| Requests | 15 / 15 succeeded |
| Total wall time | 60.5 s |
| Sequential equivalent | 174.9 s |
| **Speedup** | **2.89x** |
| Throughput | 0.25 req/s |
| p50 latency | 11,106 ms |
| p95 latency | 14,046 ms |
| Avg output tokens | ~305 |
| Total tokens (est) | 4,747 |

> Latency figures reflect Haiku model inference time. The socket and pool overhead is negligible (<5 ms). Switching to `sonnet` or `opus` will increase latency and output quality.

---

## Output Files

Each test writes a JSON report alongside the test scripts:

```
claude_api/tests/
├── results_sequential_haiku.json
├── results_sequential_sonnet.json   # if run with --model sonnet
├── results_parallel_haiku.json
└── results_parallel_sonnet.json
```

Each report contains the full per-request breakdown alongside aggregate stats, making it easy to diff results across models or server configurations.

---

## Prompts Used

All prompts are Indian stock market / finance Q&A — realistic for the MarketCruise use case. They are hardcoded in each test file and designed to produce varied output lengths so latency and token distributions are meaningful rather than artificially uniform.

**Sequential prompts** (`test_sequential.py`): general finance concepts (stocks vs bonds, RSI, MACD, P/E ratio, moving averages, NSE vs BSE, stop-loss).

**Parallel prompts** (`test_parallel.py`): split across three users with distinct topics:
- **Alice** — technical analysis (Bollinger Bands, volume, moving average crossover)
- **Bob** — Indian market specifics (Nifty 50, RBI repo rate, FII/DII, circuit breakers)
- **Carol** — fundamentals (dividend yield, EPS, short selling, futures, blue chip)
