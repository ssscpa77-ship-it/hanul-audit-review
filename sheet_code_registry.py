"""Hanul FY2026 조서번호(영문 코드) ↔ 계정과목 매핑.

출처 (Hanul DB 한울 예시조서):
  - 01.K-IFRS조서/4000_계정별 실증절차_FY2026_v1_상장용(IFRS).xlsx  → 상장·K-IFRS
  - 02.일반기준조서/4000_계정별 실증절차_FY2026_v1_비상장.xlsx      → 비상장

데이터: data/sheet_code_map_fy2026.json (scripts/extract_sheet_code_map.py 로 재생성)
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent / "data" / "sheet_code_map_fy2026.json"

_mapping_variant: ContextVar[str] = ContextVar("sheet_mapping_variant", default="ifrs_listed")

# 시트명 변형 → 표준 조서번호 (목차에 없어도 시트 탭에 존재)
_CODE_ALIASES: dict[str, str] = {
    "BB": "BB.DD",
    "DD": "BB.DD",
    "BB,DD": "BB.DD",
}

_SHEET_INDEX_NOISE = frozenset({
    "MEMO", "메모", "NOTE", "전기말", "당기말", "전년말", "당년말",
    "LEAD", "리드", "SUMMARY", "요약", "개요", "INDEX", "목차",
})
_PERIOD_LABEL_RE = re.compile(r"^\d{4}년말$", re.I)


def set_mapping_variant(is_listed: bool | None) -> None:
    """상장 여부에 따라 매핑 variant 설정 (상장=ifrs_listed, 비상장=non_listed)."""
    _mapping_variant.set("ifrs_listed" if is_listed else "non_listed")


def get_mapping_variant() -> str:
    return _mapping_variant.get()


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def registry_version() -> str:
    return str(_load_registry().get("version", ""))


def index_label(code: str, *, variant: str | None = None) -> str | None:
    """조서번호의 공식 계정과목 원문(한울 목차)."""
    v = variant or get_mapping_variant()
    labels = _load_registry().get("index_labels", {}).get(v, {})
    return labels.get(_normalize_code_key(code))


def all_index_codes(*, variant: str | None = None) -> frozenset[str]:
    v = variant or get_mapping_variant()
    return frozenset(_load_registry().get("index_labels", {}).get(v, {}).keys())


def _normalize_code_key(code: str) -> str:
    c = str(code or "").strip().upper().replace(",", ".")
    return _CODE_ALIASES.get(c, c)


def is_sheet_index_token(token: str) -> bool:
    """숫자 조서·MEMO·전기말 등 비인덱스 토큰 제외."""
    t = str(token or "").strip().upper().replace(",", ".")
    if not t:
        return False
    t = re.sub(r"(?:\s*(?:LEAD|리드))$", "", t, flags=re.I).strip()
    if t in _SHEET_INDEX_NOISE or _PERIOD_LABEL_RE.match(t):
        return False
    if re.fullmatch(r"\d+", t):
        return False
    return parse_sheet_code(t) is not None


def display_sheet_index(label: str) -> str:
    """유효한 계정과목 조서 인덱스만 반환 (예: D, E100, BB.DD)."""
    raw = str(label or "").strip()
    if not raw or raw == "-":
        return ""
    head = re.sub(r"^.*/", "", raw).strip()
    if not head:
        return ""
    head = head.split()[0].upper().replace(",", ".")
    head = re.sub(r"(?:\s*(?:LEAD|리드))$", "", head, flags=re.I).strip()
    if not is_sheet_index_token(head):
        return ""
    if head in _CODE_ALIASES:
        return _CODE_ALIASES[head]
    return head


def sheet_code_for_account(account: str, *, variant: str | None = None) -> str | None:
    """canonical 계정과목 → 대표 조서 인덱스 (짧은 코드 우선)."""
    acct = str(account or "").strip()
    if not acct:
        return None
    v = variant or get_mapping_variant()
    candidates = [code for code, name in build_sheet_code_map(variant=v).items() if name == acct]
    if not candidates:
        return None

    def _sort_key(code: str) -> tuple:
        has_digit = bool(re.search(r"\d", code))
        return (has_digit, len(code), code)

    return sorted(candidates, key=_sort_key)[0]


def parse_sheet_code(label: str) -> str | None:
    """시트명·조서번호 문자열에서 표준 조서번호 추출."""
    raw = str(label or "").strip().upper()
    if not raw:
        return None
    token = raw.split()[0].replace(",", ".")
    if token in _CODE_ALIASES:
        token = _CODE_ALIASES[token]

    canonical_defs = _load_registry().get("canonical", {})
    known = sorted(canonical_defs.keys(), key=len, reverse=True)

    if token in canonical_defs:
        return token
    for code in known:
        if token == code or token.startswith(f"{code}-") or token.startswith(f"{code}."):
            return code
        if token.startswith(code) and len(token) > len(code) and token[len(code) :].isdigit():
            return code if code in canonical_defs else code

    m = re.match(r"^([A-Z]+\d+)", token)
    if m:
        key = m.group(1)
        if key in canonical_defs:
            return key
        base = re.match(r"^([A-Z]+)", key)
        if base:
            aliased = _CODE_ALIASES.get(base.group(1), base.group(1))
            if aliased in canonical_defs:
                return aliased

    m = re.match(r"^([A-Z]+)\d+$", token)
    if m:
        aliased = _CODE_ALIASES.get(m.group(1), m.group(1))
        if aliased in canonical_defs:
            return aliased

    m = re.match(r"^([A-Z]+)", token)
    if m:
        key = m.group(1)
        if key in canonical_defs:
            return key
    return None


def canonical_account(code: str, *, variant: str | None = None) -> str | None:
    """조서번호 → 내부 canonical 계정과목."""
    key = parse_sheet_code(code)
    if not key:
        return None
    v = variant or get_mapping_variant()
    spec = _load_registry().get("canonical", {}).get(key)
    if not spec:
        return None
    if isinstance(spec, str):
        return spec
    if v in spec:
        return spec[v]
    return spec.get("default") or spec.get("ifrs_listed")


def account_from_label(label: str, *, variant: str | None = None) -> str | None:
    """시트명/조서번호 라벨 → canonical 계정."""
    key = parse_sheet_code(label)
    if not key:
        return None
    return canonical_account(key, variant=variant)


def build_sheet_code_map(*, variant: str = "ifrs_listed") -> dict[str, str]:
    """variant별 flat SHEET_CODE_MAP (review_engine 호환)."""
    out: dict[str, str] = {}
    defs = _load_registry().get("canonical", {})
    for code, spec in defs.items():
        acct = canonical_account(code, variant=variant)
        if acct:
            out[code] = acct
    out.setdefault("BB", out.get("BB.DD", "차입금"))
    out.setdefault("DD", out.get("BB.DD", "차입금"))
    out.setdefault("J100", out.get("J", "자산손상"))
    return out


def label_synonyms(*, variant: str | None = None) -> dict[str, tuple[str, ...]]:
    """공식 목차 라벨 → 토큰 (ACCOUNT_TAXONOMY 보강용)."""
    v = variant or get_mapping_variant()
    labels = _load_registry().get("index_labels", {}).get(v, {})
    out: dict[str, list[str]] = {}
    for _code, label in labels.items():
        acct = canonical_account(_code, variant=v)
        if not acct:
            continue
        parts = [p.strip() for p in re.split(r"[,·/]", label) if p.strip()]
        tokens = [label] + parts
        out.setdefault(acct, []).extend(tokens)
    return {k: tuple(dict.fromkeys(v)) for k, v in out.items()}


def mapping_table_markdown(*, variant: str) -> str:
    """작업지시서용 마크다운 표."""
    labels = _load_registry().get("index_labels", {}).get(variant, {})
    lines = ["| 조서번호 | 계정과목 (한울 목차) | 내부 canonical |", "|----------|------------------------|----------------|"]
    for code in sorted(labels.keys(), key=lambda x: (len(x), x)):
        acct = canonical_account(code, variant=variant) or "-"
        lines.append(f"| {code} | {labels[code]} | {acct} |")
    return "\n".join(lines)
