"""4대 중점 골든셋 회귀 검증."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import fss_focus
import golden_set_catalog as gsc
from parser import ParsedDocument


@dataclass
class RegressionResult:
    case_id: str
    passed: bool
    scenario: str
    focus_notes: int
    errors: list[str] = field(default_factory=list)
    matched_checklist_ids: list[str] = field(default_factory=list)


def _mock_doc(case: gsc.GoldenSetCase) -> ParsedDocument:
    """골든셋 케이스용 최소 ParsedDocument."""
    import pandas as pd

    text = case.mock_sheet_text or ""
    doc = ParsedDocument(file_name=f"{case.case_id}.mock", file_type="mock", text=text)
    if not text:
        return doc
    df = pd.DataFrame([[text]], columns=["검토내용"])
    df.attrs["title"] = case.mock_sheet_title or "테스트 시트"
    df.attrs["source"] = case.mock_sheet_code or "GS"
    doc.tables = [df]
    return doc


def _note_blob(notes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for n in notes:
        parts.extend(
            str(n.get(k, "") or "")
            for k in ("defect", "reason", "to_be", "focus_checklist_id")
        )
    return "\n".join(parts)


def _all_focus_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        n
        for n in notes
        if n.get("is_focus_related") or n.get("category") == "중점감리"
    ]


def _focus_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _all_focus_notes(notes)


def _case_focus_notes(
    focus: list[dict[str, Any]], case: gsc.GoldenSetCase
) -> list[dict[str, Any]]:
    """케이스에 해당하는 4대중점 노트만 추출."""
    if case.focus_issue_no:
        focus = [n for n in focus if n.get("focus_issue_no") == case.focus_issue_no]
    if case.checklist_ids:
        focus = [
            n
            for n in focus
            if str(n.get("focus_checklist_id") or "") in case.checklist_ids
            or any(cid in str(n.get("defect") or "") for cid in case.checklist_ids)
        ]
    return focus


def _match_patterns(blob: str, patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if p and not _pattern_found(blob, p)]


def _pattern_found(blob: str, pattern: str) -> bool:
    if not pattern:
        return False
    if pattern in blob:
        return True
    if "[" in pattern or "]" in pattern:
        return False
    try:
        return bool(re.search(pattern, blob, re.I))
    except re.error:
        return pattern.lower() in blob.lower()


def evaluate_case(case: gsc.GoldenSetCase) -> RegressionResult:
    """단일 골든셋 케이스 실행."""
    listed = case.company_type == "상장"
    doc = _mock_doc(case)
    engagement: dict[str, Any] = {
        "audit_year": 2026,
        "is_listed": listed,
        "materiality_te": 100_000_000,
    }
    notes = fss_focus.run_focus_review(doc, engagement, is_listed=listed)
    focus = _case_focus_notes(_all_focus_notes(notes), case)
    blob = _note_blob(focus)
    errors: list[str] = []

    matched_ids = [
        str(n.get("focus_checklist_id") or "")
        for n in focus
        if n.get("focus_checklist_id")
    ]

    if case.expected_gap_type == "없음":
        if focus:
            errors.append(f"4대중점 노트 {len(focus)}건 발생 (0건 기대)")
    else:
        if not focus:
            errors.append("4대중점 노트 0건 (1건 이상 기대)")
        else:
            gaps = {str(n.get("review_gap_type") or "") for n in focus}
            if case.expected_gap_type and case.expected_gap_type not in gaps:
                errors.append(
                    f"기대 gap_type={case.expected_gap_type}, 실제={gaps}"
                )

    for p in case.must_have_defects:
        if not _pattern_found(blob, p):
            errors.append(f"must_have 누락: {p}")

    for p in case.must_not_have_defects:
        if _pattern_found(blob, p):
            errors.append(f"must_not_have 발생: {p}")

    cnt = len(focus)
    if cnt < case.expected_tier1_min:
        errors.append(f"노트 수 {cnt} < min {case.expected_tier1_min}")
    if case.expected_tier1_max >= 0 and cnt > case.expected_tier1_max:
        errors.append(f"노트 수 {cnt} > max {case.expected_tier1_max}")

    if case.checklist_ids:
        for cid in case.checklist_ids:
            if case.expected_gap_type != "없음" and cid not in matched_ids:
                if cid not in blob:
                    errors.append(f"checklist_id 미매칭: {cid}")

    return RegressionResult(
        case_id=case.case_id,
        passed=not errors,
        scenario=case.scenario,
        focus_notes=len(focus),
        errors=errors,
        matched_checklist_ids=matched_ids,
    )


def run_focus_golden_tests(
    *,
    issue_no: int | None = None,
    company_type: str | None = None,
) -> list[RegressionResult]:
    """재고·지분법 등 focus 골든셋 일괄 실행."""
    cases = gsc.cases_for_focus(issue_no=issue_no, company_type=company_type)
    return [evaluate_case(c) for c in cases if c.mock_sheet_text or c.focus_issue_no == 0]


def summarize_results(results: list[RegressionResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 1.0,
        "tier1_recall": round(passed / total, 3) if total else 1.0,
        "results": results,
    }


def validate_review_notes(
    notes: list[dict[str, Any]],
    *,
    file_name: str = "",
    is_listed: bool = True,
) -> list[RegressionResult]:
    """실제 리뷰 결과를 골든셋 기대치와 대조 (file_pattern 매칭 케이스)."""
    import fnmatch

    focus = _focus_notes(notes)
    blob = _note_blob(focus)
    out: list[RegressionResult] = []
    ctype = "상장" if is_listed else "비상장"

    for case in gsc.GOLDEN_SET_CASES:
        if case.company_type != ctype:
            continue
        if case.file_pattern and file_name:
            if not fnmatch.fnmatch(file_name, case.file_pattern):
                continue
        elif case.file_pattern:
            continue

        errors: list[str] = []
        if case.expected_gap_type == "없음":
            if focus:
                errors.append(f"4대중점 노트 {len(focus)}건 (0건 기대)")
        for p in case.must_have_defects:
            if not _pattern_found(blob, p):
                errors.append(f"must_have 누락: {p}")
        for p in case.must_not_have_defects:
            if _pattern_found(blob, p):
                errors.append(f"must_not_have: {p}")

        out.append(
            RegressionResult(
                case_id=case.case_id,
                passed=not errors,
                scenario=case.scenario,
                focus_notes=len(focus),
                errors=errors,
            )
        )
    return out


if __name__ == "__main__":
    results = run_focus_golden_tests()
    summary = summarize_results(results)
    print(f"골든셋 회귀: {summary['passed']}/{summary['total']} 통과")
    for r in results:
        mark = "✅" if r.passed else "❌"
        print(f"  {mark} {r.case_id}: {r.scenario} (notes={r.focus_notes})")
        for e in r.errors:
            print(f"      - {e}")
