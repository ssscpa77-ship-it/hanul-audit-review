"""리뷰노트 후처리 파이프라인 — Streamlit 핫리로드 시 review_engine 캐시 문제를 피하기 위해 분리."""

from __future__ import annotations

import re
from typing import Any

import note_merge
import output_formatter as out_fmt
import qc_review
import review_engine as re_engine
from parser import ParsedDocument

_CROSS_SHEET_NOTE_PATTERNS: list[tuple[re.Pattern[str], dict[str, Any]]] = [
    (
        re.compile(
            r"(재고|상품|제품|원재료|재공품).{0,40}(cut.?off|컷오프|기간귀속)"
            r"|(cut.?off|컷오프|기간귀속).{0,40}(재고|상품|제품|입고|출고|선적)",
            re.IGNORECASE,
        ),
        {
            "detect": [
                "cut-off", "cutoff", "컷오프", "cut off", "기간귀속",
                "결산일", "선적", "입고", "출고", "미착", "shipping",
            ],
        },
    ),
    (
        re.compile(
            r"(매출|수익).{0,40}(cut.?off|컷오프|기간귀속)"
            r"|(cut.?off|컷오프|기간귀속).{0,40}(매출|수익|인식시점|귀속시점)",
            re.IGNORECASE,
        ),
        {
            "detect": ["기간귀속", "cut-off", "cutoff", "마감", "귀속시점", "인식시점"],
        },
    ),
    (
        re.compile(r"실사|입회|재고조사|재고\s?실사", re.IGNORECASE),
        {"detect": ["실사", "입회", "재고조사", "재고 실사", "입회자"]},
    ),
    (
        re.compile(
            r"외부\s?조회|조회서|은행\s?조회|금융기관|confirmation|잔액\s?(?:확인|조회)|예금\s?잔액",
            re.IGNORECASE,
        ),
        re_engine._CASH_CONFIRM_PROC,
    ),
]

_ANALYTICAL_KW = (
    "분석적", "analytical", "변동분석", "증감분석", "전기대비", "추세", "ratio",
    "fluctuation", "변동원인", "증감원인", "분석적절차", "분석적 검토", "분석적검토",
)
_DOC_GAP_KW = ("문서화", "기재", "서술", "근거", "설명", "미흡", "부족", "보완", "미확인", "소홀")
_SUBSTANTIVE_GAP_KW = (
    "미수행", "누락", "없음", "부재", "미실시", "하지 않", "수행하지",
    "조회 미", "실사 미", "입회 미", "절차누락", "불일치", "과대", "과소",
)
_PROTECTED_CATEGORIES = frozenset({"중점감리", "절차누락", "주석검증", "중요성"})
_DROP_CATEGORIES = frozenset({"개선제안", "형식·완전성", "계산검증"})


