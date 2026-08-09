"""멀티에이전트 아키텍처 — 오케스트레이터 (Orchestra).

지휘자(`conductor.build_work_plan`)가 정한 WorkPlan의 **call 목록만** 실행한다.
L1과 중복되는 전수 체크리스트·교차대사는 after_L1 모드에서 호출하지 않는다.

설계: 「docs/오케스트라_지휘자_설계_2026-08-09.md」
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import account_agents
import conductor
import functional_agents
import review_engine as re_engine
from agent_schema import group_key, has_evidence
from parser import ParsedDocument

TIER_IMPORTANCE = {1: "상", 2: "중", 3: "하"}


def _cross_validate(findings: list[dict[str, Any]], audit_trail: list[str]) -> list[dict[str, Any]]:
    """계정 에이전트 단독 지적은 기능 에이전트 교차확인이 있어야 Tier1 유지."""
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_group[group_key(f)].append(f)

    for key, group in by_group.items():
        functional_ids = {f["agent_id"] for f in group if f.get("agent_type") == "functional"}
        for f in group:
            if f.get("agent_type") == "account":
                if functional_ids:
                    f["cross_checked_by"] = sorted(functional_ids)
                elif f.get("importance") == "상":
                    f["importance"] = "중"
                    audit_trail.append(
                        f"[하향] {f['agent_id']} 단독 지적(교차확인 없음) — 상→중 하향: {f['defect'][:40]}..."
                    )
    return findings


def _verify_evidence(findings: list[dict[str, Any]], audit_trail: list[str]) -> list[dict[str, Any]]:
    for f in findings:
        if f.get("importance") == "상" and not has_evidence(f):
            f["importance"] = "중"
            f["basis"] = f.get("basis") or "근거 미확인"
            audit_trail.append(f"[하향] {f['agent_id']} 근거 미확인 — 상→중 하향: {f['defect'][:40]}...")
        if f.get("confidence", 1.0) < 0.6 and f.get("importance") == "상":
            f["importance"] = "중"
            audit_trail.append(f"[하향] {f['agent_id']} confidence<0.6 — 상→중 하향: {f['defect'][:40]}...")
    return findings


_PROC_ID_RE = __import__("re").compile(r"\(([A-Z]{1,4}[0-9]{0,3}(?:\.\d+)?-\d{2})\)")


def _dedup_signature(f: dict[str, Any]) -> str:
    defect = str(f.get("defect") or "")
    m = _PROC_ID_RE.search(defect)
    if m:
        return m.group(1)
    return defect[:60]


def _dedup(findings: list[dict[str, Any]], audit_trail: list[str]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for f in findings:
        key = (
            str(f.get("sheet_no")),
            str(f.get("category")),
            str(f.get("account")),
            _dedup_signature(f),
        )
        cur = by_key.get(key)
        if cur is None or f.get("confidence", 0) > cur.get("confidence", 0):
            if cur is not None:
                audit_trail.append(
                    f"[중복제거] {cur['agent_id']} finding을 {f['agent_id']}(confidence 높음)로 대체"
                )
            by_key[key] = f
    return list(by_key.values())


def _assign_ids(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, f in enumerate(
        sorted(findings, key=lambda x: {"상": 0, "중": 1, "하": 2}.get(x.get("importance"), 1)),
        start=1,
    ):
        f["id"] = f"MA-{i:03d}"
    return findings


def _build_task_fns(
    plan: conductor.WorkPlan,
    doc: ParsedDocument,
    mat: re_engine.Materiality,
    listed: bool,
    eng: dict[str, Any],
) -> dict[str, Callable[[], list[dict[str, Any]]]]:
    """WorkPlan.call 항목만 실행 가능한 람다로 변환."""
    tasks: dict[str, Callable[[], list[dict[str, Any]]]] = {}
    for item in plan.call:
        if item == "FA-1":
            accts = list(plan.accounts)
            tasks["FA-1"] = (
                lambda: functional_agents.run_fa1_tie_out(doc, mat, accounts=accts)
            )
        elif item == "FA-2":
            tasks["FA-2"] = lambda: functional_agents.run_fa2_cross_reference(doc, mat)
        elif item == "FA-3":
            tasks["FA-3"] = (
                lambda: functional_agents.run_fa3_procedure_completeness(doc, mat, listed)
            )
        elif item == "FA-4:checklists":
            tasks["FA-4"] = lambda: functional_agents.run_fa4_regulatory_focus(
                doc, eng, listed, include_checklists=True
            )
        elif item == "FA-4:redflag":
            tasks["FA-4"] = lambda: functional_agents.run_fa4_regulatory_focus(
                doc, eng, listed, include_checklists=False
            )
        elif item.startswith("AA:"):
            acct = item[3:]
            tasks[item] = lambda a=acct: account_agents.run_account_agent(a, doc)
    return tasks


def run_multi_agent_review(
    doc: ParsedDocument,
    materiality: re_engine.Materiality | None = None,
    is_listed: bool | None = None,
    engagement: dict[str, Any] | None = None,
    max_workers: int = 8,
    *,
    mode: str = "after_L1",
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """지휘자 WorkPlan에 따라 필요한 에이전트만 병렬 실행.

    mode="after_L1"(기본): app이 run_review 직후 호출 — 중복 전수 검사 생략.
    mode="standalone": 체크리스트 포함 단독 실행.
    """
    def _prog(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:  # noqa: BLE001
                pass

    audit_trail: list[str] = []
    mat = materiality or re_engine.extract_materiality(doc)
    listed = is_listed if is_listed is not None else re_engine.detect_is_listed(doc)
    eng = engagement or re_engine.extract_engagement(doc)

    _prog("지휘자: 조서 악보(계정) 읽는 중…")
    plan = conductor.build_work_plan(doc, mode=mode, max_workers=max_workers)
    audit_trail.append(f"[지휘] {conductor.plan_summary_ko(plan)}")
    for k, v in plan.reasons.items():
        audit_trail.append(f"[생략사유] {k}: {v}")
    _prog(f"지휘자 배치: {conductor.plan_summary_ko(plan)}")

    tasks = _build_task_fns(plan, doc, mat, listed, eng)
    if not tasks:
        audit_trail.append("[지휘] 호출할 에이전트 없음 — 종료")
        return {
            "findings": [],
            "audit_trail": audit_trail,
            "accounts_reviewed": plan.accounts,
            "work_plan": plan.to_dict(),
            "tier_counts": {"상": 0, "중": 0, "하": 0},
        }

    all_findings: list[dict[str, Any]] = []
    _prog(f"오케스트라 연주 시작 ({len(tasks)}개 에이전트)…")
    with ThreadPoolExecutor(max_workers=plan.max_workers) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                audit_trail.append(f"[오류] {name} 실행 실패: {exc!r}")
                _prog(f"오류: {name}")
                continue
            audit_trail.append(f"[완료] {name}: {len(result)}건 산출")
            _prog(f"완료 {name} ({len(result)}건)")
            all_findings.extend(result)

    _prog("합주 조율(상호검증·중복제거)…")
    all_findings = _cross_validate(all_findings, audit_trail)
    all_findings = _dedup(all_findings, audit_trail)
    all_findings = _verify_evidence(all_findings, audit_trail)
    all_findings = _assign_ids(all_findings)

    return {
        "findings": all_findings,
        "audit_trail": audit_trail,
        "accounts_reviewed": plan.accounts,
        "work_plan": plan.to_dict(),
        "tier_counts": {
            "상": sum(1 for f in all_findings if f.get("importance") == "상"),
            "중": sum(1 for f in all_findings if f.get("importance") == "중"),
            "하": sum(1 for f in all_findings if f.get("importance") == "하"),
        },
    }


if __name__ == "__main__":
    import pandas as pd
    from parser import ParsedDocument as PD

    text_inv = "재고자산 F1 실사입회 참관함. 저가법 검토함. 특이사항 없음."
    df_inv = pd.DataFrame([[text_inv]], columns=["검토내용"])
    df_inv.attrs["title"] = "재고자산 검토"
    df_inv.attrs["source"] = "F1"

    text_cash = "A Lead 현금및예금 조회 진행. tick 표시함."
    df_cash = pd.DataFrame([[text_cash]], columns=["검토내용"])
    df_cash.attrs["title"] = "현금 리드"
    df_cash.attrs["source"] = "A Lead"

    doc = PD(file_name="smoke.mock", file_type="mock", text=text_inv + "\n" + text_cash)
    doc.tables = [df_inv, df_cash]

    result = run_multi_agent_review(doc, mode="after_L1")
    print("work_plan:", result["work_plan"])
    print("accounts_reviewed:", result["accounts_reviewed"])
    print("tier_counts:", result["tier_counts"])
    for n in result["findings"]:
        print(f"[{n['importance']}] {n.get('agent_id',''):8s} {n['defect']}")
    print("\n--- audit trail ---")
    for line in result["audit_trail"]:
        print(line)
