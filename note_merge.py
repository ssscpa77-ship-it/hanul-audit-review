"""AI·규칙엔진 리뷰노트 병합·통합 — 중복 지적을 하나로 묶고 중점감리 노트를 보호."""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

import review_engine as re_engine
import sheet_code_registry as scr

_INVENTORY_SUB_RE = re.compile(r"원재료|부재료|재공품|상품|제품|저장품|미착품|반제품")
_KO = re.compile(r"[가-힣]{2,}")
_SUBSTANTIVE_CATEGORIES = frozenset({"절차누락", "중점감리", "주석검증", "중요성"})
_IMP_RANK = {"상": 3, "중": 2, "하": 1}
_TOKEN_STOP = frozenset(
    {"조서", "확인", "관련", "내역", "검토", "수행", "기재", "포함", "해당", "경우", "절차", "미확인", "흔적"}
)

# 동일 주제·계정의 분산 지적을 하나로 통합 (실사입회·Cut-off·조회 등)
_CONSOLIDATION_THEMES: list[dict[str, Any]] = [
    {
        "id": "inventory_physical_count",
        "account": "재고자산",
        "match": re.compile(r"실사|입회|재고조사|재고\s?실사|physical\s?count", re.IGNORECASE),
        "defect": "재고자산 실사입회 절차·문서화 미흡",
        "sheet_boost": ("실사", "입회", "E100", "재고실사", "재고조사"),
        "sheet_penalty": re.compile(r"lead|개요|계획|summary|요약", re.IGNORECASE),
    },
    {
        "id": "inventory_cutoff",
        "account": "재고자산",
        "match": re.compile(r"cut.?off|컷오프|기간귀속", re.IGNORECASE),
        "defect": "재고자산 Cut-off(기간귀속) 검토 미흡",
        "sheet_boost": ("cut", "컷", "기간", "입출고", "선적", "E"),
        "sheet_penalty": re.compile(r"lead|개요|계획", re.IGNORECASE),
    },
    {
        "id": "inventory_valuation",
        "account": "재고자산",
        "match": re.compile(r"저가법|NRV|순실현|감모|평가손실|진부화|유효기간", re.IGNORECASE),
        "defect": "재고자산 평가(저가법·감모 등) 검토 미흡",
        "sheet_boost": ("평가", "저가", "NRV", "감모"),
        "sheet_penalty": re.compile(r"lead|개요", re.IGNORECASE),
    },
    {
        "id": "ar_confirmation",
        "account": "매출채권",
        "match": re.compile(r"조회|확인서|confirmation|잔액확인|조회서", re.IGNORECASE),
        "defect": "매출채권 외부조회(조회서) 절차·문서화 미흡",
        "sheet_boost": ("조회", "확인", "AR", "채권"),
        "sheet_penalty": re.compile(r"lead|개요", re.IGNORECASE),
    },
    {
        "id": "ar_ecl",
        "account": "매출채권",
        "match": re.compile(r"대손|기대신용|ECL|연령분석|손실충당", re.IGNORECASE),
        "defect": "대손충당금(기대신용손실) 평가·문서화 미흡",
        "sheet_boost": ("대손", "ECL", "연령", "충당"),
        "sheet_penalty": re.compile(r"lead|개요", re.IGNORECASE),
    },
    {
        "id": "revenue_cutoff",
        "account": "매출",
        "match": re.compile(r"cut.?off|컷오프|기간귀속|귀속시점|인식시점", re.IGNORECASE),
        "defect": "수익(매출) Cut-off·기간귀속 검토 미흡",
        "sheet_boost": ("매출", "수익", "cut", "컷", "기간"),
        "sheet_penalty": re.compile(r"lead|개요", re.IGNORECASE),
    },
    {
        "id": "cogs_inventory_valuation",
        "account": "매출원가",
        "match": re.compile(
            r"재고자산?\s?평가|평가손실|매출원가.*반영|원가.*반영|저가법|순실현|NRV", re.IGNORECASE
        ),
        "defect": "매출원가 조서 — 재고자산 평가손실 반영·검토 미흡",
        "sheet_boost": ("Q", "매출원가", "원가", "제조"),
        "sheet_penalty": re.compile(r"개요|summary|요약", re.IGNORECASE),
    },
    {
        "id": "cash_confirmation",
        "account": "현금및예금",
        "match": re.compile(r"조회|은행조회|잔액조회|확인서", re.IGNORECASE),
        "defect": "예금·현금 잔액조회(은행조회서) 절차 미흡",
        "sheet_boost": ("예금", "현금", "조회", "은행"),
        "sheet_penalty": re.compile(r"lead|개요", re.IGNORECASE),
    },
    {
        "id": "contingency_disclosure",
        "account": "우발부채·약정",
        "match": re.compile(
            r"우발|약정|지급보증|소송|담보|공시|계류|연대|보증", re.IGNORECASE
        ),
        "defect": "우발부채·약정사항 주석 공시·검토 미흡",
        "sheet_boost": ("CL", "우발", "약정", "지급보증"),
        "sheet_penalty": re.compile(r"lead|개요|summary|요약", re.IGNORECASE),
    },
    {
        "id": "off_balance",
        "account": "부외부채",
        "match": re.compile(
            r"부외|팩토링|리스|SPE|일광|우선\s?수익|계속\s?기", re.IGNORECASE
        ),
        "defect": "부외부채 검토·보완 필요",
        "sheet_boost": ("TUL", "부외", "팩토링", "리스"),
        "sheet_penalty": re.compile(r"lead|개요|summary|요약", re.IGNORECASE),
    },
]

