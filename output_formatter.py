"""리뷰노트 출력 포맷 — 중요도별 문장 길이 규칙."""

from __future__ import annotations

import re
from typing import Any

_CODE_ALIASES: dict[str, str] = {
    "BB": "BB.DD",
    "DD": "BB.DD",
    "BB,DD": "BB.DD",
}
_SHEET_INDEX_NOISE = frozenset({
    "MEMO", "메모", "NOTE", "전기말", "당기말", "전년말", "당년말",
    "LEAD", "리드", "SUMMARY", "요약", "개요", "INDEX", "목차",
})


def format_citation(group: str, source: str, snippet: str, *, doc_no: str = "") -> str:
    no = doc_no or _extract_doc_no(source)
    brief = " ".join(snippet.split())[:120]
    if no:
        return f"[{group}] {no} — {brief}"
    return f"[{group}] {source} — {brief}"


def _extract_doc_no(source: str) -> str:
    m = re.search(r"[A-Z]{2,6}-\d{4}-\d+|\d{4}\s?-\s?[가-힣]+\s?-\s?\d+|제\s?\d+\s?호", source)
    return m.group(0).replace(" ", "") if m else ""


_BASIS_NOISE_RE = re.compile(
    r"한울\s*예시조서|검토준칙|회계포탈|동법시행령|윤리규정|품질관리제도|"
    r"번대_|전사수준|통제활동|9200|9500|4000_계정별",
    re.I,
)
_PERIOD_SHEET_RE = re.compile(r"^\d{4}년말$", re.I)
_SHEET_CODE_TOKEN_RE = re.compile(r"^([A-Z]{1,4}\d{0,4})", re.I)
_LOC_REF_RE = re.compile(r"([A-Z]{1,4}\d{0,4})\s+([A-Z]+\d+)\s*$", re.I)


def _extract_sheet_index_token(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"^.*/", "", text)
    if not text or text == "-":
        return ""
    head = text.split()[0].upper().replace(",", ".")
    return re.sub(r"(?:\s*(?:LEAD|리드))$", "", head, flags=re.I).strip()


def short_sheet_code(raw: str) -> str:
    """파일경로·장황한 표기에서 계정과목 조서 인덱스만 추출 (예: D, E100)."""
    head = _extract_sheet_index_token(raw)
    if not head:
        return ""
    if head in _SHEET_INDEX_NOISE or _PERIOD_SHEET_RE.match(head):
        return ""
    if re.fullmatch(r"\d+", head):
        return ""
    import sheet_code_registry as reg
    if not reg.parse_sheet_code(head):
        return ""
    return _CODE_ALIASES.get(head, head)


def _sheet_code_for_account(account: str) -> str | None:
    import sheet_code_registry as reg
    fn = getattr(reg, "sheet_code_for_account", None)
    return fn(account) if fn else None


def parse_location_refs(location: str) -> list[tuple[str, str]]:
    """`path/F100 B25 · F200 C43` → `[('F100','B25'), ('F200','C43')]`."""
    refs: list[tuple[str, str]] = []
    if not location:
        return refs
    for part in re.split(r"\s*·\s*", location):
        part = part.strip()
        if not part or re.search(r"외\s*\d+건", part):
            continue
        m = _LOC_REF_RE.search(part)
        if m:
            refs.append((m.group(1).upper(), m.group(2).upper()))
    return refs


_MERGE_META_RE = re.compile(r"하나로 통합|통합했습니다|동일·유사 지적|유사·경미 지적")


def _note_account(note: dict[str, Any]) -> str | None:
    import review_engine as re_engine
    return re_engine.note_account(note)


def _join_sheet_codes(codes: list[str]) -> str:
    if not codes:
        return ""
    if len(codes) == 1:
        return codes[0]
    if len(codes) == 2:
        return f"{codes[0]}, {codes[1]}"
    return ", ".join(codes[:-1]) + f", {codes[-1]}"


def format_workpaper_column(note: dict[str, Any]) -> str:
    """엑셀·UI 조서 컬럼 — 계정과목 조서 인덱스만 (D, E100 등)."""
    codes: list[str] = []
    seen: set[str] = set()
    for sheet, _ in parse_location_refs(str(note.get("location") or "")):
        sc = short_sheet_code(sheet)
        if sc and sc not in seen:
            seen.add(sc)
            codes.append(sc)
    if not codes:
        raw = str(
            note.get("sheet_no") or note.get("workpaper_ref") or note.get("sheet") or ""
        )
        for tok in re.split(r"[,와和·\s]+", raw):
            sc = short_sheet_code(tok)
            if sc and sc not in seen:
                seen.add(sc)
                codes.append(sc)
    if not codes:
        acct = _note_account(note)
        if acct:
            code = _sheet_code_for_account(acct)
            if code:
                return code
        sc = short_sheet_code(str(note.get("sheet_no") or ""))
        return sc or "조서"
    return _join_sheet_codes(codes)


