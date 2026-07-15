"""Streamlit A/B 비교 대시보드 — QRM 정답셋 없이 variant 구조·회귀 비교."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import ab_experiment
import ai_review
import config as app_config
import knowledge_base as kb
import note_merge
import notes_pipeline
import output_formatter
from dual_review_pipeline import build_dual_context, narrative_for_ai
from parser import ParsedDocument
from rag_strategy import ReviewVariant, rag_mode
from review_engine import Materiality, extract_engagement, extract_materiality, run_review
from sample_data import count_by_importance


VARIANT_META: dict[ReviewVariant, dict[str, str]] = {
    ReviewVariant.VECTOR_ONLY: {
        "id": "A",
        "label": "Vector RAG only",
        "short": "벡터 RAG",
        "desc": "Hanul DB 정성 근거(벡터/하이브리드)만 사용. 조서 본문은 최소.",
    },
    ReviewVariant.FILE_CONTEXT_ONLY: {
        "id": "B",
        "label": "File context only",
        "short": "조서 본문만",
        "desc": "RAG 없이 업로드 조서 텍스트만 AI·규칙에 전달.",
    },
    ReviewVariant.STRUCTURED_HYBRID: {
        "id": "C",
        "label": "Structured hybrid",
        "short": "구조화 하이브리드",
        "desc": "서술=RAG · 수치=규칙엔진. 교수님 권장 기본안.",
    },
}

ALL_VARIANTS = [
    ReviewVariant.VECTOR_ONLY,
    ReviewVariant.FILE_CONTEXT_ONLY,
    ReviewVariant.STRUCTURED_HYBRID,
]


@dataclass
class VariantSnapshot:
    variant: str
    label: str
    notes: list[dict[str, Any]] = field(default_factory=list)
    rule_count: int = 0
    ai_count: int = 0
    citation_count: int = 0
    rag_mode: str = ""
    segment_summary: dict[str, int] = field(default_factory=dict)
    quant_summary: dict[str, Any] = field(default_factory=dict)
    narrative_chars: int = 0
    importance: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    pipelines: dict[str, int] = field(default_factory=dict)
    elapsed_sec: int = 0
    golden_passed: bool | None = None
    golden_errors: list[str] = field(default_factory=list)


def current_settings() -> dict[str, str]:
    return {
        "review_variant": app_config.review_variant(),
        "rag_mode": rag_mode().value,
        "dual_rag": str(app_config.dual_rag_enabled()).lower(),
        "embedding_provider": app_config.embedding_provider(),
        "vectors_ready": str(kb.vectors_ready()).lower(),
    }


def _count_pipelines(notes: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in notes:
        key = str(n.get("pipeline") or "unknown")
        out[key] = out.get(key, 0) + 1
    return out


def summarize_notes(
    notes: list[dict[str, Any]], *, variant: ReviewVariant
) -> dict[str, Any]:
    meta = VARIANT_META[variant]
    imp = count_by_importance(notes)
    cats: dict[str, int] = {}
    for n in notes:
        c = str(n.get("category") or "기타")
        cats[c] = cats.get(c, 0) + 1
    return {
        "variant": variant.value,
        "variant_id": meta["id"],
        "label": meta["label"],
        "short": meta["short"],
        "total": len(notes),
        "importance": imp,
        "categories": cats,
        "pipelines": _count_pipelines(notes),
    }


def build_lite_snapshot(
    doc: ParsedDocument,
    variant: ReviewVariant,
    *,
    query: str = "",
) -> VariantSnapshot:
    """AI 없이 듀얼 컨텍스트·RAG·규칙엔진만 비교 (빠름)."""
    import time

    t0 = time.perf_counter()
    q = query or (doc.text[:500] if doc.text else "")
    ctx = build_dual_context(doc, variant=variant, query=q)
    engagement = extract_engagement(doc)
    mat = extract_materiality(doc)
    rule_notes = run_review(
        doc,
        include_minor=False,
        materiality=mat,
        is_listed=engagement.get("is_listed"),
        engagement=engagement,
    )
    notes = notes_pipeline.post_process_notes(doc, rule_notes, variant=variant)
    notes = output_formatter.apply_all(notes)
    dt = int(time.perf_counter() - t0)
    imp = count_by_importance(notes)
    cats: dict[str, int] = {}
    for n in notes:
        c = str(n.get("category") or "기타")
        cats[c] = cats.get(c, 0) + 1
    meta = VARIANT_META[variant]
    return VariantSnapshot(
        variant=variant.value,
        label=meta["label"],
        notes=notes,
        rule_count=len(rule_notes),
        ai_count=0,
        citation_count=len(ctx.qualitative_citations),
        rag_mode=rag_mode().value,
        segment_summary=ctx.meta.get("segment_summary", {}),
        quant_summary=ctx.meta.get("quant_summary", {}),
        narrative_chars=int(ctx.meta.get("narrative_chars", 0)),
        importance=imp,
        categories=cats,
        pipelines=_count_pipelines(notes),
        elapsed_sec=dt,
    )


def run_variant_review(
    doc: ParsedDocument,
    variant: ReviewVariant,
    *,
    engagement: dict[str, Any] | None = None,
    materiality: Materiality | None = None,
    use_ai: bool = False,
    include_minor: bool = False,
    progress: Callable[[str], None] | None = None,
) -> VariantSnapshot:
    """단일 variant 전체 심리 파이프라인 (선택적 AI)."""
    import time

    t0 = time.perf_counter()
    eng = engagement or extract_engagement(doc)
    mat = materiality or extract_materiality(doc)
    q = doc.text[:500] if doc.text else ""

    if progress:
        progress(f"{VARIANT_META[variant]['short']}: 규칙엔진 실행 중…")
    rule_notes = run_review(
        doc,
        include_minor=include_minor,
        materiality=mat,
        is_listed=eng.get("is_listed"),
        engagement=eng,
    )

    ai_notes: list[dict[str, Any]] = []
    if use_ai and ai_review.is_configured():
        if progress:
            progress(f"{VARIANT_META[variant]['short']}: AI 심층 분석 중…")
        ai_notes = ai_review.run_sheet_reviews(doc, eng, variant=variant)

    notes = note_merge.merge_review_notes(ai_notes, rule_notes) if ai_notes else rule_notes
    if progress:
        progress(f"{VARIANT_META[variant]['short']}: 후처리·근거 연결 중…")
    notes = notes_pipeline.post_process_notes(doc, notes, variant=variant)
    notes = output_formatter.apply_all(notes)

    ctx = build_dual_context(doc, variant=variant, query=q)
    dt = int(time.perf_counter() - t0)
    imp = count_by_importance(notes)
    cats: dict[str, int] = {}
    for n in notes:
        c = str(n.get("category") or "기타")
        cats[c] = cats.get(c, 0) + 1
    meta = VARIANT_META[variant]
    return VariantSnapshot(
        variant=variant.value,
        label=meta["label"],
        notes=notes,
        rule_count=len(rule_notes),
        ai_count=len(ai_notes),
        citation_count=len(ctx.qualitative_citations),
        rag_mode=rag_mode().value,
        segment_summary=ctx.meta.get("segment_summary", {}),
        quant_summary=ctx.meta.get("quant_summary", {}),
        narrative_chars=int(ctx.meta.get("narrative_chars", 0)),
        importance=imp,
        categories=cats,
        pipelines=_count_pipelines(notes),
        elapsed_sec=dt,
    )


def compare_variants_lite(
    doc: ParsedDocument, *, query: str = ""
) -> list[VariantSnapshot]:
    return [build_lite_snapshot(doc, v, query=query) for v in ALL_VARIANTS]


def compare_variants_full(
    doc: ParsedDocument,
    *,
    use_ai: bool = False,
    engagement: dict[str, Any] | None = None,
    materiality: Materiality | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[VariantSnapshot]:
    return [
        run_variant_review(
            doc,
            v,
            engagement=engagement,
            materiality=materiality,
            use_ai=use_ai,
            progress=progress,
        )
        for v in ALL_VARIANTS
    ]


def run_golden_ab_report() -> dict[str, Any]:
    """골든셋(모의) A/B/C 회귀 — QRM 정답셋 불필요."""
    return ab_experiment.run_ab_experiment(ALL_VARIANTS)


def golden_summary_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in report.get("variants", []):
        vid = block.get("variant", "")
        try:
            v = ReviewVariant(vid)
            meta = VARIANT_META[v]
        except ValueError:
            meta = {"id": "?", "short": vid, "label": vid}
        rows.append(
            {
                "Variant": f"{meta['id']} · {meta['short']}",
                "케이스": block.get("cases_run", 0),
                "통과": block.get("cases_passed", 0),
                "Recall": f"{100 * float(block.get('tier1_recall', 0)):.1f}%",
                "권장": "✓" if report.get("recommendation") == vid else "",
            }
        )
    return rows


def comparison_table_rows(snapshots: list[VariantSnapshot]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for s in snapshots:
        try:
            v = ReviewVariant(s.variant)
            meta = VARIANT_META[v]
        except ValueError:
            meta = {"id": "?", "short": s.variant}
        rows.append(
            {
                "Variant": f"{meta['id']} · {meta['short']}",
                "리뷰노트": s.importance.get("상", 0)
                + s.importance.get("중", 0)
                + s.importance.get("하", 0),
                "상": s.importance.get("상", 0),
                "중": s.importance.get("중", 0),
                "RAG인용": s.citation_count,
                "서술chars": s.narrative_chars,
                "규칙": s.rule_count,
                "AI": s.ai_count,
                "소요(초)": s.elapsed_sec,
            }
        )
    return rows


def narrative_preview(doc: ParsedDocument, variant: ReviewVariant) -> str:
    ctx = build_dual_context(doc, variant=variant, query=doc.text[:500] if doc.text else "")
    return narrative_for_ai(ctx, full_text=doc.text or "")
