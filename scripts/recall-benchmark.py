#!/usr/bin/env python3
"""
Recall Benchmarking Self-Diagnostic

Tests the semantic recall pipeline (proactive-recall.py) against known
ground-truth facts stored in the database. Measures retrieval accuracy
across different query patterns.

Usage:
    python3 recall-benchmark.py [--verbose] [--json]

Output: Score summary with per-query results. Exit code 0 if hit rate >= 60%.
"""

import os
import sys
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────

PROACTIVE_RECALL_PATH = Path(__file__).parent / "proactive-recall.py"
PASS_THRESHOLD = 0.60  # 60% minimum hit rate to pass

# ── Benchmark Queries ──────────────────────────────────────────────
# Each query has:
#   - query: what we ask the recall system
#   - expected_keywords: at least one must appear in results for a "hit"
#   - category: the retrieval pattern being tested
#   - description: human explanation of what we're testing

BENCHMARK_QUERIES = [
    # --- Entity Lookups ---
    {
        "query": "What is I)ruid's real name?",
        "expected_keywords": ["dustin", "trammell"],
        "category": "entity_lookup",
        "description": "Direct entity fact retrieval — real name"
    },
    {
        "query": "What is I)ruid's birthday?",
        "expected_keywords": ["1978", "may", "27"],
        "category": "entity_lookup",
        "description": "Direct entity fact retrieval — birthday"
    },
    {
        "query": "How does I)ruid like to communicate?",
        "expected_keywords": ["direct", "technical", "concise", "no-nonsense"],
        "category": "entity_lookup",
        "description": "Entity fact — communication style"
    },
    {
        "query": "What is I)ruid's relationship to Bitcoin?",
        "expected_keywords": ["satoshi", "bitcoin", "btc", "earliest"],
        "category": "entity_lookup",
        "description": "Entity fact — notable history"
    },
    # --- Library / Knowledge Retrieval ---
    {
        "query": "Tell me about the Silmarillion",
        "expected_keywords": ["tolkien", "silmarillion", "arda", "first age"],
        "category": "library",
        "description": "Library work retrieval — Tolkien"
    },
    {
        "query": "What D&D books do we have?",
        "expected_keywords": ["dungeon", "dragon", "player", "handbook", "monster manual", "d&d"],
        "category": "library",
        "description": "Library collection query — D&D"
    },
    {
        "query": "What philosophy books are in the library?",
        "expected_keywords": ["meditations", "aurelius", "epictetus", "stoic", "enchiridion", "philosophy"],
        "category": "library",
        "description": "Library retrieval by subject"
    },
    # --- Lessons / Corrections ---
    {
        "query": "What have we learned about storing credentials?",
        "expected_keywords": ["credential", "immediately", "store", "account"],
        "category": "lesson",
        "description": "Lesson recall — credential handling"
    },
    {
        "query": "What happens when you restart the gateway?",
        "expected_keywords": ["restart", "gateway", "kill", "in-flight", "config"],
        "category": "lesson",
        "description": "Lesson recall — gateway restart behavior"
    },
    # --- Event Retrieval ---
    {
        "query": "When did we first post on Instagram?",
        "expected_keywords": ["instagram", "daily", "inspiration", "2026-02"],
        "category": "event",
        "description": "Event date retrieval — Instagram launch"
    },
    # --- Cross-Reference / Fuzzy ---
    {
        "query": "What projects does the NOVA agent ecosystem include?",
        "expected_keywords": ["nova-memory", "nova-cognition", "nova-mind", "memory", "cognition"],
        "category": "cross_reference",
        "description": "Cross-reference — project/repo knowledge"
    },
    {
        "query": "How does the semantic recall hook work?",
        "expected_keywords": ["embedding", "semantic", "recall", "proactive", "memory"],
        "category": "cross_reference",
        "description": "Architecture knowledge — recall pipeline"
    },
    {
        "query": "What is the agent bootstrap context system?",
        "expected_keywords": ["bootstrap", "context", "domain", "agent", "universal"],
        "category": "cross_reference",
        "description": "Architecture knowledge — bootstrap context"
    },
    # --- Negative / Noise Test ---
    {
        "query": "What is the weather like on Mars?",
        "expected_keywords": [],  # Empty = we expect NO relevant results (noise test)
        "category": "noise",
        "description": "Noise test — irrelevant query should return low-relevance or no results"
    },
]


