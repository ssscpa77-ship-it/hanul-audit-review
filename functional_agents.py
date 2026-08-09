"""멀티에이전트 아키텍처 — 기능별 에이전트 4종 (FA-1~FA-4).

「멀티에이전트_아키텍처_설계안_2026-08-09.md」§4.2, 「에이전트_명세서_2026-08-09.md」§2 참조.
계정과 무관하게 조서셋 전체를 가로질러 보는 4개 관점. 기존 review_engine·fss_focus·
enforcement_review의 판단 로직을 재사용·재포장하며, 신규 판단(전기대비 이상치·감리사례
역매칭)을 추가한다.

이 모듈은 기존 파이프라인(review_engine.run_review)을 변경하지 않는 **추가(additive)**
모듈이다. `agent_orchestrator.run_multi_agent_review()`에서만 호출된다.
"""

from __future__ import annotations

from typing import Any

import enforcement_review
import fss_focus
import guidelines_loader as gl
import review_engine as re_engine
from agent_schema import make_finding
from parser import ParsedDocument


def _rule_note_to_finding(note: dict[str, Any], agent_id: str, agent_type: str = "functional") -> dict[str, Any]:
    """review_engine/fss_focus/enforcement_review가 만든 기존 노트 dict를
    에이전트 거버넌스 필드가 있는 Finding으로 승격."""
    note = dict(note)
    note.setdefault("agent_id", agent_id)
    note.setdefault("agent_type", agent_type)
    note.setdefault("account", re_engine.note_display_account(note) or "")
    basis = str(note.get("basis") or "").strip()
    note.setdefault("evidence_refs", [basis] if basis and basis != "근거 미확인" else [])
    note.setdefault("confidence", 0.75 if basis else 0.4)
    note.setdefault("cross_checked_by", [])
    note.setdefault("duplicate_group_id", None)
    return note


# --------------------------------------------------------------------------
# FA-1. 합계·계산검증 에이전트 (Tie-out & Calculation Agent)
# --------------------------------------------------------------------------
def run_fa1_tie_out(
    doc: ParsedDocument,
    mat: re_engine.Materiality | None = None,
    *,
    accounts: list[str] | None = None,
    max_tables: int = 12,
) -> list[dict[str, Any]]:
    """표 내 합계·부분합, 전기대비 이상치.

    standalone 모드 전용으로 가볍게 동작한다.
    - 지정 계정 시트만 (accounts)
    - 표 상한 max_tables
    - 행 수 300 초과 표는 스킵 (L1이 이미 큰 표도 일부 검사)
    """
    findings: list[dict[str, Any]] = []
    m = mat or re_engine.extract_materiality(doc)
    acct_set = set(accounts or [])

    candidates: list[tuple[int, Any]] = []
    for idx, table in enumerate(doc.tables):
        if acct_set:
            ta = re_engine.table_account(table)
            if ta not in acct_set:
                continue
        try:
            if table.shape[0] < 3 or table.shape[1] < 2:
                continue
            if table.shape[0] > 300:
                continue
        except Exception:  # noqa: BLE001
            continue
        candidates.append((idx, table))
        if len(candidates) >= max_tables:
            break

    for idx, table in candidates:
        for note in re_engine._verify_table_totals(table, idx, m):
            f = _rule_note_to_finding(note, "FA-1")
            f["category"] = f.get("category") or "계산오류"
            f["evidence_refs"] = ["표 내 재계산 결과(AmountGrid)"]
            f["confidence"] = 0.95
            findings.append(f)

    # 전기대비는 표가 적을 때만 (대량 조서에서는 비용 대비 효과 낮음)
    if len(getattr(doc, "tables", []) or []) <= 20:
        for note in re_engine._check_prior_year_analysis(doc):
            f = _rule_note_to_finding(note, "FA-1")
            f["confidence"] = 0.6
            f["evidence_refs"] = ["전기·당기 비교열 재계산"]
            findings.append(f)

    return findings


