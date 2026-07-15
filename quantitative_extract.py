"""정량 판단용 구조화 추출 — RAG 아님, 추출 → 계산 → 규칙 파이프라인."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from parser import ParsedDocument, to_number
from review_engine import Materiality, extract_materiality
from workpaper_segment import SegmentedWorkpaper, segment_document


@dataclass
class AmountFact:
    sheet: str
    label: str
    value: float
    row: int = -1
    col: int = -1
    period: str = ""
    is_total: bool = False


@dataclass
class QuantitativeSheet:
    sheet: str
    facts: list[AmountFact] = field(default_factory=list)
    row_labels: list[str] = field(default_factory=list)


@dataclass
class QuantitativeFacts:
    materiality: Materiality
    sheets: list[QuantitativeSheet] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "materiality": {
                "te": self.materiality.te,
                "pm": self.materiality.pm,
                "ctt": self.materiality.ctt,
            },
            "sheet_count": len(self.sheets),
            "fact_count": sum(len(s.facts) for s in self.sheets),
            "anomaly_count": len(self.anomalies),
        }


_TOTAL_RE = __import__("re").compile(r"합\s*계|소계|총계|total|sum", __import__("re").I)
_PERIOD_RE = __import__("re").compile(r"당기|전기|기말|당년|전년|\d{4}년", __import__("re").I)


def _extract_from_table(df: pd.DataFrame, *, sheet: str) -> QuantitativeSheet:
    qs = QuantitativeSheet(sheet=sheet)
    if df.empty:
        return qs

    period_cols: dict[int, str] = {}
    for c in range(df.shape[1]):
        col_text = " ".join(str(df.iloc[r, c]) for r in range(min(5, len(df))))
        m = _PERIOD_RE.search(col_text)
        if m:
            period_cols[c] = m.group(0)

    for r in range(len(df)):
        row = df.iloc[r]
        label = str(row.iloc[0]).strip() if len(row) else ""
        if label:
            qs.row_labels.append(label)
        is_total = bool(_TOTAL_RE.search(label))
        for c in range(1, len(row)):
            val = to_number(row.iloc[c])
            if val is None:
                continue
            qs.facts.append(
                AmountFact(
                    sheet=sheet,
                    label=label or f"row{r}",
                    value=val,
                    row=r,
                    col=c,
                    period=period_cols.get(c, ""),
                    is_total=is_total,
                )
            )
    return qs


def extract_quantitative_facts(
    doc: ParsedDocument,
    *,
    segmented: SegmentedWorkpaper | None = None,
    materiality: Materiality | None = None,
) -> QuantitativeFacts:
    """조서에서 정량 facts 추출 (벡터/RAG 미사용)."""
    mat = materiality or extract_materiality(doc)
    seg = segmented or segment_document(doc)
    out = QuantitativeFacts(materiality=mat)

    for table in doc.tables:
        sheet = str(table.attrs.get("source") or table.attrs.get("title") or "sheet")
        qs = _extract_from_table(table, sheet=sheet)
        if qs.facts:
            out.sheets.append(qs)

    out.anomalies = detect_anomalies(out)
    return out


def detect_anomalies(facts: QuantitativeFacts) -> list[dict[str, Any]]:
    """중요성 대비·이상치 탐지 (규칙 기반)."""
    anomalies: list[dict[str, Any]] = []
    threshold = facts.materiality.min_calc_threshold()

    for sheet in facts.sheets:
        totals = [f for f in sheet.facts if f.is_total]
        for f in totals:
            if abs(f.value) >= threshold:
                anomalies.append(
                    {
                        "type": "materiality_exceeds",
                        "sheet": sheet.sheet,
                        "label": f.label,
                        "value": f.value,
                        "threshold": threshold,
                    }
                )
        values = [f.value for f in sheet.facts if not f.is_total]
        if len(values) >= 5:
            avg = sum(values) / len(values)
            for f in sheet.facts:
                if not f.is_total and avg > 0 and abs(f.value) > avg * 10:
                    anomalies.append(
                        {
                            "type": "balance_outlier",
                            "sheet": sheet.sheet,
                            "label": f.label,
                            "value": f.value,
                            "avg": avg,
                        }
                    )
    return anomalies
