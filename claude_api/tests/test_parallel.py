"""
Parallel test: 3 simulated users, each sending 5 prompts concurrently.
Measures per-user latency, cross-user interference, throughput, and pool pressure.

Run from repo root:
    python -m claude_api.tests.test_parallel
    python -m claude_api.tests.test_parallel --model sonnet --users 3 --prompts 5
"""
import argparse
import asyncio
import json
import statistics
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__file__))))
from claude_api.client import ask

USER_PROMPTS = {
    "Alice": [
        "What is a moving average crossover strategy?",
        "Explain Bollinger Bands in one paragraph.",
        "What does volume in stock trading indicate?",
        "What is the difference between a limit order and a market order?",
        "What is 'support and resistance' in technical analysis?",
    ],
    "Bob": [
        "What is the Nifty 50 index?",
        "How does the RBI's repo rate affect stock markets?",
        "What is FII vs DII in Indian markets?",
        "Explain what a circuit breaker is on the NSE.",
        "What is the difference between delivery and intraday trading?",
    ],
    "Carol": [
        "What is a dividend yield and how is it calculated?",
        "What does EPS stand for in stock analysis?",
        "Explain what short selling is.",
        "What is a futures contract in simple terms?",
        "What does 'blue chip stock' mean?",
    ],
}


def token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


async def run_user(user_name: str, prompts: list[str], model: str, results: dict):
    user_results = []
    print(f"  [{user_name}] starting {len(prompts)} prompts …")
    user_start = time.perf_counter()

    for i, prompt in enumerate(prompts, 1):
        t0 = time.perf_counter()
        # ask() is blocking — run in thread so users are truly concurrent
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda p=prompt: ask(p, model=model)
        )
        elapsed = int((time.perf_counter() - t0) * 1000)

        if "error" in resp:
            user_results.append({"prompt": prompt, "error": resp["error"], "round_trip_ms": elapsed})
            print(f"  [{user_name}] #{i} ERROR: {resp['error']}")
        else:
            out_tok = token_estimate(resp["result"])
            in_tok = token_estimate(prompt)
            user_results.append({
                "prompt": prompt,
                "result_preview": resp["result"][:60].replace("\n", " "),
                "round_trip_ms": elapsed,
                "worker_ms": resp.get("worker_ms", elapsed),
                "prompt_tokens_est": in_tok,
                "output_tokens_est": out_tok,
            })
            print(f"  [{user_name}] #{i} {elapsed}ms | ~{out_tok} out tokens | {prompt[:40]}…")

    user_total_ms = int((time.perf_counter() - user_start) * 1000)
    results[user_name] = {"requests": user_results, "total_wall_ms": user_total_ms}
    print(f"  [{user_name}] done in {user_total_ms}ms\n")


async def run_parallel(users: dict[str, list[str]], model: str):
    results: dict = {}
    wall_start = time.perf_counter()

    await asyncio.gather(*[
        run_user(name, prompts, model, results)
        for name, prompts in users.items()
    ])

    total_wall_ms = int((time.perf_counter() - wall_start) * 1000)
    return results, total_wall_ms


def print_report(results: dict, total_wall_ms: int, model: str, num_users: int):
    print(f"\n{'='*60}")
    print(f"  PARALLEL TEST RESULTS — model: {model}")
    print(f"{'='*60}\n")

    all_latencies = []
    all_out_tokens = []
    all_total_tokens = []
    user_summaries = {}

    for user, data in results.items():
        reqs = [r for r in data["requests"] if "error" not in r]
        if not reqs:
            continue
        lats = [r["round_trip_ms"] for r in reqs]
        out_toks = [r["output_tokens_est"] for r in reqs]
        total_toks = [r["prompt_tokens_est"] + r["output_tokens_est"] for r in reqs]

        all_latencies.extend(lats)
        all_out_tokens.extend(out_toks)
        all_total_tokens.extend(total_toks)

        user_summaries[user] = {
            "succeeded": len(reqs),
            "total": len(data["requests"]),
            "wall_ms": data["total_wall_ms"],
            "lat_mean_ms": int(statistics.mean(lats)),
            "lat_min_ms": min(lats),
            "lat_max_ms": max(lats),
            "total_tokens_est": sum(total_toks),
        }

        print(f"  {user}")
        print(f"    requests    : {len(reqs)}/{len(data['requests'])} ok")
        print(f"    wall time   : {data['total_wall_ms']}ms")
        print(f"    latency avg : {int(statistics.mean(lats))}ms  (min {min(lats)} / max {max(lats)})")
        print(f"    tokens est  : {sum(total_toks)} total ({sum(out_toks)} output)")
        print()

    if all_latencies:
        throughput = round(len(all_latencies) / (total_wall_ms / 1000), 2)
        sequential_equiv = sum(all_latencies)
        speedup = round(sequential_equiv / total_wall_ms, 2)

        print(f"{'─'*60}")
        print(f"  AGGREGATE")
        print(f"{'─'*60}")
        print(f"  Users / prompts each  : {num_users} / {len(all_latencies)//num_users}")
        print(f"  Total requests        : {len(all_latencies)}")
        print(f"  Total wall time       : {total_wall_ms}ms  ({total_wall_ms/1000:.1f}s)")
        print(f"  Sequential equiv      : {sequential_equiv}ms  ({sequential_equiv/1000:.1f}s)")
        print(f"  Speedup vs sequential : {speedup}x")
        print(f"  Throughput            : {throughput} req/s")
        print(f"  Latency p50           : {int(statistics.median(all_latencies))}ms")
        print(f"  Latency p95           : {int(sorted(all_latencies)[int(len(all_latencies)*0.95)-1])}ms")
        print(f"  Latency min/max       : {min(all_latencies)}ms / {max(all_latencies)}ms")
        print(f"  Avg output tokens     : {int(statistics.mean(all_out_tokens))} (est)")
        print(f"  Total tokens          : {sum(all_total_tokens)} (est)")
        print(f"{'─'*60}\n")

        report = {
            "test": "parallel",
            "model": model,
            "num_users": num_users,
            "prompts_per_user": len(all_latencies) // num_users,
            "total_requests": len(all_latencies),
            "total_wall_ms": total_wall_ms,
            "sequential_equiv_ms": sequential_equiv,
            "speedup": speedup,
            "throughput_rps": throughput,
            "latency_ms": {
                "min": min(all_latencies),
                "max": max(all_latencies),
                "mean": round(statistics.mean(all_latencies), 1),
                "median": round(statistics.median(all_latencies), 1),
                "p95": sorted(all_latencies)[int(len(all_latencies)*0.95)-1],
            },
            "tokens_est": {
                "avg_output": round(statistics.mean(all_out_tokens), 1),
                "total": sum(all_total_tokens),
            },
            "per_user": user_summaries,
        }

        out_path = f"claude_api/tests/results_parallel_{model}.json"
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  Report saved → {out_path}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--users", type=int, default=3, help="Number of concurrent users (max 3 with built-in prompts)")
    parser.add_argument("--prompts", type=int, default=5, help="Prompts per user (max 5 with built-in prompts)")
    args = parser.parse_args()

    users = {
        name: prompts[:args.prompts]
        for name, prompts in list(USER_PROMPTS.items())[:args.users]
    }

    print(f"\n{'='*60}")
    print(f"  PARALLEL TEST — {args.users} users × {args.prompts} prompts — model: {args.model}")
    print(f"{'='*60}\n")

    results, total_wall_ms = asyncio.run(run_parallel(users, args.model))
    print_report(results, total_wall_ms, args.model, len(users))


if __name__ == "__main__":
    main()
