"""금감원·한공회 4대 중점 회계이슈 심층검증."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import config as app_config
from parser import ParsedDocument
import review_engine as re_engine
import sheet_code_registry as scr


@dataclass
class ChecklistItem:
    name: str
    detect_all: tuple[str, ...]
    detect_any: tuple[str, ...] = ()
    basis: str = ""
    to_be: str = ""
    case_hint: str = ""


@dataclass
class FocusIssue:
    issue_no: int
    title: str
    related_accounts: tuple[str, ...]
    sheet_keywords: tuple[str, ...]
    checklist: list[ChecklistItem] = field(default_factory=list)


# 금융감독원 「2026년 재무제표에 대한 중점심사 회계이슈 사전예고」(2026.6.19. 보도자료,
# Hanul DB/4대 중점사항 감리대상/금융감독원_상장_4대 중점사항_2026년) 유의사항 ①②③ 기준.
_DEFAULT_LISTED_2026: list[FocusIssue] = [
    FocusIssue(
        1,
        "국외 매출·매출채권 회계처리",
        ("매출채권", "매출"),
        ("국외", "해외", "수출", "외화", "매출채권", "외상매출"),
        [
            ChecklistItem(
                "인도조건별 수익인식 시점 (수행의무·통제 이전)",
                ("인도조건",),
                ("수행의무", "통제", "선적", "수익인식", "FOB", "기간귀속"),
                "K-IFRS 1115호(5단계 수익인식모형)",
                "국외 거래 인도조건에 따른 수행의무 이행 시점(재화·용역 통제 이전 시점) 검토",
            ),
            ChecklistItem(
                "매출채권 기대신용손실(손실충당금) 측정",
                ("신용",),
                ("기대신용손실", "손실충당금", "대손", "12개월", "전체기간", "회수가능"),
                "K-IFRS 1109호(기대신용손실)",
                "신용위험 유의적 증가 평가 및 기대신용손실(12개월/전체기간) 손실충당금 산정",
            ),
            ChecklistItem(
                "환율·지정학적 리스크 등 거시요인 반영",
                ("환율",),
                ("지정학", "수출입", "외화환산", "변동성", "cut-off", "cutoff"),
                "K-IFRS 1021호; K-IFRS 1109호",
                "환율 변동·수출입 제한 등 거시요인이 채무불이행 위험에 미치는 영향 평가",
            ),
        ],
    ),
    FocusIssue(
        2,
        "재고자산 평가손실 인식의 적정성",
        ("재고자산",),
        ("재고", "저가법", "평가손실", "순실현"),
        [
            ChecklistItem(
                "저가법 평가손실 인식 (NRV<원가 시 당기손익)",
                ("저가법",),
                ("순실현", "NRV", "평가손실", "판매가격", "원가 상승"),
                "K-IFRS 1002호",
                "물리적 손상·진부화·판매가격 하락 시 순실현가능가치와 원가의 차액 평가손실 인식",
            ),
            ChecklistItem(
                "항목별 적용·신뢰성 있는 증거 기반 NRV 추정",
                ("항목별",),
                ("품목별", "신뢰성", "증거", "세부 항목"),
                "K-IFRS 1002호",
                "저가법 항목별 적용 및 추정일 현재 가장 신뢰성 있는 증거에 기초한 NRV 추정",
            ),
            ChecklistItem(
                "진부화·장기체화·확정판매계약 보유목적 고려",
                ("진부화",),
                ("장기체화", "단종", "판매부진", "확정판매", "계약가격", "감모"),
                "K-IFRS 1002호",
                "진부화·장기체화 재고 식별, 확정판매계약 보유 재고의 계약가격 기초 NRV 산정",
            ),
        ],
    ),
    FocusIssue(
        3,
        "투자부동산 회계처리",
        ("투자부동산", "유형자산"),
        ("투자부동산", "공정가치", "임대", "처분"),
        [
            ChecklistItem(
                "투자부동산·자가사용부동산 분류 구분",
                ("투자부동산",),
                ("자가사용", "분류", "구분", "임대수익", "시세차익"),
                "K-IFRS 1040호",
                "임대수익·시세차익 목적 보유분의 투자부동산 분류 및 자가사용부동산과의 구분",
            ),
            ChecklistItem(
                "공정가치모형/원가모형 일관 적용·평가",
                ("공정가치",),
                ("원가모형", "평가", "감정", "DCF", "일관"),
                "K-IFRS 1040호",
                "공정가치모형·원가모형의 일관된 적용 및 매기 공정가치 평가(변동손익 당기 인식)",
            ),
            ChecklistItem(
                "투자부동산 주석 공시 (공정가치·장부금액 변동)",
                ("주석",),
                ("공시", "공정가치", "장부금액", "변동"),
                "K-IFRS 1040호(공시)",
                "당기손익 인식 금액·공정가치·장부금액 변동 내용 등 주석 공시(원가모형도 공정가치 주석 필요)",
            ),
        ],
    ),
    FocusIssue(
        4,
        "충당부채의 인식·측정과 우발부채 공시",
        ("충당부채", "우발부채·약정"),
        ("충당", "우발", "약정", "소송", "지급보증"),
        [
            ChecklistItem(
                "충당부채 인식요건·최선의 추정치 측정",
                ("충당",),
                ("최선의 추정", "현재가치", "현재의무", "제품보증", "손실부담"),
                "K-IFRS 1037호",
                "현재의무·유출가능성·신뢰성 있는 추정 요건 검토 및 최선의 추정치(현재가치) 측정",
            ),
            ChecklistItem(
                "우발부채 공시 (지급보증·소송·약정) 및 지속 평가",
                ("우발",),
                ("약정", "지급보증", "소송", "공시", "연대"),
                "K-IFRS 1037호; K-IFRS 1001호",
                "유출가능성이 희박하지 않은 우발부채(보증·소송·약정)의 주석 공시 및 지속 재평가",
            ),
        ],
    ),
]

# 한국공인회계사회 「2026년 비상장법인 재무제표에 대한 2027년 중점 점검분야 사전예고」
# (2026.6.29. 보도자료, Hanul DB/4대 중점사항 감리대상/한국공인회계사회_비상장_4대 중점사항) 기준.
_DEFAULT_UNLISTED_2026: list[FocusIssue] = [
    FocusIssue(
        1,
        "장기공사계약(수주산업) 수익인식 적정성",
        ("매출", "매출채권"),
        ("공사", "수주", "진행률", "도급", "분양", "공사미수금", "계약부채"),
        [
            ChecklistItem(
                "진행기준 적용 여부 판단",
                ("진행",),
                ("진행기준", "진행률", "기간에 걸쳐", "수행의무"),
                "K-IFRS 1115호; 일반기업회계기준 제16장",
                "계약내용·재화 용역 특성을 고려한 진행기준(기간에 걸친 수익인식) 적용 여부 판단",
            ),
            ChecklistItem(
                "진행률 측정·총공사예정원가 반영",
                ("진행률",),
                ("예정원가", "총공사", "산정", "설계변경", "재측정"),
                "K-IFRS 1115호; 일반기업회계기준 제16장",
                "공사지연·설계변경 등을 반영한 총공사예정원가 및 진행률 산정의 적정성",
            ),
            ChecklistItem(
                "공사손실충당부채(손실부담계약) 검토",
                ("손실",),
                ("공사손실", "충당부채", "손실부담", "예상손실"),
                "K-IFRS 1037호; 일반기업회계기준 제16장",
                "향후 공사손실 예상 시 예상손실의 즉시 공사손실충당부채 인식",
            ),
        ],
    ),
    FocusIssue(
        2,
        "지분법 회계처리 적정성",
        ("투자자산",),
        ("지분법", "관계기업", "투자주식", "종속기업", "피투자"),
        [
            ChecklistItem(
                "유의적인 영향력·지분법 적용대상 검토",
                ("지분",),
                ("유의적", "영향력", "지분율", "적용대상"),
                "K-IFRS 1028호; 일반기업회계기준 제8장",
                "지분율·주주간 약정을 고려한 유의적 영향력 및 지분법 적용대상 여부 검토",
            ),
            ChecklistItem(
                "내부거래 미실현손익 제거",
                ("내부거래",),
                ("미실현", "제거"),
                "K-IFRS 1028호",
                "투자·피투자기업 간 내부거래 미실현손익 제거 여부 검토",
            ),
            ChecklistItem(
                "피투자기업 재무제표 신뢰성 (연결재무제표 사용 등)",
                ("피투자",),
                ("연결", "가결산", "신뢰성", "회계정책"),
                "K-IFRS 1028호; 일반기업회계기준 제8장",
                "피투자기업이 지배기업인 경우 연결재무제표 사용, 회계정책 일치·재무제표 신뢰성 검증",
            ),
        ],
    ),
    FocusIssue(
        3,
        "충당부채와 우발부채 회계처리 및 공시 적정성",
        ("충당부채", "우발부채·약정"),
        ("충당", "우발", "약정", "소송", "지급보증"),
        [
            ChecklistItem(
                "충당부채 인식·측정 (품질보증·소송 등)",
                ("충당",),
                ("최선의 추정", "품질보증", "소송", "현재가치", "손실부담"),
                "K-IFRS 1037호; 일반기업회계기준 제14장",
                "품질보증·소송·손실부담계약 관련 충당부채의 인식요건 검토 및 최선의 추정치 측정",
            ),
            ChecklistItem(
                "우발부채 공시 (지급보증·PF약정 등)",
                ("우발",),
                ("지급보증", "약정", "연대", "공시", "PF"),
                "K-IFRS 1037호; 일반기업회계기준 제14장",
                "지급보증·채무인수 약정·연대보증 등 우발부채의 누락 없는 주석 공시(한도금액 포함)",
            ),
        ],
    ),
    FocusIssue(
        4,
        "특수관계자 거래 공시 적정성",
        (),
        ("특수관계자", "특수관계", "관계회사", "계열", "대여금"),
        [
            ChecklistItem(
                "특수관계자 식별 (법적 형식·실질 관계)",
                ("특수관계",),
                ("식별", "범위", "실질", "지배"),
                "K-IFRS 1024호; 일반기업회계기준 제25장",
                "법적 형식과 실질 관계를 모두 고려한 특수관계자 범위 식별",
            ),
            ChecklistItem(
                "거래총액·채권채무 잔액 공시",
                ("특수관계",),
                ("거래총액", "잔액", "채권", "채무", "매출", "매입"),
                "K-IFRS 1024호; 일반기업회계기준 제25장",
                "특수관계자별 거래총액·기말 채권채무 잔액·특수관계 성격의 구분 공시(비경상 거래 포함)",
            ),
            ChecklistItem(
                "지급보증·약정(풋옵션 등) 공시",
                ("보증",),
                ("풋옵션", "약정", "담보", "지급보증", "전환우선주"),
                "K-IFRS 1024호; K-IFRS 1032호",
                "특수관계자에 제공한 지급보증·투자약정(풋옵션 등)의 공시 및 금융부채 분류 검토",
            ),
        ],
    ),
]


def _parse_issue_titles(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def _title_match(custom: str, default: str) -> bool:
    """이슈명 매칭 — 공백·구분자(·) 차이를 흡수하고, 4자 이상 공통 어절이면 동일 이슈로 본다."""
    def norm(s: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]", "", s.lower())

    c, d = norm(custom), norm(default)
    if not c or not d:
        return False
    if c in d or d in c:
        return True
    return any(c[i : i + 4] in d for i in range(len(c) - 3))


def load_current_focus_issues(year: int, is_listed: bool) -> list[FocusIssue]:
    cfg_year = app_config.get_int("FSS_FOCUS_ISSUES_YEAR", year)
    if cfg_year:
        year = cfg_year
    defaults = _DEFAULT_LISTED_2026 if is_listed else _DEFAULT_UNLISTED_2026
    custom = app_config.get(
        "FSS_FOCUS_ISSUES_LISTED" if is_listed else "FSS_FOCUS_ISSUES_UNLISTED", ""
    )
    if custom:
        titles = _parse_issue_titles(custom)
        out: list[FocusIssue] = []
        for i, t in enumerate(titles[:4]):
            matched = next((d for d in defaults if _title_match(t, d.title)), None)
            if matched:
                out.append(
                    FocusIssue(
                        matched.issue_no, t, matched.related_accounts,
                        matched.sheet_keywords, matched.checklist,
                    )
                )
            else:
                out.append(FocusIssue(i + 1, t, (), (t.replace(" ", ""),), []))
        return out
    return defaults


def _sheet_index_from_source(source: str) -> str:
    """시트 source에서 조서 인덱스 추출 (D, E100 등)."""
    from output_formatter import short_sheet_code
    return short_sheet_code(source) or ""


def _sheet_matches_issue(
    t,
    title: str,
    issue: FocusIssue,
    item: Any | None = None,
) -> bool:
    """시트가 해당 중점 이슈·체크항목의 계정·조서 인덱스를 다루는지 판정."""
    source = str(t.attrs.get("source", "")).strip()
    sheet_code = _sheet_index_from_source(source)
    codes: tuple[str, ...] = ()
    if item is not None:
        codes = tuple(getattr(item, "related_sheet_codes", ()) or ())
    if codes and sheet_code:
        base = scr.parse_sheet_code(sheet_code) or sheet_code
        if sheet_code in codes or base in codes:
            return True
        if any(sheet_code.startswith(c) or c.startswith(base) for c in codes):
            return True

    primary = re_engine.table_account(t)
    accounts = issue.related_accounts
    if item is not None and getattr(item, "trigger_accounts", ()):
        accounts = tuple(set(accounts) | set(item.trigger_accounts))

    if accounts:
        if primary and primary in accounts:
            return True
        if primary == "대손충당금" and "매출채권" in accounts:
            return True

    t_low = title.lower()
    return any(kw.lower() in t_low for kw in issue.sheet_keywords if kw)


def _focus_reference_parts(item: Any) -> list[str]:
    """Hanul DB 2026-07-16 보강 컬럼 → reason/basis 보조 문장."""
    parts: list[str] = []
    for label, attr in (
        ("기준문단", "standard_paragraphs"),
        ("감사기준", "audit_standard_ref"),
        ("추가사례", "additional_case_refs"),
        ("질의회신", "qna_refs"),
        ("QC심리", "qc_checklist_ref"),
    ):
        val = str(getattr(item, attr, "") or "").strip()
        if val:
            parts.append(f"{label}: {val[:220]}")
    return parts


def _focus_basis(item: Any, *, src: str, default: str) -> str:
    basis = str(getattr(item, "basis", "") or default).strip()
    refs = _focus_reference_parts(item)
    if not refs:
        return basis
    extra = " | ".join(refs[:3])
    return f"{basis} — {extra}" if basis else extra


def _matched_sheets_for_item(
    doc: ParsedDocument,
    issue: FocusIssue,
    item: Any,
) -> list[tuple[str, str, str]]:
    """체크항목에 해당하는 (source, title, body) 시트 목록."""
    matched: list[tuple[str, str, str]] = []
    for t in doc.tables:
        title = str(t.attrs.get("title", "")).strip()
        source = str(t.attrs.get("source", "")).strip()
        if _sheet_matches_issue(t, title, issue, item):
            matched.append((source, title, re_engine._sheet_text(t)))
    return matched


def _display_sheet_codes(sheets: list[tuple[str, str, str]]) -> str:
    """매칭 시트들의 조서 인덱스 표기."""
    codes: list[str] = []
    seen: set[str] = set()
    for source, _, _ in sheets:
        code = _sheet_index_from_source(source)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return ""
    if len(codes) == 1:
        return codes[0]
    if len(codes) == 2:
        return f"{codes[0]}, {codes[1]}"
    return ", ".join(codes[:-1]) + f", {codes[-1]}"


def _checklist_satisfied(stext: str, item: ChecklistItem) -> bool:
    low = stext.lower()
    if item.detect_all and not all(k.lower() in low for k in item.detect_all):
        return False
    if item.detect_any and not any(k.lower() in low for k in item.detect_any):
        if item.detect_all:
            return True
        return False
    return True


def _focus_checklist_satisfied(stext: str, issue, item) -> bool:
    """DB 템플릿(Enhanced) 또는 기본 ChecklistItem 충족 판정."""
    try:
        import guidelines_loader as gl

        if hasattr(item, "acceptable_phrases") or hasattr(item, "required_evidence"):
            return gl.checklist_satisfied_enhanced(stext, item)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(item, ChecklistItem):
        return _checklist_satisfied(stext, item)
    return True


def _focus_item_unmet(stext: str, item) -> str | None:
    """미충족 시 리뷰 유형(검토누락/결론미비) 반환. 충족 시 None."""
    if _focus_checklist_satisfied(stext, None, item):
        return None
    low = stext.lower()
    trace_keys = tuple(
        k for k in (getattr(item, "detect_all", ()) or ())
        + (getattr(item, "detect_any", ()) or ())
        if k
    )
    has_trace = any(k.lower() in low for k in trace_keys)
    gap = str(getattr(item, "review_gap_type", "") or "").strip()
    if not has_trace:
        return "검토누락"
    return gap or "결론미비"


def _extract_issue_balance_hint(body: str, accounts: tuple[str, ...]) -> float | None:
    """조서 본문에서 관련 계정 잔액 힌트 추출 (중요성 판단용)."""
    if not body or not accounts:
        return None
    best: float | None = None
    num_re = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:원|백만|천)?")
    for acct in accounts:
        for m in re.finditer(re.escape(acct), body):
            window = body[m.end() : m.end() + 120]
            for nm in num_re.finditer(window):
                try:
                    val = float(nm.group(1).replace(",", ""))
                except ValueError:
                    continue
                if val <= 0:
                    continue
                if best is None or val > best:
                    best = val
    return best


def _focus_importance(
    issue: FocusIssue,
    item,
    body: str,
    mat: re_engine.Materiality,
) -> str:
    """중요성·materiality_note 기반 중요도 ('상'|'중'|'하')."""
    note = str(getattr(item, "materiality_note", "") or "").strip()
    if any(k in note for k in ("마이너", "미만", "경미", "사소")):
        te = mat.te or mat.pm
        if te and te > 0:
            bal = _extract_issue_balance_hint(body, issue.related_accounts)
            if bal is not None and bal < te * 0.05:
                return "하"
        return "중"
    if "중요성 이상" in note:
        te = mat.te or mat.pm
        if te and te > 0:
            bal = _extract_issue_balance_hint(body, issue.related_accounts)
            if bal is not None and bal < te * 0.1:
                return "중"
    return "상"


def _item_to_be(item, gap_type: str) -> str:
    if gap_type == "결론미비":
        weak = str(getattr(item, "to_be_if_weak", "") or "").strip()
        if weak:
            return weak
    missing = str(getattr(item, "to_be_if_missing", "") or getattr(item, "to_be", "") or "").strip()
    return missing


def run_focus_review(
    doc: ParsedDocument,
    engagement: dict[str, Any],
    *,
    is_listed: bool | None = None,
) -> list[dict[str, Any]]:
    year_s = str(engagement.get("audit_year", "")).strip()
    year = int(year_s) if year_s.isdigit() else 2026
    listed = is_listed if is_listed is not None else bool(engagement.get("is_listed"))
    issues = load_current_focus_issues(year, listed)
    enhanced: list | None = None
    try:
        import guidelines_loader as gl

        gl.load_focus_issues_from_db.cache_clear()
        enhanced = gl.load_focus_issues_from_db(listed)
        if enhanced:
            issues = [
                FocusIssue(
                    e.issue_no,
                    e.title,
                    e.related_accounts,
                    e.sheet_keywords,
                    list(e.checklist),
                )
                for e in enhanced
            ]
    except Exception:  # noqa: BLE001
        pass
    checklist_items_map: dict[int, list] = {}
    if enhanced:
        checklist_items_map = {e.issue_no: list(e.checklist) for e in enhanced}

    mat = re_engine.extract_materiality(doc)
    te_manual = engagement.get("materiality_te")
    if te_manual and float(te_manual) > 0:
        mat.te = float(te_manual)

    notes: list[dict[str, Any]] = []
    src = "금융감독원" if listed else "한국공인회계사회"

    for issue in issues:
        items = checklist_items_map.get(issue.issue_no) or issue.checklist
        if not items:
            continue

        for item in items:
            matched = _matched_sheets_for_item(doc, issue, item)
            if not matched:
                na = str(getattr(item, "na_condition", "") or "").strip()
                if na:
                    continue
                continue

            body = "\n".join(s[2] for s in matched)
            sheet_no = _display_sheet_codes(matched) or matched[0][0]
            sheet_title = matched[0][1] or issue.title

            gap = _focus_item_unmet(body, item)
            if not gap:
                continue
            importance = _focus_importance(issue, item, body, mat)
            if importance == "하":
                continue

            vtype = str(getattr(item, "violation_type", "") or "").strip()
            case_ex = str(getattr(item, "case_example", "") or "").strip()
            case_src = str(getattr(item, "case_source", "") or "").strip()
            cid = str(getattr(item, "checklist_id", "") or "").strip()
            procedure = str(getattr(item, "review_procedure", "") or "").strip()
            gs_ids = getattr(item, "golden_set_ids", "") or ""
            if isinstance(gs_ids, str):
                gs_tuple = tuple(x.strip() for x in gs_ids.split(";") if x.strip())
            else:
                gs_tuple = tuple(gs_ids) if gs_ids else ()
            name = getattr(item, "name", str(item))
            tag = f"[4대중점·{gap}]"
            defect = f"{tag} {issue.issue_no}. {issue.title} — {name}"
            if cid:
                defect += f" ({cid})"

            reason_parts = [
                f"{src} 4대 중점 지적유형「{vtype}」관련 계정·조서({sheet_no})가 있어 검토대상입니다."
                if vtype
                else f"{src} 4대 중점사항 관련 계정·조서({sheet_no})가 있어 검토대상입니다.",
            ]
            if case_src or case_ex:
                reason_parts.append(
                    f"감리 예시({case_src}): {case_ex}" if case_src else f"감리 예시: {case_ex}"
                )
            if procedure:
                reason_parts.append(f"검토지침: {procedure}")
            if gap == "검토누락":
                req = tuple(getattr(item, "required_evidence", ()) or ())
                if req:
                    reason_parts.append(
                        f"조서에서「{name}」필수증거({', '.join(req[:4])})가 확인되지 않습니다."
                    )
                else:
                    reason_parts.append(
                        f"조서에서「{name}」에 대한 검토·문서화 흔적이 확인되지 않았습니다."
                    )
            else:
                acc = tuple(getattr(item, "acceptable_phrases", ()) or ())
                if acc:
                    reason_parts.append(
                        f"「{name}」검토는 있으나 인정문장({acc[0]} 등) 또는 감사결론이 불충분합니다."
                    )
                else:
                    reason_parts.append(
                        f"「{name}」검토는 있으나 감사결론·근거가 불충분합니다."
                    )
            if getattr(item, "materiality_note", ""):
                reason_parts.append(f"({item.materiality_note})")
            reason_parts.extend(_focus_reference_parts(item)[:2])

            basis = _focus_basis(
                item,
                src=src,
                default=str(getattr(item, "basis", "") or f"{src} 중점심사 회계이슈 사전예고"),
            )
            to_be = _item_to_be(item, gap)
            if procedure and procedure not in to_be:
                to_be = f"{to_be}\n검토절차: {procedure}" if to_be else f"검토절차: {procedure}"
            if to_be and not to_be.startswith("다음"):
                to_be = f"다음 내용으로 보완 바랍니다: {to_be}"

            notes.append(_focus_note(
                issue,
                defect=defect,
                reason=" ".join(reason_parts),
                basis=basis,
                to_be=to_be,
                sheet_no=sheet_no,
                sheet_title=sheet_title,
                importance=importance,
                review_gap_type=gap,
                checklist_id=cid,
                violation_type=vtype,
                golden_set_ids=gs_tuple,
                review_procedure=procedure,
                is_listed=listed,
                item=item,
            ))
    return notes


def _focus_note(
    issue,
    *,
    defect,
    reason,
    basis="금융감독원 중점심사 회계이슈",
    to_be,
    sheet_no,
    sheet_title,
    importance: str = "상",
    review_gap_type: str = "",
    checklist_id: str = "",
    violation_type: str = "",
    golden_set_ids: tuple[str, ...] = (),
    review_procedure: str = "",
    is_listed: bool = True,
    item: Any | None = None,
):
    label = f"{sheet_no} ({sheet_title})" if sheet_no and sheet_title else sheet_no
    note = {
        "id": "", "importance": importance, "category": "중점감리",
        "defect": defect, "reason": reason, "basis": basis, "to_be": to_be,
        "sheet_no": sheet_no or "-", "sheet_title": sheet_title, "sheet": label,
        "location": "", "summary": "", "workpaper_ref": sheet_no or label,
        "is_focus_related": True, "focus_issue_no": issue.issue_no,
        "focus_issue_title": issue.title, "source": "rule", "focus_protected": True,
        "review_gap_type": review_gap_type,
        "focus_checklist_id": checklist_id,
        "focus_violation_type": violation_type,
        "focus_golden_set_ids": list(golden_set_ids),
        "focus_review_procedure": review_procedure,
        "is_listed": is_listed,
    }
    if item is not None:
        for key, attr in (
            ("focus_standard_paragraphs", "standard_paragraphs"),
            ("focus_audit_standard_ref", "audit_standard_ref"),
            ("focus_additional_case_refs", "additional_case_refs"),
            ("focus_qna_refs", "qna_refs"),
            ("focus_qc_checklist_ref", "qc_checklist_ref"),
        ):
            val = str(getattr(item, attr, "") or "").strip()
            if val:
                note[key] = val
    return note


def build_focus_sheet(
    notes: list[dict[str, Any]],
    year: int,
    is_listed: bool,
    doc: ParsedDocument | None = None,
) -> list[dict[str, Any]]:
    issues = load_current_focus_issues(year, is_listed)
    focus_notes = [n for n in notes if n.get("is_focus_related") or n.get("category") == "중점감리"]

    # 조서에 실제 존재하는 이슈만 판정 (doc 제공 시)
    present: dict[int, bool] = {}
    if doc is not None:
        for issue in issues:
            present[issue.issue_no] = any(
                _sheet_matches_issue(t, str(t.attrs.get("title", "")).strip(), issue)
                for t in doc.tables
            )

    rows: list[dict[str, Any]] = []
    for issue in issues:
        related = [
            n for n in focus_notes
            if n.get("focus_issue_no") == issue.issue_no or issue.title in n.get("defect", "")
        ]
        if related:
            for n in related:
                rows.append({
                    "issue_no": issue.issue_no, "issue_title": issue.title, "status": "중점검토 필요",
                    "defect": n.get("defect", ""), "reason": n.get("reason", ""),
                    "basis": n.get("basis", ""), "to_be": n.get("to_be", ""), "sheet": n.get("sheet", ""),
                })
        else:
            status = "이상 없음"
            if doc is not None and not present.get(issue.issue_no, False):
                status = "해당사항 없음"  # 조서에 관련 계정과목 없음
            rows.append({
                "issue_no": issue.issue_no, "issue_title": issue.title, "status": status,
                "defect": "", "reason": "", "basis": "", "to_be": "", "sheet": "",
            })
    return rows
