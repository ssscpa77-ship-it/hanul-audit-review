"""자가검토 QC 지침 — 규칙·AI·4대 중점 공통 기준.

Hanul DB `자가검토_지침_템플릿/` 폴더의 xlsx가 있으면 `guidelines_loader`가
우선 로드한다. 없으면 본 모듈의 기본 지침을 사용한다.
"""

from __future__ import annotations

# Hanul DB 상대 경로 (build_index 색인 대상)
GUIDELINES_DB_SUBDIR = "자가검토_지침_템플릿"

TEMPLATE_FILES = {
    "focus_listed": "4대중점_체크리스트_상장_FY2026.xlsx",
    "focus_unlisted": "4대중점_체크리스트_비상장_FY2026.xlsx",
    "procedures": "계정별_필수절차_카탈로그_FY2026.xlsx",
    "sheet_tieout": "조서연결_대사_사전_FY2026.xlsx",
    "review_phrases": "검토내역_결론_인정문장_FY2026.xlsx",
    "golden_set": "골든셋_회귀기준.xlsx",
    "enforcement_listed": "감리지적_체크리스트_상장_FY2026.xlsx",
    "enforcement_unlisted": "감리지적_체크리스트_비상장_FY2026.xlsx",
}

# 조서번호 역할 — 규칙엔진 교차합·이자테스트 제외에 사용 (§D 기본값)
SHEET_ROLE_REGISTRY: dict[str, str] = {
    "BB100": "차입금_잔액_유형별",
    "BB200": "차입금_이자테스트",
    "CL": "우발부채_약정",
    "TUL": "부외부채",
    "A Lead": "현금_리드",
    "F Lead": "투자자산_리드",
}

REVIEW_PASS_PRIORITY = """
[판정 우선순위]
1. 중대 절차 누락(조회서·실사·평가 근거 전무) → 문서화 여부와 무관하게 지적
2. Hanul DB 「자가검토_지침_템플릿」 감리지적 체크리스트 — **해당 조서인덱스가 있으면 항목별 필수 검토**
3. 4대 중점 체크리스트 항목별 미충족 → Tier1 지적
4. 검토내역·결론·인접 각주에 업무상 타당한 해소 문장 → 해당 항목 지적 제외
5. Lead·주석·타 조서에 이미 문서화 → 세부조서 단독 미기재는 지적 제외
""".strip()

ENFORCEMENT_CHECKLIST_MANDATORY = """
[감리지적사례 체크리스트 — 필수 검토 (자가검토_지침_템플릿)]
· 출처: Hanul DB `자가검토_지침_템플릿/감리지적_체크리스트_{상장|비상장}_FY2026.xlsx`
· 내용: 금융감독원·한국공인회계사회 **과거 감리 지적사례**를 조서 인덱스(A,C,D,E,SAJ…)별로
  분류·요약한 체크리스트(지적유형·절차흠결·핵심키워드·사례번호).
· **리뷰노트 생성 시 반드시 적용**: 업로드 조서에 해당 조서인덱스(4000 계정별 실증절차)가
  존재하면, 그 인덱스의 체크리스트 **전 항목**을 빠짐없이 검토한다.
· 판정: `detect_any`·`required_evidence`·`acceptable_phrases` 기준으로 충족 여부 판단.
  미충족 시 `[감리지적·검토누락]` 또는 `[감리지적·결론미비]` 노트 생성(중요도 중 이상).
· 근거: 체크리스트의 `case_numbers`·`case_examples`·`case_context`(과거 지적 맥락)를
  reason·enforcement_cases에 반드시 연결한다. `audit_focus`로 조서 점검 항목을 구체화한다.
· 생략 금지: 키워드 미매칭을 이유로 항목 검토를 건너뛰지 않는다. 조서가 존재하면
  해당 인덱스 체크리스트는 **전수 검토** 대상이다.
· 보호: `enforcement_protected` 노트는 QC 경미 제거·무분별 통합에서 제외한다.
""".strip()

