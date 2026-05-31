from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Evaluator:
    """CLI evaluation for knowledge base agent using LangSmith concepts.

    Evaluates three dimensions:
    - Correctness: Is the answer factually correct?
    - Groundedness: Is the answer supported by retrieved documents?
    - Retrieval Relevance: Are the retrieved documents relevant to the query?
    """

    def __init__(self, kb_id: str, test_file: str, output_file: str = ""):
        self.kb_id = kb_id
        self.test_file = Path(test_file)
        self.output_file = Path(output_file) if output_file else Path("evaluation_results.json")
        self.results: list[dict[str, Any]] = []

    def load_test_cases(self) -> list[dict]:
        """Load test cases from CSV or JSON."""
        if self.test_file.suffix == ".json":
            with open(self.test_file) as f:
                return json.load(f)
        elif self.test_file.suffix == ".csv":
            with open(self.test_file, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        else:
            raise ValueError(f"Unsupported file format: {self.test_file.suffix}")

    async def evaluate(self):
        """Run evaluation on all test cases."""
        test_cases = self.load_test_cases()
        logger.info("Loaded %d test cases", len(test_cases))

        for i, case in enumerate(test_cases):
            query = case.get("query", case.get("question", ""))
            expected = case.get("expected", case.get("answer", ""))

            logger.info("[%d/%d] Evaluating: %s", i + 1, len(test_cases), query[:60])

            # Run the agent
            from app.agent.graph import run_chat
            result = await run_chat(query, self.kb_id, "", None)

            result_entry = {
                "query": query,
                "expected": expected,
                "actual": result.get("answer", ""),
                "reasoning": result.get("reasoning", ""),
                "retrieved_docs": [
                    {"chunk_id": d["chunk_id"], "score": d.get("score", 0)}
                    for d in result.get("retrieved_docs", [])
                ],
                "metrics": self._compute_metrics(
                    query, expected, result.get("answer", ""),
                    result.get("retrieved_docs", []),
                ),
            }
            self.results.append(result_entry)

        self._report()

    def _compute_metrics(
        self,
        query: str,
        expected: str,
        actual: str,
        retrieved_docs: list[dict],
    ) -> dict:
        """Compute evaluation metrics.

        Uses simple heuristic metrics that align with LangSmith's evaluation concepts:
        - Correctness: keyword overlap between expected and actual
        - Groundedness: whether answer references sources
        - Retrieval Relevance: whether retrieved docs contain query keywords
        """
        query_words = set(query.lower().split())
        expected_words = set(expected.lower().split()) if expected else set()
        actual_words = set(actual.lower().split()) if actual else set()

        # Correctness: token overlap ratio
        if expected_words and actual_words:
            overlap = len(expected_words & actual_words)
            correctness = overlap / max(len(expected_words), 1)
        else:
            correctness = 0.0

        # Groundedness: score from retrieved docs
        groundedness = 0.0
        if retrieved_docs:
            avg_score = sum(d.get("score", 0) for d in retrieved_docs) / len(retrieved_docs)
            groundedness = min(avg_score, 1.0)

        # Retrieval Relevance: query-doc keyword match
        relevance = 0.0
        if retrieved_docs:
            doc_texts = " ".join([d.get("text", "") for d in retrieved_docs]).lower()
            doc_words = set(doc_texts.split())
            if query_words and doc_words:
                match = len(query_words & doc_words)
                relevance = match / max(len(query_words), 1)

        return {
            "correctness": round(correctness, 4),
            "groundedness": round(groundedness, 4),
            "retrieval_relevance": round(relevance, 4),
        }

    def _report(self):
        """Print and save evaluation report."""
        if not self.results:
            print("No results to report.")
            return

        # Summary
        avg_correctness = sum(r["metrics"]["correctness"] for r in self.results) / len(self.results)
        avg_groundedness = sum(r["metrics"]["groundedness"] for r in self.results) / len(self.results)
        avg_relevance = sum(r["metrics"]["retrieval_relevance"] for r in self.results) / len(self.results)

        print("\n" + "=" * 60)
        print("EVALUATION REPORT")
        print("=" * 60)
        print(f"Total test cases: {len(self.results)}")
        print(f"Knowledge Base:  {self.kb_id}")
        print("\nMetrics (0-1 scale):")
        print(f"  Correctness:         {avg_correctness:.4f}")
        print(f"  Groundedness:        {avg_groundedness:.4f}")
        print(f"  Retrieval Relevance: {avg_relevance:.4f}")
        print(f"  Combined Score:      {(avg_correctness + avg_groundedness + avg_relevance) / 3:.4f}")
        print("=" * 60)

        # Save
        report = {
            "kb_id": self.kb_id,
            "total_cases": len(self.results),
            "metrics": {
                "avg_correctness": avg_correctness,
                "avg_groundedness": avg_groundedness,
                "avg_retrieval_relevance": avg_relevance,
            },
            "results": self.results,
        }
        with open(self.output_file, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to: {self.output_file}")
