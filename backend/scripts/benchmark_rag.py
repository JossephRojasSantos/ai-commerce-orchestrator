#!/usr/bin/env python
"""
Benchmark RAG endpoint latency and hit quality.

Usage:
    python scripts/benchmark_rag.py [--url URL] [--runs N]
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

QUERIES = [
    "muñeca para niña de 5 años",
    "juguete educativo matemáticas",
    "regalo cumpleaños niño 8 años",
    "juego de mesa familia",
    "peluche suave bebé",
    "lego construcción avanzado",
    "juguete al aire libre verano",
    "kit ciencia experimentos niños",
]


async def run_benchmark(base_url: str, runs: int) -> None:
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in QUERIES:
            latencies = []
            hit_counts = []
            scores = []

            for _ in range(runs):
                t0 = time.monotonic()
                resp = await client.post(
                    f"{base_url}/v1/rag/recommend",
                    json={"query": query, "top_k": 5, "min_score": 0.35, "generate": False},
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    latencies.append(elapsed_ms)
                    hit_counts.append(len(data.get("hits", [])))
                    scores.extend(h["score"] for h in data.get("hits", []))
                else:
                    print(f"  ERROR {resp.status_code}: {query[:40]}")

            if latencies:
                results.append(
                    {
                        "query": query[:45],
                        "p50_ms": int(statistics.median(latencies)),
                        "p95_ms": int(sorted(latencies)[int(len(latencies) * 0.95)]),
                        "avg_hits": round(statistics.mean(hit_counts), 1),
                        "avg_score": round(statistics.mean(scores), 3) if scores else 0.0,
                    }
                )

    print(f"\n{'Query':<46} {'P50':>6} {'P95':>6} {'Hits':>5} {'Score':>6}")
    print("-" * 75)
    for r in results:
        print(
            f"{r['query']:<46} {r['p50_ms']:>5}ms {r['p95_ms']:>5}ms "
            f"{r['avg_hits']:>5} {r['avg_score']:>6.3f}"
        )

    all_p50 = [r["p50_ms"] for r in results]
    if all_p50:
        print(f"\nOverall P50: {int(statistics.median(all_p50))}ms | P95: {max(r['p95_ms'] for r in results)}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark RAG endpoint")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.url, args.runs))


if __name__ == "__main__":
    main()
