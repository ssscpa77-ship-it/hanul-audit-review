"""계정·조서인덱스별 감리지적 체크리스트 기반 자가검토.

리뷰노트 설계 원칙 (2026-08-09):
1) 리뷰사항 — 검토대상·누락절차를 짧게·구체적으로 (사례 원문 dump 금지)
2) 리뷰근거 — 파일명 금지, 점검 내용 한 줄
3) 감리지적사례 — 지적유형·계정과 유사한 사례만, 왜 지적됐는지 사유 명확
"""

from __future__ import annotations

import re
from typing import Any

import guidelines_loader as gl
import knowledge_base as kb
import review_engine as re_engine
import sheet_code_registry as scr
from parser import ParsedDocument

_REASON_MAX = 220
_FOCUS_MAX = 90
_BRIEF_MAX = 140


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


def _clip(text: str, limit: int) -> str:
    t = " ".join((text or "").split()).strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


def _first_sentence(text: str, limit: int = 120) -> str:
    """사례 맥락에서 첫 핵심 문장만 (다중 사례번호 나열 제거)."""
    t = " ".join((text or "").split()).strip()
    if not t:
        return ""
    # FSS/KICPA 번호 나열·세미콜론 분절 중 첫 의미 단위
    parts = re.split(r"[;|]|FSS\d{4}|KICPA-", t)
    for p in parts:
        p = p.strip(" -—·,.")
        if len(p) >= 12 and not re.fullmatch(r"[\d\-_/]+", p):
            return _clip(p, limit)
    return _clip(t, limit)


def _review_target(sheet_title: str, code: str, vtype: str) -> str:
    """검토대상을 회계사가 바로 알 수 있게."""
    acct = sheet_title or code
    v = (vtype or "지적유형").strip()
    return f"{acct}({code}) 조서 — 「{v}」 위험 관련 실증절차·결론"


def _build_defect(tag: str, code: str, sheet_title: str, item: gl.EnhancedChecklistItem) -> str:
    vtype = (item.violation_type or item.name or "검토항목").strip()
    acct = sheet_title or code
    # 예: [감리지적·검토누락] 매출(P) — 과소계상 위험 검토 누락
    return f"[감리지적·{tag}] {acct}({code}) — {vtype} 위험 검토 누락"


def _build_reason(
    sheet_title: str,
    code: str,
    item: gl.EnhancedChecklistItem,
    gap: str,
) -> str:
    """짧게: ①검토대상 ②미충족 항목 ③무엇을 볼지. 사례 원문 dump 금지."""
    vtype = (item.violation_type or item.name or "").strip()
    target = _review_target(sheet_title, code, vtype)
    gap_label = "검토 흔적 없음" if gap == "검토누락" else "결론·판단 기재 미비"
    proc = _clip(item.procedure_gap or item.name or "필수 실증절차", 80)
    focus = _clip(item.audit_focus or "", _FOCUS_MAX)
    cid = item.checklist_id or ""

    lines = [
        f"검토대상: {target}.",
        f"체크리스트 {cid} 미충족({gap_label}) — {proc}.",
    ]
    if focus:
        lines.append(f"조서에서 확인할 것: {focus}.")
    return _clip(" ".join(lines), _REASON_MAX)


def _build_basis(item: gl.EnhancedChecklistItem) -> str:
    """파일명·템플릿 코드 금지 — 점검 내용 한 줄."""
    focus = _clip(item.audit_focus or "", 70)
    if focus:
        return f"감리지적 체크리스트 — {focus}"
    proc = _clip(item.procedure_gap or item.name or "", 70)
    if proc:
        return f"감리지적 체크리스트 — {proc}"
    return "감리지적 체크리스트(필수 검토) — 관련 실증절차·결론 문서화"


