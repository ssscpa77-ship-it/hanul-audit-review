"""Hanul DB 카테고리별 구조인식(structure-aware) 청킹.

「Hanul_DB_청킹_학습_방법론_2026-08-09.md」의 실행 코드. 기존 `kb_extract.chunk_text()`
(고정길이 슬라이딩 윈도우, size=800/overlap=120)는 문서 구조를 전혀 인식하지 않아
- 기준서 조문이 문단 중간에서 잘리고
- 질의회신의 질의/회신이 분리되고
- 감리지적사례 여러 건이 한 청크에 뒤섞이고
- 감사조서의 여러 시트가 한 청크에 걸쳐 섞이는

문제가 있었다. 이 모듈은 카테고리별로 문서의 실제 구조(조항 번호, Q/A 마커, 시트
마커, 사례 제목 등)를 인식해 그 경계에서만 자르고, 각 청크 앞에 출처 컨텍스트를
prefix로 덧붙여 검색 시 문맥이 끊기지 않도록 한다.

`build_index.py`는 `chunk_for_category(category, text, title)`만 호출하면 된다.
매핑되지 않은 카테고리는 기존 `kb_extract.chunk_text()`로 안전하게 폴백한다.
"""

from __future__ import annotations

import re

import kb_extract as ke
import knowledge_base as kb

_MIN_CHUNK = 30
_DEFAULT_SIZE = 800
_DEFAULT_OVERLAP = 120

# --------------------------------------------------------------------------
# 공통 유틸
# --------------------------------------------------------------------------


def _pack(paragraphs: list[str], *, target: int, prefix: str = "") -> list[str]:
    """문단 리스트를 목표 크기(target)에 가깝게 묶어 청크로 합친다.

    문단 하나가 target보다 크면 그 문단만으로 청크를 만든다(억지로 자르지 않음
    — 조항 하나가 길어도 의미 단위를 보존하는 것이 더 중요하다).
    """
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if buf and buf_len + len(p) > target:
            chunks.append((prefix + "\n" + "\n".join(buf)).strip() if prefix else "\n".join(buf))
            buf, buf_len = [], 0
        buf.append(p)
        buf_len += len(p)
    if buf:
        chunks.append((prefix + "\n" + "\n".join(buf)).strip() if prefix else "\n".join(buf))
    return [c for c in chunks if len(c) >= _MIN_CHUNK]


# --------------------------------------------------------------------------
# 1) 기준서류 (회계감사기준·K-IFRS·K-GAAP·실무해설) — 조항 단위
# --------------------------------------------------------------------------
_STD_BOUNDARY_RE = re.compile(
    r"(?=(?:감사기준서\s*\d+|K-?IFRS\s*\d{4}|제\s*\d+\s*장)\s)"
)
_PARA_NUM_RE = re.compile(r"(?=(?:^|\n)\s*(?:A?\d{1,4})\.\s)")


