"""RAG 전략 라우터 — 교수님 자문: 정성(semantic) vs 정량(non-RAG) 이원화."""

from __future__ import annotations

from enum import Enum
from typing import Any

import config as app_config
import knowledge_base as kb


class ReviewVariant(str, Enum):
    VECTOR_ONLY = "vector_only"
    FILE_CONTEXT_ONLY = "file_context_only"
    STRUCTURED_HYBRID = "structured_hybrid"


class RagMode(str, Enum):
    FTS = "fts"
    VECTOR = "vector"
    HYBRID = "hybrid"


# 정성적 RAG 대상 — K-IFRS·질의회신·감리지적 해설·4대중점
QUALITATIVE_CATEGORIES: list[str] = (
    kb.STANDARDS_CATEGORIES
    + kb.QNA_CATEGORIES
    + kb.ENFORCEMENT_CATEGORIES
    + kb.FOCUS_CATEGORIES
)

# 모범 조서 — 서술만 RAG, 수치는 별도 테이블 (workpaper_segment)
WORKPAPER_NARRATIVE_CATEGORIES: list[str] = list(kb.WORKPAPER_CATEGORIES)

# RAG 사용 금지 — 정량 판단·계산·중요성
NON_RAG_DOMAINS = frozenset({"materiality", "calculation", "tieout", "anomaly"})


def review_variant() -> ReviewVariant:
    raw = app_config.get("REVIEW_VARIANT", "structured_hybrid").lower()
    try:
        return ReviewVariant(raw)
    except ValueError:
        return ReviewVariant.STRUCTURED_HYBRID


def rag_mode() -> RagMode:
    raw = app_config.get("RAG_MODE", "hybrid").lower()
    try:
        return RagMode(raw)
    except ValueError:
        return RagMode.HYBRID


def dual_rag_enabled() -> bool:
    return app_config.get_bool("DUAL_RAG_ENABLED", True)


def _qualitative_retrieve(query: str, *, k: int = 6) -> list[kb.Citation]:
    mode = rag_mode()
    if mode == RagMode.VECTOR:
        return kb.retrieve_semantic(query, k=k, categories=QUALITATIVE_CATEGORIES)
    if mode == RagMode.HYBRID:
        return kb.retrieve_hybrid(query, k=k, categories=QUALITATIVE_CATEGORIES)
    return kb.retrieve(query, k=k, categories=QUALITATIVE_CATEGORIES)


def retrieve_qualitative(query: str, *, k: int = 6) -> list[kb.Citation]:
    """정성적 근거 검색 — vector / hybrid / fts."""
    return _qualitative_retrieve(query, k=k)


def retrieve_workpaper_narrative(query: str, *, k: int = 4) -> list[kb.Citation]:
    """모범 조서 서술 부분만 검색."""
    mode = rag_mode()
    if mode == RagMode.VECTOR:
        return kb.retrieve_semantic(query, k=k, categories=WORKPAPER_NARRATIVE_CATEGORIES)
    if mode == RagMode.HYBRID:
        return kb.retrieve_hybrid(query, k=k, categories=WORKPAPER_NARRATIVE_CATEGORIES)
    return kb.retrieve(query, k=k, categories=WORKPAPER_NARRATIVE_CATEGORIES)


def gather_qualitative_citations(
    query: str,
    *,
    variant: ReviewVariant | None = None,
    k_std: int = 3,
    k_qna: int = 2,
    k_case: int = 3,
    k_focus: int = 1,
) -> list[dict[str, Any]]:
    """Variant별 정성 근거 수집."""
    v = variant or review_variant()
    if v == ReviewVariant.FILE_CONTEXT_ONLY:
        return []

    mode = rag_mode()
    rag_tag = mode.value

    if v == ReviewVariant.VECTOR_ONLY:
        cites = _qualitative_retrieve(query, k=k_std + k_qna + k_case + k_focus)
        return [
            {
                "group": "정성RAG",
                "source": c.source,
                "snippet": c.snippet[:420],
                "ref": c.ref,
                "variant": v.value,
                "rag_mode": rag_tag,
            }
            for c in cites
        ]

    # structured_hybrid: 카테고리별 검색 (hybrid/vector/fts)
    plans = [
        ("기준", kb.STANDARDS_CATEGORIES, k_std),
        ("질의회신", kb.QNA_CATEGORIES, k_qna),
        ("감리지적사례", kb.ENFORCEMENT_CATEGORIES, k_case),
        ("4대중점", kb.FOCUS_CATEGORIES, k_focus),
    ]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group, cats, k in plans:
        if mode == RagMode.VECTOR:
            hits = kb.retrieve_semantic(query, k=k, categories=cats)
        elif mode == RagMode.HYBRID:
            hits = kb.retrieve_hybrid(query, k=k, categories=cats)
        else:
            hits = kb.retrieve(query, k=k, categories=cats)
        for c in hits:
            key = (c.source, c.snippet[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "group": group,
                    "source": c.source,
                    "snippet": c.snippet[:420],
                    "ref": c.ref,
                    "variant": v.value,
                    "rag_mode": rag_tag,
                }
            )
    return out


def should_use_rag_for(category: str) -> bool:
    """정량 카테고리는 RAG 미사용."""
    return category.lower() not in NON_RAG_DOMAINS
