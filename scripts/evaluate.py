#!/usr/bin/env python3
"""CLI evaluation script for Knowledge Base Agent.

Usage:
    python scripts/evaluate.py --kb-id <kb_id> --test-file <path> [--output <path>]

Example:
    python scripts/evaluate.py --kb-id abc123 --test-file tests/cases.json
    python scripts/evaluate.py --kb-id abc123 --test-file tests/cases.csv --output results.json
"""
import argparse
import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="Knowledge Base Agent Evaluation")
    parser.add_argument("--kb-id", required=True, help="Knowledge base ID")
    parser.add_argument("--test-file", required=True, help="Test cases file (JSON/CSV)")
    parser.add_argument("--output", default="", help="Output file path")
    args = parser.parse_args()

    from app.evaluation.cli import Evaluator
    evaluator = Evaluator(args.kb_id, args.test_file, args.output)

    try:
        asyncio.run(evaluator.evaluate())
    except KeyboardInterrupt:
        print("\nEvaluation interrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"Evaluation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