def run_recall(query: str) -> dict:
    """Run proactive-recall.py and return parsed results."""
    try:
        result = subprocess.run(
            ["python3", str(PROACTIVE_RECALL_PATH), query],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ}
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "memories": []}

        output = result.stdout.strip()
        if not output:
            return {"memories": []}

        return json.loads(output)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "memories": []}
    except json.JSONDecodeError:
        return {"error": "invalid JSON output", "memories": []}
    except Exception as e:
        return {"error": str(e), "memories": []}


def check_hit(recall_result: dict, expected_keywords: list[str]) -> tuple[bool, str]:
    """
    Check if any expected keyword appears in the recall results.
    For noise tests (empty keywords), a hit means no high-relevance results.
    Returns (is_hit, explanation).
    """
    if "error" in recall_result:
        return False, f"Error: {recall_result['error']}"

    memories = recall_result.get("memories", [])

    # Noise test: success if no memories returned or all low relevance
    if not expected_keywords:
        if not memories:
            return True, "No results (correct for noise query)"
        # If results came back, it's a miss for the noise test
        return False, f"Got {len(memories)} results for noise query"

    # Normal test: check if any keyword appears in any memory
    all_text = " ".join(
        str(m.get("content", "")) + " " + str(m.get("source", ""))
        for m in memories
    ).lower()

    matched = [kw for kw in expected_keywords if kw.lower() in all_text]
    if matched:
        return True, f"Matched: {', '.join(matched)}"
    else:
        return False, f"None of [{', '.join(expected_keywords)}] found in {len(memories)} results"


def run_benchmark(verbose=False, json_output=False):
    """Run all benchmark queries and report results."""
    results = []
    categories = {}
    total_hits = 0
    total_queries = len(BENCHMARK_QUERIES)

    for i, bq in enumerate(BENCHMARK_QUERIES, 1):
        if verbose and not json_output:
            print(f"[{i}/{total_queries}] {bq['description']}...", end=" ", flush=True)

        recall_result = run_recall(bq["query"])
        is_hit, explanation = check_hit(recall_result, bq["expected_keywords"])

        if is_hit:
            total_hits += 1

        cat = bq["category"]
        if cat not in categories:
            categories[cat] = {"hits": 0, "total": 0}
        categories[cat]["total"] += 1
        if is_hit:
            categories[cat]["hits"] += 1

        result = {
            "query": bq["query"],
            "category": cat,
            "description": bq["description"],
            "hit": is_hit,
            "explanation": explanation,
            "num_results": len(recall_result.get("memories", [])),
        }
        results.append(result)

        if verbose and not json_output:
            status = "✅" if is_hit else "❌"
            print(f"{status} {explanation}")

    hit_rate = total_hits / total_queries if total_queries > 0 else 0
    passed = hit_rate >= PASS_THRESHOLD

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_queries": total_queries,
        "total_hits": total_hits,
        "hit_rate": round(hit_rate, 4),
        "pass_threshold": PASS_THRESHOLD,
        "passed": passed,
        "categories": {
            cat: {
                "hits": data["hits"],
                "total": data["total"],
                "rate": round(data["hits"] / data["total"], 2)
            }
            for cat, data in categories.items()
        },
    }

    if json_output:
        output = {"summary": summary, "results": results}
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  Recall Benchmark Results")
        print(f"  {summary['timestamp']}")
        print(f"{'='*60}")
        print(f"  Overall: {total_hits}/{total_queries} ({hit_rate:.0%})")
        print(f"  Threshold: {PASS_THRESHOLD:.0%}")
        print(f"  Status: {'✅ PASS' if passed else '❌ FAIL'}")
        print(f"{'─'*60}")
        print(f"  By Category:")
        for cat, data in summary["categories"].items():
            cat_status = "✅" if data["rate"] >= PASS_THRESHOLD else "⚠️"
            print(f"    {cat_status} {cat}: {data['hits']}/{data['total']} ({data['rate']:.0%})")
        print(f"{'='*60}")

    return 0 if passed else 1


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    json_out = "--json" in sys.argv
    sys.exit(run_benchmark(verbose=verbose, json_output=json_out))
