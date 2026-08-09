"""4대 중점 회계이슈 — 4단계 게이트 기반 자가진단 엔진.

「4대중점_심층검토_보완지침_2026-08-09.md」의 실행 코드.

기존 `fss_focus.run_focus_review()`의 구조적 한계
------------------------------------------------
1. **이슈 수준 조서 누락을 탐지하지 못함** — `_matched_sheets_for_item()`이 빈
   목록을 반환하면 `continue`로 침묵한다. 즉 투자부동산 조서를 아예 작성하지
   않으면 4대중점 검토에서 아무 지적도 나오지 않는다. 대표님이 지적하신
   "누락된 항목이 있는지"를 구조적으로 확인할 수 없는 상태였다.
2. **판정이 2단계뿐** — `검토누락`/`결론미비`만 있어 "절차는 있으나 정량근거가
   없다(미흡)"와 "결론이 증거와 배치된다(부적정)"를 구분하지 못한다.
3. **키워드 1~2개로 충족 판정** — `required_evidence`가 성기어, 조서에 해당
   단어가 스치듯 등장하면 통과된다.
4. **절차의 깊이를 보지 않음** — 재계산·표본·대사 등 정량근거 유무를 평가하지
   않아 "검토하였음. 이상없음" 한 줄로도 충족 처리된다.

이 모듈의 해법
-------------
- `focus_procedure_steps`의 220개 원자 절차단계를 4단계 게이트(G1~G4)로 평가
- 이슈 수준 커버리지 점검을 **먼저** 수행하여 조서 자체의 부재를 적발
- 판정을 4단계(적합/보완필요/미비/해당없음)로 세분
- 리뷰노트를 「①리뷰사항 ②리뷰근거 ③감리지적사례」 3칸 규격(작업지시서 §0.0)에
  맞추어 생성
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import focus_procedure_steps as fps
import review_engine as re_engine
from parser import ParsedDocument

try:
    import fss_focus as ff
except ImportError:  # pragma: no cover
    ff = None  # type: ignore[assignment]

try:
    import sheet_code_registry as scr
except ImportError:  # pragma: no cover
    scr = None  # type: ignore[assignment]


VERDICT_OK = fps.VERDICT_OK          # 적합
VERDICT_WEAK = fps.VERDICT_WEAK      # 보완필요
VERDICT_GAP = fps.VERDICT_GAP        # 미비
VERDICT_NA = fps.VERDICT_NA          # 해당없음

# 판정 → 리뷰노트 중요도
_VERDICT_IMPORTANCE = {
    VERDICT_GAP: "상",
    VERDICT_WEAK: "중",
    VERDICT_OK: "하",
    VERDICT_NA: "하",
}

# 리뷰사항 본문 길이 상한(작업지시서 §0.0 — 220자 이내)
_REASON_MAX = 220


@dataclass
class StepResult:
    """절차 단계 1건의 진단 결과."""

    step: fps.ProcedureStep
    verdict: str
    sheet_no: str = ""
    sheet_title: str = ""
    matched_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    hit_red_flags: tuple[str, ...] = ()
    has_quant: bool = False
    note: str = ""

    @property
    def failed(self) -> bool:
        return self.verdict in (VERDICT_GAP, VERDICT_WEAK)


@dataclass
class IssueGap:
    """이슈 수준 조서 커버리지 결손."""

    coverage: fps.IssueCoverage
    present_codes: tuple[str, ...] = ()


@dataclass
class SelfCheckResult:
    is_listed: bool = True
    issue_gaps: list[IssueGap] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        counts = {VERDICT_OK: 0, VERDICT_WEAK: 0, VERDICT_GAP: 0, VERDICT_NA: 0}
        for r in self.step_results:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        counts["이슈조서누락"] = len(self.issue_gaps)
        return counts


# ---------------------------------------------------------------------------
# 텍스트 평가 유틸
# ---------------------------------------------------------------------------
def _hits(text_low: str, keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if k and k.lower() in text_low]


def _has_quant_evidence(text_low: str) -> bool:
    """정량근거(재계산·표본·대사 등) 마커 존재 여부."""
    return bool(_hits(text_low, fps.COMMON_DEPTH_KEYS))


def _is_boilerplate_conclusion(text_low: str) -> bool:
    """결론이 상투문구뿐인지 — 위험문구는 있는데 정량근거가 없는 경우."""
    return bool(_hits(text_low, fps.COMMON_RED_FLAGS)) and not _has_quant_evidence(text_low)


def evaluate_step(step: fps.ProcedureStep, text: str) -> StepResult:
    """단일 절차단계를 4단계 게이트 규칙으로 평가."""
    low = (text or "").lower()
    ev_hit = _hits(low, step.evidence_keys)
    ev_missing = tuple(k for k in step.evidence_keys if k not in ev_hit)
    has_ev = bool(ev_hit) if step.evidence_keys else True
    red_hit = tuple(_hits(low, step.red_flags))
    has_quant = _has_quant_evidence(low)

    gate = step.gate
    if gate == "G1":
        verdict = VERDICT_OK if has_ev else VERDICT_GAP
    elif gate == "G2":
        if not has_ev:
            verdict = VERDICT_GAP
        elif red_hit:
            verdict = VERDICT_WEAK
        else:
            verdict = VERDICT_OK
    elif gate == "G3":
        if not has_ev:
            verdict = VERDICT_GAP
        elif red_hit:
            # 감리지적 유형과 동일한 위험문구가 실제로 확인됨 → 미비
            verdict = VERDICT_GAP
        else:
            dep_hit = _hits(low, step.depth_keys) if step.depth_keys else []
            verdict = VERDICT_OK if dep_hit else VERDICT_WEAK
    else:  # G4 결론 적정성
        if red_hit:
            verdict = VERDICT_GAP
        elif not has_ev:
            verdict = VERDICT_WEAK
        elif _is_boilerplate_conclusion(low):
            verdict = VERDICT_WEAK
        else:
            verdict = VERDICT_OK

    return StepResult(
        step=step,
        verdict=verdict,
        matched_evidence=tuple(ev_hit),
        missing_evidence=ev_missing,
        hit_red_flags=red_hit,
        has_quant=has_quant,
    )


# ---------------------------------------------------------------------------
# 게이트 계층 억제(gate cascade suppression)
# ---------------------------------------------------------------------------
def select_reportable(results: list[StepResult]) -> list[StepResult]:
    """한 체크항목의 단계 결과 중 **리뷰노트로 발행할 것**만 선별.

    원칙: 상위 게이트가 무너지면 하위 게이트의 결손은 그 결과일 뿐이므로
    근본원인 1건만 발행한다. G1(절차 자체 부재)이 무너진 상태에서
    "증빙부족·절차미흡·결론부적정"을 함께 발행하면 리뷰노트가 중복·비대해져
    회계사가 실제 지적사항을 식별하기 어려워진다.

    - G1 미비  → G1만 발행 (근본원인: 절차 누락)
    - G2 미비  → G2 발행, 하위 억제
    - 그 외    → 남은 G3·G4 결손을 각각 발행
    - 예외: G3에서 **감리지적 위험문구가 실제로 적중**한 경우는 독립된 실질
      지적사항이므로 억제 대상에서 제외하고 항상 발행한다.
    """
    by_gate: dict[str, list[StepResult]] = {}
    for r in results:
        by_gate.setdefault(r.step.gate, []).append(r)

    substantive = [
        r for r in results
        if r.step.gate == "G3" and r.hit_red_flags and r.verdict == VERDICT_GAP
    ]

    out: list[StepResult] = []
    for gate in fps.GATE_ORDER:
        failed = [r for r in by_gate.get(gate, []) if r.failed]
        if not failed:
            continue
        if gate in ("G1", "G2"):
            root = [r for r in failed if r.verdict == VERDICT_GAP] or failed
            out.append(root[0])
            break
        out.extend(failed)

    for r in substantive:
        if r not in out:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# 이슈 수준 커버리지 점검 — 조서 자체의 부재를 적발
# ---------------------------------------------------------------------------
def _document_sheet_codes(doc: ParsedDocument) -> tuple[str, ...]:
    codes: list[str] = []
    seen: set[str] = set()
    for t in doc.tables:
        source = str(t.attrs.get("source", "")).strip()
        code = ""
        if ff is not None:
            try:
                code = ff._sheet_index_from_source(source)
            except Exception:  # noqa: BLE001
                code = ""
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return tuple(codes)


def _document_accounts(doc: ParsedDocument) -> tuple[str, ...]:
    accounts: list[str] = []
    seen: set[str] = set()
    for t in doc.tables:
        try:
            acct = re_engine.table_account(t)
        except Exception:  # noqa: BLE001
            acct = ""
        if acct and acct not in seen:
            seen.add(acct)
            accounts.append(acct)
    return tuple(accounts)


def _one_code_matches(code: str, req: str) -> bool:
    """조서코드 1건이 필수코드에 해당하는지.

    주의: 접두 매칭은 '알파벳 접두가 같고 나머지가 숫자'인 경우로 한정한다
    (E100 ← E 는 허용, C ← CL 은 불허). 초기 구현에서 역방향 접두 매칭
    (`req.startswith(base)`)을 허용해 매출채권(C) 조서가 우발부채(CL) 필수조서를
    충족한 것으로 오판정되어, 충당부채·우발부채 조서 누락이 은폐된 결함이 있었다.
    """
    if not code or not req:
        return False
    if code == req:
        return True
    base = code
    if scr is not None:
        try:
            base = scr.parse_sheet_code(code) or code
        except Exception:  # noqa: BLE001
            base = code
    if base == req:
        return True
    for cand in (code, base):
        if cand.startswith(req) and cand[len(req):].isdigit():
            return True
    return False


def _code_matches(present: tuple[str, ...], required: tuple[str, ...]) -> bool:
    return any(_one_code_matches(c, r) for c in present for r in required)


def check_issue_coverage(doc: ParsedDocument, is_listed: bool) -> list[IssueGap]:
    """중점이슈별 필수 조서의 존재 여부 점검.

    기존 파이프라인이 침묵하던 '조서 자체 누락'을 여기서 적발한다.
    """
    present_codes = _document_sheet_codes(doc)
    present_accounts = _document_accounts(doc)
    gaps: list[IssueGap] = []
    for cov in fps.coverage_for(is_listed):
        if _code_matches(present_codes, cov.required_sheet_codes):
            continue
        if cov.trigger_accounts and set(cov.trigger_accounts) & set(present_accounts):
            continue
        gaps.append(IssueGap(coverage=cov, present_codes=present_codes))
    return gaps


# ---------------------------------------------------------------------------
# 리뷰노트 생성 (작업지시서 §0.0 — 3칸 규격)
# ---------------------------------------------------------------------------
def _clip(text: str, limit: int = _REASON_MAX) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _case_block(step: fps.ProcedureStep, item: Any, src_label: str) -> list[dict[str, str]]:
    """⚖️ 감리지적사례 블록 — 지적유형이 유사한 사례만, '왜 지적됐는지' 포함."""
    blocks: list[dict[str, str]] = []
    case_ex = str(getattr(item, "case_example", "") or "").strip()
    case_src = str(getattr(item, "case_source", "") or "").strip()
    vtype = str(getattr(item, "violation_type", "") or "").strip()
    if step.case_ref and case_ex:
        blocks.append({
            "case_id": step.case_ref,
            "violation_type": vtype,
            "source": case_src or f"{src_label} 2026년 중점심사 사전예고",
            "why": _clip(case_ex, 160),
        })
    extra = str(getattr(item, "additional_case_refs", "") or "").strip()
    if extra:
        for chunk in extra.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            blocks.append({
                "case_id": chunk.split("(")[0].strip(),
                "violation_type": vtype,
                "source": "감리지적사례(FSS·KICPA)",
                "why": _clip(chunk, 140),
            })
            if len(blocks) >= 3:
                break
    return blocks


def _step_note(
    result: StepResult,
    *,
    issue_no: int,
    issue_title: str,
    item: Any,
    is_listed: bool,
) -> dict[str, Any]:
    step = result.step
    src_label = "금융감독원" if is_listed else "한국공인회계사회"
    gate_name = step.gate_name
    ftype = step.failure_type if result.verdict == VERDICT_GAP else f"{step.failure_type}(경미)"

    defect = (
        f"[4대중점·{step.failure_type}] {issue_no}. {issue_title} — "
        f"{getattr(item, 'name', '') or getattr(item, 'checklist_item', '')} "
        f"／{step.title} ({step.step_id})"
    )

    reason_bits = [step.review_note]
    if result.hit_red_flags:
        reason_bits.append(f"조서에서 위험문구({', '.join(result.hit_red_flags[:2])})가 확인됩니다.")
    elif result.missing_evidence and result.verdict == VERDICT_GAP:
        reason_bits.append(f"확인되지 않은 키워드: {', '.join(result.missing_evidence[:4])}.")
    elif result.verdict == VERDICT_WEAK and step.gate == "G3":
        reason_bits.append("정량근거(재계산·표본·대사 내역)가 확인되지 않습니다.")
    reason = _clip(" ".join(reason_bits))

    basis = str(getattr(item, "basis", "") or "").strip()
    if not basis:
        basis = f"{src_label} 2026년 중점심사 회계이슈 사전예고"
    std = str(getattr(item, "standard_paragraphs", "") or "").strip()
    if std:
        basis = f"{basis} — {_clip(std, 90)}"

    to_be = str(getattr(item, "to_be_if_missing", "") or "").strip()
    if result.verdict == VERDICT_WEAK:
        to_be = str(getattr(item, "to_be_if_weak", "") or "").strip() or to_be
    to_be = to_be or step.review_note
    if not to_be.startswith("다음"):
        to_be = f"다음 내용으로 보완 바랍니다: {to_be}"

    note: dict[str, Any] = {
        "id": "",
        "importance": _VERDICT_IMPORTANCE.get(result.verdict, "중"),
        "category": "중점감리",
        "defect": defect,
        "reason": reason,
        "basis": basis,
        "to_be": to_be,
        "sheet_no": result.sheet_no or "-",
        "sheet_title": result.sheet_title,
        "sheet": (
            f"{result.sheet_no} ({result.sheet_title})"
            if result.sheet_no and result.sheet_title
            else result.sheet_no or "-"
        ),
        "location": "",
        "summary": "",
        "workpaper_ref": result.sheet_no or "-",
        "is_focus_related": True,
        "focus_protected": True,
        "focus_issue_no": issue_no,
        "focus_issue_title": issue_title,
        "focus_checklist_id": step.checklist_id,
        "focus_step_id": step.step_id,
        "focus_gate": step.gate,
        "focus_gate_name": gate_name,
        "focus_verdict": result.verdict,
        "focus_violation_type": str(getattr(item, "violation_type", "") or ""),
        "review_gap_type": ftype,
        "source": "rule",
        "is_listed": is_listed,
        "enforcement_cases": _case_block(step, item, src_label),
    }
    return note


def _issue_gap_note(gap: IssueGap) -> dict[str, Any]:
    cov = gap.coverage
    src_label = "금융감독원" if cov.is_listed else "한국공인회계사회"
    codes = ", ".join(cov.required_sheet_codes)
    return {
        "id": "",
        "importance": "상",
        "category": "중점감리",
        "defect": (
            f"[4대중점·조서누락] {cov.issue_no}. {cov.issue_title} — "
            f"필수 조서({codes}) 미확인 (COV-{'L' if cov.is_listed else 'U'}{cov.issue_no})"
        ),
        "reason": _clip(cov.absence_note),
        "basis": f"{src_label} 2026년 중점심사 회계이슈 사전예고 — 제{cov.issue_no}항 {cov.issue_title}",
        "to_be": (
            f"다음 내용으로 보완 바랍니다: {cov.issue_title} 관련 조서({codes})를 작성하시거나, "
            f"해당 사항이 없는 경우 '{cov.trigger_hint}'에 해당하지 않음을 확인한 근거를 "
            f"조서에 명시하여 주시기 바랍니다."
        ),
        "sheet_no": "-",
        "sheet_title": cov.issue_title,
        "sheet": f"- ({cov.issue_title})",
        "location": "",
        "summary": "",
        "workpaper_ref": "-",
        "is_focus_related": True,
        "focus_protected": True,
        "focus_issue_no": cov.issue_no,
        "focus_issue_title": cov.issue_title,
        "focus_checklist_id": f"COV-{'L' if cov.is_listed else 'U'}{cov.issue_no}",
        "focus_step_id": f"COV-{'L' if cov.is_listed else 'U'}{cov.issue_no}",
        "focus_gate": "G0",
        "focus_gate_name": "조서 커버리지",
        "focus_verdict": VERDICT_GAP,
        "review_gap_type": "조서누락",
        "source": "rule",
        "is_listed": cov.is_listed,
        "enforcement_cases": [],
    }


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------
def run_selfcheck(
    doc: ParsedDocument,
    engagement: dict[str, Any] | None = None,
    *,
    is_listed: bool | None = None,
    include_ok: bool = False,
) -> SelfCheckResult:
    """4대중점 자가진단 실행.

    Parameters
    ----------
    include_ok:
        True이면 적합(OK) 판정 단계도 `step_results`에 포함(리뷰노트 xlsx 출력용).
    """
    engagement = engagement or {}
    listed = is_listed if is_listed is not None else bool(engagement.get("is_listed"))
    result = SelfCheckResult(is_listed=listed)

    # ── 1단계: 이슈 수준 조서 커버리지 ──────────────────────────────
    result.issue_gaps = check_issue_coverage(doc, listed)
    for gap in result.issue_gaps:
        result.notes.append(_issue_gap_note(gap))

    if ff is None:
        return result

    # ── 2단계: 체크항목·절차단계 수준 진단 ──────────────────────────
    year_s = str(engagement.get("audit_year", "")).strip()
    year = int(year_s) if year_s.isdigit() else 2026
    issues = ff.load_current_focus_issues(year, listed)
    checklist_map: dict[int, list] = {}
    try:
        import guidelines_loader as gl

        gl.load_focus_issues_from_db.cache_clear()
        enhanced = gl.load_focus_issues_from_db(listed)
        if enhanced:
            issues = [
                ff.FocusIssue(e.issue_no, e.title, e.related_accounts, e.sheet_keywords, list(e.checklist))
                for e in enhanced
            ]
            checklist_map = {e.issue_no: list(e.checklist) for e in enhanced}
    except Exception:  # noqa: BLE001
        pass

    gap_issue_nos = {g.coverage.issue_no for g in result.issue_gaps}

    for issue in issues:
        if issue.issue_no in gap_issue_nos:
            # 조서 자체가 없으면 단계별 진단은 무의미 — 커버리지 지적으로 갈음
            continue
        items = checklist_map.get(issue.issue_no) or issue.checklist
        for item in items:
            cid = str(getattr(item, "checklist_id", "") or "").strip()
            steps = fps.steps_for(cid)
            if not steps:
                continue
            matched = ff._matched_sheets_for_item(doc, issue, item)
            if not matched:
                for step in steps:
                    result.step_results.append(
                        StepResult(step=step, verdict=VERDICT_NA, note="관련 조서 미매칭")
                    )
                continue
            body = "\n".join(s[2] for s in matched)
            sheet_no = ff._display_sheet_codes(matched) or matched[0][0]
            sheet_title = matched[0][1] or issue.title

            evaluated: list[StepResult] = []
            for step in steps:
                r = evaluate_step(step, body)
                r.sheet_no = sheet_no
                r.sheet_title = sheet_title
                evaluated.append(r)
                result.step_results.append(r)

            for r in select_reportable(evaluated):
                result.notes.append(
                    _step_note(
                        r,
                        issue_no=issue.issue_no,
                        issue_title=issue.title,
                        item=item,
                        is_listed=listed,
                    )
                )
    if not include_ok:
        pass  # step_results는 전량 보존(요약·xlsx용), notes만 결손 기준으로 생성
    return result


def run_focus_selfcheck_notes(
    doc: ParsedDocument,
    engagement: dict[str, Any] | None = None,
    *,
    is_listed: bool | None = None,
) -> list[dict[str, Any]]:
    """기존 파이프라인 호환 — 리뷰노트 dict 목록만 반환."""
    return run_selfcheck(doc, engagement, is_listed=is_listed).notes


if __name__ == "__main__":  # pragma: no cover
    print("4대중점 자가진단 엔진")
    print(f"  등록 절차단계: {fps.step_count()}개 (상장 {fps.step_count(True)} / 비상장 {fps.step_count(False)})")
    print(f"  이슈 커버리지: 상장 {len(fps.coverage_for(True))}건 / 비상장 {len(fps.coverage_for(False))}건")
