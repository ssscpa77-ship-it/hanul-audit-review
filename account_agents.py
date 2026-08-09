"""멀티에이전트 아키텍처 — 계정별 전문 에이전트 (Account Specialist Agents, AA-01~14).

「멀티에이전트_아키텍처_설계안_2026-08-09.md」§4.3, 「에이전트_명세서_2026-08-09.md」§3 참조.

각 계정 에이전트는 FA-3(절차완전성)과 달리 "그 계정만 아는 사람"의 시각에서, 카탈로그
Pass/Fail로는 잡히지 않는 계정 고유의 판단 함정(예: 재고자산의 저가법 vs 진부화 구분,
현금의 제한예금 오분류)을 규칙 기반으로 짚어낸다. Phase 1에서는 AA-01(현금및예금)·
AA-03(재고자산)을 완전 구현하고, 나머지 계정은 카탈로그 기반 공통 로직(_generic_risk_scan)
으로 동작한다 — 계정 실무진의 리스크 키워드 보강(§4.3 카탈로그 갱신)에 따라 자연히
고도화된다.
"""

from __future__ import annotations

from typing import Any, Callable

import guidelines_loader as gl
import review_engine as re_engine
from agent_schema import make_finding
from parser import ParsedDocument

# 계정과목 → 에이전트 ID (설계안 §4.3 카탈로그와 일치)
ACCOUNT_AGENT_IDS: dict[str, str] = {
    "현금및예금": "AA-01",
    "매출채권": "AA-02",
    "재고자산": "AA-03",
    "유형자산": "AA-04",
    "무형자산": "AA-05",
    "투자자산": "AA-06",
    "차입금": "AA-07",
    "충당부채": "AA-08",
    "우발부채": "AA-08",
    "매출": "AA-09",
    "법인세": "AA-10",
    "자본": "AA-11",
    "특수관계자": "AA-12",
    "리스": "AA-13",
    "계속기업": "AA-14",
}


def _sheet_text_for_account(doc: ParsedDocument, account: str) -> tuple[str, str]:
    """해당 계정의 조서 텍스트와 대표 sheet_no를 반환."""
    stext = re_engine.account_sheet_text(doc, account)
    sheet_no = ""
    for t in doc.tables:
        if re_engine.table_account(t) != account:
            continue
        sheet_no = str(t.attrs.get("source", "")).strip()
        break
    return stext, sheet_no


