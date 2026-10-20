#!/usr/bin/env python3
"""Run the complete DETOUR LAB research & performance benchmark suite.

Usage:
    python scripts/run_benchmarks.py [--iterations 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add apps/api to path
REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from detour_lab.benchmarks.runner import execute_full_benchmark_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DETOUR LAB research & scalability benchmarks.")
    parser.add_argument("--iterations", type=int, default=20, help="Number of repetitions for latency measurements")
    args = parser.parse_args()

    print(f"==> Starting DETOUR LAB research & scalability benchmarks ({args.iterations} iterations)...")
    res = execute_full_benchmark_suite(REPO_ROOT, iterations=args.iterations)

    summary = res["research_benchmark"]["summary_metrics"]
    print("\n--- RESEARCH BENCHMARK SUMMARY ---")
    print(f"  Baseline A (Shortest Path) False-Safe Rate : {summary['baseline_a_false_safe_rate']:.1%}")
    print(f"  DETOUR LAB False-Safe Rate                 : {summary['detour_lab_false_safe_rate']:.1%}")
    print(f"  Baseline B (Static) Phase Blindness Rate   : {summary['baseline_b_phase_blindness_rate']:.1%}")
    print(f"  Baseline C (Checklist) Disconnection Blind : {summary['baseline_c_disconnection_blindness_rate']:.1%}")
    print(f"  Baseline E (B-5) Gain Over Random Order    : {summary['baseline_e_inspection_gain_over_random']:.1%}")
    print(f"  Total Controlled Fixtures Evaluated        : {summary['benchmarks_total_fixtures']}")

    perf = res["performance_benchmark"]
    print("\n--- SCALABILITY TIMINGS (Dijkstra Routing) ---")
    for t in perf["routing_timings"]:
        print(f"  {t['workload_name']:<18} ({t['node_count']} nodes, {t['edge_count']} edges): p50={t['p50_ms']} ms, p95={t['p95_ms']} ms, mean={t['mean_ms']} ms")

    print("\n--- SCALABILITY TIMINGS (Rule Evaluation) ---")
    for t in perf["rule_eval_timings"]:
        print(f"  {t['workload_name']:<18} ({t['node_count']} nodes, {t['edge_count']} edges): p50={t['p50_ms']} ms, p95={t['p95_ms']} ms, mean={t['mean_ms']} ms")

    print(f"\nSaved raw research benchmarks to: {res['research_path']}")
    print(f"Saved raw performance benchmarks to: {res['performance_path']}")
    print("==> Research benchmarks completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
