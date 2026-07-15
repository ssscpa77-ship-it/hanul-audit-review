"""듀얼 RAG 리뷰 오케스트레이터 — 정성(RAG) + 정량(추출·규칙) 병렬 처리."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from parser import ParsedDocument
from quantitative_extract import QuantitativeFacts, extract_quantitative_facts
from rag_strategy import ReviewVariant, gather_qualitative_citations, review_variant
from review_engine import Materiality, extract_materiality
from workpaper_segment import SegmentedWorkpaper, segment_document


@dataclass
class DualReviewContext:
    """한 번의 분석에 공유되는 이원 파이프라인 컨텍스트."""

    variant: ReviewVariant
    segmented: SegmentedWorkpaper
    quant_facts: QuantitativeFacts
    materiality: Materiality
    qualitative_citations: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def attach_to_notes(self, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """리뷰노트에 파이프라인 출처 태그 부여."""
        for n in notes:
            n.setdefault("rag_variant", self.variant.value)
            cat = str(n.get("category") or "")
            if cat in ("계산검증", "중요성", "대사"):
                n["pipeline"] = "quant_rules"
                n["evidence_type"] = "structured"
            elif n.get("ai_generated"):
                n["pipeline"] = "qual_ai"
                n["evidence_type"] = "citation"
            else:
                n["pipeline"] = "qual_rag" if self.qualitative_citations else "rules"
        return notes


def build_dual_context(
    doc: ParsedDocument,
    *,
    variant: ReviewVariant | None = None,
    query: str = "",
) -> DualReviewContext:
    """업로드 직후 이원 컨텍스트 구축."""
    v = variant or review_variant()
    segmented = segment_document(doc)
    mat = extract_materiality(doc)
    quant = extract_quantitative_facts(doc, segmented=segmented, materiality=mat)

    cites: list[dict[str, Any]] = []
    if v != ReviewVariant.FILE_CONTEXT_ONLY and query.strip():
        cites = gather_qualitative_citations(query, variant=v)

    return DualReviewContext(
        variant=v,
        segmented=segmented,
        quant_facts=quant,
        materiality=mat,
        qualitative_citations=cites,
        meta={
            "segment_summary": segmented.summary(),
            "quant_summary": quant.to_dict(),
            "narrative_chars": len(segmented.narrative_text()),
        },
    )


def narrative_for_ai(ctx: DualReviewContext, *, full_text: str) -> str:
    """Variant별 AI 입력 텍스트."""
    if ctx.variant == ReviewVariant.FILE_CONTEXT_ONLY:
        return full_text
    if ctx.variant == ReviewVariant.STRUCTURED_HYBRID:
        narr = ctx.segmented.narrative_text()
        return narr if narr.strip() else full_text
    return full_text
