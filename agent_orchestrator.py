"""멀티에이전트 아키텍처 — 오케스트레이터 (Lead Reviewer Agent).

「멀티에이전트_아키텍처_설계안_2026-08-09.md」§5 협업 프로토콜을 구현한다.

기존 review_engine.run_review()를 대체하지 않는 **병행(parallel-track) 파이프라인**이다.
app.py 등 기존 통합 지점은 이번 라운드에서 변경하지 않았다(작업 시점에 app.py·
enforcement_review.py·output_formatter.py에 다른 협업자의 미커밋 변경사항이 있어,
충돌 방지를 위해 신규 모듈로만 구현). 통합 방법은 본 파일 하단 `if __name__ ==
"__main__":` 스모크 테스트 및 개발지침서 §8 로드맵 Phase 4를 참고해 검토 후 진행할 것.

사용 예:
    import agent_orchestrator as orch
    result = orch.run_multi_agent_review(doc)
    for note in result["findings"]:
        print(note["importance"], note["defect"])
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import account_agents
import functional_agents
import review_engine as re_engine
from agent_schema import group_key, has_evidence
from parser import ParsedDocument

TIER_IMPORTANCE = {1: "상", 2: "중", 3: "하"}


def _cross_validate(findings: list[dict[str, Any]], audit_trail: list[str]) -> list[dict[str, Any]]:
    """§5 Step2 — 계정 에이전트 단독 지적은 기능 에이전트 교차확인이 있어야 Tier1 유지."""
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
    """§5 Step4 — 근거 없는 finding은 Tier1(상)로 승격 금지."""
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
    """finding의 실질적 판단 대상을 식별하는 서명.

    같은 계정·같은 카테고리라도 procedure_id(예: F1-01/F1-02/F1-03)가 다르면
    서로 다른 절차에 대한 지적이므로 병합하면 안 된다. defect 문구에서
    괄호 안 procedure_id를 우선 추출하고, 없으면 defect 앞부분(60자)을
    서명으로 사용해 진짜 중복(동일 문구를 여러 에이전트가 각자 산출)만 합친다.
    """
    defect = str(f.get("defect") or "")
    m = _PROC_ID_RE.search(defect)
    if m:
        return m.group(1)
    return defect[:60]


def _dedup(findings: list[dict[str, Any]], audit_trail: list[str]) -> list[dict[str, Any]]:
    """§5 Step2 — 동일 (sheet_no, category, account, 판단대상서명) 그룹 내 최고 confidence 1건만 유지."""
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
                    f"[중복제거] {cur['agent_id']} finding을 {f['agent_id']}(confidence 높음)로 대체: {key}"
                )
            by_key[key] = f
    return list(by_key.values())


def _assign_ids(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, f in enumerate(sorted(findings, key=lambda x: {"상": 0, "중": 1, "하": 2}.get(x.get("importance"), 1)), start=1):
        f["id"] = f"MA-{i:03d}"
    return findings


def run_multi_agent_review(
    doc: ParsedDocument,
    materiality: re_engine.Materiality | None = None,
    is_listed: bool | None = None,
    engagement: dict[str, Any] | None = None,
    max_workers: int = 8,
) -> dict[str, Any]:
    """멀티에이전트 협업 리뷰 실행 — §5 Step1~7.

    반환: {"findings": [...], "audit_trail": [...], "accounts_reviewed": [...]}
    """
    audit_trail: list[str] = []
    mat = materiality or re_engine.extract_materiality(doc)
    listed = is_listed if is_listed is not None else re_engine.detect_is_listed(doc)
    eng = engagement or re_engine.extract_engagement(doc)

    accounts = re_engine.document_accounts(doc)
    audit_trail.append(f"[Step1] 조서 계정 매핑: {accounts}")

    # --- Step1~ 계정·기능 에이전트 병렬 실행 ---
    tasks: dict[str, Any] = {
        "FA-1": lambda: functional_agents.run_fa1_tie_out(doc, mat),
        "FA-2": lambda: functional_agents.run_fa2_cross_reference(doc, mat),
        "FA-3": lambda: functional_agents.run_fa3_procedure_completeness(doc, mat, listed),
        "FA-4": lambda: functional_agents.run_fa4_regulatory_focus(doc, eng, listed),
    }
    for account in set(accounts) & set(account_agents.ACCOUNT_AGENT_IDS):
        tasks[f"AA:{account}"] = lambda a=account: account_agents.run_account_agent(a, doc)

    all_findings: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                audit_trail.append(f"[오류] {name} 실행 실패: {exc!r}")
                continue
            audit_trail.append(f"[완료] {name}: {len(result)}건 산출")
            all_findings.extend(result)

    # --- Step2 상호검증 ---
    all_findings = _cross_validate(all_findings, audit_trail)
    # --- Step2 중복제거 ---
    all_findings = _dedup(all_findings, audit_trail)
    # --- Step4 근거 재검증 ---
    all_findings = _verify_evidence(all_findings, audit_trail)
    # --- Step5 ID 배정(3칸 포맷은 기존 output_formatter/word_export가 처리) ---
    all_findings = _assign_ids(all_findings)

    return {
        "findings": all_findings,
        "audit_trail": audit_trail,
        "accounts_reviewed": accounts,
        "tier_counts": {
            "상": sum(1 for f in all_findings if f.get("importance") == "상"),
            "중": sum(1 for f in all_findings if f.get("importance") == "중"),
            "하": sum(1 for f in all_findings if f.get("importance") == "하"),
        },
    }


if __name__ == "__main__":
    # 스모크 테스트 — 합성 조서 2건(재고자산/현금)으로 파이프라인이 예외 없이
    # 동작하는지, FA-3/AA-03가 저가법 NRV 누락을 잡아내는지 확인.
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

    result = run_multi_agent_review(doc)
    print("accounts_reviewed:", result["accounts_reviewed"])
    print("tier_counts:", result["tier_counts"])
    for n in result["findings"]:
        print(f"[{n['importance']}] {n['agent_id']:6s} {n['defect']}")
    print("\n--- audit trail ---")
    for line in result["audit_trail"]:
        print(line)