REVIEW_NOTE_STYLE = """
[리뷰노트 문체 — 규칙·AI 공통]
· defect: [유형] 계정 — 쟁점 (한 줄)
· reason: 조서에서 확인된 사실(1문장) + 중요성/기준(1문장) + 비어 있는 점(1문장)
· to_be: 동사로 시작하는 실행 가능 보완 (이미 수행·기재된 절차는 열거하지 않음)
· 중요도 상: 4대 중점, 표준절차 누락, 주석·FS 불일치
· 중요도 중: 대사·분석 미흡, 판단 근거 약함
· 중요도 하: §0.2 경미사항 — 기본 제외
""".strip()

AI_ROLE_GUIDE = """
[AI 역할 — 서술 보조]
· L1(규칙)에서 Pass인 시트는 notes=[] (전수 탐지기 아님)
· L1 Fail·4대 중점 미충족·판단 계정(손상·ECL·수익인식)만 reason·to_be 구체화
· 조서에 없는 사실 단정·근거 없는 KSA/감리번호 창작 금지
· 동일 계정 품목별 산발 지적 금지 — 계정·이슈당 1건 통합
""".strip()

FOCUS_WORKFLOW_STEPS = (
    ("1 Trigger", "관련 계정·거래 유의?"),
    ("2 Procedure", "필수 감사절차 수행·문서화?"),
    ("3 Enforcement", "감리지적 체크리스트(과거 사례) 항목별 충족?"),
    ("4 Focus", "당국 유의사항·4대 중점 체크리스트 반영?"),
    ("5 Disclosure", "주석·공시 충분?"),
)


def ai_system_addon() -> str:
    """ai_review 시스템 프롬프트에 추가할 지침 블록."""
    return (
        f"\n{REVIEW_PASS_PRIORITY}\n"
        f"{ENFORCEMENT_CHECKLIST_MANDATORY}\n"
        f"{REVIEW_NOTE_STYLE}\n{AI_ROLE_GUIDE}\n"
    )


def template_upload_requests() -> list[dict[str, str]]:
    """Hanul DB 업로드 요청 목록 — 사용자가 채워 업로드할 템플릿."""
    return [
        {
            "file": TEMPLATE_FILES["focus_listed"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "상장 4대 중점 이슈별 체크리스트(증거유형·Pass문장·Red flag·AI질문)",
            "status": "필수 — 빈 양식 제공됨, 내부 작성 후 업로드",
        },
        {
            "file": TEMPLATE_FILES["focus_unlisted"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "비상장 4대 중점 이슈별 체크리스트",
            "status": "필수 — 빈 양식 제공됨, 내부 작성 후 업로드",
        },
        {
            "file": TEMPLATE_FILES["procedures"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "4000 계정별 필수 절차 카탈로그(증거유형·대체절차·교차조서)",
            "status": "필수 — 빈 양식 제공됨",
        },
        {
            "file": TEMPLATE_FILES["sheet_tieout"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "조서번호별 역할·교차합 비교 단위(잔액/이자테스트/주석)",
            "status": "권장 — 빈 양식 제공됨 (BB100/BB200 샘플 포함)",
        },
        {
            "file": TEMPLATE_FILES["review_phrases"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "계정별 검토내역·결론 인정 문장 사전",
            "status": "권장 — 빈 양식 제공됨",
        },
        {
            "file": TEMPLATE_FILES["golden_set"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "골든 조서·기대 리뷰노트·회귀 합격선(Tier1 recall≥95%)",
            "status": "선택 — 빈 양식 제공됨",
        },
        {
            "file": TEMPLATE_FILES["enforcement_listed"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "상장 — 조서인덱스별 감리지적사례 학습 체크리스트(절차흠결·키워드)",
            "status": "필수 — 리뷰노트 생성 시 전 항목 검토",
        },
        {
            "file": TEMPLATE_FILES["enforcement_unlisted"],
            "folder": GUIDELINES_DB_SUBDIR,
            "purpose": "비상장 — 조서인덱스별 감리지적사례 학습 체크리스트",
            "status": "필수 — 리뷰노트 생성 시 전 항목 검토",
        },
    ]
