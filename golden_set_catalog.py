"""4대 중점 골든셋 회귀 케이스 — 체크리스트 checklist_id 연동."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenSetCase:
    case_id: str
    company_type: str  # 상장 | 비상장
    focus_issue_no: int
    checklist_ids: tuple[str, ...]
    scenario: str
    file_pattern: str = ""
    expected_gap_type: str = "검토누락"  # 검토누락 | 결론미비 | 없음
    must_have_defects: tuple[str, ...] = ()
    must_not_have_defects: tuple[str, ...] = ()
    expected_tier1_min: int = 1
    expected_tier1_max: int = 3
    tier1_recall_target: float = 0.95
    false_positive_max: float = 0.05
    mock_sheet_title: str = ""
    mock_sheet_code: str = ""
    mock_sheet_text: str = ""
    notes: str = ""


def _cases() -> list[GoldenSetCase]:
    return [
        # --- 상장 재고 (L2) ---
        GoldenSetCase(
            "GS-F-L2-01", "상장", 2, ("L2-01",),
            "재고 시트에 저가법 키워드만 있고 항목별 NRV 결론 없음",
            expected_gap_type="결론미비",
            must_have_defects=("[4대중점·결론미비]", "L2-01", "항목별"),
            must_not_have_defects=("[4대중점·검토누락]", "L2-04"),
            mock_sheet_code="E200",
            mock_sheet_title="재고자산 평가",
            mock_sheet_text=(
                "재고자산 잔액 1,200,000,000원. 저가법 적용. "
                "제품군별 합산 평가. 손실 인식 없음."
            ),
            notes="항목별 평가 결론 미비 → 결론미비 노트 기대",
        ),
        GoldenSetCase(
            "GS-F-L2-02", "상장", 2, ("L2-02",),
            "진부화·단종 재고 식별 검토 누락",
            expected_gap_type="검토누락",
            must_have_defects=("[4대중점·검토누락]", "L2-02", "진부화"),
            mock_sheet_code="E200",
            mock_sheet_title="재고자산",
            mock_sheet_text="재고자산 실사 완료. 수량 대사 일치. 취득원가 850,000,000원.",
            notes="진부화·판매부진 검토 흔적 없음",
        ),
        GoldenSetCase(
            "GS-F-L2-04", "상장", 2, ("L2-04",),
            "확정판매계약 재고 NRV 검토 누락",
            expected_gap_type="결론미비",
            must_have_defects=("[4대중점", "L2-04", "확정"),
            mock_sheet_code="E210",
            mock_sheet_title="재고자산 — 확정판매계약",
            mock_sheet_text=(
                "확정판매계약 보유 재고 320,000,000원. 장기체화 재고 포함. "
                "일반 판매가격 기준 순실현가치 산정. 계약 단가 미적용."
            ),
        ),
        GoldenSetCase(
            "GS-F-L2-06", "상장", 2, ("L2-06",),
            "물리적 손상 재고 검토 누락",
            expected_gap_type="검토누락",
            must_have_defects=("[4대중점·검토누락]", "L2-06"),
            mock_sheet_code="E200",
            mock_sheet_title="재고자산 실사",
            mock_sheet_text="재고 실사 수행. 창고 대사 완료. 재고자산 500,000,000원.",
        ),
        GoldenSetCase(
            "GS-F-L2-PASS", "상장", 2, ("L2-01", "L2-02"),
            "재고 저가법·진부화 검토 충분 — 4대중점 노트 없음",
            expected_gap_type="없음",
            expected_tier1_min=0,
            expected_tier1_max=0,
            must_not_have_defects=("[4대중점", "재고"),
            mock_sheet_code="E200",
            mock_sheet_title="재고자산 평가",
            mock_sheet_text=(
                "저가법 항목별 적용. 품목별 NRV 산정·평가손실 인식. "
                "진부화·단종 재고 식별 및 평가손실 반영. 물리적 손상 재고 폐기 처리. "
                "확정판매계약 보유 재고 계약가격 기초 NRV. 원가·판매가 변동 재평가. "
                "부대비용·정상생산능력 배분 검토. 손실부담계약·충당 구분. "
                "결론: 재고 평가 적정."
            ),
            notes="인정문장 충족 → focus 노트 0건",
        ),
        # --- 비상장 지분법 (U2) ---
        GoldenSetCase(
            "GS-F-U2-01", "비상장", 2, ("U2-01",),
            "지분법 적용대상 판단 검토 누락",
            expected_gap_type="검토누락",
            must_have_defects=("[4대중점·검토누락]", "U2-01", "지분법"),
            mock_sheet_code="SAJ300",
            mock_sheet_title="투자자산 — 관계기업",
            mock_sheet_text="관계기업 투자주식 40%. 매도가능증권 분류. 장부금액 2,000,000,000원.",
        ),
        GoldenSetCase(
            "GS-F-U2-02", "비상장", 2, ("U2-02",),
            "내부거래 미실현손익 검토 있으나 제거 결론 미비",
            expected_gap_type="결론미비",
            must_have_defects=("[4대중점·결론미비]", "U2-02", "미실현"),
            mock_sheet_code="SAJ300",
            mock_sheet_title="지분법 투자",
            mock_sheet_text=(
                "지분법 적용. 유의적 영향력 있음. 내부거래 존재. "
                "미실현손익 검토하였으나 소거 절차 미완료."
            ),
        ),
        GoldenSetCase(
            "GS-F-U2-05", "비상장", 2, ("U2-05",),
            "지분법 중지·회복 판단 결론 미비",
            expected_gap_type="결론미비",
            must_have_defects=("[4대중점", "U2-05", "중지"),
            mock_sheet_code="SAJ310",
            mock_sheet_title="지분법 — 누적손실",
            mock_sheet_text=(
                "피투자 누적손실 초과. 지분법중지 해당. 투자장부가액 0원."
            ),
        ),
        GoldenSetCase(
            "GS-F-U2-06", "비상장", 2, ("U2-06",),
            "투자차액·영업권 상각 검토 누락",
            expected_gap_type="검토누락",
            must_have_defects=("[4대중점·검토누락]", "U2-06"),
            mock_sheet_code="SAJ300",
            mock_sheet_title="관계기업 투자",
            mock_sheet_text="지분법 적용. 영업권 포함. 지분법손익 반영.",
        ),
        GoldenSetCase(
            "GS-F-U2-PASS", "비상장", 2, ("U2-01", "U2-02"),
            "지분법 검토 충분 — 4대중점 노트 없음",
            expected_gap_type="없음",
            expected_tier1_min=0,
            expected_tier1_max=0,
            must_not_have_defects=("[4대중점", "지분법"),
            mock_sheet_code="SAJ300",
            mock_sheet_title="지분법 투자자산",
            mock_sheet_text=(
                "유의적 영향력 및 지분법 적용대상 확인. 내부거래 미실현손익 제거 완료. "
                "피투자 연결재무제표 사용. 누적손실 반영. 투자차액 상각·손상검토 수행. "
                "결론: 지분법 회계처리 적정."
            ),
        ),
        # --- 전체 양호 (기존 GS-001 호환) ---
        GoldenSetCase(
            "GS-001", "상장", 0, (),
            "양호 조서 — 4대중점·Tier1 0건 기대",
            file_pattern="F_F_*.xlsx",
            expected_gap_type="없음",
            expected_tier1_min=0,
            expected_tier1_max=0,
            must_not_have_defects=("교차합 불일치", "[4대중점"),
            notes="파트너 확정 후 last_verified 기재",
        ),
    ]


GOLDEN_SET_CASES: list[GoldenSetCase] = _cases()


def cases_for_focus(*, issue_no: int | None = None, company_type: str | None = None) -> list[GoldenSetCase]:
    out = GOLDEN_SET_CASES
    if issue_no is not None:
        out = [c for c in out if c.focus_issue_no == issue_no]
    if company_type:
        out = [c for c in out if c.company_type == company_type]
    return out
