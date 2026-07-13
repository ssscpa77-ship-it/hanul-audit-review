"""계정·조서인덱스별 감리지적 체크리스트 기반 자가검토."""

from __future__ import annotations

import re
from typing import Any

import guidelines_loader as gl
import knowledge_base as kb
import review_engine as re_engine
import sheet_code_registry as scr
from parser import ParsedDocument


def _sheet_text(table) -> str:
    return re_engine._sheet_text(table)


def _sheet_code_for_table(table) -> str | None:
    source = str(table.attrs.get("source", "")).strip()
    title = str(table.attrs.get("title", "")).strip()
    for label in (source, title, f"{source} {title}"):
        code = scr.parse_sheet_code(label)
        if code:
            return code
    acct = re_engine.table_account(table)
    if acct:
        return scr.sheet_code_for_account(acct)
    return None


def _tables_for_code(doc: ParsedDocument, code: str) -> list:
    code_up = code.upper()
    out = []
    for t in doc.tables:
        sc = _sheet_code_for_table(t)
        if sc and sc.upper() == code_up:
            out.append(t)
        elif not sc:
            acct = re_engine.table_account(t)
            mapped = scr.sheet_code_for_account(acct) if acct else None
            if mapped and mapped.upper() == code_up:
                out.append(t)
    return out


def _check_item_mandatory(stext: str, item: gl.EnhancedChecklistItem) -> str | None:
    """조서인덱스가 존재하면 체크리스트 항목을 반드시 검토. 미충족 시 gap 반환."""
    if gl.checklist_satisfied_enhanced(stext, item):
        return None
    return item.review_gap_type or "검토누락"


def _enforcement_cases_for_item(item: gl.EnhancedChecklistItem) -> list[dict[str, Any]]:
    """체크리스트에 연결된 과거 지적사례 샘플을 enforcement_cases 형식으로."""
    brief_src = item.case_context or item.case_example or item.procedure_gap or ""
    cases: list[dict[str, Any]] = []
    nums = [n.strip() for n in re.split(r"[;|]", item.case_numbers or "") if n.strip()]
    for num in nums[:2]:
        cases.append(
            {
                "number": num,
                "subject": item.violation_type or item.name,
                "brief": brief_src[:280],
                "summary_line": (
                    f"감리지적사례 {num} {item.violation_type or ''}"
                    + (f" — {item.audit_focus[:60]}" if item.audit_focus else " — 과거 지적사례")
                ),
                "has_number": True,
                "file": item.case_source or "자가검토_지침_템플릿",
            }
        )
    if not cases and (item.case_example or item.case_context):
        cases.append(
            {
                "number": item.checklist_id or "",
                "subject": item.violation_type or item.name,
                "brief": brief_src[:280],
                "summary_line": (
                    f"감리지적 체크리스트 {item.checklist_id} — {item.violation_type}"
                    + (f" ({item.audit_focus[:50]})" if item.audit_focus else "")
                ),
                "has_number": bool(item.checklist_id),
                "file": item.case_source or "자가검토_지침_템플릿",
            }
        )
    return cases


