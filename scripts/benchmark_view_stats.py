#!/usr/bin/env python3
"""
Benchmark view stats REST endpoints against a running Argus dev server.

Usage:
    # Start the server first:
    #   FLASK_ENV=development FLASK_APP=argus_backend:start_server \\
    #   CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 uv run flask run
    #
    uv run python scripts/benchmark_view_stats.py
    uv run python scripts/benchmark_view_stats.py --host http://localhost:5000 \\
        --username admin --password admin --iterations 5

Benchmarks:
    1. GET /api/v1/views/stats?viewId=<id>&force=1       (cold — bypasses cache)
    2. GET /api/v1/views/stats?viewId=<id>&force=0       (warm — served from cache)
    3. GET /api/v1/views/<id>/versions
    4. GET /api/v1/views/<id>/images
"""

import argparse
import sys
import time

import requests


def login(session: requests.Session, host: str, username: str, password: str) -> None:
    resp = session.post(f"{host}/auth/login", data={"username": username, "password": password}, allow_redirects=True)
    # After successful login Flask redirects to home; check we're not on an error page
    if resp.status_code not in (200, 302):
        print(f"Login failed: HTTP {resp.status_code}")
        sys.exit(1)
    # Verify session cookie was set
    if not session.cookies:
        print("Login failed: no session cookie received")
        sys.exit(1)


def get_view_id(session: requests.Session, host: str, view_name: str) -> str:
    resp = session.get(f"{host}/api/v1/views/all")
    resp.raise_for_status()
    views = resp.json().get("response", [])
    for v in views:
        if v["name"] == view_name:
            return str(v["id"])
    print(f"View '{view_name}' not found. Available: {[v['name'] for v in views]}")
    sys.exit(1)


def measure(label: str, fn, iterations: int) -> dict:
    times = []
    for i in range(iterations):
        t0 = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        times.append(elapsed_ms)
        print(f"    [{i + 1}/{iterations}] {elapsed_ms:.1f}ms")
    times_sorted = sorted(times)
    return {
        "label": label,
        "min": times_sorted[0],
        "median": times_sorted[len(times_sorted) // 2],
        "mean": sum(times) / len(times),
        "max": times_sorted[-1],
    }


def print_results(results: list[dict]) -> None:
    print()
    print("=" * 65)
    print("  BENCHMARK RESULTS")
    print("=" * 65)
    for r in results:
        print(f"  {r['label']}")
        print(f"    min={r['min']:.0f}ms  median={r['median']:.0f}ms  mean={r['mean']:.0f}ms  max={r['max']:.0f}ms")
    print("=" * 65)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark view stats REST endpoints")
    parser.add_argument("--host", default="http://localhost:5000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--view-name", default="benchmark-view")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()

    session = requests.Session()

    print(f"Logging in to {args.host} as {args.username}...")
    login(session, args.host, args.username, args.password)

    print(f"Resolving view '{args.view_name}'...")
    view_id = get_view_id(session, args.host, args.view_name)
    print(f"  view_id = {view_id}")
    print(f"  iterations = {args.iterations}")
    print()

    results = []

    # 1. Cold stats (force=1 — always recomputes, bypasses cache)
    url_cold = f"{args.host}/api/v1/views/stats?viewId={view_id}&force=1&includeNoVersion=1&limited=0"
    print("[1/4] GET /api/v1/views/stats  force=1  (cold — full fan-out every time):")
    results.append(
        measure(
            "GET /api/v1/views/stats  force=1  (cold)",
            lambda: session.get(url_cold).raise_for_status(),
            args.iterations,
        )
    )

    # 2. Warm stats (force=0 — served from cache after first hit)
    url_warm = f"{args.host}/api/v1/views/stats?viewId={view_id}&force=0&includeNoVersion=1&limited=0"
    # Prime the cache with one force=0 request first
    session.get(url_warm)
    print("\n[2/4] GET /api/v1/views/stats  force=0  (warm — cache hit):")
    results.append(
        measure(
            "GET /api/v1/views/stats  force=0  (warm cache)",
            lambda: session.get(url_warm).raise_for_status(),
            args.iterations,
        )
    )

    # 3. Versions
    url_versions = f"{args.host}/api/v1/views/{view_id}/versions"
    print("\n[3/4] GET /api/v1/views/<id>/versions:")
    results.append(
        measure(
            "GET /api/v1/views/<id>/versions",
            lambda: session.get(url_versions).raise_for_status(),
            args.iterations,
        )
    )

    # 4. Images
    url_images = f"{args.host}/api/v1/views/{view_id}/images"
    print("\n[4/4] GET /api/v1/views/<id>/images:")
    results.append(
        measure(
            "GET /api/v1/views/<id>/images",
            lambda: session.get(url_images).raise_for_status(),
            args.iterations,
        )
    )

    print_results(results)


if __name__ == "__main__":
    main()