# --------------------------------------------------------------------------
# AA-01. 현금및예금 — 특이 함정: 제한예금 오분류, tick·Ref만 있고 조회서 미첨부
# --------------------------------------------------------------------------
def _aa01_cash(doc: ParsedDocument, stext: str, sheet_no: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    has_restriction_kw = any(k in stext for k in ("사용제한", "담보제공", "질권", "제한예금"))
    disclosed_in_note = any(k in stext for k in ("주석", "공시"))
    if has_restriction_kw and not disclosed_in_note:
        findings.append(
            make_finding(
                agent_id="AA-01",
                agent_type="account",
                category="절차누락",
                defect="현금및예금 — 사용제한(담보제공 등) 예금이 언급되나 주석 공시·유동/비유동 재분류 근거가 확인되지 않음",
                reason="제한예금은 별도 분류 및 주석 공시가 필요합니다(§0.8 tick·Ref 인정 기준과 별개 판단).",
                basis="K-IFRS1001 §54~55(현금및현금성자산의 사용제한 공시)",
                to_be="제한예금 분류·주석 공시 근거 보완",
                account="현금및예금",
                sheet_no=sheet_no,
                evidence_refs=["K-IFRS1001 §54~55"],
                confidence=0.65,
            )
        )
    has_confirm_word = "조회" in stext
    has_actual_letter = any(k in stext for k in ("조회서", "회신", "confirmation"))
    if has_confirm_word and not has_actual_letter:
        findings.append(
            make_finding(
                agent_id="AA-01",
                agent_type="account",
                category="절차누락",
                defect="현금및예금 — 외부조회 절차 언급은 있으나 조회서 첨부·회신 근거가 조서에서 확인되지 않음(tick·Ref만 존재 가능성)",
                reason="tick·Ref만 있고 실제 조회서가 첨부되지 않은 경우 '외부조회 완료'로 인정하지 않습니다(§0.8).",
                basis="KSA505(외부조회)",
                to_be="금융기관 조회서 원본·회신 근거 첨부",
                account="현금및예금",
                sheet_no=sheet_no,
                evidence_refs=["KSA505"],
                confidence=0.55,
            )
        )
    return findings


# --------------------------------------------------------------------------
# AA-03. 재고자산 — 특이 함정: 저가법 서술만 있고 NRV 계산 근거 부재, 저가법≠진부화
# --------------------------------------------------------------------------
def _aa03_inventory(doc: ParsedDocument, stext: str, sheet_no: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    mentions_low_cost = "저가법" in stext
    has_nrv_calc = any(k in stext for k in ("순실현가능가치", "NRV", "처분비용"))
    if mentions_low_cost and not has_nrv_calc:
        findings.append(
            make_finding(
                agent_id="AA-03",
                agent_type="account",
                category="절차누락",
                defect="재고자산 — '저가법 검토' 서술은 있으나 품목별 순실현가능가치(NRV) 계산 근거(단가·처분비용 추정)가 확인되지 않음",
                reason="서술의 존재가 곧 절차 완료를 의미하지 않습니다. NRV 계산표가 있어야 저가법 판단을 인정합니다.",
                basis="K-IFRS1002 §28~33",
                to_be="품목별 NRV 계산표(단가·수량·처분비용 추정) 작성 근거 보완",
                account="재고자산",
                sheet_no=sheet_no,
                evidence_refs=["K-IFRS1002 §28~33"],
                confidence=0.7,
            )
        )
    mentions_obsolete = any(k in stext for k in ("진부화", "장기재고", "재고연령"))
    if mentions_low_cost and not mentions_obsolete:
        findings.append(
            make_finding(
                agent_id="AA-03",
                agent_type="account",
                category="절차누락",
                defect="재고자산 — 저가법(NRV)만 검토되고 진부화·장기재고(재고 연령) 별도 판단이 확인되지 않음",
                reason="저가법과 진부화는 별개 판단입니다. 저가법만 검토하고 진부화를 누락하면 4대중점 재고 이슈(L2/U2)에 해당할 수 있습니다.",
                basis="4대중점 재고 저가법·진부화(L2/U2)",
                to_be="재고 연령분석 및 진부화 평가감 근거 추가 검토",
                account="재고자산",
                sheet_no=sheet_no,
                evidence_refs=["4대중점 재고 이슈"],
                confidence=0.6,
            )
        )
    return findings


_SPECIALIZED: dict[str, Callable[[ParsedDocument, str, str], list[dict[str, Any]]]] = {
    "현금및예금": _aa01_cash,
    "재고자산": _aa03_inventory,
}


# --------------------------------------------------------------------------
# 공통(제네릭) 계정 에이전트 — 카탈로그의 required_evidence 중 아직 FA-3에서
# 다루지 않은 "계정 고유 함정" 성격 항목(§4.3 특이 리스크)을 보강 스캔.
# 실무 카탈로그가 채워질수록 자동으로 정교해진다.
# --------------------------------------------------------------------------
def _generic_risk_scan(account: str, agent_id: str, stext: str, sheet_no: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    catalog = gl.load_procedure_catalog_from_db() or {}
    items = catalog.get(account, [])
    for item in items:
        if not item.procedure_gap:  # fail_if 문구
            continue
        # fail_if 조건이 "~없이", "~만" 등 결함 서술이면서, 트리거 상황(주요 키워드)만
        # 관측되고 대응 대응 조치(required_evidence)가 부분적으로만 있는 경우를
        # 계정 전문가 관점에서 한 번 더 경고 — FA-3의 엄격한 Pass/Fail과 별개로
        # "부분 충족" 케이스를 놓치지 않기 위한 보조 레이어.
        if item.detect_any and any(k in stext for k in item.detect_any):
            if item.required_evidence and not all(k in stext for k in item.required_evidence):
                findings.append(
                    make_finding(
                        agent_id=agent_id,
                        agent_type="account",
                        category="절차누락",
                        defect=f"{account} 전문가 관점 — {item.name}({item.checklist_id}) 관련 증빙이 일부만 확인됨",
                        reason=f"실무상 자주 놓치는 함정: {item.procedure_gap}",
                        basis=item.basis or "계정별 필수절차 카탈로그",
                        to_be=item.to_be or "관련 증빙 보완",
                        account=account,
                        sheet_no=sheet_no,
                        evidence_refs=[item.basis] if item.basis else [],
                        confidence=0.5,
                    )
                )
    return findings


def run_account_agent(account: str, doc: ParsedDocument) -> list[dict[str, Any]]:
    """지정 계정의 전문 에이전트를 실행."""
    agent_id = ACCOUNT_AGENT_IDS.get(account)
    if not agent_id:
        return []
    stext, sheet_no = _sheet_text_for_account(doc, account)
    if not stext:
        return []
    specialized = _SPECIALIZED.get(account)
    findings = specialized(doc, stext, sheet_no) if specialized else []
    # 전문화 에이전트가 있으면 카탈로그 부분충족 스캔은 생략(FA-3와 중복·노이즈)
    if specialized is None:
        findings += _generic_risk_scan(account, agent_id, stext, sheet_no)
    return findings


def run_all(doc: ParsedDocument) -> list[dict[str, Any]]:
    """조서에 실제로 존재하는 계정에 대해서만 계정 에이전트 실행(§0.1 원칙)."""
    accounts = set(re_engine.document_accounts(doc)) & set(ACCOUNT_AGENT_IDS)
    out: list[dict[str, Any]] = []
    for account in accounts:
        out += run_account_agent(account, doc)
    return out
