"""계정·조서인덱스별 감리지적 체크리스트 카탈로그."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import enforcement_case_learner as ecl

EnforcementCheckRow = ecl.EnforcementCheckRow
AccountKeywordSummary = ecl.AccountKeywordSummary


@lru_cache(maxsize=2)
def rows_for_listed() -> tuple[EnforcementCheckRow, ...]:
    return tuple(ecl.learn_and_build(variant="ifrs_listed")["rows"])


@lru_cache(maxsize=2)
def rows_for_unlisted() -> tuple[EnforcementCheckRow, ...]:
    return tuple(ecl.learn_and_build(variant="non_listed")["rows"])


@lru_cache(maxsize=2)
def summaries_for_listed() -> tuple[AccountKeywordSummary, ...]:
    return tuple(ecl.learn_and_build(variant="ifrs_listed")["summaries"])


@lru_cache(maxsize=2)
def summaries_for_unlisted() -> tuple[AccountKeywordSummary, ...]:
    return tuple(ecl.learn_and_build(variant="non_listed")["summaries"])


def rows_by_sheet_code(*, is_listed: bool) -> dict[str, list[EnforcementCheckRow]]:
    rows = rows_for_listed() if is_listed else rows_for_unlisted()
    out: dict[str, list[EnforcementCheckRow]] = {}
    for r in rows:
        out.setdefault(r.sheet_code, []).append(r)
    return out


def stats(*, is_listed: bool) -> dict[str, Any]:
    rows = rows_for_listed() if is_listed else rows_for_unlisted()
    sums = summaries_for_listed() if is_listed else summaries_for_unlisted()
    data = ecl.learn_and_build(variant="ifrs_listed" if is_listed else "non_listed")
    codes = {r.sheet_code for r in rows}
    return {
        "learned_cases": data["total_cases"],
        "checklist_rows": len(rows),
        "sheet_codes": len(codes),
        "accounts": len(sums),
    }