_CONTINGENCY_SUB_RE = re.compile(
    r"지급보증|약정사항|약정|소송|담보|연대보증|연대|PF|풋옵션|우발부채|우발|"
    r"계류|보증|담보제공|채무인수|지급약정",
    re.I,
)
_OFF_BALANCE_SUB_RE = re.compile(
    r"부외|팩토링|리스|일광|SPE|우선\s?수익|계속\s?기|연대|채무|약정|"
    r"공시|제재|불이익|일광\s?특수",
    re.I,
)
_SHEET_CODE_RE = re.compile(r"^([A-Z]{1,4})", re.I)
_LEAD_RE = re.compile(r"lead|리드", re.I)
_FAMILY_TOPIC_KW = ("재고", "평가", "매출원가", "반영", "원가", "저가", "NRV", "순실현")


def _raw_sheet_token(note: dict[str, Any]) -> str:
    raw = str(note.get("sheet_no") or note.get("workpaper_ref") or "").strip()
    return re.sub(r"^.*/", "", raw.split()[0] if raw else "")


def _sheet_code_root(note: dict[str, Any]) -> str:
    """조서번호 루트 (Q200→Q, A Lead→A)."""
    m = _SHEET_CODE_RE.match(_raw_sheet_token(note))
    return m.group(1).upper() if m else ""


def _sheet_display_codes(note: dict[str, Any]) -> str:
    """UI·엑셀용 조서 인덱스 (D, E100 … — 숫자·MEMO·전기말 제외)."""
    from output_formatter import short_sheet_code

    raw = str(note.get("sheet_no") or note.get("workpaper_ref") or "").strip()
    raw = re.sub(r"^.*/", "", raw).strip()
    if not raw or raw == "-":
        return ""
    code = short_sheet_code(raw)
    if not code:
        acct = re_engine.note_account(note)
        if acct:
            return scr.sheet_code_for_account(acct) or ""
        return ""
    parts = raw.split()
    if len(parts) >= 2 and _LEAD_RE.search(" ".join(parts[1:3])):
        base = re.match(r"^([A-Z]+)", code, re.I)
        if base and code.upper() == base.group(1).upper():
            return f"{code} Lead"
    return code


def _format_merged_sheet_codes(group: list[dict[str, Any]]) -> str:
    """Lead·세부 조서를 'Q 와 Q200' 형식으로 표기."""
    codes: list[str] = []
    seen: set[str] = set()
    for note in group:
        code = _sheet_display_codes(note)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)

    if not codes:
        acct = re_engine.note_account(group[0]) if group else None
        if acct:
            fallback = scr.sheet_code_for_account(acct)
            return fallback or ""

    # Q Lead와 Q가 함께 있으면 Lead 표기는 Q로 통합
    bases = {re.match(r"^([A-Z]+)", c, re.I).group(1).upper()
             for c in codes if re.match(r"^([A-Z]+)", c, re.I)}
    normalized: list[str] = []
    for c in codes:
        m = re.match(r"^([A-Z]+)", c, re.I)
        base = m.group(1).upper() if m else c
        if _LEAD_RE.search(c) and base in bases and any(x.upper() == base for x in codes):
            continue
        normalized.append(c)
    codes = normalized or codes

    def _sort_key(c: str) -> tuple:
        m = re.match(r"^([A-Z]+)", c, re.I)
        base = (m.group(1) if m else c).upper()
        num_m = re.search(r"(\d+)\s*$", c)
        num = int(num_m.group(1)) if num_m else 0
        is_base = c.upper() == base
        return (base, 0 if is_base else 1, num, c)

    codes.sort(key=_sort_key)
    if len(codes) == 1:
        return codes[0]
    if len(codes) == 2:
        return f"{codes[0]} 와 {codes[1]}"
    return ", ".join(codes[:-1]) + f" 와 {codes[-1]}"


