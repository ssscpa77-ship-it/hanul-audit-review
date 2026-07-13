"""Hanul DB 감리지적사례 학습 — 계정·조서인덱스별 분류·키워드 요약.

금융감독원·한국공인회계사회 감리지적사례(FTS 색인)를 읽어
FY2026 4000 계정별 실증절차 조서 인덱스에 매핑한다.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import knowledge_base as kb
import review_engine as re_engine
import sheet_code_registry as scr

_CASE_FILE_RE = re.compile(
    r"^(?:FSS|KICPA)[\w\-]+|"
    r"FSS\d{4}[-_]\d+|KICPA-\d{4}-\d+",
    re.I,
)
_VIOLATION_RE = re.compile(
    r"(과대계상|과소계상|미인식|미기재|누락|허위|오분류|오류|부적절|"
    r"조회\s?미|실사\s?미|평가\s?미|인식\s?오|계상\s?오|공시\s?미|"
    r"충당금?\s?미|손상차손\s?미|Cut.?off|컷오프|기간귀속)",
    re.I,
)
_AUDIT_FOCUS: dict[str, str] = {
    "과대계상": "거래·잔액 실재성, 조회서·계약·전기 대사, 수익·자산 인식 근거·증빙 문서화",
    "과소계상": "평가·충당·손상 산정 근거, 회수가능액·NRV·ECL 산출 과정 문서화",
    "미인식": "손상징후·평가손실·충당 인식 시점·금액·가정 문서화",
    "미기재": "주석·공시·조서 상호참조·필수 기재항목 누락 여부",
    "누락": "표준 감사절차(조회·실사·분석·대사) 수행·결론 기재",
    "허위": "거래 실질·증빙 적정성, 관련자 거래·특수관계 확인",
    "오분류": "계정과목·공정가치·수익·비용 분류 판단 근거",
    "오류": "계산·합계·대사·회계처리 재검토",
    "부적절": "회계추정·가정·판단의 타당성·민감도 분석",
    "조회": "외부조회 발송·회신·차이 조정·후속절차",
    "실사": "실사입회·현장확인·차이 조정 문서화",
    "평가": "평가모형·입력값·전문가 보고서 검토",
    "인식": "인식시점·Cut-off·계약 조건 검토",
    "공시": "주석·공시 완전성·정확성·교차 대사",
    "충당": "충당부채·ECL 산정 가정·근거·변동 분석",
    "손상": "CGU 식별·회수가능액·손상차손 인식",
    "컷오프": "기말 전후 거래 표본·인식 시점 검토",
}
_PROCEDURE_GAP: dict[str, str] = {
    "과대계상": "잔액·수익 과대계상 방지 실증절차(조회·대사·증빙) 미흡",
    "과소계상": "잔액·비용 과소계상 방지 평가·충당 절차 미흡",
    "미인식": "손상·평가손실·충당 인식 절차·문서화 미흡",
    "미기재": "주석·공시·조서 기재 누락",
    "누락": "필수 감사절차·검토 누락",
    "허위": "거래 실질·증빙 검증 절차 미흡",
    "오분류": "계정분류·공정가치·모형 판단 검토 미흡",
    "오류": "계산·대사·회계처리 검토 미흡",
    "부적절": "회계추정·가정·결론 문서화 미흡",
    "조회": "외부조회(은행·채권·법률) 절차 미흡",
    "실사": "실사입회·현장확인 절차 미흡",
    "평가": "평가·공정가치·NRV 산정 절차 미흡",
    "인식": "인식시점·Cut-off 검토 미흡",
    "공시": "주석·공시 검토 미흡",
    "충당": "충당부채·ECL 산정·근거 문서화 미흡",
    "손상": "손상검토·CGU 식별 절차 미흡",
    "컷오프": "기간귀속(Cut-off) 검토 미흡",
}
_STOP = frozenset(
    {"관련", "내용", "경우", "대한", "위한", "따라", "회계처리", "지적", "사례", "감리"}
)


@dataclass
class LearnedCase:
    number: str
    title: str
    source: str  # 금융감독원 | 한공회
    path: str
    account: str
    violation_type: str
    procedure_gap: str
    keywords: tuple[str, ...] = ()
    snippet: str = ""
    situation: str = ""  # 사례 맥락·지적 상황 요약
    audit_focus: str = ""  # 감사인 점검 포인트


@dataclass
class AccountKeywordSummary:
    account: str
    sheet_code: str
    sheet_label: str
    case_count: int
    violation_types: tuple[str, ...]
    key_keywords: tuple[str, ...]
    case_numbers: tuple[str, ...] = ()
    case_narratives: str = ""  # 계정별 대표 사례 맥락


@dataclass
class EnforcementCheckRow:
    sheet_code: str
    sheet_label: str
    canonical_account: str
    checklist_id: str
    checklist_item: str
    violation_type: str
    procedure_gap: str
    case_source: str
    case_numbers: str
    case_examples: str
    key_keywords: str
    detect_any: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    acceptable_phrases: tuple[str, ...] = ()
    red_flag_phrases: tuple[str, ...] = ()
    review_procedure: str = ""
    to_be: str = ""
    case_count: int = 0
    review_gap_type: str = "검토누락"
    case_context: str = ""  # 유형별 통합 맥락·지적 배경
    audit_focus: str = ""  # 조서에서 확인할 구체 항목


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(kb.STORE_PATH)


def _source_label(category: str) -> str:
    if "공인회계사" in category:
        return "한국공인회계사회"
    return "금융감독원"


def _extract_case_number(title: str, path: str) -> str:
    m = kb._CASE_NO_RE.search(title) or kb._CASE_NO_RE.search(path)
    if m:
        return m.group(0).replace(" ", "")
    m2 = _CASE_FILE_RE.search(title)
    return m2.group(0) if m2 else title[:24]


def _classify_account(text: str) -> str | None:
    return re_engine._primary_account("", text)


def _violation_type(text: str) -> str:
    m = _VIOLATION_RE.search(text)
    if not m:
        return "회계처리 오류"
    raw = m.group(1).replace(" ", "")
    for key in _PROCEDURE_GAP:
        if key in raw:
            return raw if len(raw) <= 12 else key
    return raw[:12]


def _procedure_gap(vtype: str, account: str) -> str:
    for key, gap in _PROCEDURE_GAP.items():
        if key in vtype:
            return gap
    return f"「{account}」 관련 실증절차·검토 문서화 미흡"


def _audit_focus(vtype: str, account: str) -> str:
    for key, focus in _AUDIT_FOCUS.items():
        if key in vtype:
            return f"「{account}」 {focus}"
    return f"「{account}」 지적 유형({vtype}) 관련 실증절차·결론·근거 문서화"


def _load_case_body(con: sqlite3.Connection, path: str, *, max_chars: int = 1200) -> str:
    """사례 문서 본문 — 다중 청크 결합."""
    rows = con.execute(
        "SELECT chunk_text FROM chunks WHERE path=? ORDER BY rowid LIMIT 6",
        (path,),
    ).fetchall()
    parts: list[str] = []
    total = 0
    for (txt,) in rows:
        chunk = " ".join(str(txt or "").split())
        if not chunk:
            continue
        if total + len(chunk) > max_chars:
            parts.append(chunk[: max_chars - total])
            break
        parts.append(chunk)
        total += len(chunk)
    return " ".join(parts)


def _extract_situation(
    body: str, title: str, account: str, vtype: str, *, limit: int = 280
) -> str:
    """지적 맥락·상황 1~2문장 요약."""
    hay = f"{title} {body}"
    hay = re.sub(r"\s+", " ", hay).strip()
    # 제목에서 괄호·파일명 제거 후 핵심
    title_clean = re.sub(r"[_\-\.]+\w+$", "", title).strip()
    if len(title_clean) > 20 and _VIOLATION_RE.search(title_clean):
        lead = title_clean[:120]
    else:
        lead = ""

    sentences = re.split(r"(?<=[다음함]\.)\s+|(?<=\.)\s+", hay)
    picked: list[str] = []
    vkey = vtype.replace(" ", "")
    for s in sentences:
        s = s.strip()
        if len(s) < 20 or len(s) > 300:
            continue
        score = 0
        if vkey and vkey in s.replace(" ", ""):
            score += 3
        if account and account in s:
            score += 2
        if re.search(r"지적|위반|미흡|누락|부적절|확인.*않|수행.*않", s):
            score += 2
        if re.search(r"조회|실사|평가|대사|인식|공시|충당|손상", s):
            score += 1
        if score >= 2:
            picked.append(s[:200])
        if len(picked) >= 2:
            break

    if picked:
        out = " ".join(picked)
    elif lead:
        out = lead
    else:
        out = kb._brief(body, limit)

    if account and account not in out:
        out = f"「{account}」 {out}"
    return out[:limit]


def _format_case_example_detail(case: LearnedCase) -> str:
    """리뷰노트용 상세 사례 한 줄."""
    sit = case.situation or kb._brief(case.snippet, 160)
    return (
        f"[{case.number}] {case.source} · {case.violation_type} — "
        f"{sit} → 점검: {case.audit_focus[:80]}"
    )[:320]


def _merge_context(items: list[LearnedCase], *, limit: int = 600) -> str:
    """동일 유형 사례 맥락 통합."""
    parts: list[str] = []
    for it in items[:4]:
        sit = it.situation or kb._brief(it.snippet, 140)
        line = f"({it.number}) {sit}"
        if line not in parts:
            parts.append(line)
    return " ".join(parts)[:limit]


def _extract_keywords(text: str, *, limit: int = 8) -> tuple[str, ...]:
    tokens = [
        t for t in kb._TOKEN_RE.findall(text)
        if len(t) >= 2 and t not in _STOP
    ]
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return tuple(seen[:limit])


def _is_individual_case(title: str) -> bool:
    t = str(title or "").strip()
    if not t or "DB구축" in t or re.match(r"^\d{4}년", t):
        return False
    if _CASE_FILE_RE.search(t) or kb._CASE_NO_RE.search(t):
        return True
    return bool(_VIOLATION_RE.search(t) and len(t) < 120)


def learn_from_kb(*, variant: str = "ifrs_listed") -> list[LearnedCase]:
    """FTS 색인에서 감리지적사례 문서를 학습."""
    if not kb.is_ready():
        return []
    scr.set_mapping_variant(variant == "ifrs_listed")
    con = _connect()
    rows = con.execute(
        "SELECT category, title, path FROM documents "
        "WHERE category IN (?, ?)",
        tuple(kb.ENFORCEMENT_CATEGORIES),
    ).fetchall()
    out: list[LearnedCase] = []
    seen_path: set[str] = set()
    for category, title, path in rows:
        if path in seen_path or not _is_individual_case(title):
            continue
        seen_path.add(path)
        body = _load_case_body(con, path)
        snippet = body[:500]
        hay = f"{title} {body}"
        account = _classify_account(hay)
        if not account:
            continue
        vtype = _violation_type(title)
        pgap = _procedure_gap(vtype, account)
        focus = _audit_focus(vtype, account)
        situation = _extract_situation(body, title, account, vtype)
        out.append(
            LearnedCase(
                number=_extract_case_number(title, path),
                title=title,
                source=_source_label(category),
                path=path,
                account=account,
                violation_type=vtype,
                procedure_gap=pgap,
                keywords=_extract_keywords(hay, limit=10),
                snippet=snippet,
                situation=situation,
                audit_focus=focus,
            )
        )
    return out


def _sheet_meta(code: str, *, variant: str) -> tuple[str, str]:
    labels = scr._load_registry().get("index_labels", {}).get(variant, {})
    label = labels.get(code, code)
    acct = scr.canonical_account(code, variant=variant) or ""
    return label, acct


def build_account_summaries(
    cases: list[LearnedCase], *, variant: str = "ifrs_listed"
) -> list[AccountKeywordSummary]:
    by_acct: dict[str, list[LearnedCase]] = defaultdict(list)
    for c in cases:
        by_acct[c.account].append(c)

    summaries: list[AccountKeywordSummary] = []
    for acct, group in sorted(by_acct.items(), key=lambda x: (-len(x[1]), x[0])):
        code = scr.sheet_code_for_account(acct, variant=variant) or "—"
        label, _ = _sheet_meta(code, variant=variant) if code != "—" else ("", acct)
        vtypes = tuple(dict.fromkeys(c.violation_type for c in group))
        kws: list[str] = []
        for c in group:
            kws.extend(c.keywords)
        kws = list(dict.fromkeys(kws))[:12]
        nums = tuple(dict.fromkeys(c.number for c in group))[:8]
        narratives = " || ".join(
            _format_case_example_detail(c) for c in group[:3]
        )[:900]
        summaries.append(
            AccountKeywordSummary(
                account=acct,
                sheet_code=code,
                sheet_label=label,
                case_count=len(group),
                violation_types=vtypes,
                key_keywords=tuple(kws),
                case_numbers=nums,
                case_narratives=narratives,
            )
        )
    return summaries


def build_checklist_rows(
    cases: list[LearnedCase], *, variant: str = "ifrs_listed"
) -> list[EnforcementCheckRow]:
    """조서 인덱스별 감리지적 체크리스트 행 생성."""
    labels = scr._load_registry().get("index_labels", {}).get(variant, {})
    # sheet_code → cases (via account)
    by_sheet: dict[str, list[LearnedCase]] = defaultdict(list)
    for c in cases:
        code = scr.sheet_code_for_account(c.account, variant=variant)
        if code:
            by_sheet[code].append(c)

    rows: list[EnforcementCheckRow] = []
    for code in sorted(labels.keys(), key=lambda x: (len(x), x)):
        sheet_label, canon = _sheet_meta(code, variant=variant)
        group = by_sheet.get(code, [])
        if not group:
            continue
        # violation_type 별 집계
        by_vtype: dict[str, list[LearnedCase]] = defaultdict(list)
        for c in group:
            by_vtype[c.violation_type].append(c)

        seq = 1
        for vtype, items in sorted(by_vtype.items(), key=lambda x: -len(x[1])):
            kws: list[str] = []
            examples: list[str] = []
            nums: list[str] = []
            sources: set[str] = set()
            for it in items:
                kws.extend(it.keywords)
                sources.add(it.source)
                if it.number not in nums:
                    nums.append(it.number)
                ex = _format_case_example_detail(it)
                if ex not in examples:
                    examples.append(ex)
            kws = list(dict.fromkeys(kws))[:12]
            detect = tuple(kws[:8]) or (canon, vtype)
            req_kw = ("검토", "결론", "근거", "대사", "조회", "확인")
            req = tuple(k for k in req_kw if k not in " ".join(kws))[:4]
            if not req:
                req = ("검토", "문서화", "근거")
            context = _merge_context(items)
            focus = _audit_focus(vtype, canon or items[0].account)
            proc_gap = (
                f"{items[0].procedure_gap}. "
                f"대표 맥락: {kb._brief(context, 200)}"
            )
            item_title = (
                f"{vtype} — {canon or code} 조서 "
                f"({len(items)}건 사례: {', '.join(nums[:3])})"
            )
            review_steps = (
                f"① {canon or code} 조서에서 {vtype} 관련 위험·거래 유형 식별\n"
                f"② 감리사례 {', '.join(nums[:3])}과 유사 절차(조회·대사·평가·문서화) 수행 여부 확인\n"
                f"③ {focus}\n"
                f"④ 미흡 시 결론·근거·후속조치 기재"
            )
            to_be = (
                f"{items[0].procedure_gap} "
                f"감리사례 {nums[0] if nums else ''} 유형과 동일한 흠결이 없도록 "
                f"{focus} 관련 실증절차·검토 결론을 조서에 구체적으로 보완하십시오."
            )
            rows.append(
                EnforcementCheckRow(
                    sheet_code=code,
                    sheet_label=sheet_label,
                    canonical_account=canon or items[0].account,
                    checklist_id=f"{code}-{seq:02d}",
                    checklist_item=item_title,
                    violation_type=vtype,
                    procedure_gap=proc_gap,
                    case_source="; ".join(sorted(sources)),
                    case_numbers="; ".join(nums[:8]),
                    case_examples=" || ".join(examples[:5]),
                    key_keywords="; ".join(kws),
                    detect_any=detect,
                    required_evidence=req,
                    acceptable_phrases=(
                        "검토 완료", "이상 없음", "적정", "인식", "기재",
                        "대사 완료", "조회 회신", "확인",
                    ),
                    red_flag_phrases=(vtype, "미기재", "미확인", "누락", "미수행"),
                    review_procedure=review_steps,
                    to_be=to_be,
                    case_count=len(items),
                    review_gap_type="검토누락",
                    case_context=context,
                    audit_focus=focus,
                )
            )
            seq += 1
    return rows


def learn_and_build(*, variant: str = "ifrs_listed") -> dict[str, Any]:
    cases = learn_from_kb(variant=variant)
    return {
        "cases": cases,
        "summaries": build_account_summaries(cases, variant=variant),
        "rows": build_checklist_rows(cases, variant=variant),
        "variant": variant,
        "total_cases": len(cases),
    }


if __name__ == "__main__":
    for v in ("ifrs_listed", "non_listed"):
        data = learn_and_build(variant=v)
        print(v, "cases:", data["total_cases"], "rows:", len(data["rows"]))
