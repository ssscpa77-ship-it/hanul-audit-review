"""감사조서 시트 분리 — 서술(narrative) vs 수치(amount_grid) 영역."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from parser import ParsedDocument, to_number

_NARRATIVE_HINTS = re.compile(
    r"감사메모|결론|검토|수행|절차|확인|입회|조회|분석|판단|근거|의견|"
    r"결론적으로|To\s*Be|to\s*be|감사대응|증빙|샘플링|표본",
    re.I,
)
_AMOUNT_HEADER = re.compile(
    r"금액|잔액|합계|당기|전기|기말|차변|대변|수량|원|백만|천원|%"
    r"|TE|PM|CTT|중요성|합\s*계|소계",
    re.I,
)
_PROCEDURE_LINE = re.compile(
    r"^\s*[\d①②③④⑤⑥⑦⑧⑨⑩]+[\.\)]\s*|^\s*[-•]\s+|실시|수행함|확인함",
    re.I,
)


@dataclass
class SheetRegion:
    sheet: str
    region_type: str  # narrative | amount_grid | header | mixed
    text: str = ""
    row_start: int = 0
    row_end: int = 0
    numeric_density: float = 0.0


@dataclass
class SegmentedWorkpaper:
    file_name: str
    narrative_blocks: list[SheetRegion] = field(default_factory=list)
    amount_grids: list[SheetRegion] = field(default_factory=list)
    header_blocks: list[SheetRegion] = field(default_factory=list)

    def narrative_text(self) -> str:
        return "\n\n".join(b.text for b in self.narrative_blocks if b.text.strip())

    def summary(self) -> dict[str, int]:
        return {
            "narrative_blocks": len(self.narrative_blocks),
            "amount_grids": len(self.amount_grids),
            "header_blocks": len(self.header_blocks),
        }


def _row_numeric_density(row: pd.Series) -> float:
    cells = [str(c).strip() for c in row if str(c).strip()]
    if not cells:
        return 0.0
    nums = sum(1 for c in cells if to_number(c) is not None)
    return nums / len(cells)


def _classify_row(row: pd.Series, row_text: str) -> str:
    if _NARRATIVE_HINTS.search(row_text) or _PROCEDURE_LINE.search(row_text):
        return "narrative"
    dens = _row_numeric_density(row)
    if dens >= 0.5 and _AMOUNT_HEADER.search(row_text):
        return "amount_grid"
    if dens >= 0.7:
        return "amount_grid"
    if dens <= 0.2 and len(row_text) > 20:
        return "narrative"
    return "mixed"


def segment_dataframe(df: pd.DataFrame, *, sheet: str = "") -> list[SheetRegion]:
    """단일 시트 DataFrame을 영역별로 분리."""
    if df.empty:
        return []

    regions: list[SheetRegion] = []
    current_type = ""
    current_rows: list[int] = []
    current_text: list[str] = []

    def _flush() -> None:
        nonlocal current_type, current_rows, current_text
        if not current_rows:
            return
        text = "\n".join(current_text)
        dens = sum(_row_numeric_density(df.iloc[i]) for i in current_rows) / len(current_rows)
        regions.append(
            SheetRegion(
                sheet=sheet,
                region_type=current_type or "mixed",
                text=text,
                row_start=current_rows[0],
                row_end=current_rows[-1],
                numeric_density=dens,
            )
        )
        current_type = ""
        current_rows = []
        current_text = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_text = " ".join(str(c).strip() for c in row if str(c).strip())
        if not row_text:
            if len(current_rows) >= 3:
                _flush()
            continue
        rtype = _classify_row(row, row_text)
        if rtype != current_type and current_rows:
            _flush()
        current_type = rtype
        current_rows.append(idx)
        current_text.append(row_text)
    _flush()
    return regions


def segment_document(doc: ParsedDocument) -> SegmentedWorkpaper:
    """ParsedDocument 전체를 서술/수치로 분리."""
    out = SegmentedWorkpaper(file_name=doc.file_name)
    for table in doc.tables:
        sheet = str(table.attrs.get("source") or table.attrs.get("title") or "sheet")
        for region in segment_dataframe(table, sheet=sheet):
            if region.region_type == "narrative":
                out.narrative_blocks.append(region)
            elif region.region_type == "amount_grid":
                out.amount_grids.append(region)
            elif region.region_type == "header":
                out.header_blocks.append(region)
            else:
                if region.numeric_density >= 0.45:
                    out.amount_grids.append(region)
                else:
                    out.narrative_blocks.append(region)

        table.attrs["segment_regions"] = [
            {"type": r.region_type, "rows": (r.row_start, r.row_end)}
            for r in segment_dataframe(table, sheet=sheet)
        ]
    return out