def _case_why(item: gl.EnhancedChecklistItem, num: str) -> str:
    """왜 지적받았는지 — 체크리스트 맥락에서 짧게."""
    ctx = item.case_context or item.case_example or ""
    # 해당 번호가 포함된 구간 우선
    if num and ctx and num in ctx:
        idx = ctx.find(num)
        window = ctx[idx + len(num) : idx + len(num) + 180].lstrip(" :-—·,.")
        why = _first_sentence(window, 100)
        why = re.sub(r"^\d{1,4}\s+", "", why)
        if why and len(why) >= 10:
            return why
    why = _first_sentence(ctx, 100)
    why = re.sub(r"^\d{1,4}\s+", "", why)
    if why:
        return why
    focus = _clip(item.audit_focus or "", 80)
    if focus:
        return f"{focus} 미흡"
    return _clip(item.procedure_gap or item.violation_type or "관련 절차 미흡", 80)


def _enforcement_cases_for_item(item: gl.EnhancedChecklistItem) -> list[dict[str, Any]]:
    """지적유형과 직접 연결된 사례만, 사유 명확한 summary."""
    cases: list[dict[str, Any]] = []
    vtype = (item.violation_type or item.name or "").strip()
    nums = [n.strip() for n in re.split(r"[;|]", item.case_numbers or "") if n.strip()]
    # 사례번호가 맥락 문자열에 섞여 있는 경우도 추출
    if not nums:
        nums = re.findall(r"(?:FSS|KICPA)[\w\-]+", item.case_context or item.case_example or "", re.I)[:2]

    for num in nums[:2]:
        why = _case_why(item, num)
        # 애매한 요약(번호만·템플릿명) 제외
        if len(why) < 8 or re.search(r"FY\d{4}|번대_|전사수준|_v\d", why, re.I):
            why = f"{vtype} — 유사 유형으로 감리에서 지적된 사례"
        summary = f"{num} — {vtype}: {why}"
        cases.append(
            {
                "number": num,
                "subject": vtype,
                "brief": _clip(why, _BRIEF_MAX),
                "summary_line": _clip(summary, 160),
                "has_number": True,
                "file": item.case_source or "자가검토_지침_템플릿",
                "why_cited": why,
            }
        )

    if not cases and (item.case_example or item.case_context):
        why = _case_why(item, "")
        if len(why) >= 12 and not re.search(r"우발부채|약정\s*주석", why):
            # 지적유형과 무관한 우발부채 등 애매 문구는 붙이지 않음
            if vtype and vtype not in why and "과소" not in why and "과대" not in why:
                # still allow if procedure_gap related
                if not (item.procedure_gap and any(w in why for w in item.procedure_gap[:20])):
                    return []
        cases.append(
            {
                "number": item.checklist_id or "체크리스트",
                "subject": vtype,
                "brief": _clip(why, _BRIEF_MAX),
                "summary_line": _clip(f"{item.checklist_id} — {vtype}: {why}", 160),
                "has_number": bool(item.checklist_id),
                "file": item.case_source or "자가검토_지침_템플릿",
                "why_cited": why,
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
            vtype = item.violation_type or item.name or ""
            defect = _build_defect(tag, code, sheet_title, item)
            reason = _build_reason(sheet_title, code, item, gap)
            basis = _build_basis(item)
            note = re_engine._note(
                category="감리지적체크",
                importance="중",
                defect=defect,
                reason=reason,
                basis=basis,
                to_be=item.to_be or item.to_be_if_missing or "해당 절차를 수행·문서화하십시오.",
                sheet_no=code,
                sheet_title=sheet_title,
            )
            note["enforcement_protected"] = True
            note["enforcement_checklist_id"] = item.checklist_id
            note["enforcement_cases"] = _enforcement_cases_for_item(item)
            note["violation_type"] = vtype
            note["procedure_gap"] = item.procedure_gap or ""
            note["case_example"] = item.case_example or ""
            note["case_context"] = item.case_context or ""
            note["audit_focus"] = item.audit_focus or ""
            note["review_target"] = _review_target(sheet_title, code, vtype)
            note["issue_detail_line"] = (
                f"검토대상: {note['review_target']} · "
                f"미비: {_clip(item.procedure_gap or item.name or '', 70)}"
            )
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
