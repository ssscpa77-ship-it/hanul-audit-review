"""멀티에이전트 아키텍처 — 공통 Finding 스키마.

「멀티에이전트_아키텍처_설계안_2026-08-09.md」§6 참조. 기존 review_engine._note()가
만드는 리뷰노트 dict(category/defect/reason/basis/to_be/importance/sheet_no/...)와
호환되도록 설계하여, note_merge / notes_pipeline / _assign_ids 등 기존 파이프라인에
그대로 흘려 넣을 수 있다. 여기에 에이전트 거버넌스용 필드(agent_id, evidence_refs,
confidence, cross_checked_by 등)를 추가한다.
"""

from __future__ import annotations

from typing import Any

# 오케스트레이터가 승격시키는 Tier ↔ 기존 importance 매핑
TIER_TO_IMPORTANCE = {1: "상", 2: "중", 3: "하"}

_IMPORTANCE_BY_CATEGORY = {
    "절차누락": "상",
    "계산오류": "상",
    "상호참조불일치": "중",
    "중점감리": "상",
    "감리지적유사": "중",
}


def make_finding(
    *,
    agent_id: str,
    agent_type: str,  # "account" | "functional" | "orchestrator"
    category: str,
    defect: str,
    reason: str,
    basis: str,
    to_be: str,
    account: str = "",
    sheet_no: str = "",
    sheet_title: str = "",
    evidence_refs: list[str] | None = None,
    confidence: float = 0.7,
    importance: str | None = None,
) -> dict[str, Any]:
    """기존 review_engine._note() 스키마 + 에이전트 거버넌스 필드를 갖는 dict 생성."""
    sheet_no = (sheet_no or "").strip()
    sheet_title = (sheet_title or "").strip()
    label = f"{sheet_no} ({sheet_title})" if sheet_no and sheet_title else (sheet_no or sheet_title or "조서 본문")
    imp = importance or _IMPORTANCE_BY_CATEGORY.get(category, "중")
    finding_text = defect if len(defect) <= 220 else defect[:217] + "..."
    return {
        # --- 기존 리뷰노트 필드(review_engine._note 호환) ---
        "id": "",
        "importance": imp,
        "category": category,
        "defect": finding_text,
        "reason": reason,
        "basis": basis or "근거 미확인",
        "to_be": to_be,
        "sheet_no": sheet_no or "-",
        "sheet_title": sheet_title,
        "sheet": label,
        "location": "",
        "summary": f"〈{sheet_no or label}〉 {finding_text} — {to_be}",
        "workpaper_ref": sheet_no or label,
        "is_focus_related": category == "중점감리",
        "source": f"agent:{agent_id}",
        # --- 신규 에이전트 거버넌스 필드 ---
        "agent_id": agent_id,
        "agent_type": agent_type,
        "account": account,
        "evidence_refs": evidence_refs or [],
        "confidence": confidence,
        "cross_checked_by": [],
        "duplicate_group_id": None,
    }


def has_evidence(finding: dict[str, Any]) -> bool:
    return bool(finding.get("evidence_refs")) and finding.get("basis") not in ("", "근거 미확인", None)


def group_key(finding: dict[str, Any]) -> tuple[str, str]:
    """중복 그룹핑 키 — 동일 시트 + 동일 카테고리."""
    return (str(finding.get("sheet_no") or finding.get("sheet") or ""), str(finding.get("category") or ""))