def chunk_standards(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    # 1단계: 기준서/장(chapter) 경계로 큰 블록 분리
    blocks = [b for b in _STD_BOUNDARY_RE.split(text) if b.strip()]
    if len(blocks) <= 1:
        blocks = [text]
    chunks: list[str] = []
    for block in blocks:
        header_line = block.strip().split("\n", 1)[0][:80]
        # 2단계: 블록 내부를 조항 번호(1. / A1. 등) 경계로 문단화
        paras = [p for p in _PARA_NUM_RE.split(block) if p.strip()]
        if len(paras) <= 1:
            paras = [block]
        prefix = f"[{title} — {header_line}]" if header_line and header_line != title else f"[{title}]"
        chunks.extend(_pack(paras, target=650, prefix=prefix))
    return chunks


# --------------------------------------------------------------------------
# 2) 질의회신 — 질의/회신을 분리하지 않고, 제목 컨텍스트를 항상 prefix
# --------------------------------------------------------------------------
_QNA_SPLIT_RE = re.compile(r"(?=(?:Ⅱ\.|II\.|2\.)\s*회신\s*내용)")


def chunk_qna(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    prefix = f"[질의회신: {title}]"
    if len(text) <= 1400:
        # 대다수 질의회신은 이 크기 이내 — 질의+회신을 통째로 1청크 유지
        return [f"{prefix}\n{text}"]
    parts = [p for p in _QNA_SPLIT_RE.split(text) if p.strip()]
    if len(parts) <= 1:
        return _pack([text], target=900, prefix=prefix)
    return _pack(parts, target=900, prefix=prefix)


# --------------------------------------------------------------------------
# 3) 감리지적사례 — 여러 사례가 한 파일에 있으면 사례 경계로 분리
# --------------------------------------------------------------------------
_CASE_BOUNDARY_RE = re.compile(
    r"(?=(?:^|\n)\s*(?:\d{1,3}\s*[.)]\s*[가-힣]|사례\s*\d+|【\s*사례|■\s*[가-힣]))"
)


def chunk_enforcement(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    prefix = f"[감리지적사례: {title}]"
    parts = [p for p in _CASE_BOUNDARY_RE.split(text) if p.strip()]
    # 사례 경계가 뚜렷하지 않으면(단일 사례 파일) 통째로 취급
    if len(parts) <= 1 or all(len(p) < 200 for p in parts):
        return _pack([text], target=900, prefix=prefix)
    return _pack(parts, target=700, prefix=prefix)


# --------------------------------------------------------------------------
# 4) 4대 중점사항 — 이슈 번호(Ⅰ/Ⅱ, 1./2., 가./나.) 경계
# --------------------------------------------------------------------------
_FOCUS_BOUNDARY_RE = re.compile(r"(?=(?:^|\n)\s*(?:[Ⅰ-Ⅹ]\.|\d{1,2}\.\s|[가-하]\.\s))")


def chunk_focus(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    prefix = f"[4대중점: {title}]"
    parts = [p for p in _FOCUS_BOUNDARY_RE.split(text) if p.strip()]
    if len(parts) <= 1:
        return _pack([text], target=700, prefix=prefix)
    return _pack(parts, target=700, prefix=prefix)


# --------------------------------------------------------------------------
# 5) 감사조서 예시·샘플 (xlsx) — 시트([시트: ...]) 경계를 절대 넘지 않음
# --------------------------------------------------------------------------
_SHEET_MARKER_RE = re.compile(r"(?=\[시트:\s*[^\]]+\])")
_NUMERIC_LINE_RE = re.compile(r"^[\d.,\-()%\s]+$")


def _compact_numeric_tail(lines: list[str], *, keep: int = 6) -> list[str]:
    """숫자만 있는 행이 다수면(집계표) 앞부분만 남기고 '...외 N행'으로 요약.

    감사조서 원본 표는 행이 수백 개인 경우가 많아, 서술(절차·결론)과
    무관한 순수 숫자 나열을 그대로 인덱싱하면 검색 신호 대비 잡음이 커진다.
    """
    numeric_run = 0
    out: list[str] = []
    for ln in lines:
        if _NUMERIC_LINE_RE.match(ln):
            numeric_run += 1
            if numeric_run <= keep:
                out.append(ln)
        else:
            if numeric_run > keep:
                out.append(f"…(숫자 행 {numeric_run - keep}건 생략)")
            numeric_run = 0
            out.append(ln)
    if numeric_run > keep:
        out.append(f"…(숫자 행 {numeric_run - keep}건 생략)")
    return out


def chunk_workpaper(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    sheets = [s for s in _SHEET_MARKER_RE.split(text) if s.strip()]
    if not sheets:
        sheets = [text]
    chunks: list[str] = []
    for sheet in sheets:
        lines = sheet.split("\n")
        header = lines[0].strip() if lines else ""
        body_lines = _compact_numeric_tail(lines[1:] if header.startswith("[시트:") else lines)
        prefix = f"[조서: {title} — {header}]" if header else f"[조서: {title}]"
        chunks.extend(_pack(body_lines, target=800, prefix=prefix))
    return chunks


# --------------------------------------------------------------------------
# 6) 자가검토_지침_템플릿 (한울 자체 xlsx: 계정별 카탈로그·체크리스트 등)
#    — 행(row) = 이미 개별 줄바꿈 단위이므로 행 단위로 1청크(구조화 레코드 보존)
# --------------------------------------------------------------------------
def chunk_guideline(text: str, title: str) -> list[str]:
    text = ke.normalize(text)
    if not text:
        return []
    sheets = [s for s in _SHEET_MARKER_RE.split(text) if s.strip()]
    if not sheets:
        sheets = [text]
    chunks: list[str] = []
    for sheet in sheets:
        lines = [ln.strip() for ln in sheet.split("\n") if ln.strip()]
        if not lines:
            continue
        header = lines[0]
        sheet_name = header[5:-1] if header.startswith("[시트:") else header
        rows = lines[1:] if header.startswith("[시트:") else lines
        for row in rows:
            if len(row) < _MIN_CHUNK:
                continue
            chunks.append(f"[{title} — {sheet_name}] {row}")
    return chunks if chunks else _pack([text], target=800, prefix=f"[{title}]")


# --------------------------------------------------------------------------
# 디스패치
# --------------------------------------------------------------------------
_CATEGORY_CHUNKERS = {}
for _cat in kb.STANDARDS_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_standards
for _cat in kb.QNA_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_qna
for _cat in kb.ENFORCEMENT_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_enforcement
for _cat in kb.FOCUS_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_focus
for _cat in kb.WORKPAPER_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_workpaper
for _cat in kb.GUIDELINES_CATEGORIES:
    _CATEGORY_CHUNKERS[_cat] = chunk_guideline


def chunk_for_category(category: str, text: str, title: str) -> list[str]:
    """카테고리별 구조인식 청커로 분기. 매핑 없으면 기존 슬라이딩 윈도우 폴백."""
    fn = _CATEGORY_CHUNKERS.get(category)
    if fn is None:
        return ke.chunk_text(text, size=_DEFAULT_SIZE, overlap=_DEFAULT_OVERLAP)
    try:
        chunks = fn(text, title)
    except Exception:  # noqa: BLE001 — 청커 오류 시 기존 방식으로 안전하게 폴백
        chunks = []
    return chunks or ke.chunk_text(text, size=_DEFAULT_SIZE, overlap=_DEFAULT_OVERLAP)