def run_enforcement_checklist_review(
    doc: ParsedDocument,
    *,
    is_listed: bool = True,
) -> list[dict[str, Any]]:
    """조서 인덱스별 감리지적 체크리스트 — **전 항목 필수 검토**."""
    scr.set_mapping_variant(is_listed)
    items = gl.load_enforcement_checklist_from_db(is_listed)
    if not items:
        return []

    notes: list[dict[str, Any]] = []
    seen: set[str] = set()

    by_code: dict[str, list[gl.EnhancedChecklistItem]] = {}
    for item in items:
        code = (item.sheet_code or (item.related_sheet_codes[0] if item.related_sheet_codes else "")).upper()
        if code:
            by_code.setdefault(code, []).append(item)

    for code, group in by_code.items():
        tables = _tables_for_code(doc, code)
        if not tables:
            continue
        stext = "\n".join(_sheet_text(t) for t in tables)
        if len(stext.strip()) < 20:
            continue
        sheet_no = code
        sheet_title = (
            group[0].canonical_account
            or group[0].sheet_label
            or re_engine.note_display_account(
                {"sheet_title": tables[0].attrs.get("title", ""), "sheet_no": sheet_no}
            )
            or code
        )

        for item in group:
            gap = _check_item_mandatory(stext, item)
            if not gap:
                continue
            key = f"{code}:{item.checklist_id}"
            if key in seen:
                continue
            seen.add(key)

            tag = "검토누락" if gap == "검토누락" else "결론미비"
            defect = f"[감리지적·{tag}] {code} — {item.violation_type or item.name}"
            case_ref = item.case_numbers or item.checklist_id or "자가검토_지침_템플릿"
            context = item.case_context or item.case_example or ""
            focus = item.audit_focus or ""
            reason = (
                f"「{sheet_title}」({code}) 조서 — 자가검토 지침 템플릿 감리지적 체크리스트 "
                f"「{item.checklist_id}」 항목 미충족. "
                f"{item.procedure_gap or item.name}. "
            )
            if context:
                reason += f"과거 지적 맥락: {context} "
            if focus:
                reason += f"점검 포인트: {focus} "
            if not context:
                reason += f"과거 지적사례 샘플: {case_ref}"
            note = re_engine._note(
                category="감리지적체크",
                importance="중",
                defect=defect,
                reason=reason,
                basis="Hanul DB 자가검토_지침_템플릿 · 감리지적사례 체크리스트(필수 검토)",
                to_be=item.to_be or item.to_be_if_missing or "해당 절차를 수행·문서화하십시오.",
                sheet_no=code,
                sheet_title=sheet_title,
            )
            note["enforcement_protected"] = True
            note["enforcement_checklist_id"] = item.checklist_id
            note["enforcement_cases"] = _enforcement_cases_for_item(item)
            note["violation_type"] = item.violation_type or ""
            note["procedure_gap"] = item.procedure_gap or ""
            note["case_example"] = item.case_example or ""
            note["case_context"] = item.case_context or ""
            note["audit_focus"] = item.audit_focus or ""
            vtype = item.violation_type or item.name or ""
            pgap = item.procedure_gap or item.name or ""
            ctx_snip = (item.case_context or item.case_example or item.case_numbers or "")[:120]
            focus_snip = (item.audit_focus or "")[:80]
            detail = f"{code} {vtype} — {pgap}"
            if ctx_snip:
                detail += f" | 맥락: {ctx_snip}"
            if focus_snip:
                detail += f" | 점검: {focus_snip}"
            note["issue_detail_line"] = detail
            notes.append(note)

    return notes


def checklist_coverage(doc: ParsedDocument, *, is_listed: bool = True) -> dict[str, Any]:
    """필수 검토 커버리지 — 조서인덱스별 체크리스트 적용 현황."""
    items = gl.load_enforcement_checklist_from_db(is_listed) or []
    by_code: dict[str, list[gl.EnhancedChecklistItem]] = {}
    for item in items:
        code = (item.sheet_code or "").upper()
        if code:
            by_code.setdefault(code, []).append(item)

    reviewed = 0
    passed = 0
    sheets_in_doc = 0
    for code, group in by_code.items():
        tables = _tables_for_code(doc, code)
        if not tables:
            continue
        sheets_in_doc += 1
        stext = "\n".join(_sheet_text(t) for t in tables)
        for item in group:
            reviewed += 1
            if gl.checklist_satisfied_enhanced(stext, item):
                passed += 1
    return {
        "checklist_items_total": len(items),
        "sheet_codes_in_doc": sheets_in_doc,
        "items_reviewed": reviewed,
        "items_passed": passed,
        "items_failed": reviewed - passed,
        "kb_ready": kb.is_ready(),
    }