def filter_cross_sheet_procedure_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cut-off·실사입회 등은 다른 조서에 있을 수 있음 — 전체 조서 검색 후에만 지적 유지."""
    doc_ev = re_engine._doc_evidence(doc).lower()
    has_cash_confirm = re_engine.doc_has_cash_confirmation_evidence(doc)
    kept: list[dict[str, Any]] = []
    for note in notes:
        hay = f"{note.get('defect', '')} {note.get('reason', '')}"
        suppressed = False
        for pat, spec in _CROSS_SHEET_NOTE_PATTERNS:
            if not pat.search(hay):
                continue
            if spec is re_engine._CASH_CONFIRM_PROC:
                if has_cash_confirm:
                    suppressed = True
                break
            if re_engine._procedure_satisfied(doc_ev, spec):
                suppressed = True
                break
        if not suppressed:
            kept.append(note)
    return kept


def filter_cash_external_confirm_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """tick·Ref·조회서 흔적이 있으면 외부조회 미수행 지적 제거."""
    if not re_engine.doc_has_cash_confirmation_evidence(doc):
        return notes
    return [n for n in notes if not re_engine.is_cash_external_confirm_note(n)]


def _doc_has_analytical(doc: ParsedDocument, account: str | None = None) -> bool:
    for t in doc.tables:
        acct = re_engine.table_account(t)
        text = re_engine._sheet_text(t).lower()
        if account and acct and acct != account and account not in text:
            continue
        if any(k.lower() in text for k in _ANALYTICAL_KW):
            return True
    hay = (doc.text or "").lower()
    return any(k.lower() in hay for k in _ANALYTICAL_KW)


def _is_documentation_enhancement(note: dict[str, Any]) -> bool:
    hay = f"{note.get('defect', '')} {note.get('reason', '')}"
    if any(k in hay for k in _SUBSTANTIVE_GAP_KW):
        return False
    has_gap = any(k in hay for k in _DOC_GAP_KW)
    has_anal = any(k in hay for k in _ANALYTICAL_KW) or any(
        k in hay for k in ("분석", "변동", "증감", "전기")
    )
    return has_gap and (has_anal or note.get("category") in ("계산검증", "증빙·절차"))


def _is_minor_qc_note(note: dict[str, Any]) -> bool:
    """품질관리(QC) 관점에서 제출 목록에서 제외할 경미 지적."""
    if note.get("focus_protected") or note.get("enforcement_protected") or note.get("category") in ("중점감리", "감리지적체크"):
        return False
    if note.get("brief_merged") or note.get("collateral_memo") or note.get("contingency_merged"):
        return False
    if note.get("off_balance_merged"):
        return False
    if note.get("category") in _PROTECTED_CATEGORIES and note.get("importance") == "상":
        return False

    hay = f"{note.get('defect', '')} {note.get('reason', '')} {note.get('category', '')}"
    if any(k in hay for k in _SUBSTANTIVE_GAP_KW):
        return False

    if note.get("importance") == "하":
        return True
    if note.get("category") in _DROP_CATEGORIES:
        return True
    if note.get("importance") == "중" and note.get("source") == "ai":
        if "AI 추정" in (note.get("basis") or "") or any(k in hay for k in _DOC_GAP_KW):
            return True
    if note.get("importance") == "중" and note.get("category") == "증빙·절차":
        if any(k in hay for k in _DOC_GAP_KW) and not any(k in hay for k in ("조회", "실사", "입회", "cut", "컷")):
            return True
    return False


def adjust_analytical_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """분석적 절차가 이미 수행된 경우, 문서 보완 수준의 경미 지적은 제외."""
    kept: list[dict[str, Any]] = []
    for note in notes:
        if note.get("focus_protected") or note.get("enforcement_protected") or note.get("category") in ("중점감리", "감리지적체크"):
            kept.append(note)
            continue
        acct = re_engine.note_account(note)
        if _doc_has_analytical(doc, acct) and _is_documentation_enhancement(note):
            continue
        kept.append(note)
    return kept


def prune_qc_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """QC 리뷰어 관점 — 중요도 낮은·경미 지적을 최종 목록에서 제외."""
    return [n for n in notes if not _is_minor_qc_note(n)]


def adjust_cash_physical_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """실물 현금 없음(n/a·nan)은 정상 — 실사 지적은 다액·절차 누락 시에만."""
    info = re_engine.analyze_physical_cash(doc)
    mat = re_engine.extract_materiality(doc)
    small_thr = re_engine.physical_cash_small_threshold(mat)
    sig_thr = re_engine.physical_cash_significant_threshold(mat)
    kept: list[dict[str, Any]] = []
    for note in notes:
        if not re_engine.is_cash_physical_disclosure_note(note):
            kept.append(note)
            continue
        if info.has_count_evidence:
            continue
        amt = info.amount
        if info.explicitly_none and (amt is None or amt <= small_thr):
            continue
        if amt is not None and amt <= 0:
            continue
        if amt is not None and amt <= small_thr:
            down = dict(note)
            down["importance"] = "중"
            defect = down.get("defect", "")
            if not defect.startswith("[경미]"):
                down["defect"] = f"[경미] {defect}"
            if "소액" not in down.get("reason", ""):
                down["reason"] = (
                    f"{down.get('reason', '').rstrip('.')} "
                    f"(실물 현금 소액 {amt:,.0f}원 — 실사 누락 시 참고 수준의 경미 지적입니다.)"
                ).strip()
            kept.append(down)
            continue
        if amt is not None and amt < sig_thr:
            continue
        if amt is None and info.explicitly_none:
            continue
        kept.append(note)
    return kept


def filter_cross_sheet_disclosure_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """주석·공시는 Lead·별도 주석 조서에 있을 수 있음 — 타 조서에 있으면 지적 제거."""
    kept: list[dict[str, Any]] = []
    for note in notes:
        if not re_engine.is_cross_sheet_disclosure_note(note):
            kept.append(note)
            continue
        acct = re_engine.disclosure_note_account(note)
        exclude = str(
            note.get("sheet_no") or note.get("workpaper_ref") or note.get("sheet") or ""
        )
        if re_engine.doc_has_account_disclosure_elsewhere(doc, acct, exclude_sheet=exclude):
            continue
        kept.append(note)
    return kept


def filter_off_account_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """시트 계정·본문과 무관한 리뷰노트·첨부 근거·감리사례 제거."""
    kept: list[dict[str, Any]] = []
    for note in notes:
        if re_engine.is_off_account_note(note, doc):
            continue
        re_engine.sanitize_note_citations(note)
        kept.append(note)
    return kept


def adjust_borrowing_collateral_notes(
    doc: ParsedDocument, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """차입 담보 공시 — CL 조서에 있으면 생략, 없으면 확인 메모만."""
    if not any(re_engine.is_borrowing_collateral_disclosure_note(n) for n in notes):
        return notes
    has_cl = re_engine.doc_has_borrowing_collateral_in_contingency(doc)
    kept: list[dict[str, Any]] = []
    collateral_hits: list[dict[str, Any]] = []
    for note in notes:
        if not re_engine.is_borrowing_collateral_disclosure_note(note):
            kept.append(note)
            continue
        if has_cl:
            continue
        collateral_hits.append(note)
    if collateral_hits and not has_cl:
        kept.append(re_engine.soft_borrowing_collateral_memo(collateral_hits[0]))
    return kept


def simplify_note_outputs(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """리뷰근거 간소화 — 세부 인용문(references) 제거, basis 한 줄만."""
    for note in notes:
        note.pop("references", None)
        if note.get("basis"):
            simple = out_fmt.simplify_basis(str(note["basis"]))
            if simple:
                note["basis"] = simple
    return notes


def post_process_notes(doc: ParsedDocument, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """전체 조서 검색 → 주제별 통합 → 계정별 약식 통합 → 경미 지적 제외."""
    notes = filter_off_account_notes(doc, notes)
    notes = filter_cross_sheet_procedure_notes(doc, notes)
    notes = filter_cross_sheet_disclosure_notes(doc, notes)
    notes = filter_cash_external_confirm_notes(doc, notes)
    notes = adjust_cash_physical_notes(doc, notes)
    notes = qc_review.prune_documented_review_notes(doc, notes)
    notes = note_merge.consolidate_review_notes(notes, doc)
    notes = note_merge.consolidate_account_briefs(notes, doc)
    notes = note_merge.consolidate_lead_detail_notes(notes)
    notes = note_merge.consolidate_contingency_notes(notes)
    notes = note_merge.consolidate_off_balance_notes(notes)
    notes = adjust_borrowing_collateral_notes(doc, notes)
    notes = adjust_analytical_notes(doc, notes)
    notes = qc_review.prune_documented_review_notes(doc, notes)
    notes = prune_qc_notes(notes)
    notes = simplify_note_outputs(notes)
    return notes
