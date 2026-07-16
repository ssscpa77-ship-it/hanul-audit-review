"""4대 중점 체크리스트 — 항목별 구체적 검토 지침 (보도자료·감리지적사례 기반).

`focus_checklist_catalog` 행에 review_procedure·related_sheet_codes·ai_review_questions 를 보강한다.
"""

from __future__ import annotations

from typing import TypedDict


class GuidanceSpec(TypedDict, total=False):
    review_procedure: str
    related_sheet_codes: tuple[str, ...]
    ai_review_questions: tuple[str, ...]
    trigger_accounts: tuple[str, ...]
    na_condition: str


# checklist_id → 구체적 지침 (상장 L* / 비상장 U*)
CHECKLIST_GUIDANCE: dict[str, GuidanceSpec] = {
    # ── 상장 L1 국외 매출·매출채권 ──
    "L1-01": {
        "review_procedure": (
            "① C·P Lead에서 국외·수출 거래 목록·인도조건(FOB/CIF 등) 확인 "
            "② 수행의무 이행·통제 이전 시점과 매출 인식 시점 대사 "
            "③ 선적일만 근거로 인식한 거래·대리점 경유 거래 식별 "
            "④ 인도조건 판단 근거·결론 문장 기재 여부 확인"
        ),
        "related_sheet_codes": ("C", "P"),
        "ai_review_questions": (
            "FOB 선적 시점만으로 수익을 인식했는가?",
            "실제 인도·통제 이전 시점과 인식 시점이 일치하는가?",
            "인도조건별 수행의무 이행 근거가 문서화되어 있는가?",
        ),
    },
    "L1-02": {
        "review_procedure": (
            "① 국외 매출 계약·수출신고·납품 증빙 대사 "
            "② 실질 납품 없이 인식된 매출(허위·가공) 여부 점검 "
            "③ 수출입 실적·통관 자료와 장부 대사 "
            "④ 이상 거래에 대한 추가 절차·결론 기재 확인"
        ),
        "related_sheet_codes": ("C", "P"),
        "ai_review_questions": (
            "계약·신고·납품 증빙 없이 인식된 매출이 있는가?",
            "허위·가공 매출에 대한 실질 검토가 문서화되어 있는가?",
        ),
    },
    "L1-03": {
        "review_procedure": (
            "① C Lead에서 국외·종속 해외채권 잔액·연령 확인 "
            "② 신용위험 유의적 증가 평가(12개월/전체기간 ECL) 문서화 "
            "③ 손실충당금 산정 모형·가정·결론 확인 "
            "④ '기대신용손실 반영 완료' 등 인정문장 기재"
        ),
        "related_sheet_codes": ("C",),
        "ai_review_questions": (
            "국외·종속 해외채권에 ECL이 계상되어 있는가?",
            "신용위험 증가 평가 및 손실충당금 산정 근거가 있는가?",
        ),
    },
    "L1-04": {
        "review_procedure": (
            "① 환율·지정학·수출입 제한 등 거시요인이 ECL에 반영되었는지 확인 "
            "② 외화환산·cut-off와 연계 검토 "
            "③ 거시요인 평가 결론·민감도 분석 문서화"
        ),
        "related_sheet_codes": ("C", "P"),
        "ai_review_questions": (
            "환율·지정학 리스크가 ECL 산정에 반영되었는가?",
            "거시요인 평가 결론이 문서화되어 있는가?",
        ),
    },
    # ── 상장 L2 재고 ──
    "L2-01": {
        "review_procedure": (
            "① E Lead·세부조서에서 품목별 NRV 산정표·저가법 적용 확인 "
            "② 평가손실 인식 품목·금액·근거 문서화 "
            "③ 제품군 일괄평가·일부 품목만 평가 등 red flag 점검 "
            "④ '항목별 NRV 산정·평가손실 인식' 결론문 기재"
        ),
        "related_sheet_codes": ("E", "E100"),
        "ai_review_questions": (
            "저가법이 항목별로 적용되었는가?",
            "NRV 산정 및 평가손실 인식 결론이 구체적으로 기재되어 있는가?",
        ),
    },
    "L2-02": {
        "review_procedure": (
            "① 진부화·단종·판매부진 재고 식별 절차 확인 "
            "② 해당 재고 NRV·평가손실 인식 여부 "
            "③ 품질문제·체화 재고 목록·금액 대사"
        ),
        "related_sheet_codes": ("E",),
        "ai_review_questions": (
            "진부화·단종 재고가 식별·평가되었는가?",
            "판매부진 재고에 평가손실이 인식되었는가?",
        ),
    },
    "L2-03": {
        "review_procedure": (
            "① 손실부담계약 관련 재고·충당부채 구분 확인 "
            "② 저가법 평가와 충당부채 인식 기준 대사 "
            "③ 초과 계약물량·예상손실 반영 결론"
        ),
        "related_sheet_codes": ("E", "FF"),
        "ai_review_questions": (
            "재고 평가손실과 손실부담계약 충당이 구분되어 있는가?",
            "충당부채 인식 요건·금액이 문서화되어 있는가?",
        ),
    },
    "L2-04": {
        "review_procedure": (
            "① 확정판매계약 보유 재고 식별 "
            "② NRV 산정 시 계약가격(일반 판매가 아님) 적용 확인 "
            "③ 장기체화 재고 평가 결론"
        ),
        "related_sheet_codes": ("E",),
        "ai_review_questions": (
            "확정판매계약 재고에 계약가격 기초 NRV가 적용되었는가?",
            "일반 판매가만 사용한 품목이 없는가?",
        ),
    },
    "L2-05": {
        "review_procedure": (
            "① 원가 상승·판매가 하락 동시 발생 시 NRV 재평가 여부 "
            "② 평가손실 인식 시점·금액 문서화 "
            "③ 당기 변동 요인·결론 기재"
        ),
        "related_sheet_codes": ("E",),
        "ai_review_questions": (
            "원가·판매가 동시 변동 시 NRV가 재평가되었는가?",
            "평가손실 인식 결론이 있는가?",
        ),
    },
    "L2-06": {
        "review_procedure": (
            "① 실사·입회(E100)에서 물리적 손상·유통기한 경과 재고 확인 "
            "② 파손·감모·폐기 대상 식별·평가손실 인식 "
            "③ 손상 재고 목록·금액 문서화"
        ),
        "related_sheet_codes": ("E", "E100"),
        "ai_review_questions": (
            "물리적 손상·유통기한 경과 재고가 식별되었는가?",
            "해당 재고에 평가손실이 인식되었는가?",
        ),
    },
    "L2-07": {
        "review_procedure": (
            "① 재고 원가 산정(부대비용·정상생산능력·고정비 배분) 검토 "
            "② 비정상 생산능력 고정비 처리 확인 "
            "③ 원가 배분 결론·산식 문서화"
        ),
        "related_sheet_codes": ("E", "Q"),
        "ai_review_questions": (
            "부대비용·정상생산능력 기준 원가 배분이 적정한가?",
            "비정상 생산 시 고정비 처리가 문서화되어 있는가?",
        ),
    },
    # ── 상장 L3 투자부동산 ──
    "L3-01": {
        "review_procedure": (
            "① F Lead에서 보유목적(임대·자가사용·처분)별 분류 확인 "
            "② 임대 부분 투자부동산 vs 유형자산 구분 "
            "③ 분류 변경·재분류 결론 문서화"
        ),
        "related_sheet_codes": ("F", "G"),
        "ai_review_questions": (
            "임대·자가사용 목적에 따른 분류가 적정한가?",
            "투자부동산·유형자산 오분류가 없는가?",
        ),
    },
    "L3-02": {
        "review_procedure": (
            "① 공정가치모형 선택 시 당기 평가 수행 여부 "
            "② 감정·DCF 등 평가 방법·가정·결과 문서화 "
            "③ 변동손익 인식 결론"
        ),
        "related_sheet_codes": ("F",),
        "ai_review_questions": (
            "공정가치모형 적용 시 당기 평가가 수행되었는가?",
            "평가 방법·가정·결론이 문서화되어 있는가?",
        ),
    },
    "L3-03": {
        "review_procedure": (
            "① 투자부동산 주석 공시 항목(공정가치·변동·장부금액) 확인 "
            "② 원가모형 적용 시 공정가치 주석 포함 여부 "
            "③ 공시 누락·불충분 항목 식별"
        ),
        "related_sheet_codes": ("F",),
        "ai_review_questions": (
            "투자부동산 주석 공시가 충분한가?",
            "원가모형 적용 시 공정가치 주석이 있는가?",
        ),
    },
    # ── 상장 L4 충당·우발 ──
    "L4-01": {
        "review_procedure": (
            "① FF·CL에서 보증·손실부담 관련 충당 인식요건 검토 "
            "② 최선의 추정치·현재가치 측정 문서화 "
            "③ 낙관적 가정만으로 충당 미계상 여부 점검"
        ),
        "related_sheet_codes": ("FF", "CL"),
        "ai_review_questions": (
            "보증·손실부담 충당 인식요건이 충족되는가?",
            "충당부채 측정·결론이 문서화되어 있는가?",
        ),
    },
    "L4-02": {
        "review_procedure": (
            "① 소송·분쟁 현황·진행 단계 확인 "
            "② 패소 가능성·충당 인식 여부 "
            "③ 소송 관련 충당·공시 결론"
        ),
        "related_sheet_codes": ("FF", "CL"),
        "ai_review_questions": (
            "소송·분쟁에 대한 충당 인식이 검토되었는가?",
            "패소 가능성 반영 결론이 있는가?",
        ),
    },
    "L4-03": {
        "review_procedure": (
            "① CL에서 연대·지급보증·약정 우발부채 식별 "
            "② 유출가능성·공시 요건 검토 "
            "③ 계약 변경(구두 합의 등) 반영·공시 확인"
        ),
        "related_sheet_codes": ("CL",),
        "ai_review_questions": (
            "연대·약정 우발부채가 식별·공시되었는가?",
            "지급보증·약정 변경이 반영되었는가?",
        ),
    },
    # ── 비상장 U1 장기공사 ──
    "U1-01": {
        "review_procedure": (
            "① P·C Lead에서 공사·수주 거래와 수익인식 시점 확인 "
            "② 진행기준 적용 여부·세금계산서 발행 시점과 구분 "
            "③ 수행의무·기간에 걸친 인식 결론 문서화"
        ),
        "related_sheet_codes": ("P", "C"),
        "ai_review_questions": (
            "진행기준이 적용되었는가?",
            "세금계산서 발행 시점만으로 매출을 인식하지 않았는가?",
        ),
    },
    "U1-02": {
        "review_procedure": (
            "① 총공사예정원가·진행률 산정 근거 확인 "
            "② 설계변경·공사지연 반영 여부 "
            "③ 진행률·수익 인식 결론 문서화"
        ),
        "related_sheet_codes": ("P",),
        "ai_review_questions": (
            "예정원가 변경이 진행률에 반영되었는가?",
            "진행률 산정 근거·결론이 있는가?",
        ),
    },
    "U1-03": {
        "review_procedure": (
            "① 준공·도급 정산 시점 수익·원가 반영 확인 "
            "② 최종 원가와 예정원가 차이 조정 "
            "③ 정산 반영 결론"
        ),
        "related_sheet_codes": ("P",),
        "ai_review_questions": (
            "준공 후 도급 정산이 수익·원가에 반영되었는가?",
            "정산 차이 조정 결론이 문서화되어 있는가?",
        ),
    },
    "U1-04": {
        "review_procedure": (
            "① 분양·공사원가 vs 판관비(수수료·금융비용) 구분 "
            "② 자본화 대상 금융비용 식별 "
            "③ 원가 분류 결론"
        ),
        "related_sheet_codes": ("P", "Q", "R"),
        "ai_review_questions": (
            "금융비용·수수료가 공사원가와 판관비로 적정 분류되었는가?",
        ),
    },
    "U1-05": {
        "review_procedure": (
            "① 손실부담계약·향후 공사손실 예상 여부 확인 "
            "② 공사손실충당부채 인식 검토 "
            "③ 충당 인식·측정 결론"
        ),
        "related_sheet_codes": ("P", "FF"),
        "ai_review_questions": (
            "손실부담계약에 대한 공사손실충당이 검토되었는가?",
        ),
    },
    # ── 비상장 U2 지분법 ──
    "U2-01": {
        "review_procedure": (
            "① SAJ Lead에서 지분율·유의적 영향력 판단 "
            "② 지분법 적용대상·특례(매도가능 등) 오적용 여부 "
            "③ 적용대상 결론 문서화"
        ),
        "related_sheet_codes": ("SAJ", "B"),
        "ai_review_questions": (
            "유의적 영향력·지분법 적용대상이 검토되었는가?",
            "특례 오적용이 없는가?",
        ),
    },
    "U2-02": {
        "review_procedure": (
            "① 내부거래(유형자산·재고 등) 식별 "
            "② 미실현손익 제거 금액·방법 확인 "
            "③ '미실현손익 제거 완료' 결론문 기재"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "내부거래 미실현손익이 제거되었는가?",
            "제거 결론이 문서화되어 있는가?",
        ),
    },
    "U2-03": {
        "review_procedure": (
            "① 피투자 재무제표(연결 우선) 사용 여부 "
            "② 누적손실·지분법 중지 반영 "
            "③ 회계정책·결산일 차이 조정"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "연결재무제표 또는 신뢰성 있는 재무제표를 사용했는가?",
            "누적손실이 반영되었는가?",
        ),
    },
    "U2-04": {
        "review_procedure": (
            "① 피투자 가결산·재평가(토지 등) 반영 확인 "
            "② 조정 분개·근거 문서화 "
            "③ 재평가 미반영 가결산 사용 여부"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "피투자 재평가·가결산 조정이 반영되었는가?",
        ),
    },
    "U2-05": {
        "review_procedure": (
            "① 지분법 중지 요건(누적손실 등) 충족 여부 "
            "② 중지 시점·회복 시점 판단 "
            "③ 중지·회복 결론 문서화"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "지분법 중지·회복 판단이 문서화되어 있는가?",
            "회복 시점 검토가 있는가?",
        ),
    },
    "U2-06": {
        "review_procedure": (
            "① 투자차액·영업권 식별·상각 기간 확인 "
            "② 손상검토(현금창출단위) 수행 여부 "
            "③ 상각·손상 결론"
        ),
        "related_sheet_codes": ("SAJ", "J"),
        "ai_review_questions": (
            "투자차액·영업권 상각이 검토되었는가?",
            "손상검토 결론이 있는가?",
        ),
    },
    "U2-07": {
        "review_procedure": (
            "① 피투자 배당·자본변동 수취 시 지분법 반영 "
            "② 기타포괄손익·자본변동 대사 "
            "③ 반영 결론 문서화"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "배당·자본변동이 지분법에 반영되었는가?",
        ),
    },
    "U2-08": {
        "review_procedure": (
            "① 지분율 변동·추가취득 시 회계처리(종속/관계/지분법) "
            "② 재측정·영향력 변동 검토 "
            "③ 변동 시 회계처리 결론"
        ),
        "related_sheet_codes": ("SAJ",),
        "ai_review_questions": (
            "지분율 변동 시 회계처리가 검토되었는가?",
        ),
    },
    # ── 비상장 U3 충당·우발 ──
    "U3-01": {
        "review_procedure": (
            "① FF에서 품질보증·제품결함 충당 인식요건 검토 "
            "② 구조적 결함·예상 보증비용 추정 "
            "③ 충당 인식·측정 결론"
        ),
        "related_sheet_codes": ("FF", "CL"),
        "ai_review_questions": (
            "품질보증 충당이 검토·계상되었는가?",
        ),
    },
    "U3-02": {
        "review_procedure": (
            "① 소송·분쟁 현황·심급 진행 확인 "
            "② '진행중'만으로 충당 미계상 여부 점검 "
            "③ 충당·공시 결론"
        ),
        "related_sheet_codes": ("FF", "CL"),
        "ai_review_questions": (
            "소송 충당 인식이 검토되었는가?",
            "2심 진행만으로 충당을 면제하지 않았는가?",
        ),
    },
    "U3-03": {
        "review_procedure": (
            "① CL에서 PF·지급보증·채무인수 약정 식별 "
            "② 우발부채 공시 요건·금액 확인 "
            "③ 공시 누락 여부"
        ),
        "related_sheet_codes": ("CL",),
        "ai_review_questions": (
            "PF·지급보증 우발부채가 공시되었는가?",
        ),
    },
    "U3-04": {
        "review_procedure": (
            "① 지급보증 한도·상세 내역 공시 확인 "
            "② 연대보증·담보 제공 범위 대사 "
            "③ 과소·누락 공시 식별"
        ),
        "related_sheet_codes": ("CL",),
        "ai_review_questions": (
            "지급보증 한도·상세가 충분히 공시되었는가?",
        ),
    },
    # ── 비상장 U4 특수관계자 ──
    "U4-01": {
        "review_procedure": (
            "① 특수관계자 범위(법적·실질) 식별 "
            "② 누락 관계자·지배구조 변경 반영 "
            "③ 식별 결론·목록 문서화"
        ),
        "related_sheet_codes": ("CL", "GG"),
        "ai_review_questions": (
            "특수관계자 범위가 충분히 식별되었는가?",
        ),
        "na_condition": "특수관계자 거래가 전혀 없고 주석에도 해당 없음",
    },
    "U4-02": {
        "review_procedure": (
            "① 주석·CL에서 거래총액·잔액 공시 확인 "
            "② 특수관계자별 구분 공시 "
            "③ 누락·불완전 공시 식별"
        ),
        "related_sheet_codes": ("CL",),
        "ai_review_questions": (
            "거래총액·잔액이 특수관계자별로 공시되었는가?",
        ),
    },
    "U4-03": {
        "review_procedure": (
            "① 비경상 거래(대여·매각·상계 등) 식별 "
            "② 부적절 상계·대손 미반영 여부 "
            "③ 비경상 거래 공시·결론"
        ),
        "related_sheet_codes": ("CL", "C"),
        "ai_review_questions": (
            "비경상 거래가 공시되었는가?",
            "부적절 상계가 없는가?",
        ),
    },
    "U4-04": {
        "review_procedure": (
            "① 지급보증·풋옵션·투자약정 식별 "
            "② 특수관계자 제공 보증·약정 공시 "
            "③ 누락 약정 확인"
        ),
        "related_sheet_codes": ("CL",),
        "ai_review_questions": (
            "지급보증·풋옵션 약정이 공시되었는가?",
        ),
    },
    "U4-05": {
        "review_procedure": (
            "① 전환우선주·풋옵션 금융부채 vs 자본 분류 "
            "② IPO 실패·행사 조건 반영 "
            "③ 분류·공시 결론"
        ),
        "related_sheet_codes": ("CL", "GG"),
        "ai_review_questions": (
            "전환우선주·풋옵션이 적정 분류되었는가?",
            "금융부채 분류 결론이 있는가?",
        ),
    },
    # ── 2026-07-16 Hanul DB 보강 (상장 L1-05~L4-05, 비상장 U1-06~U4-07) ──
    "L1-05": {
        "related_sheet_codes": ("C", "P"),
        "ai_review_questions": (
            "해외 관계사 거래 통제지표 3요소를 검토하였는가?",
            "우회 회수 매출채권이 위장 제거되지 않았는가?",
        ),
    },
    "L1-06": {
        "related_sheet_codes": ("C", "P"),
        "ai_review_questions": (
            "발생사실 증빙을 세금계산서에 한정하지 않았는가?",
            "조회 미회신 건에 대체적 절차를 수행하였는가?",
        ),
    },
    "L2-08": {"related_sheet_codes": ("E", "CS")},
    "L2-09": {"related_sheet_codes": ("E", "E100")},
    "L3-04": {"related_sheet_codes": ("F", "G", "CL")},
    "L3-05": {"related_sheet_codes": ("F",)},
    "L4-04": {"related_sheet_codes": ("CL", "A", "F", "G")},
    "L4-05": {"related_sheet_codes": ("R", "FF")},
    "U1-06": {"related_sheet_codes": ("P", "Q")},
    "U2-09": {"related_sheet_codes": ("SAJ", "J", "T")},
    "U2-10": {"related_sheet_codes": ("SAJ", "T")},
    "U3-05": {"related_sheet_codes": ("CL", "A", "F", "G")},
    "U3-06": {"related_sheet_codes": ("R", "FF")},
    "U4-06": {"related_sheet_codes": ("CL",)},
    "U4-07": {"related_sheet_codes": ("CL",)},
}


def apply_guidance(row) -> None:
    """FocusCheckRow에 구체적 지침 필드 보강."""
    spec = CHECKLIST_GUIDANCE.get(row.checklist_id, {})
    if not spec:
        return
    if spec.get("review_procedure") and not row.review_procedure:
        row.review_procedure = spec["review_procedure"]
    if spec.get("related_sheet_codes") and not row.related_sheet_codes:
        row.related_sheet_codes = spec["related_sheet_codes"]
    if spec.get("ai_review_questions"):
        row.ai_review_questions = spec["ai_review_questions"]
    if spec.get("trigger_accounts"):
        row.trigger_accounts = spec["trigger_accounts"]
    if spec.get("na_condition"):
        row.na_condition = spec["na_condition"]
