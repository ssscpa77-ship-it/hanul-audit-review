"""A/B 실험 — (a) Vector only (b) File context (c) Structured hybrid vs QRM 골든셋."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any

import golden_set_catalog as gsc
import golden_set_regression as gsr
from dual_review_pipeline import build_dual_context
from rag_strategy import ReviewVariant


@dataclass
class VariantScore:
    variant: str
    cases_run: int = 0
    cases_passed: int = 0
    tier1_recall: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)


def run_variant_on_golden(variant: ReviewVariant) -> VariantScore:
    """단일 variant로 골든셋 4대중점 회귀 + 듀얼 컨텍스트 메타 수집."""
    score = VariantScore(variant=variant.value)
    for case in gsc.GOLDEN_SET_CASES:
        if not (case.mock_sheet_text or case.focus_issue_no == 0):
            continue
        doc = gsr._mock_doc(case)
        ctx = build_dual_context(
            doc,
            variant=variant,
            query=case.mock_sheet_text or case.scenario,
        )
        reg = gsr.evaluate_case(case)
        detail = {
            "case_id": case.case_id,
            "passed": reg.passed,
            "errors": reg.errors,
            "focus_notes": reg.focus_notes,
            "dual_meta": ctx.meta,
        }
        score.details.append(detail)
        score.cases_run += 1
        if reg.passed:
            score.cases_passed += 1

    if score.cases_run:
        score.tier1_recall = score.cases_passed / score.cases_run
    return score


def run_ab_experiment(
    variants: list[ReviewVariant] | None = None,
) -> dict[str, Any]:
    """A/B/C 3-variant 비교 실행."""
    variants = variants or [
        ReviewVariant.VECTOR_ONLY,
        ReviewVariant.FILE_CONTEXT_ONLY,
        ReviewVariant.STRUCTURED_HYBRID,
    ]
    results = [run_variant_on_golden(v) for v in variants]
    best = max(results, key=lambda x: x.tier1_recall) if results else None
    return {
        "experiment": "dual_rag_ab",
        "description": "교수님 A/B 설계: vector_only | file_context_only | structured_hybrid",
        "variants": [
            {
                "variant": r.variant,
                "cases_run": r.cases_run,
                "cases_passed": r.cases_passed,
                "tier1_recall": round(r.tier1_recall, 4),
                "details": r.details,
            }
            for r in results
        ],
        "recommendation": best.variant if best else "structured_hybrid",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Dual RAG A/B experiment")
    ap.add_argument(
        "--variants",
        default="vector_only,file_context_only,structured_hybrid",
        help="Comma-separated variant IDs",
    )
    ap.add_argument("--output", default="", help="JSON output path")
    args = ap.parse_args()
    ids = [ReviewVariant(v.strip()) for v in args.variants.split(",") if v.strip()]
    report = run_ab_experiment(ids)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)


if __name__ == "__main__":
    main()
