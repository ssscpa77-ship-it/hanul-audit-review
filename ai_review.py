"""AI(LLM) 심층 분석 레이어.

규칙엔진이 잡지 못하는 서술형 위험(판단·설명 미흡, 기준 적용 적정성 등)을
LLM으로 보조 점검합니다. Azure OpenAI 와 OpenAI 를 모두 지원합니다.

핵심 원칙 (기획서 반영)
    - 환각 금지: 구체적인 근거(기준 조항·감리지적 번호)는 지식 저장소(RAG)에서
      검색된 인용만 사용합니다. RAG 미연결 시 근거는 "AI 추정 (근거 미확인)" 으로
      표시하고, 모델이 임의의 출처를 지어내지 않도록 프롬프트로 강하게 제약합니다.
    - 보조 도구: 최종 판단·책임은 회계사에게 있습니다.

설정 방법
    [로컬 테스트 · OpenAI 개인 키]
        프로젝트 루트 `.env` 파일 (`.env.example` 참고)
        OPENAI_API_KEY, OPENAI_MODEL (선택)
    [법인 운영 · Azure OpenAI]
        `.env` 또는 `.streamlit/secrets.toml`
    Streamlit secrets 도 동일 키 이름으로 지원합니다.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import config as app_config
import knowledge_base as kb
import review_engine as re_engine

_MAX_TEXT_CHARS = 6000

# 시트 1개당 모델에 전달할 본문 상한
_MAX_SHEET_CHARS = 3800
# 리뷰 대상에서 제외할 최소 본문 길이 (표지·목차 등 스킵)
_MIN_SHEET_CHARS = 80
# 한 번의 분석에서 처리할 시트 상한 (과도한 호출 방지)
_MAX_SHEETS = 40

_CATEGORIES = [
    "증빙·절차",
    "절차누락",
    "계산검증",
    "기준적용",
    "판단·설명",
    "공시",
    "중점감리",
]
_IMPORTANCE = {"상", "중", "하"}


def _cfg(name: str, default: str = "") -> str:
    return app_config.get(name, default)


def provider() -> str | None:
    """설정된 LLM 제공자 ('azure' | 'openai' | None)."""
    return app_config.ai_provider()


def provider_label() -> str:
    return app_config.ai_provider_label()


def model_name() -> str:
    return app_config.ai_model_name()


def is_configured() -> bool:
    return app_config.ai_is_configured()


def test_connection() -> tuple[bool, str]:
    """API 키·모델 연결을 간단히 검증합니다."""
    if not is_configured():
        return False, "API 키가 설정되지 않았습니다."
    try:
        client, model = _build_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        reply = (resp.choices[0].message.content or "").strip()
        label = f"{provider_label()} · {model}"
        if reply:
            return True, f"{label} 연결 성공"
        return True, f"{label} 연결 성공 (응답 확인)"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip()
        if "429" in msg or "quota" in msg.lower():
            return False, "API 할당량 초과 — OpenAI 결제·크레딧을 확인해 주세요."
        if "401" in msg or "invalid" in msg.lower() and "api" in msg.lower():
            return False, "API 키가 올바르지 않습니다. 키를 다시 확인해 주세요."
        if "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            return False, f"모델 '{model_name()}' 을(를) 사용할 수 없습니다. OPENAI_MODEL 값을 변경해 주세요."
        return False, f"연결 실패: {msg[:200]}"


def _build_client():
    kind = provider()
    if kind == "azure":
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=_cfg("AZURE_OPENAI_API_KEY"),
            azure_endpoint=_cfg("AZURE_OPENAI_ENDPOINT"),
            api_version=_cfg("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            timeout=90.0,
            max_retries=1,
        )
        model = _cfg("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        return client, model
    if kind == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=_cfg("OPENAI_API_KEY"), timeout=90.0, max_retries=1)
        model = _cfg("OPENAI_MODEL", "gpt-4o-mini")
        return client, model
    raise RuntimeError("LLM 제공자가 설정되지 않았습니다.")


_SYSTEM_PROMPT = (
    "당신은 한국 회계법인의 심리(품질검토) 담당 회계사입니다. "
    "감사조서 본문을 읽고, 규칙엔진이 이미 찾은 항목 외에 추가로 점검이 필요한 "
    "서술형 위험을 한국어로 지적하세요.\n"
    "절대 규칙:\n"
    "1) 제공된 '인용 가능한 근거' 목록에 있는 출처만 basis 로 사용하십시오. "
    "목록이 비어 있으면 basis 는 반드시 'AI 추정 (근거 미확인)' 으로 적고, "
    "기준 조항 번호·감리지적 번호 등 구체적 출처를 절대 지어내지 마십시오.\n"
    "2) 조서에 실제로 드러난 내용에만 근거해 지적하고, 추측성 단정은 피하십시오.\n"
    "3) 반드시 아래 JSON 스키마의 객체만 출력하십시오. 다른 텍스트 금지."
)


def _schema_hint() -> str:
    return (
        '{"notes":[{"importance":"상|중|하",'
        f'"category":"{"|".join(_CATEGORIES)}",'
        '"defect":"지적 내용(한 줄)",'
        '"reason":"지적 사유(2~3문장)",'
        '"basis":"인용 근거 또는 \'AI 추정 (근거 미확인)\'",'
        '"to_be":"개선 방안","workpaper_ref":"관련 위치"}]}'
    )


def run_ai_review(
    text: str,
    engagement: dict[str, Any],
    rule_notes: list[dict[str, Any]],
    max_notes: int = 6,
) -> list[dict[str, Any]]:
    """AI 심층 분석 실행. 미설정 시 빈 리스트 반환."""
    if not is_configured():
        return []

    client, model = _build_client()

    # RAG 연결 시 관련 근거를 인용 목록으로 제공
    citations: list[kb.Citation] = []
    if kb.is_ready():
        query = f"{engagement.get('related_account','')} {engagement.get('accounting_standard','')} 감사조서 점검"
        for c in kb.gather_citations(query, k_std=3, k_qna=2, k_case=2, k_wp=3, k_focus=1):
            citations.append(kb.Citation(source=c["source"], snippet=c["snippet"], ref=c.get("ref", "")))
    citation_block = (
        "\n".join(f"- {c.source}: {c.snippet}" for c in citations)
        if citations
        else "(없음 — basis 는 'AI 추정 (근거 미확인)' 으로 작성)"
    )

    already = "; ".join(n["defect"] for n in rule_notes) or "(없음)"
    user_prompt = (
        f"[기본정보] 회사: {engagement.get('company_name')}, "
        f"연도: {engagement.get('audit_year')}, "
        f"회계기준: {engagement.get('accounting_standard')}, "
        f"계정: {engagement.get('related_account')}\n\n"
        f"[규칙엔진이 이미 찾은 항목 — 중복 금지]\n{already}\n\n"
        f"[인용 가능한 근거]\n{citation_block}\n\n"
        f"[출력 형식]\n{_schema_hint()}\n"
        f"최대 {max_notes}건. 추가 지적이 없으면 notes 를 빈 배열로.\n\n"
        f"[감사조서 본문]\n{text[:_MAX_TEXT_CHARS]}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return _parse_notes(content, max_notes)


_SHEET_SYSTEM_PROMPT = (
    "당신은 한국 회계법인 품질관리실(심리)의 최고 수준 리뷰어입니다. "
    "감사조서를 '계정과목 시트 단위'로 정독하고, 심리(QRM) 제출 전 반드시 시정해야 할 "
    "중대한 감사 흠결·누락·오류를 전문가 관점에서 지적하는 것이 임무입니다.\n\n"
    "[검토 원칙]\n"
    "1) 해당 시트가 실제로 다루는 계정과목에 대해서만 지적하십시오. "
    "시트 본문에 없는 계정과목(예: 재고자산 시트가 아닌데 재고자산)을 언급하거나 지적하지 마십시오. "
    "A300 장기성예금 조서에 장기공사계약·수익인식 등 **전혀 다른 주제**를 지적하면 안 됩니다. "
    "시트 본문에 등장하지 않는 주제는 notes 를 빈 배열로 두십시오. "
    "점검 대상은 회계감사기준(KSA)·표준 Audit Program상 필수 감사절차(외부조회·실사입회·평가·"
    "기간귀속·분석적절차·후속사건 등)와 회계기준(K-IFRS/일반기준) 적용 적정성, 필요한 공시입니다.\n"
    "2) 중요성 원칙을 엄격히 지키십시오. 사소한 형식·오탈자·서명 누락·단순 문서화 보완 등 경미사항은 지적하지 마십시오. "
    "동일 계정의 세부품목(예: 원재료·부재료·재공품)별로 나누어 지적하지 말고, 정말 중요한 누락이 있을 때만 "
    "계정 단위로 1건 이내로 지적하십시오. "
    "**실물 현금(시재)**: 대부분의 회사는 실물 현금을 보유하지 않습니다. "
    "세부내역에 'nan'·'n/a'·'none'·'해당없음'·'0' 등은 실물 현금 미보유의 정상 표기이므로 지적하지 마십시오. "
    "실물 현금이 없거나 소액인 경우 현금실사·공시 nan 표기를 지적하지 마십시오. "
    "실물 현금을 다량 보유했는데 현금실사·대체 절차 흔적이 전혀 없을 때만 지적하고, "
    "아주 소액(100만원 이하 수준)이면 중요도 '하'로만 표시하십시오. "
    "**주석·공시**: 계정별 상세 조서(A·C·E 등) 본문에 주석 공시가 없어도 정상입니다. "
    "Lead·주석 통합시트 또는 별도 주석 조서에 공시·검토 내용이 있으면 "
    "'공시 미비·조서 미포함'을 지적하지 마십시오. 업로드 묶음 전체를 기준으로 판단하십시오. "
    "**차입금 담보**: 담보·제공자산 내역은 통상 우발부채·약정(CL) 조서에 기재합니다. "
    "차입금 조서 주석에 담보 공시가 없더라도 감리지적사례·기준서 위반으로 지적하지 마십시오. "
    "우발·약정 조서 확인이 필요하다는 수준의 간단한 메모만 해당됩니다. "
    "**우발부채·약정(CL)**: CL·우발·약정 시트별로 나누어 지적하지 말고, "
    "검토·보완이 필요한 항목(지급보증·소송·약정·담보 등)을 열거하는 "
    "하나의 검토요청으로 정리하십시오. "
    "**부외부채(TUL)**: TUL·부외부채 시트별 대동소이한 지적을 하나의 "
    "「검토 요청」 체크리스트로 통합하십시오. 감리지적·중과 지적보다 "
    "리마인드·확인 차원의 항목 열거가 적절합니다. "
    "조서 전반의 중요성과 맥락으로 볼 때 중대한 위반이나 절차상 흠결이 없다면 지적하지 말고 "
    "notes 를 빈 배열로 두십시오. '정말로 중요한 누락'만 지적 대상입니다.\n"
    "3) 당해연도 금융감독원 중점감리(핵심감사)사항 관련 계정이면 필수 점검절차 대응 여부를 확인하십시오. "
    "조서에 검토 내용이 이미 문서화되어 있으면 추가 지적하지 마십시오. "
    "문서화가 없을 때만 '중점검토 필요' 취지의 간단한 지적 1건을 category '중점감리' 로 작성하십시오.\n"
    "4) 감리지적사례 인용 시 **문서번호(사건번호) + 핵심 위반사항 1줄** 형식을 사용하십시오.\n"
    "5) 사소한 사항은 defect·reason 을 **한 줄**로, 중대사항(중점감리·표준절차 누락·주석 불일치)은 상세 서술하십시오.\n"
    "[환각 절대 금지]\n"
    "6) 기준 조항 번호·감리지적 사례번호·질의회신 번호 등 구체적 출처는 아래 '인용 가능한 근거' "
    "목록에 있는 항목만 사용하고, 사용한 근거의 id 를 각 지적의 cites 배열에 적으십시오. "
    "목록으로 뒷받침되지 않으면 basis 는 'AI 추정 (근거 미확인)' 으로 적고 출처를 지어내지 마십시오.\n"
    "7) 조서에 실제로 드러난 내용에만 근거해 지적하고, 확인되지 않은 사실을 단정하지 마십시오.\n"
    "8) 반드시 지정된 JSON 스키마 객체만 출력하십시오. 다른 텍스트 금지. 지적할 중대사항이 없으면 "
    "notes 를 빈 배열로 두십시오."
)

import review_guidelines as _review_guidelines  # noqa: E402

_SHEET_SYSTEM_PROMPT = _SHEET_SYSTEM_PROMPT + _review_guidelines.ai_system_addon()


def _sheet_schema_hint() -> str:
    return (
        '{"notes":[{'
        '"importance":"상|중|하",'
        f'"category":"{"|".join(_CATEGORIES)}",'
        '"defect":"지적 내용(한 줄, 계정·절차 명시)",'
        '"reason":"근거 있는 지적 사유(2~4문장, 조서에서 확인된 사실 기반)",'
        '"basis":"인용한 기준/사례의 요지 또는 \'AI 추정 (근거 미확인)\'",'
        '"cites":["C1","C3"],'
        '"to_be":"구체적 수정·보완 방안",'
        '"is_focus_related":true}]}'
    )


def _format_citations(cites: list[dict]) -> tuple[str, dict[str, dict]]:
    """근거 목록을 프롬프트 문자열과 id→근거 매핑으로 변환."""
    if not cites:
        return "(없음 — basis 는 'AI 추정 (근거 미확인)' 으로 작성)", {}
    lines: list[str] = []
    id_map: dict[str, dict] = {}
    for i, c in enumerate(cites, start=1):
        cid = f"C{i}"
        id_map[cid] = c
        lines.append(f"[{cid}] ({c['group']}) {c['source']}: {c['snippet']}")
    return "\n".join(lines), id_map


def _sheet_query(account: str, engagement: dict[str, Any]) -> str:
    parts = [
        account,
        engagement.get("accounting_standard", ""),
        engagement.get("audit_year", ""),
        "감사절차 필수 점검 중점감리",
    ]
    return " ".join(p for p in parts if p)


def _to_note(
    item: dict,
    id_map: dict[str, dict],
    *,
    sheet_no: str,
    account: str,
    sheet_title: str,
) -> dict[str, Any] | None:
    """LLM 지적 1건 + 인용 근거 → 리뷰노트 dict (앱/엑셀 공통 스키마)."""
    if not isinstance(item, dict) or not item.get("defect"):
        return None
    importance = item.get("importance", "중")
    importance = importance if importance in _IMPORTANCE else "중"
    category = item.get("category", "판단·설명")
    if category not in _CATEGORIES:
        category = "판단·설명"

    used = [id_map[c] for c in item.get("cites", []) if c in id_map]
    # 감리지적사례로 분류된 근거는 사례카드로만 정리 (리뷰근거 세부 인용문은 UI에 표시 안 함)
    enforcement_cases: list[dict] = []
    for c in used:
        if c["group"] == "감리지적사례":
            if re_engine.is_off_account_enforcement(c["source"], c["snippet"], account):
                continue
            case = kb.parse_case(kb.Citation(source=c["source"], snippet=c["snippet"], ref=c["ref"]))
            enforcement_cases.append(case)

    basis = str(item.get("basis") or "").strip()
    if not basis:
        ksa = [c["source"] for c in used if c["group"] != "감리지적사례"]
        basis = ksa[0] if ksa else "AI 추정 (근거 미확인)"
    import output_formatter as _fmt
    basis = _fmt.simplify_basis(basis) or basis[:80]

    label = f"{sheet_no} ({sheet_title})" if sheet_no and sheet_title else (sheet_no or sheet_title or account)
    note = {
        "id": "",
        "importance": importance,
        "category": category,
        "defect": str(item.get("defect", "")).strip(),
        "reason": str(item.get("reason", "")).strip(),
        "basis": basis,
        "to_be": str(item.get("to_be", "")).strip(),
        "sheet_no": sheet_no or "-",
        "sheet_title": sheet_title or account,
        "sheet": label,
        "location": "",
        "summary": "",
        "workpaper_ref": sheet_no or label,
        "enforcement_cases": enforcement_cases,
        "is_focus_related": bool(item.get("is_focus_related")),
        "account": account,
        "source": "ai",
    }
    if re_engine.is_off_account_text(
        f"{note['defect']} {note['reason']}", account
    ):
        return None
    re_engine.sanitize_note_citations(note)
    return note


def _review_one_sheet(
    client,
    model: str,
    sheet_no: str,
    account: str,
    sheet_title: str,
    sheet_text: str,
    engagement: dict[str, Any],
    max_notes: int,
) -> list[dict[str, Any]]:
    cites = kb.gather_citations(_sheet_query(account, engagement)) if kb.is_ready() else []
    # 해당 시트 계정과 무관한 다른 계정의 근거·감리사례는 인용 목록에서 제외
    cites = [
        c for c in cites
        if not re_engine.is_off_account_text(f"{c.get('source', '')} {c.get('snippet', '')}", account)
    ]
    citation_block, id_map = _format_citations(cites)

    year_s = str(engagement.get("audit_year", "2026"))
    year = int(year_s) if year_s.isdigit() else 2026
    import fss_focus

    focus_titles = [
        f"①{i.issue_no} {i.title}"
        for i in fss_focus.load_current_focus_issues(year, bool(engagement.get("is_listed")))
    ]
    focus_block = "\n".join(f"- {t}" for t in focus_titles) or "(해당 연도 항목 확인 필요)"

    user_prompt = (
        f"[감사 대상] 회사: {engagement.get('company_name')}, "
        f"연도: {engagement.get('audit_year')}, "
        f"회계기준: {engagement.get('accounting_standard')}, "
        f"감사기준: {engagement.get('audit_standard')}, "
        f"중요성: {engagement.get('materiality_display', '미확인')}\n\n"
        f"[당해연도 4대 중점 회계이슈 — 해당 시트면 엄격 점검]\n{focus_block}\n\n"
        f"[검토 대상 시트] 조서번호: {sheet_no or '-'} / 계정과목: {account}"
        + (f" / 시트제목: {sheet_title}" if sheet_title and sheet_title != account else "")
        + "\n\n"
        f"[인용 가능한 근거]\n{citation_block}\n\n"
        f"[출력 형식]\n{_sheet_schema_hint()}\n"
        f"이 시트에 대해 최대 {max_notes}건. 중대사항이 없으면 notes 를 빈 배열로.\n\n"
        f"[조서 시트 본문]\n{sheet_text[:_MAX_SHEET_CHARS]}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SHEET_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    raw = data.get("notes", []) if isinstance(data, dict) else []
    notes: list[dict[str, Any]] = []
    for item in raw[:max_notes]:
        note = _to_note(item, id_map, sheet_no=sheet_no, account=account, sheet_title=sheet_title)
        if note:
            notes.append(note)
    return notes


def _present_accounts(doc) -> set[str]:
    """조서 본문·시트제목에 실제 등장하는 계정과목 집합.

    시트 주계정뿐 아니라 본문에 언급된 계정(예: 매출채권 시트의 대손충당금)도
    포함해, 조서가 실제로 다루는 계정에 대한 지적만 통과시킨다.
    """
    hay_parts = [getattr(doc, "text", "") or ""]
    present: set[str] = set()
    for t in getattr(doc, "tables", []):
        hay_parts.append(str(t.attrs.get("title", "")))
        hay_parts.append(re_engine._sheet_text(t))
        code_acct = re_engine.table_account(t)
        if code_acct:
            present.add(code_acct)
    hay = "\n".join(hay_parts)
    for name, syns in re_engine.ACCOUNT_TAXONOMY:
        for s in (name, *syns):
            if re_engine._synonym_pos(hay, s) is not None:
                present.add(name)
                break
    return present


def _filter_offtopic_notes(
    notes: list[dict[str, Any]], present: set[str], doc=None
) -> list[dict[str, Any]]:
    """조서·시트 계정과 무관한 지적·경미(하) 노트를 제거."""
    present_syns: list[str] = []
    absent_syns: list[str] = []
    for name, syns in re_engine.ACCOUNT_TAXONOMY:
        target = present_syns if name in present else absent_syns
        target.extend([name, *syns])
    present_syns.sort(key=len, reverse=True)

    minor_doc = ("문서화", "기재", "서술", "설명", "보완", "미흡", "부족", "근거")
    substantive = ("미수행", "누락", "조회", "실사", "입회", "cut", "컷", "공시", "불일치")

    out: list[dict[str, Any]] = []
    for note in notes:
        if doc and re_engine.is_off_account_note(note, doc):
            continue
        acct = re_engine.note_account(note) or note.get("account")
        hay = f"{note.get('defect', '')} {note.get('reason', '')} {note.get('to_be', '')}"
        if acct and re_engine.is_off_account_text(hay, acct):
            continue
        if note.get("importance") == "하":
            continue
        if note.get("importance") == "중":
            if any(k in hay for k in minor_doc) and not any(k in hay for k in substantive):
                continue
        text = hay
        for s in present_syns:
            text = text.replace(s, " ")
        if any(re_engine._synonym_pos(text, s) is not None for s in absent_syns):
            continue
        out.append(note)
    return out


def run_sheet_reviews(
    doc,
    engagement: dict[str, Any],
    max_notes_per_sheet: int = 1,
    progress: Callable[[float, str], None] | None = None,
) -> list[dict[str, Any]]:
    """조서를 시트 단위로 정독하며 RAG 근거 기반 AI 심층 리뷰를 수행.

    각 시트의 주계정을 식별하고, 그 계정 관련 기준·질의회신·감리지적사례·절차예시를
    Hanul DB(RAG)에서 검색해 '인용 가능한 근거'로 제공한 뒤, Azure/OpenAI 로
    중대한 감사 흠결·누락·오류를 지적하게 한다. 미설정 시 빈 리스트 반환.
    """
    if not is_configured():
        return []

    import fss_focus
    import sheet_code_registry as scr

    scr.set_mapping_variant(bool(engagement.get("is_listed")))
    year_s = str(engagement.get("audit_year", "2026"))
    year = int(year_s) if year_s.isdigit() else 2026
    focus_issues = fss_focus.load_current_focus_issues(year, bool(engagement.get("is_listed")))
    focus_kw: set[str] = set()
    for fi in focus_issues:
        focus_kw.update(fi.related_accounts)
        focus_kw.update(fi.sheet_keywords)

    # 리뷰할 시트 선별 (본문이 충분한 시트만, 4대 중점항목 시트는 예외)
    targets: list[tuple[str, str, str, str]] = []
    for t in getattr(doc, "tables", []):
        stext = re_engine._sheet_text(t)
        title = str(t.attrs.get("title", "")).strip()
        source = str(t.attrs.get("source", "")).strip()
        account = re_engine.table_account(t) or title or "미분류 계정"
        is_focus = any(
            kw in title or kw in stext or kw in account for kw in focus_kw if kw
        )
        if len(stext.strip()) < _MIN_SHEET_CHARS and not is_focus:
            continue
        targets.append((source, account, title, stext))
        if len(targets) >= _MAX_SHEETS:
            break

    if not targets:
        return []

    client, model = _build_client()
    all_notes: list[dict[str, Any]] = []
    total = len(targets)
    for idx, (source, account, title, stext) in enumerate(targets, start=1):
        if progress:
            progress((idx - 1) / total, f"시트 분석 중 ({idx}/{total}) · {account}")
        try:
            all_notes.extend(
                _review_one_sheet(
                    client, model, source, account, title, stext, engagement, max_notes_per_sheet
                )
            )
        except Exception:  # noqa: BLE001 - 개별 시트 실패는 건너뛰고 계속
            continue
    if progress:
        progress(1.0, "분석 완료")
    # 조서에 없는 계정 지적·경미(하) 지적은 최종 제거
    return _filter_offtopic_notes(all_notes, _present_accounts(doc), doc)


def _parse_notes(content: str, max_notes: int) -> list[dict[str, Any]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    raw = data.get("notes", []) if isinstance(data, dict) else []
    notes: list[dict[str, Any]] = []
    for item in raw[:max_notes]:
        if not isinstance(item, dict) or not item.get("defect"):
            continue
        importance = item.get("importance", "중")
        ref = str(item.get("workpaper_ref", "")).strip() or "조서 본문"
        notes.append(
            {
                "id": "",
                "importance": importance if importance in _IMPORTANCE else "중",
                "category": item.get("category", "판단·설명"),
                "defect": str(item.get("defect", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
                "basis": str(item.get("basis") or "AI 추정 (근거 미확인)").strip(),
                "to_be": str(item.get("to_be", "")).strip(),
                "workpaper_ref": ref,
                "sheet_no": ref,
                "sheet_title": "",
                "sheet": ref,
                "is_focus_related": False,
                "source": "ai",
            }
        )
    return notes
