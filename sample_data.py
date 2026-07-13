"""샘플 리뷰노트 데이터 (MVP 데모용).

실제 검토 엔진 연동 전, 대시보드·엑셀 다운로드 UI를 검증하기 위한 예시 데이터입니다.
"""

from __future__ import annotations

from typing import Any

# 중요도 정렬 순서 (낮을수록 먼저 표시)
IMPORTANCE_ORDER = {"상": 0, "중": 1, "하": 2}

SAMPLE_ENGAGEMENT: dict[str, Any] = {
    "company_name": "(주)한울전자",
    "audit_year": "2025",
    "accounting_standard": "K-IFRS",
    "audit_standard": "회계감사기준(KSA)",
    "related_workpaper": "매출채권 및 대손충당금",
    "related_account": "매출채권 / 대손충당금",
    "preparer": "김○○ 회계사",
    "review_status": "심리 제출 전 자가검토 진행중",
}

# 2025년도 중점감리사항 대조 결과 (예시)
SAMPLE_FOCUS_AUDIT: list[dict[str, Any]] = [
    {
        "focus_item": "기대신용손실(ECL) 모형 및 가정의 합리성",
        "match_status": "주의",
        "summary": "ECL 산정 가정(전이율·PD) 문서화 미흡, 민감도 분석 누락",
        "source": "금융감독원 2025년 중점감리사항 (회계처리 분야)",
    },
    {
        "focus_item": "수익인식 시점 및 계약요건 검토",
        "match_status": "해당없음",
        "summary": "본 조서 범위 외 (재고자산 조서)",
        "source": "금융감독원 2025년 중점감리사항",
    },
    {
        "focus_item": "내부회계관리제도 운영실태 및 IT일반통제",
        "match_status": "양호",
        "summary": "ITGC 테스트 결과 요약 첨부 확인",
        "source": "금융감독원 2025년 중점감리사항",
    },
]

SAMPLE_REVIEW_NOTES: list[dict[str, Any]] = [
    {
        "id": "RN-001",
        "importance": "상",
        "category": "증빙·절차",
        "defect": "기대신용손실(ECL) 산정 근거 조서 미첨부",
        "reason": "K-IFRS 제1109호에 따른 손상측정 시 ECL 산정내역·가정·민감도 분석이 문서화되어야 하나, 조서 본문에 '별첨' 표기만 있고 실제 첨부 확인 불가",
        "basis": "K-IFRS 제1109호 문단 5.5.17; 회계감사기준 501호(감사증거); 금감원 감리지적 2023-회계-042호(유사 사례)",
        "to_be": "ECL 산정내역서·전이행렬·PD/LGD 가정·민감도 분석표를 조서에 첨부하고, 담당자·검토자 서명란 완비",
        "workpaper_ref": "AR-03 대손충당금",
        "is_focus_related": True,
    },
    {
        "id": "RN-002",
        "importance": "상",
        "category": "계산검증",
        "defect": "대손충당금 설정액과 ECL 산출액 불일치",
        "reason": "조서 표 내 장부금액 합계(1,250백만원)와 ECL 산출 결과(1,180백만원) 차이 70백만원에 대한 조정분개·설명 없음",
        "basis": "회계감사기준 520호(분석적절차); 내부 품질관리지침 §4.2 계산검증",
        "to_be": "차이 원인을 명시하고(반올림·개별평가 반영 등) 조정 내역 또는 차이 설명란 추가",
        "workpaper_ref": "AR-03-2 ECL 산정",
        "is_focus_related": True,
    },
    {
        "id": "RN-003",
        "importance": "중",
        "category": "절차누락",
        "defect": "채권 실사(입회) 절차 수행 흔적 미기재",
        "reason": "중요 계정에 대한 실사·확인 절차가 조서에 기술되지 않음. 잔액확인서 회신 여부 불명",
        "basis": "회계감사기준 501호; 회계감사기준 505호(외부확인); 감리지적 2022-감사-018호",
        "to_be": "실사 일시·장소·대상·입회자 기재, 잔액확인서 발송·회신 현황표 첨부",
        "workpaper_ref": "AR-05 실사",
        "is_focus_related": False,
    },
    {
        "id": "RN-004",
        "importance": "중",
        "category": "형식·완전성",
        "defect": "전기 대비 분석적검토 미수행",
        "reason": "매출채권 잔액 전기 대비 32% 증가에 대한 원인 분석·경영진 문답 기록 없음",
        "basis": "회계감사기준 520호; K-IFRS 제1109호 공시요건(관련 공시 조서 연계)",
        "to_be": "전기/당기 비교표, 증감 원인, 추가 절차 필요 시 수행 내역 기재",
        "workpaper_ref": "AR-01 요약",
        "is_focus_related": False,
    },
    {
        "id": "RN-005",
        "importance": "하",
        "category": "형식·완전성",
        "defect": "조서 상단 기본정보(작성일·검토일) 미기재",
        "reason": "표준조서 양식 필수 항목 중 작성일·1차 검토일란 공란",
        "basis": "법인 표준조서 양식 §1.1; 품질관리 매뉴얼 조서완결성 체크리스트",
        "to_be": "작성일·검토일·검토자 직함 기재 후 전자결재 또는 서명",
        "workpaper_ref": "AR-00 표지",
        "is_focus_related": False,
    },
    {
        "id": "RN-006",
        "importance": "하",
        "category": "증빙·절차",
        "defect": "연체채권 연령분석표 미첨부",
        "reason": "연체 구간별 잔액 분석이 본문에 언급만 되고 표가 첨부되지 않음",
        "basis": "회계감사기준 520호; 금감원 질의회신 2021-회계-0892(채권 손상 관련)",
        "to_be": "연령분석표를 첨부하고 연체채권에 대한 개별평가 또는 집합평가 근거 기재",
        "workpaper_ref": "AR-04 연령분석",
        "is_focus_related": False,
    },
]


def sort_notes_by_importance(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """중요도(상→중→하) 순으로 정렬."""
    return sorted(
        notes,
        key=lambda n: IMPORTANCE_ORDER.get(n.get("importance", "하"), 99),
    )


def count_by_importance(notes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"상": 0, "중": 0, "하": 0}
    for n in notes:
        imp = n.get("importance", "하")
        if imp in counts:
            counts[imp] += 1
    return counts
