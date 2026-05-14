"""
Sequential test: 10 prompts fired one-after-another.
Measures per-request latency, token counts, and aggregate stats.

Run from repo root:
    python -m claude_api.tests.test_sequential
    python -m claude_api.tests.test_sequential --model sonnet
"""
import argparse
import json
import statistics
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__file__))))
from claude_api.client import ask

PROMPTS = [
    "What is the difference between a stock and a bond?",
    "Explain what RSI means in technical analysis in one paragraph.",
    "What does MACD stand for and how is it used?",
    "Name three candlestick patterns used in trading.",
    "What is the P/E ratio and why does it matter?",
    "Describe what a bull market is in two sentences.",
    "What is the difference between NSE and BSE?",
    "What does 'market capitalisation' mean?",
    "Explain what a moving average is.",
    "What is a stop-loss order and when would you use it?",
]


def token_estimate(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def run(model: str):
    print(f"\n{'='*60}")
    print(f"  SEQUENTIAL TEST — 10 prompts — model: {model}")
    print(f"{'='*60}\n")

    results = []
    for i, prompt in enumerate(PROMPTS, 1):
        print(f"[{i:02d}/10] {prompt[:55]}…")
        resp = ask(prompt, model=model)

        if "error" in resp:
            print(f"       ERROR: {resp['error']}\n")
            results.append({"prompt": prompt, "error": resp["error"]})
            continue

        result_text = resp["result"]
        worker_ms = resp.get("worker_ms", 0)
        rtt_ms = resp.get("round_trip_ms", worker_ms)
        prompt_tokens = token_estimate(prompt)
        output_tokens = token_estimate(result_text)

        results.append({
            "index": i,
            "prompt": prompt,
            "result_preview": result_text[:80].replace("\n", " "),
            "worker_ms": worker_ms,
            "round_trip_ms": rtt_ms,
            "prompt_tokens_est": prompt_tokens,
            "output_tokens_est": output_tokens,
            "total_tokens_est": prompt_tokens + output_tokens,
        })

        print(f"       latency: {rtt_ms}ms | tokens est: {prompt_tokens}p + {output_tokens}o = {prompt_tokens+output_tokens} total")
        print(f"       preview: {result_text[:80].replace(chr(10), ' ')}…\n")

    # ── Summary ──────────────────────────────────────────────────────────────
    ok = [r for r in results if "error" not in r]
    if not ok:
        print("All requests failed.")
        return

    latencies = [r["round_trip_ms"] for r in ok]
    tokens_out = [r["output_tokens_est"] for r in ok]
    tokens_total = [r["total_tokens_est"] for r in ok]

    print(f"\n{'─'*60}")
    print(f"  SUMMARY")
    print(f"{'─'*60}")
    print(f"  Requests        : {len(ok)}/{len(PROMPTS)} succeeded")
    print(f"  Total wall time : {sum(latencies)}ms")
    print(f"  Latency p50     : {int(statistics.median(latencies))}ms")
    print(f"  Latency p95     : {int(sorted(latencies)[int(len(latencies)*0.95)-1])}ms")
    print(f"  Latency min/max : {min(latencies)}ms / {max(latencies)}ms")
    print(f"  Avg latency     : {int(statistics.mean(latencies))}ms")
    print(f"  Avg output tok  : {int(statistics.mean(tokens_out))} (est)")
    print(f"  Total tokens    : {sum(tokens_total)} (est)")
    print(f"{'─'*60}\n")

    # Save JSON report
    report = {
        "test": "sequential",
        "model": model,
        "num_prompts": len(PROMPTS),
        "succeeded": len(ok),
        "latency_ms": {
            "min": min(latencies), "max": max(latencies),
            "mean": round(statistics.mean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "p95": sorted(latencies)[int(len(latencies)*0.95)-1],
            "total_wall": sum(latencies),
        },
        "tokens_est": {
            "avg_output": round(statistics.mean(tokens_out), 1),
            "total": sum(tokens_total),
        },
        "requests": ok,
    }
    out_path = f"claude_api/tests/results_sequential_{model}.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved → {out_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="haiku")
    args = parser.parse_args()
    run(args.model)