def _apply_merged_sheet_label(merged: dict[str, Any], group: list[dict[str, Any]]) -> None:
    """병합 노트의 조서번호·시트 필드를 조서 인덱스 표기로 갱신."""
    label = _format_merged_sheet_codes(group)
    if not label:
        acct = re_engine.note_account(merged)
        if acct:
            label = scr.sheet_code_for_account(acct) or ""
    if not label:
        return
    acct = re_engine.note_display_account(merged) or re_engine.note_account(merged) or ""
    merged["sheet_no"] = label
    merged["workpaper_ref"] = label
    if acct:
        merged["sheet_title"] = acct
        merged["sheet"] = f"{label} ({acct})"
    else:
        title = str(merged.get("sheet_title") or "").strip()
        merged["sheet"] = f"{label} ({title})" if title else label


def _same_sheet_family(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ra, rb = _sheet_code_root(a), _sheet_code_root(b)
    return bool(ra and rb and ra == rb)


def _issue_points_from_group(group: list[dict[str, Any]]) -> list[str]:
    """통합 노트용 지적 항목 — 구체·간결 bullet."""
    points: list[str] = []
    seen: set[str] = set()
    for n in group:
        tieout = str(n.get("tieout_detail") or "").strip()
        if tieout:
            line = tieout if tieout.startswith("·") else f"· {tieout}"
            if line not in seen:
                seen.add(line)
                points.append(line)
                continue
        defect = re.sub(
            r"^\[(?:중요\s?절차\s?누락|개선\s?제안|검토\s?요청|확인)\]\s*",
            "",
            str(n.get("defect") or ""),
        ).strip()
        pt = _brief_point(n) or defect[:120]
        if not pt:
            continue
        line = pt if pt.startswith("·") else f"· {pt}"
        if line not in seen:
            seen.add(line)
            points.append(line)
    return points[:12]


def _set_merged_issue_detail(merged: dict[str, Any], group: list[dict[str, Any]]) -> None:
    """통합 메타 문구 대신 항목별 지적사항을 기록."""
    points = _issue_points_from_group(group)
    if points:
        merged["merged_points"] = points
        merged["reason"] = "\n".join(points)


def _note_text(note: dict[str, Any]) -> str:
    return f"{note.get('defect', '')} {note.get('reason', '')} {note.get('to_be', '')}"


def _sheet_label(note: dict[str, Any]) -> str:
    acct = re_engine.note_display_account(note)
    if acct:
        return acct
    parts = [
        re_engine._sanitize_account_label(str(note.get(k, "") or ""))
        for k in ("sheet_no", "sheet_title", "sheet", "workpaper_ref")
    ]
    return " ".join(p for p in parts if p).strip()


def _point_sheet_prefix(note: dict[str, Any]) -> str:
    """통합 노트 bullet 앞에 붙일 시트·계정 표기."""
    acct = re_engine.note_display_account(note)
    if acct:
        return acct
    raw = str(note.get("sheet_no") or note.get("workpaper_ref") or "").strip()
    return re.sub(r"^.*/", "", raw.split()[0] if raw else "")


def _is_protected_note(note: dict[str, Any]) -> bool:
    return bool(
        note.get("focus_protected")
        or note.get("enforcement_protected")
        or note.get("category") in ("중점감리", "감리지적체크")
    )


def _theme_key(note: dict[str, Any]) -> tuple[str, str] | None:
    if _is_protected_note(note):
        return None
    text = _note_text(note)
    acct = re_engine.note_account(note) or ""
    for cfg in _CONSOLIDATION_THEMES:
        if not cfg["match"].search(text):
            continue
        theme_acct = cfg.get("account")
        if theme_acct and acct and acct != theme_acct:
            continue
        if theme_acct and not acct and theme_acct not in text:
            continue
        return (cfg["id"], theme_acct or acct or "공통")
    return None


def _content_tokens(note: dict[str, Any]) -> set[str]:
    return {t for t in _KO.findall(_note_text(note)) if t not in _TOKEN_STOP and len(t) >= 2}


def _generic_key(note: dict[str, Any]) -> tuple[str, str, str] | None:
    if _theme_key(note):
        return None
    acct = re_engine.note_account(note) or ""
    if not acct:
        return None
    tokens = sorted(_content_tokens(note))[:8]
    if len(tokens) < 2:
        return None
    return ("generic", acct, "|".join(tokens[:4]))


def _token_overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if _is_protected_note(a) or _is_protected_note(b):
        return False
    tk = _theme_key(a)
    if tk and tk == _theme_key(b):
        return True
    acct_a = re_engine.note_account(a)
    acct_b = re_engine.note_account(b)
    if acct_a and acct_b and acct_a != acct_b:
        return False
    if acct_a and acct_b and acct_a == acct_b and _same_sheet_family(a, b):
        if _token_overlap(a, b) >= 0.28:
            return True
    if _token_overlap(a, b) >= 0.42:
        return True
    da = (a.get("defect") or "")[:40]
    db = (b.get("defect") or "")[:40]
    return bool(da and db and (da in db or db in da))


def _sheet_score(note: dict[str, Any], cfg: dict[str, Any] | None) -> int:
    label = _sheet_label(note)
    score = _IMP_RANK.get(note.get("importance", "중"), 2) * 5
    if note.get("source") == "rule":
        score += 2
    if not cfg:
        return score
    for kw in cfg.get("sheet_boost") or ():
        if kw.lower() in label.lower():
            score += 12
    penalty = cfg.get("sheet_penalty")
    if penalty and penalty.search(label):
        score -= 15
    return score


def _theme_cfg(theme_id: str) -> dict[str, Any] | None:
    for cfg in _CONSOLIDATION_THEMES:
        if cfg["id"] == theme_id:
            return cfg
    return None


def _filter_enforcement_cases(cases: list[dict], acct: str) -> list[dict]:
    kept: list[dict] = []
    seen: set[str] = set()
    for c in cases:
        src = f"{c.get('subject', '')} {c.get('number', '')}"
        snip = f"{c.get('brief', '')} {c.get('summary_line', '')}"
        if re_engine.is_off_account_enforcement(src, snip, acct):
            continue
        num = c.get("number", "")
        if num in seen:
            continue
        seen.add(num)
        kept.append(c)
    return kept


def _merge_group(group: list[dict[str, Any]], theme_id: str | None) -> dict[str, Any]:
    cfg = _theme_cfg(theme_id) if theme_id else None
    primary = max(group, key=lambda n: _sheet_score(n, cfg))
    merged = copy.deepcopy(primary)

    if cfg and cfg.get("defect"):
        merged["defect"] = cfg["defect"]

    merged["importance"] = max(
        (n.get("importance", "중") for n in group),
        key=lambda x: _IMP_RANK.get(x, 2),
    )

    bases: list[str] = []
    for n in group:
        b = (n.get("basis") or "").strip()
        if b and b not in bases:
            bases.append(b)
    if bases:
        merged["basis"] = "; ".join(bases)

    refs: list[dict] = []
    seen_ref: set[str] = set()
    for n in group:
        for r in n.get("references") or []:
            key = r.get("source", "") + r.get("snippet", "")[:40]
            if key not in seen_ref:
                seen_ref.add(key)
                refs.append(r)
    if refs:
        merged["references"] = refs

    cases: list[dict] = []
    seen_case: set[str] = set()
    acct = re_engine.note_account(merged) or ""
    for n in group:
        for c in _filter_enforcement_cases(n.get("enforcement_cases") or [], acct):
            num = c.get("number", "")
            if num not in seen_case:
                seen_case.add(num)
                cases.append(c)
    if cases:
        merged["enforcement_cases"] = cases[:2]

    merged["consolidated_from"] = len(group)
    if len(group) > 1:
        _apply_merged_sheet_label(merged, group)
        _set_merged_issue_detail(merged, group)
    return merged


_OVERSTAT_RE = re.compile(r"과대\s?계상|과소\s?계상|허위\s?계상")


def _brief_point(note: dict[str, Any]) -> str:
    tieout = str(note.get("tieout_detail") or "").strip()
    if tieout:
        return tieout[:140]

    detail_line = str(note.get("issue_detail_line") or "").strip()
    if detail_line:
        loc = str(note.get("location") or "").strip()
        if loc and loc not in detail_line:
            return f"{detail_line} ({loc})"[:140]
        return detail_line[:140]

    text = _note_text(note)
    if _OVERSTAT_RE.search(text):
        defect = re.sub(
            r"^\[(?:중요\s?절차\s?누락|개선\s?제안|검토\s?요청|감리지적·[^\]]+)\]\s*",
            "",
            note.get("defect", "") or "",
        ).strip()
        loc = str(note.get("location") or "").strip()
        gap = ""
        for key in ("procedure_gap", "violation_type", "case_example"):
            if note.get(key):
                gap = str(note[key])[:60]
                break
        if not gap:
            m = _OVERSTAT_RE.search(text)
            ctx_start = max(0, (m.start() if m else 0) - 30)
            gap = text[ctx_start : ctx_start + 80].strip()
        sheet = _point_sheet_prefix(note)
        parts = [p for p in (sheet, defect[:40], gap[:50], loc) if p]
        return " — ".join(parts[:3])[:140]

    defect = re.sub(
        r"^\[(?:중요\s?절차\s?누락|개선\s?제안|검토\s?요청)\]\s*",
        "",
        note.get("defect", "") or "",
    ).strip()
    subs = _INVENTORY_SUB_RE.findall(_note_text(note))
    if subs:
        label = subs[0]
        if label not in defect:
            return f"{label} — {defect[:55]}"
    sheet = _point_sheet_prefix(note)
    if sheet and sheet not in defect and len(defect) < 48:
        return f"{sheet}: {defect[:50]}"
    return defect[:72]


def _contingency_point(note: dict[str, Any]) -> str:
    """우발·약정 통합 노트용 항목 한 줄."""
    defect = re.sub(
        r"^\[(?:중요\s?절차\s?누락|개선\s?제안|검토\s?요청|확인)\]\s*",
        "",
        note.get("defect", "") or "",
    ).strip()
    sheet = _sheet_label(note)
    subs = _CONTINGENCY_SUB_RE.findall(_note_text(note))
    topic = subs[0] if subs else ""
    if topic and topic not in defect:
        line = f"{topic} — {defect[:55]}"
    elif sheet and sheet not in defect:
        short = _point_sheet_prefix(note)
        line = f"{short}: {defect[:58]}" if short else defect[:72]
    else:
        line = defect[:72]
    return line.strip(" —:")


def _merge_contingency_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """우발부채·약정 다수 시트 지적 → 검토 항목 열거형 통합 노트 1건."""
    cfg = _theme_cfg("contingency_disclosure")
    primary = max(group, key=lambda n: _sheet_score(n, cfg))
    merged = copy.deepcopy(primary)

    subitems = sorted({s for n in group for s in _CONTINGENCY_SUB_RE.findall(_note_text(n))})
    points = list(dict.fromkeys(_contingency_point(n) for n in group if _contingency_point(n)))
    sheets = sorted({_sheet_label(n) for n in group if _sheet_label(n)})

    sub_label = "·".join(subitems[:6]) if subitems else "주석·약정"
    merged["defect"] = f"[검토 요청] 우발부채·약정 ({sub_label})"
    merged["importance"] = max(
        (n.get("importance", "중") for n in group),
        key=lambda x: _IMP_RANK.get(x, 2),
    )
    merged["category"] = "검토요청"

    bullet = "\n".join(f"· {p}" for p in points[:10])
    merged["to_be"] = (
        "아래 항목을 검토·보완하여 우발부채·약정(CL) 감사조서를 업데이트하시기 바랍니다.\n"
        + bullet
        if bullet
        else "우발부채·약정 관련 주석·약정사항을 종합 검토·문서화하시기 바랍니다."
    )
    sheet_hint = ", ".join(sheets[:4])
    _set_merged_issue_detail(merged, group)
    if not merged.get("reason"):
        merged["reason"] = (
            f"· 우발부채·약정(CL) 관련 검토 항목 ({sheet_hint})"
            if sheet_hint
            else "· 우발부채·약정(CL) 관련 검토 항목"
        )
    merged["sheet_no"] = primary.get("sheet_no") or (sheets[0] if sheets else "CL")
    merged["sheet_title"] = "우발부채·약정"
    merged["brief_merged"] = True
    merged["contingency_merged"] = True
    merged["consolidated_from"] = len(group)

    bases: list[str] = []
    for n in group:
        b = (n.get("basis") or "").strip()
        if b and b not in bases and "AI 추정" not in b:
            bases.append(b)
    if bases:
        merged["basis"] = "; ".join(bases[:2])

    refs: list[dict] = []
    seen_ref: set[str] = set()
    for n in group:
        for r in n.get("references") or []:
            key = r.get("source", "") + r.get("snippet", "")[:40]
            if key not in seen_ref:
                seen_ref.add(key)
                refs.append(r)
    if refs:
        merged["references"] = refs[:2]

    cases: list[dict] = []
    seen_case: set[str] = set()
    for n in group:
        for c in _filter_enforcement_cases(
            n.get("enforcement_cases") or [], acct or "우발부채·약정"
        ):
            num = c.get("number", "")
            if num not in seen_case:
                seen_case.add(num)
                cases.append(c)
    if cases:
        merged["enforcement_cases"] = cases[:2]

    return merged


def _is_contingency_note(note: dict[str, Any]) -> bool:
    if _is_protected_note(note) or note.get("brief_merged") or note.get("collateral_memo"):
        return False
    acct = re_engine.note_account(note)
    if acct == "우발부채·약정":
        return True
    return bool(re.search(r"(?:^|\s|/)CL(?:\s|$|Lead|\d|리드)", _sheet_label(note), re.I))


def consolidate_contingency_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """우발부채·약정(CL) 시트별 분산 지적 → 검토 항목 열거형 통합 노트 1건."""
    protected: list[dict[str, Any]] = []
    contingency: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []

    for note in notes:
        if _is_protected_note(note):
            protected.append(note)
            continue
        if _is_contingency_note(note):
            contingency.append(note)
        else:
            rest.append(note)

    if len(contingency) >= 2:
        rest.append(_merge_contingency_group(contingency))
    else:
        rest.extend(contingency)

    rest.extend(protected)
    return rest


def _off_balance_point(note: dict[str, Any]) -> str:
    """부외부채 통합 노트용 항목 한 줄."""
    defect = re.sub(
        r"^\[(?:중요\s?절차\s?누락|개선\s?제안|검토\s?요청|확인)\]\s*",
        "",
        note.get("defect", "") or "",
    ).strip()
    sheet = _sheet_label(note)
    subs = _OFF_BALANCE_SUB_RE.findall(_note_text(note))
    topic = subs[0] if subs else ""
    if topic and topic not in defect:
        return f"{topic} — {defect[:55]}"
    if sheet and sheet not in defect:
        short = _point_sheet_prefix(note)
        return f"{short}: {defect[:58]}" if short else defect[:72]
    return defect[:72]


def _merge_off_balance_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """부외부채(TUL) 다수 시트 지적 → 체크·리마인드형 통합 노트 1건."""
    account = "부외부채"
    cfg = _theme_cfg("off_balance")
    primary = max(group, key=lambda n: _sheet_score(n, cfg))
    merged = copy.deepcopy(primary)

    subitems = sorted({s for n in group for s in _OFF_BALANCE_SUB_RE.findall(_note_text(n))})
    points = list(dict.fromkeys(_off_balance_point(n) for n in group if _off_balance_point(n)))
    sheets = sorted({_sheet_label(n) for n in group if _sheet_label(n)})

    sub_label = "·".join(subitems[:6]) if subitems else "체크항목"
    merged["defect"] = f"[검토 요청] 부외부채 — {sub_label} 확인·보완"
    merged["importance"] = "중"
    merged["category"] = "검토요청"

    bullet = "\n".join(f"· {p}" for p in points[:10])
    merged["to_be"] = (
        "아래 항목을 검토·보완하여 부외부채(TUL) 감사조서를 업데이트하시기 바랍니다.\n"
        + bullet
        if bullet
        else "부외부채 관련 공시·약정·연대채무 등을 종합 검토·문서화하시기 바랍니다."
    )
    sheet_hint = ", ".join(sheets[:4])
    _set_merged_issue_detail(merged, group)
    if not merged.get("reason"):
        merged["reason"] = (
            f"· 부외부채(TUL) 관련 검토 항목 ({sheet_hint})"
            if sheet_hint
            else "· 부외부채(TUL) 관련 검토 항목"
        )
    merged["sheet_no"] = primary.get("sheet_no") or (sheets[0] if sheets else "TUL")
    merged["sheet_title"] = account
    merged["brief_merged"] = True
    merged["off_balance_merged"] = True
    merged["consolidated_from"] = len(group)
    merged.pop("enforcement_cases", None)
    merged.pop("references", None)
    merged["basis"] = "실무 체크리스트(부외부채·약정사항 검토)"
    return merged


def _is_off_balance_note(note: dict[str, Any]) -> bool:
    if _is_protected_note(note) or note.get("brief_merged") or note.get("collateral_memo"):
        return False
    acct = re_engine.note_account(note)
    if acct == "부외부채":
        return True
    return bool(re.search(r"(?:^|\s|/)TUL(?:\s|$|Lead|\d|리드)", _sheet_label(note), re.I))


def consolidate_off_balance_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """부외부채(TUL) 시트별 분산 지적 → 체크·리마인드형 통합 노트 1건."""
    protected: list[dict[str, Any]] = []
    off_balance: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []

    for note in notes:
        if _is_protected_note(note):
            protected.append(note)
            continue
        if _is_off_balance_note(note):
            off_balance.append(note)
        else:
            rest.append(note)

    if len(off_balance) >= 2:
        rest.append(_merge_off_balance_group(off_balance))
    else:
        rest.extend(off_balance)

    rest.extend(protected)
    return rest


def _merge_brief_group(account: str, group: list[dict[str, Any]], doc: Any | None = None) -> dict[str, Any]:
    """동일 계정·경미 지적 다건 → 약식 검토요청 1건."""
    if doc is not None:
        import qc_review
        group = [n for n in group if not qc_review._note_should_suppress(doc, n)]
    if not group:
        return {}
    if len(group) == 1:
        single = copy.deepcopy(group[0])
        single["brief_merged"] = True
        single["defect"] = f"[검토 요청] {account}"
        return single

    cfg = _theme_cfg("inventory_physical_count") if account == "재고자산" else None
    primary = max(group, key=lambda n: _sheet_score(n, cfg))
    merged = copy.deepcopy(primary)

    subitems = sorted({s for n in group for s in _INVENTORY_SUB_RE.findall(_note_text(n))})
    points = [_brief_point(n) for n in group if _brief_point(n)]
    points = list(dict.fromkeys(points))  # 순서 유지 dedup

    sub_label = "·".join(subitems[:5]) if subitems else ""
    if sub_label:
        merged["defect"] = f"[검토 요청] {account} ({sub_label})"
    else:
        merged["defect"] = f"[검토 요청] {account}"

    merged["importance"] = max(
        (n.get("importance", "중") for n in group),
        key=lambda x: _IMP_RANK.get(x, 2),
    )
    if merged["importance"] == "하":
        merged["importance"] = "중"

    bullet = "\n".join(f"· {p}" for p in points[:8])
    merged["to_be"] = (
        "다음 사항을 검토·보완하시기 바랍니다.\n" + bullet
        if bullet
        else "상기 계정 관련 절차·문서화를 종합적으로 검토·보완하시기 바랍니다."
    )
    merged["reason"] = ""
    merged["category"] = "검토요청"
    merged["brief_merged"] = True
    merged["consolidated_from"] = len(group)
    _apply_merged_sheet_label(merged, group)
    _set_merged_issue_detail(merged, group)
    if not merged.get("reason") and points:
        merged["reason"] = "\n".join(f"· {p}" for p in points[:8])
    sheet = merged.get("sheet_no") or _sheet_label(primary)
    merged["summary"] = f"〈{sheet}〉 {merged['defect']} — {points[0][:40]}…" if points else merged["defect"]
    return merged


def _account_brief_eligible(note: dict[str, Any]) -> bool:
    if _is_protected_note(note):
        return False
    if note.get("brief_merged"):
        return False
    if note.get("category") in _SUBSTANTIVE_CATEGORIES and note.get("importance") == "상":
        return False
    if note.get("category") == "절차누락" and note.get("importance") == "상":
        return False
    return bool(re_engine.note_account(note))


def consolidate_account_briefs(notes: list[dict[str, Any]], doc: Any | None = None) -> list[dict[str, Any]]:
    """동일 계정(특히 재고자산 세부품목) 분산 지적 → 약식 검토요청 1건으로 묶기."""
    protected: list[dict[str, Any]] = []
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rest: list[dict[str, Any]] = []

    for note in notes:
        if _is_protected_note(note):
            protected.append(note)
            continue
        acct = re_engine.note_account(note)
        if acct == "우발부채·약정" and not note.get("brief_merged"):
            by_account[acct].append(note)
        elif acct == "부외부채" and not note.get("brief_merged"):
            by_account[acct].append(note)
        elif acct and _account_brief_eligible(note):
            by_account[acct].append(note)
        else:
            rest.append(note)

    if doc is not None:
        import qc_review
        for acct in list(by_account.keys()):
            by_account[acct] = [
                n for n in by_account[acct]
                if not qc_review._note_should_suppress(doc, n)
            ]

    out: list[dict[str, Any]] = list(rest)
    for acct, group in by_account.items():
        has_substantive = any(
            n.get("importance") == "상" and n.get("category") in _SUBSTANTIVE_CATEGORIES
            for n in group
        )
        force_merge = (
            (acct == "재고자산" and len(group) >= 2)
            or (acct == "우발부채·약정" and len(group) >= 2)
            or (acct == "부외부채" and len(group) >= 2)
        )
        soft_merge = (
            len(group) >= 2
            and not has_substantive
            and acct not in ("우발부채·약정", "부외부채")
        )
        if acct == "우발부채·약정" and len(group) >= 2:
            out.append(_merge_contingency_group(group))
        elif acct == "부외부채" and len(group) >= 2:
            out.append(_merge_off_balance_group(group))
        elif force_merge or soft_merge:
            merged = _merge_brief_group(acct, group, doc)
            if merged:
                out.append(merged)
        else:
            out.extend(group)

    out.extend(protected)
    return out


def consolidate_review_notes(
    notes: list[dict[str, Any]],
    doc: Any | None = None,
) -> list[dict[str, Any]]:
    """동일 주제·계정의 분산 지적을 하나로 통합. 전용 조서(실사입회 등)를 우선 앵커로 선택."""
    _ = doc  # 향후 doc 기반 앵커 보강용
    protected: list[dict[str, Any]] = []
    themed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    generic_pool: list[dict[str, Any]] = []

    for note in notes:
        if _is_protected_note(note):
            protected.append(note)
            continue
        tk = _theme_key(note)
        if tk:
            themed[tk].append(note)
        else:
            generic_pool.append(note)

    out: list[dict[str, Any]] = []
    for (theme_id, acct), group in themed.items():
        if len(group) == 1:
            out.append(group[0])
        else:
            out.append(_merge_group(group, theme_id))

    merged_generic: list[dict[str, Any]] = []
    used: set[int] = set()
    for i, note in enumerate(generic_pool):
        if i in used:
            continue
        cluster = [note]
        for j in range(i + 1, len(generic_pool)):
            if j in used:
                continue
            if _similar(note, generic_pool[j]):
                cluster.append(generic_pool[j])
                used.add(j)
        used.add(i)
        if len(cluster) == 1:
            merged_generic.append(note)
        else:
            merged_generic.append(_merge_group(cluster, None))

    out.extend(merged_generic)
    out.extend(protected)
    return out


def _family_mergeable(group: list[dict[str, Any]]) -> bool:
    """동일 계정·동일 조서코드군(Q/Q200)에서 Lead+세부 통합 가능 여부."""
    if len(group) < 2:
        return False
    codes = {_sheet_display_codes(n) for n in group if _sheet_display_codes(n)}
    if len(codes) < 2:
        return False
    accts = {re_engine.note_account(n) for n in group} - {None}
    if len(accts) != 1:
        return False
    if all(_similar(group[0], g) for g in group[1:]):
        return True
    hay = " ".join(_note_text(n) for n in group).lower()
    if sum(1 for kw in _FAMILY_TOPIC_KW if kw in hay) >= 2:
        return True
    has_brief = any(n.get("brief_merged") for n in group)
    has_other = any(not n.get("brief_merged") for n in group)
    if has_brief and has_other and any(kw in hay for kw in _FAMILY_TOPIC_KW):
        return True
    return False


def _merge_lead_detail_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Lead(Q) + 세부(Q200) 등 동일 코드군·유사 지적 → 1건, 조서 'Q 와 Q200'."""
    substantive = [
        n for n in group
        if n.get("category") in _SUBSTANTIVE_CATEGORIES
        or (n.get("category") == "절차누락" and n.get("importance") == "상")
    ]
    cfg = _theme_cfg("cogs_inventory_valuation") if re_engine.note_account(group[0]) == "매출원가" else None
    if substantive:
        primary = max(substantive, key=lambda n: _sheet_score(n, cfg))
    else:
        primary = max(group, key=lambda n: _sheet_score(n, cfg))

    merged = copy.deepcopy(primary)
    if cfg and cfg.get("defect") and not substantive:
        merged["defect"] = cfg["defect"]

    points: list[str] = []
    for n in group:
        pt = _brief_point(n)
        if pt:
            points.append(pt if pt.startswith("·") else f"· {pt}")
        tb = str(n.get("to_be") or "")
        for line in tb.splitlines():
            line = line.strip()
            if line.startswith("·"):
                points.append(line)
            elif line and not line.startswith("다음") and len(line) > 8:
                points.append(f"· {line}")
    points = list(dict.fromkeys(points))

    if points and (any(n.get("brief_merged") for n in group) or len(group) > 1):
        merged["to_be"] = (
            "다음 사항을 검토·보완하시기 바랍니다.\n" + "\n".join(points[:8])
            if points
            else merged.get("to_be", "")
        )

    merged["importance"] = max(
        (n.get("importance", "중") for n in group),
        key=lambda x: _IMP_RANK.get(x, 2),
    )

    bases: list[str] = []
    for n in group:
        b = (n.get("basis") or "").strip()
        if b and b not in bases:
            bases.append(b)
    if bases:
        merged["basis"] = "; ".join(bases)

    merged["consolidated_from"] = len(group)
    merged["lead_detail_merged"] = True
    _apply_merged_sheet_label(merged, group)
    _set_merged_issue_detail(merged, group)
    return merged


def consolidate_lead_detail_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """동일 계정·조서코드군(Q / Q200) 유사 지적 → 1건, 조서명 'Q 와 Q200' 표기."""
    protected: list[dict[str, Any]] = []
    by_family: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rest: list[dict[str, Any]] = []

    for note in notes:
        if _is_protected_note(note):
            protected.append(note)
            continue
        if note.get("lead_detail_merged") or note.get("contingency_merged") or note.get("off_balance_merged"):
            rest.append(note)
            continue
        acct = re_engine.note_account(note) or ""
        root = _sheet_code_root(note)
        if acct and root:
            by_family[(acct, root)].append(note)
        else:
            rest.append(note)

    out: list[dict[str, Any]] = list(rest)
    for _key, group in by_family.items():
        if _family_mergeable(group):
            out.append(_merge_lead_detail_group(group))
        else:
            out.extend(group)

    out.extend(protected)
    return out


def merge_review_notes(
    ai_notes: list[dict[str, Any]],
    rule_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    focus = [n for n in rule_notes if _is_protected_note(n)]
    rules_rest = [n for n in rule_notes if n not in focus]
    merged: list[dict[str, Any]] = list(ai_notes)
    for rn in rules_rest:
        if any(_similar(rn, m) for m in merged):
            for m in merged:
                if _similar(rn, m):
                    if rn.get("basis") and rn["basis"] not in (m.get("basis") or ""):
                        m["basis"] = f"{m.get('basis', '')}; {rn['basis']}".strip("; ")
                    if rn.get("references"):
                        m.setdefault("references", []).extend(rn["references"])
                    if _IMP_RANK.get(rn.get("importance"), 0) > _IMP_RANK.get(m.get("importance"), 0):
                        m["importance"] = rn["importance"]
                    break
            continue
        merged.append(rn)
    merged.extend(focus)
    return merged
