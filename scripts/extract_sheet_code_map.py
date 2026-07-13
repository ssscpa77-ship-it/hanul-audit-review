#!/usr/bin/env python3
"""Hanul FY2026 조서번호 매핑표 → data/sheet_code_map_fy2026.json 생성.

출처:
  - 01.K-IFRS조서/4000_계정별 실증절차_FY2026_v1_상장용(IFRS).xlsx
  - 02.일반기준조서/4000_계정별 실증절차_FY2026_v1_비상장.xlsx
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sheet_code_map_fy2026.json"

_HANUL_CANDIDATES = [
    ROOT.parent / "Hanul DB",
    Path.home() / "Desktop" / "Hanul DB",
    Path("/Users/admin/Desktop/Hanul DB"),
]


def _hanul_root() -> Path:
    for p in _HANUL_CANDIDATES:
        if p.is_dir():
            return p
    return _HANUL_CANDIDATES[-1]


def _source_paths() -> dict[str, Path]:
    base = _hanul_root()
    return {
        "ifrs_listed": base
        / "한울 예시조서/01.K-IFRS조서/4000 실증절차/4000_계정별 실증절차_FY2026_v1_상장용(IFRS).xlsx",
        "non_listed": base
        / "한울 예시조서/02.일반기준조서/4000 실증절차/4000_계정별 실증절차_FY2026_v1_비상장.xlsx",
    }

# 조서번호 → 내부 canonical (variant별 상이 코드만 분기)
CANONICAL: dict[str, str | dict[str, str]] = {
    "A": "현금및예금",
    "B": "유가증권",
    "SAJ": "투자자산",
    "DER": "파생상품",
    "C": "매출채권",
    "D": "기타유동자산",
    "E": "재고자산",
    "E100": "재고자산",
    "F": {"ifrs_listed": "투자부동산", "non_listed": "투자자산"},
    "G": "유형자산",
    "H": "무형자산",
    "I": "기타비유동자산",
    "J": "자산손상",
    "J100": "자산손상",
    "L": "리스",
    "AA": "매입채무",
    "BB.DD": "차입금",
    "CC": "기타유동부채",
    "EE": "퇴직급여",
    "FF": "충당부채",
    "FFF": "기타비유동부채",
    "TUL": "부외부채",
    "CL": "우발부채·약정",
    "GG": "자본",
    "P": "매출",
    "Q": "매출원가",
    "R": "판매관리비",
    "S": "영업외손익",
    "T": "법인세",
    "U": {"ifrs_listed": "매각예정자산", "non_listed": "중단사업"},
    "V": "K-IFRS 최초채택",
    "JV": {"ifrs_listed": "공동약정", "non_listed": "조인트벤처"},
    "SEG": "부문별정보",
    "EST": "회계추정치",
    "IOC": "정보시스템통제",
    "CF": "현금흐름표",
}

_CODE_RE = re.compile(r"^[A-Z][A-Z0-9.]*$")


def extract_index(fp: Path) -> dict[str, str]:
    wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
    ws = wb["4000 실증절차"]
    out: dict[str, str] = {}
    for row in ws.iter_rows(values_only=True):
        if not row or len(row) < 3:
            continue
        code = row[1]
        label = row[2]
        if not code or not label or code == "조서번호":
            continue
        code = str(code).strip().upper().replace(",", ".")
        if not _CODE_RE.match(code):
            continue
        out[code] = str(label).strip()
    wb.close()
    return out


def main() -> int:
    sources = _source_paths()
    missing = [p for p in sources.values() if not p.is_file()]
    if missing:
        print("Missing source files:", *missing, sep="\n  ", file=sys.stderr)
        return 1

    index_labels = {k: extract_index(v) for k, v in sources.items()}
    all_codes = sorted(
        set(index_labels["ifrs_listed"]) | set(index_labels["non_listed"]),
        key=lambda x: (len(x), x),
    )

    canonical: dict[str, dict[str, str]] = {}
    for code in all_codes:
        spec = CANONICAL.get(code)
        if isinstance(spec, dict):
            canonical[code] = spec
        elif isinstance(spec, str):
            canonical[code] = {"default": spec}
        else:
            canonical[code] = {"default": code}

    payload = {
        "version": "FY2026_v1",
        "sources": {k: str(v) for k, v in sources.items()},
        "index_labels": index_labels,
        "canonical": canonical,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(all_codes)} codes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