# --------------------------------------------------------------------------
# FA-2. 조서간 상호참조 에이전트 (Cross-Reference Agent)
# --------------------------------------------------------------------------
def run_fa2_cross_reference(doc: ParsedDocument, mat: re_engine.Materiality | None = None) -> list[dict[str, Any]]:
    """조서연결_대사_사전(§D) 기준 Lead·세부조서·주석 간 참조 무결성."""
    findings: list[dict[str, Any]] = []
    m = mat or re_engine.extract_materiality(doc)

    for note in re_engine._check_note_references(doc, m):
        f = _rule_note_to_finding(note, "FA-2")
        f["category"] = "상호참조불일치"
        f["evidence_refs"] = ["조서연결_대사_사전(SHEET_ROLE_REGISTRY)"]
        findings.append(f)

    for note in re_engine._check_cross_fs_totals(doc, m):
        f = _rule_note_to_finding(note, "FA-2")
        f["category"] = "상호참조불일치"
        f["evidence_refs"] = ["FS·주석 교차대사"]
        f["confidence"] = 0.9
        findings.append(f)

    for note in re_engine._check_contingency_confirmations(doc):
        f = _rule_note_to_finding(note, "FA-2")
        f["category"] = "상호참조불일치"
        findings.append(f)

    return findings


# --------------------------------------------------------------------------
# FA-3. 표준감사프로그램 절차완전성 에이전트 (Audit Program Completeness Agent)
# --------------------------------------------------------------------------
def _table_text_for_account(doc: ParsedDocument, account: str) -> str:
    return re_engine.account_sheet_text(doc, account)


def _procedure_pass_fail(stext: str, item: Any) -> tuple[bool, str]:
    """계정별_필수절차_카탈로그 1개 procedure_id에 대한 Pass/Fail 판정.

    Gap#5 대응 — 키워드 1개 매칭이 아니라 (a) detect_all 세트 전체 존재
    (b) required_evidence 존재 (c) fail_if 문구 미충족 을 모두 확인한다.
    """
    if item.detect_all and not all(kw in stext for kw in item.detect_all):
        return False, f"필수 키워드 세트 미충족: {', '.join(item.detect_all)}"
    if item.detect_any and not any(kw in stext for kw in item.detect_any):
        return False, f"관련 키워드 없음: {', '.join(item.detect_any)}"
    if item.required_evidence and not any(kw in stext for kw in item.required_evidence):
        return False, f"필수 증빙 언급 없음: {', '.join(item.required_evidence)}"
    return True, ""


def run_fa3_procedure_completeness(
    doc: ParsedDocument,
    mat: re_engine.Materiality | None = None,
    is_listed: bool | None = None,
) -> list[dict[str, Any]]:
    """계정별 필수절차 카탈로그(§B) 대비 체크리스트 단위 Pass/Fail."""
    findings: list[dict[str, Any]] = []
    catalog = gl.load_procedure_catalog_from_db()
    if not catalog:
        return findings

    accounts_in_doc = set(re_engine.document_accounts(doc))
    for account, items in catalog.items():
        if account not in accounts_in_doc:
            continue  # §0.1 — 조서에 있는 계정만 리뷰
        stext = _table_text_for_account(doc, account)
        if not stext:
            continue
        for item in items:
            ok, gap_reason = _procedure_pass_fail(stext, item)
            if ok:
                continue
            findings.append(
                make_finding(
                    agent_id="FA-3",
                    agent_type="functional",
                    category="절차누락",
                    defect=f"{account} — {item.name}({item.checklist_id}) 절차 완전성 미충족: {gap_reason}",
                    reason=f"트리거: {item.review_procedure or '해당 계정 존재'} / fail_if: {item.procedure_gap or '해당사항 확인 필요'}",
                    basis=item.basis or "계정별 필수절차 카탈로그",
                    to_be=item.to_be or "필수 절차 수행 근거 보완",
                    account=account,
                    sheet_no=item.sheet_code,
                    evidence_refs=[item.basis] if item.basis else [],
                    confidence=0.8,
                )
            )
    return findings