def format_location_lines(location: str) -> str:
    """지적 위치 — 조서이름·행열을 한 줄씩."""
    lines: list[str] = []
    for sheet, ref in parse_location_refs(location):
        lines.append(f"· {sheet} {ref}")
    return "\n".join(lines) if lines else (location or "")


def _issue_detail_points(note: dict[str, Any]) -> list[str]:
    """지적사항 본문 — 항목별 bullet (통합 메타 문구 제외)."""
    points: list[str] = []
    seen: set[str] = set()

    for raw in note.get("merged_points") or []:
        line = str(raw).strip()
        if not line:
            continue
        if not line.startswith("·"):
            line = f"· {line}"
        if line not in seen:
            seen.add(line)
            points.append(line)

    tieout = str(note.get("tieout_detail") or "").strip()
    if tieout:
        line = tieout if tieout.startswith("·") else f"· {tieout}"
        if line not in seen:
            seen.add(line)
            points.append(line)

    detail_line = str(note.get("issue_detail_line") or "").strip()
    if detail_line:
        line = detail_line if detail_line.startswith("·") else f"· {detail_line}"
        if line not in seen:
            seen.add(line)
            points.append(line)

    if not points:
        reason = str(note.get("reason") or "").strip()
        if reason and not _MERGE_META_RE.search(reason):
            for part in re.split(r"\n+", reason):
                part = part.strip()
                if not part or _MERGE_META_RE.search(part):
                    continue
                line = part if part.startswith("·") else f"· {part}"
                if line not in seen:
                    seen.add(line)
                    points.append(line)

    if not points:
        to_be = str(note.get("to_be") or "")
        for part in to_be.splitlines():
            part = part.strip()
            if part.startswith("·"):
                if part not in seen:
                    seen.add(part)
                    points.append(part)

    return points[:12]


def format_issue_detail(note: dict[str, Any]) -> str:
    """지적사항 제목 및 내용 — 항목별 간결 표기."""
    lines: list[str] = []
    title = str(note.get("defect") or "").strip()
    if title:
        lines.append(title)

    points = _issue_detail_points(note)
    if points:
        lines.extend(points)
    else:
        reason = str(note.get("reason") or "").strip()
        if reason and not _MERGE_META_RE.search(reason):
            lines.append(reason[:400])

    loc_block = format_location_lines(str(note.get("location") or ""))
    if loc_block:
        lines.append(loc_block)

    return "\n".join(lines) if lines else "· 상세 근거를 조서에서 확인하십시오."


def simplify_basis(basis: str) -> str:
    """리뷰근거 — 한 줄 요약만 (세부 인용문·파일명 제거)."""
    text = " ".join((basis or "").split()).strip()
    if not text:
        return ""
    if "근거 미확인" in text or "AI 추정" in text:
        return text[:80]
    # 첫 조항만 (세미콜론·줄바꿈 이후 장문 삭제)
    head = re.split(r"[;\n]", text)[0].strip()
    # [기준] 접두·파일명형 근거 제거
    head = re.sub(r"^\[(?:기준|감리지적사례)\]\s*", "", head)
    if _BASIS_NOISE_RE.search(head) or re.search(
        r"\.xlsx|\.pdf|\.doc|FY\d{4}|_\d{8}_|_v\d+\b|^\d{3,}번", head, re.I
    ):
        return ""
    # 체크리스트 내용형 근거 허용
    if head.startswith("감리지적 체크리스트"):
        return head[:100]
    # KSA/K-IFRS 조항 형태만 유지
    if re.search(r"회계감사기준|K-IFRS|KSA|일반기업회계|금융감독원|한국공인회계사회", head):
        return head[:100]
    if len(head) <= 80 and not re.search(r"준수하여야|구축하여야|문단\s*\d", head):
        return head
    return head[:80]


def format_note(note: dict[str, Any]) -> dict[str, Any]:
    imp = note.get("importance", "중")
    defect = (note.get("defect") or "").strip()
    to_be = (note.get("to_be") or "").strip()
    reason = (note.get("reason") or "").strip()

    if imp == "하":
        one_line = defect[:40] if len(defect) > 40 else defect
        note["summary"] = one_line or defect
        if len(defect) > 45:
            note["defect"] = one_line
    elif imp == "중":
        parts = [defect]
        if to_be:
            parts.append(to_be)
        note["summary"] = " — ".join(parts)[:200]
    else:
        head = f"{defect}. {reason[:180]}" if reason else defect
        note["summary"] = head[:280]

    note.pop("references", None)
    if note.get("basis"):
        simple = simplify_basis(str(note["basis"]))
        if simple:
            note["basis"] = simple
    return note


def apply_all(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [format_note(dict(n)) for n in notes]
