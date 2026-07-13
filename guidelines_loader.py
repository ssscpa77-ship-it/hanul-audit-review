"""Hanul DB 자가검토 지침 템플릿 로더.

`~/Desktop/Hanul DB/자가검토_지침_템플릿/` 에 xlsx가 있으면 4대 중점·절차 등을
동적으로 로드한다. 없으면 `fss_focus` 기본값 + `review_guidelines` 기본값 사용.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import knowledge_base as kb
import review_guidelines as rg


@dataclass
class EnhancedChecklistItem:
    name: str
    detect_all: tuple[str, ...] = ()
    detect_any: tuple[str, ...] = ()
    basis: str = ""
    to_be: str = ""
    required_evidence: tuple[str, ...] = ()
    acceptable_phrases: tuple[str, ...] = ()
    red_flag_phrases: tuple[str, ...] = ()
    related_sheet_codes: tuple[str, ...] = ()
    ai_review_questions: tuple[str, ...] = ()
    checklist_id: str = ""
    violation_type: str = ""
    case_source: str = ""
    case_example: str = ""
    review_gap_type: str = "검토누락"
    materiality_note: str = ""
    to_be_if_missing: str = ""
    to_be_if_weak: str = ""
    golden_set_ids: str = ""
    review_procedure: str = ""
    procedure_gap: str = ""
    case_numbers: str = ""
    sheet_code: str = ""
    sheet_label: str = ""
    canonical_account: str = ""
    case_count: int = 0
    case_context: str = ""
    audit_focus: str = ""


@dataclass
class EnhancedFocusIssue:
    issue_no: int
    title: str
    related_accounts: tuple[str, ...]
    sheet_keywords: tuple[str, ...]
    checklist: list[EnhancedChecklistItem] = field(default_factory=list)
    trigger_accounts: tuple[str, ...] = ()
    na_condition: str = ""


def guidelines_root() -> Path:
    base = Path(kb.SOURCE_DIR)
    return base / rg.GUIDELINES_DB_SUBDIR


def _split_cells(val: Any) -> tuple[str, ...]:
    if val is None:
        return ()
    s = str(val).strip()
    if not s or s.lower() in ("nan", "-", "—"):
        return ()
    parts = re.split(r"[;；|｜\n]+", s)
    return tuple(p.strip() for p in parts if p.strip())


def _read_xlsx(path: Path, *, sheet: str | int | None = None) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError:
        return []
    try:
        df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, header=0)
    except Exception:  # noqa: BLE001
        if sheet is not None:
            try:
                df = pd.read_excel(path, sheet_name=0, header=0)
            except Exception:  # noqa: BLE001
                return []
        else:
            return []
    df = df.fillna("")
    return [dict(row) for _, row in df.iterrows()]


def _read_focus_checklist_rows(path: Path) -> list[dict[str, Any]]:
    for sheet in ("체크리스트", 0):
        rows = _read_xlsx(path, sheet=sheet)
        if not rows:
            continue
        if any(
            str(r.get("checklist_item") or r.get("체크리스트항목") or "").strip()
            for r in rows
        ):
            return rows
    return []


@lru_cache(maxsize=4)
def load_focus_issues_from_db(is_listed: bool) -> list[EnhancedFocusIssue] | None:
    """Hanul DB xlsx에서 4대 중점 이슈 로드. 없으면 None."""
    key = "focus_listed" if is_listed else "focus_unlisted"
    fname = rg.TEMPLATE_FILES[key]
    path = guidelines_root() / fname
    if not path.is_file():
        return None
    rows = _read_focus_checklist_rows(path)
    if not rows:
        return None

    by_issue: dict[int, EnhancedFocusIssue] = {}
    for row in rows:
        try:
            issue_no = int(float(row.get("issue_no") or row.get("이슈번호") or 0))
        except (TypeError, ValueError):
            continue
        if issue_no < 1 or issue_no > 4:
            continue
        title = str(row.get("issue_title") or row.get("이슈명") or "").strip()
        if issue_no not in by_issue:
            by_issue[issue_no] = EnhancedFocusIssue(
                issue_no=issue_no,
                title=title or f"이슈 {issue_no}",
                related_accounts=_split_cells(
                    row.get("related_accounts") or row.get("관련계정")
                ),
                sheet_keywords=_split_cells(
                    row.get("sheet_keywords") or row.get("시트키워드")
                ),
                trigger_accounts=_split_cells(
                    row.get("trigger_accounts") or row.get("트리거계정")
                ),
                na_condition=str(
                    row.get("na_condition") or row.get("해당없음조건") or ""
                ).strip(),
            )
        item_name = str(
            row.get("checklist_item") or row.get("체크리스트항목") or row.get("항목명") or ""
        ).strip()
        if not item_name:
            continue
        to_be_missing = str(
            row.get("to_be_if_missing") or row.get("to_be") or row.get("보완지침") or ""
        ).strip()
        to_be_weak = str(row.get("to_be_if_weak") or "").strip()
        by_issue[issue_no].checklist.append(
            EnhancedChecklistItem(
                name=item_name,
                checklist_id=str(row.get("checklist_id") or "").strip(),
                violation_type=str(row.get("violation_type") or row.get("지적유형") or "").strip(),
                case_source=str(row.get("case_source") or row.get("사례출처") or "").strip(),
                case_example=str(row.get("case_example") or row.get("지적사례") or "").strip(),
                review_gap_type=str(
                    row.get("review_gap_type") or row.get("리뷰유형") or "검토누락"
                ).strip(),
                materiality_note=str(
                    row.get("materiality_note") or row.get("중요성") or ""
                ).strip(),
                detect_all=_split_cells(row.get("detect_all") or row.get("필수키워드")),
                detect_any=_split_cells(row.get("detect_any") or row.get("선택키워드")),
                basis=str(row.get("basis") or row.get("근거") or "").strip(),
                to_be=to_be_missing or to_be_weak,
                to_be_if_missing=to_be_missing,
                to_be_if_weak=to_be_weak,
                golden_set_ids=str(
                    row.get("golden_set_ids") or row.get("골든셋ID") or ""
                ).strip(),
                required_evidence=_split_cells(
                    row.get("required_evidence") or row.get("필수증거")
                ),
                acceptable_phrases=_split_cells(
                    row.get("acceptable_phrases") or row.get("인정문장")
                ),
                red_flag_phrases=_split_cells(
                    row.get("red_flag_phrases") or row.get("지적문장")
                ),
                related_sheet_codes=_split_cells(
                    row.get("related_sheet_codes") or row.get("관련조서")
                ),
                ai_review_questions=_split_cells(
                    row.get("ai_review_questions") or row.get("AI검토질문")
                ),
                review_procedure=str(
                    row.get("review_procedure") or row.get("구체적지침") or row.get("검토절차") or ""
                ).strip(),
            )
        )
    if not by_issue:
        return None
    return [by_issue[k] for k in sorted(by_issue)]


def checklist_satisfied_enhanced(stext: str, item: EnhancedChecklistItem) -> bool:
    """키워드 + 인정문장 패턴으로 체크리스트 충족 판정."""
    low = stext.lower()
    if item.red_flag_phrases and any(p.lower() in low for p in item.red_flag_phrases):
        return False
    if item.acceptable_phrases and any(p.lower() in low for p in item.acceptable_phrases):
        return True
    if item.detect_all and not all(k.lower() in low for k in item.detect_all):
        return False
    if item.detect_any and not any(k.lower() in low for k in item.detect_any):
        if item.detect_all and all(k.lower() in low for k in item.detect_all):
            if (
                item.review_gap_type == "결론미비"
                and item.acceptable_phrases
                and not any(p.lower() in low for p in item.acceptable_phrases)
            ):
                return False
            return True
        return False
    # 키워드 흔적은 있으나 결론 인정문장이 없으면 결론미비로 본다.
    if (
        item.acceptable_phrases
        and str(item.review_gap_type) == "결론미비"
        and not any(p.lower() in low for p in item.acceptable_phrases)
    ):
        return False
    if item.required_evidence:
        return all(e.lower() in low for e in item.required_evidence)
    return True


@lru_cache(maxsize=1)
def load_sheet_roles_from_db() -> dict[str, str]:
    """조서 연결·대사 사전 xlsx → {조서코드: 역할}."""
    path = guidelines_root() / rg.TEMPLATE_FILES["sheet_tieout"]
    out = dict(rg.SHEET_ROLE_REGISTRY)
    if not path.is_file():
        return out
    for row in _read_xlsx(path):
        code = str(row.get("sheet_code") or row.get("조서번호") or "").strip().upper()
        role = str(row.get("role") or row.get("역할") or "").strip()
        if code and role:
            out[code] = role
    return out


@lru_cache(maxsize=1)
def load_review_phrases_from_db() -> list[dict[str, Any]] | None:
    """검토내역·결론 인정 문장 사전."""
    path = guidelines_root() / rg.TEMPLATE_FILES["review_phrases"]
    if not path.is_file():
        return None
    rows = _read_xlsx(path)
    if not rows:
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        acct = str(row.get("account") or row.get("계정") or "").strip()
        if not acct:
            continue
        out.append(
            {
                "account": acct,
                "topic": str(row.get("topic") or row.get("쟁점") or "").strip(),
                "acceptable_phrases": _split_cells(
                    row.get("acceptable_phrases") or row.get("인정문장")
                ),
                "adjacent_cell_ok": str(
                    row.get("adjacent_cell_ok") or row.get("인접셀") or "Y"
                ).upper() in ("Y", "YES", "1", "TRUE"),
                "red_flag_phrases": _split_cells(
                    row.get("red_flag_phrases") or row.get("지적문장")
                ),
                "context_hint": str(
                    row.get("context_hint") or row.get("맥락") or ""
                ).strip(),
            }
        )
    return out or None


def _enforcement_row_to_item(row: dict[str, Any]) -> EnhancedChecklistItem:
    code = str(row.get("sheet_code") or row.get("조서인덱스") or "").strip().upper()
    return EnhancedChecklistItem(
        name=str(row.get("checklist_item") or row.get("체크리스트항목") or "").strip(),
        checklist_id=str(row.get("checklist_id") or row.get("체크ID") or "").strip(),
        violation_type=str(row.get("violation_type") or row.get("지적유형") or "").strip(),
        procedure_gap=str(row.get("procedure_gap") or row.get("절차흠결") or "").strip(),
        case_source=str(row.get("case_source") or row.get("사례출처") or "").strip(),
        case_example=str(row.get("case_examples") or row.get("사례예시") or "").strip(),
        case_numbers=str(row.get("case_numbers") or row.get("사례번호") or "").strip(),
        basis="감리지적사례·실증절차 체크리스트",
        to_be=str(row.get("to_be") or row.get("보완지침") or "").strip(),
        to_be_if_missing=str(row.get("to_be") or row.get("보완지침") or "").strip(),
        review_gap_type=str(row.get("review_gap_type") or row.get("리뷰유형") or "검토누락").strip(),
        detect_any=_split_cells(row.get("detect_any") or row.get("탐지키워드")),
        required_evidence=_split_cells(row.get("required_evidence") or row.get("필수증거")),
        acceptable_phrases=_split_cells(row.get("acceptable_phrases") or row.get("인정문장")),
        red_flag_phrases=_split_cells(row.get("red_flag_phrases") or row.get("지적문장")),
        related_sheet_codes=(code,) if code else (),
        review_procedure=str(row.get("review_procedure") or row.get("검토절차") or "").strip(),
        sheet_code=code,
        sheet_label=str(row.get("sheet_label") or row.get("조서라벨") or "").strip(),
        canonical_account=str(row.get("canonical_account") or row.get("계정과목") or "").strip(),
        case_count=int(float(row.get("case_count") or 0) or 0),
        case_context=str(row.get("case_context") or row.get("사례맥락") or "").strip(),
        audit_focus=str(row.get("audit_focus") or row.get("감사점검") or "").strip(),
    )


def _catalog_row_to_item(row: Any) -> EnhancedChecklistItem:
    return EnhancedChecklistItem(
        name=row.checklist_item,
        checklist_id=row.checklist_id,
        violation_type=row.violation_type,
        procedure_gap=row.procedure_gap,
        case_source=row.case_source,
        case_example=row.case_examples,
        case_numbers=row.case_numbers,
        basis="감리지적사례·실증절차 체크리스트",
        to_be=row.to_be,
        to_be_if_missing=row.to_be,
        review_gap_type=row.review_gap_type,
        detect_any=row.detect_any,
        required_evidence=row.required_evidence,
        acceptable_phrases=row.acceptable_phrases,
        red_flag_phrases=row.red_flag_phrases,
        related_sheet_codes=(row.sheet_code,),
        review_procedure=row.review_procedure,
        sheet_code=row.sheet_code,
        sheet_label=row.sheet_label,
        canonical_account=row.canonical_account,
        case_count=row.case_count,
        case_context=getattr(row, "case_context", "") or "",
        audit_focus=getattr(row, "audit_focus", "") or "",
    )


@lru_cache(maxsize=4)
def load_enforcement_checklist_from_db(is_listed: bool) -> list[EnhancedChecklistItem] | None:
    """Hanul DB xlsx 또는 학습 카탈로그에서 감리지적 체크리스트 로드."""
    key = "enforcement_listed" if is_listed else "enforcement_unlisted"
    path = guidelines_root() / rg.TEMPLATE_FILES[key]
    if path.is_file():
        for sheet in ("체크리스트", 0):
            rows = _read_xlsx(path, sheet=sheet)
            if not rows:
                continue
            if any(str(r.get("checklist_item") or r.get("체크리스트항목") or "").strip() for r in rows):
                items = [_enforcement_row_to_item(r) for r in rows]
                items = [i for i in items if i.name and i.sheet_code]
                if items:
                    return items
    try:
        import enforcement_checklist_catalog as ecc
        rows = ecc.rows_for_listed() if is_listed else ecc.rows_for_unlisted()
        if rows:
            return [_catalog_row_to_item(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return None


@lru_cache(maxsize=1)
def load_golden_set_from_db() -> list[dict[str, Any]] | None:
    """골든셋 회귀 기준."""
    path = guidelines_root() / rg.TEMPLATE_FILES["golden_set"]
    if not path.is_file():
        return None
    for sheet in ("골든셋", 0):
        rows = _read_xlsx(path, sheet=sheet)
        if not rows:
            continue
        if any(str(r.get("case_id") or r.get("케이스ID") or "").strip() for r in rows):
            break
    else:
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row.get("case_id") or row.get("케이스ID") or "").strip()
        if not case_id:
            continue
        out.append(dict(row))
    return out or None


def templates_status() -> list[dict[str, str]]:
    """템플릿 파일 존재 여부."""
    root = guidelines_root()
    rows: list[dict[str, str]] = []
    for req in rg.template_upload_requests():
        p = root / req["file"]
        local = Path(__file__).resolve().parent / "data" / "templates" / req["file"]
        if p.is_file():
            status = "✅ Hanul DB 연결됨"
        elif local.is_file():
            status = "📁 로컬 샘플만 (Hanul DB 업로드 대기)"
        else:
            status = "⏳ 미제공"
        rows.append({**req, "path": str(p), "status": status})
    return rows