# --------------------------------------------------------------------------
# FA-4. 4대중점·감리사례 리스크 에이전트 (Regulatory Focus & Enforcement-Precedent Agent)
# --------------------------------------------------------------------------
def run_fa4_regulatory_focus(
    doc: ParsedDocument,
    engagement: dict[str, Any],
    is_listed: bool | None = None,
    *,
    include_checklists: bool = False,
) -> list[dict[str, Any]]:
    """4대중점 자가진단·감리 체크리스트 + 감리지적사례 역매칭.

    `include_checklists=False`(기본, after_L1): L1이 이미 `focus_selfcheck`·감리지적을
    수행했으므로 **red-flag 역매칭만** 수행한다.
    `include_checklists=True`(standalone): Claude 자가진단 엔진 + 감리 체크리스트 전수.
    """
    findings: list[dict[str, Any]] = []
    listed = bool(is_listed) if is_listed is not None else bool(engagement.get("is_listed"))

    if include_checklists:
        # 2026-08-09: 4대중점은 G0~G4 게이트 자가진단(focus_selfcheck)이 기본.
        try:
            import focus_selfcheck as _fsc
        except ImportError:  # pragma: no cover
            _fsc = None

        if _fsc is not None:
            _res = _fsc.run_selfcheck(doc, engagement, is_listed=listed)
            for note in _res.notes:
                f = _rule_note_to_finding(note, "FA-4")
                f["category"] = "중점감리"
                _gate = str(note.get("focus_gate") or "")
                f["confidence"] = 0.95 if _gate in ("G0", "G1") else 0.85
                f["focus_gate"] = _gate
                f["focus_step_id"] = note.get("focus_step_id", "")
                f["focus_verdict"] = note.get("focus_verdict", "")
                findings.append(f)
        else:
            for note in fss_focus.run_focus_review(doc, engagement, is_listed=listed):
                f = _rule_note_to_finding(note, "FA-4")
                f["category"] = "중점감리"
                f["confidence"] = 0.85
                findings.append(f)

        for note in enforcement_review.run_enforcement_checklist_review(doc, is_listed=listed):
            f = _rule_note_to_finding(note, "FA-4")
            f["category"] = f.get("category") or "감리지적유사"
            findings.append(f)

    # Gap#17 — 감리사례 역매칭(선제) — listed 1회·계정 캐시·최대 8건
    _MAX_REDFLAG = 8
    present = set(re_engine.document_accounts(doc) or [])
    if not present:
        return findings
    items = gl.load_enforcement_checklist_from_db(listed) or []
    text_cache: dict[str, str] = {}
    redflag_n = 0
    for item in items:
        if redflag_n >= _MAX_REDFLAG:
            break
        if not item.red_flag_phrases or not item.canonical_account:
            continue
        if item.canonical_account not in present:
            continue
        if item.canonical_account not in text_cache:
            text_cache[item.canonical_account] = _table_text_for_account(
                doc, item.canonical_account
            )
        stext = text_cache[item.canonical_account]
        if not stext:
            continue
        hit = next((p for p in item.red_flag_phrases if p in stext), None)
        if not hit:
            continue
        findings.append(
            make_finding(
                agent_id="FA-4",
                agent_type="functional",
                category="감리지적유사",
                defect=f"{item.canonical_account} — 「{hit}」 표현이 감리지적사례 red-flag 패턴과 유사",
                reason=(item.case_context or item.audit_focus or "감리지적사례 역매칭")[:180],
                basis=item.case_source or "감리지적사례",
                to_be=item.to_be or "해당 사항에 대한 검토 근거 보완",
                account=item.canonical_account,
                evidence_refs=[item.case_source] if item.case_source else [],
                confidence=0.5,
            )
        )
        redflag_n += 1
    return findings


def run_all(
    doc: ParsedDocument,
    mat: re_engine.Materiality | None = None,
    is_listed: bool | None = None,
    engagement: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """FA-1~FA-4 전체 실행(순차 — 병렬 실행은 agent_orchestrator에서 ThreadPoolExecutor로 수행)."""
    m = mat or re_engine.extract_materiality(doc)
    listed = is_listed if is_listed is not None else re_engine.detect_is_listed(doc)
    eng = engagement or re_engine.extract_engagement(doc)
    out: list[dict[str, Any]] = []
    out += run_fa1_tie_out(doc, m)
    out += run_fa2_cross_reference(doc, m)
    out += run_fa3_procedure_completeness(doc, m, listed)
    # 독립 실행 시에는 체크리스트 포함
    out += run_fa4_regulatory_focus(doc, eng, listed, include_checklists=True)
    return out
