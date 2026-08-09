"""지휘자(Conductor) — 계정별 필요 에이전트만 선별·중복 금지 WorkPlan.

「docs/오케스트라_지휘자_설계_2026-08-09.md」구현.
오케스트레이터는 이 WorkPlan의 call 목록만 실행한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import account_agents
import review_engine as re_engine
from parser import ParsedDocument

# 계정 → 필수 계정 에이전트 (설계 §4). FA는 전역 규칙으로 별도 결정.
_ACCOUNT_REQUIRED_AA = dict(account_agents.ACCOUNT_AGENT_IDS)

# after_L1에서 기본 생략하는 기능 에이전트 (L1이 이미 소유)
_SKIP_AFTER_L1 = frozenset({"FA-2", "FA-4:checklists"})


@dataclass
class WorkPlan:
    mode: str  # "after_L1" | "standalone"
    accounts: list[str]
    call: list[str]
    skip: list[str]
    reasons: dict[str, str] = field(default_factory=dict)
    max_workers: int = 6
    has_amount_tables: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "accounts": list(self.accounts),
            "call": list(self.call),
            "skip": list(self.skip),
            "reasons": dict(self.reasons),
            "max_workers": self.max_workers,
            "has_amount_tables": self.has_amount_tables,
        }


def _has_amount_tables(doc: ParsedDocument) -> bool:
    """합계·재계산(FA-1)이 의미 있는 숫자 표가 있는지."""
    for t in getattr(doc, "tables", []) or []:
        try:
            if getattr(t, "shape", (0, 0))[1] >= 2 and len(t) >= 2:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def build_work_plan(
    doc: ParsedDocument,
    *,
    mode: str = "after_L1",
    max_workers: int = 6,
) -> WorkPlan:
    """조서 악보를 읽고 호출/생략 WorkPlan을 작성한다.

    mode:
      - after_L1: app이 이미 run_review()를 수행한 뒤 (중복 금지 엄격)
      - standalone: 멀티에이전트만 단독 실행 (체크리스트 포함 가능)
    """
    accounts = list(re_engine.document_accounts(doc) or [])
    has_amt = _has_amount_tables(doc)
    call: list[str] = []
    skip: list[str] = []
    reasons: dict[str, str] = {}

    # --- 기능 에이전트 ---
    # after_L1: L1 `_check_calculations`가 이미 합계검증을 수행하므로 FA-1 전수 재계산 금지
    # (36시트 조서에서 FA-1이 수분 이상 소요되는 병목의 주원인)
    if mode == "after_L1":
        skip.append("FA-1")
        reasons["FA-1"] = "L1이 합계·계산검증을 이미 수행 — 전표 재계산 중복 금지(속도)"
    elif has_amt:
        call.append("FA-1")
    else:
        skip.append("FA-1")
        reasons["FA-1"] = "금액·다열 표가 없어 합계검증 생략"

    if mode == "after_L1":
        skip.append("FA-2")
        reasons["FA-2"] = "L1이 교차대사·주석참조를 이미 수행 — 중복 금지"
    else:
        call.append("FA-2")

    # FA-3: 조서에 계정이 하나라도 있으면 (카탈로그 Pass/Fail)
    if accounts:
        call.append("FA-3")
    else:
        skip.append("FA-3")
        reasons["FA-3"] = "식별된 계정 없음"

    # FA-4: after_L1 → redflag만 / standalone → checklists+redflag
    if mode == "after_L1":
        call.append("FA-4:redflag")
        skip.append("FA-4:checklists")
        reasons["FA-4:checklists"] = (
            "L1이 focus_selfcheck(G0~G4)·감리지적 전수를 이미 수행 — 중복 금지"
        )
    else:
        call.append("FA-4:checklists")

    # --- 계정 에이전트: 조서에 있는 계정만 ---
    present_aa = sorted(set(accounts) & set(_ACCOUNT_REQUIRED_AA))
    for acct in present_aa:
        call.append(f"AA:{acct}")

    absent = sorted(set(_ACCOUNT_REQUIRED_AA) - set(accounts))
    if absent:
        reasons["AA:absent"] = (
            f"조서에 없는 계정 AA 미호출 ({len(absent)}종): " + ", ".join(absent[:8])
            + ("…" if len(absent) > 8 else "")
        )

    # 워커 수: 호출 수에 맞춤 (과다 스레드 방지)
    workers = max(2, min(max_workers, max(2, len(call))))

    return WorkPlan(
        mode=mode,
        accounts=accounts,
        call=call,
        skip=skip,
        reasons=reasons,
        max_workers=workers,
        has_amount_tables=has_amt,
    )


def plan_summary_ko(plan: WorkPlan) -> str:
    """UI·로그용 한 줄 요약."""
    calls = ", ".join(plan.call) if plan.call else "(없음)"
    skips = ", ".join(plan.skip) if plan.skip else "(없음)"
    return f"모드={plan.mode} · 호출[{calls}] · 생략[{skips}]"
