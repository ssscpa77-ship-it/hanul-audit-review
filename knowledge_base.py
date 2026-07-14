"""지식 저장소(RAG) — Hanul DB 검색 연결.

Hanul DB 의 자료를 색인한 로컬 SQLite FTS5 저장소를 검색해,
감사조서 리뷰 시 참고할 근거(기준서·질의회신·감리지적 등)를 인용합니다.

색인은 build_index.py 로 생성합니다.
    VENV/bin/python build_index.py            # 전체 색인
검색 품질을 임베딩(의미검색)으로 높이는 것은 향후 확장 지점입니다.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from functools import lru_cache

# 원본 자료 폴더 (환경변수로 재정의 가능)
_OLD_DB_DIR = os.path.expanduser("~/Desktop/Hanul DB")
_DEFAULT_DB_DIR = os.path.expanduser("~/Desktop/Hanul DB-SSS")
SOURCE_DIR = os.environ.get("HANUL_DB_PATH", _DEFAULT_DB_DIR)


def resolve_source_path(path: str) -> str:
    """색인에 남은 구 경로(Hanul DB)를 신규 폴더(Hanul DB-SSS)로 보정."""
    if not path:
        return path
    if os.path.isfile(path):
        return path
    if path.startswith(_OLD_DB_DIR):
        candidate = path.replace(_OLD_DB_DIR, _DEFAULT_DB_DIR, 1)
        if os.path.isfile(candidate):
            return candidate
    return path
# 색인 저장 위치
STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb_store")
STORE_PATH = os.path.join(STORE_DIR, "hanul_kb.sqlite")
STORE_GZ_PATH = os.path.join(STORE_DIR, "hanul_kb.sqlite.gz")


def _sqlite_header_ok(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16).startswith(b"SQLite format 3\x00")
    except OSError:
        return False


def ensure_store() -> None:
    """배포 환경: gzip 압축본 → sqlite 복원 (Git LFS 미지원 대비)."""
    if _sqlite_header_ok(STORE_PATH):
        return
    if not os.path.isfile(STORE_GZ_PATH):
        return
    os.makedirs(STORE_DIR, exist_ok=True)
    with gzip.open(STORE_GZ_PATH, "rb") as src, open(STORE_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    try:
        _connect.cache_clear()
    except NameError:
        pass



@dataclass
class Citation:
    """근거 인용 1건."""

    source: str  # 출처명 (예: "금융감독원 감리지적사례 · 매출 과대계상")
    snippet: str  # 인용 문구
    ref: str = ""  # 원본 파일 경로
    score: float = 0.0


_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}|\d+호|\d+")
_STOPWORDS = {"관련", "내용", "경우", "대한", "위한", "따라", "또는", "그리고", "회계처리"}

# 감리지적사례가 담긴 카테고리(폴더)명
ENFORCEMENT_CATEGORIES = [
    "금융감독원 감리지적사례",
    "한국공인회계사회 감리지적사례",
]

# 회계·감사 기준서 및 해설
STANDARDS_CATEGORIES = [
    "회계감사기준",
    "한국채택국제회계기준",
    "일반기업회계기준",
    "K-IFRS 실무사례와 해설",
]

# 4대 중점 감리대상 (당해연도 핵심 이슈)
FOCUS_CATEGORIES = ["4대 중점사항 감리대상"]

# 자가검토 지침 템플릿 (체크리스트·인정문장 등)
GUIDELINES_CATEGORIES = ["자가검토_지침_템플릿"]

# 기준원 질의회신
QNA_CATEGORIES = ["질의회신_한국회계기준원"]

# 한울 예시조서·보고서·감사조서 샘플 (Audit Program·핵심감사사항 예시 포함)
WORKPAPER_CATEGORIES = ["한울 예시조서", "한울 예시보고서", "감사조서 샘플"]

# 리뷰노트 근거 검색용 통합 카테고리
REVIEW_KB_CATEGORIES = (
    STANDARDS_CATEGORIES
    + QNA_CATEGORIES
    + ENFORCEMENT_CATEGORIES
    + WORKPAPER_CATEGORIES
    + FOCUS_CATEGORIES
    + GUIDELINES_CATEGORIES
)


@dataclass
class ProcedureSpec:
    """계정별 표준 감사절차 1건."""

    name: str
    detect_all: tuple[str, ...] = ()
    detect_any: tuple[str, ...] = ()
    basis: str = ""
    to_be: str = ""
    snippet: str = ""


_FILELIKE_TITLE_RE = re.compile(r"_|v\d|fy\s?\d{2,4}|\.xls", re.I)
_SPREADSHEET_DUMP_RE = re.compile(
    r"\[시트:\s*\w+\]|회사명:\s*㈜|결산일:\s*\d{4}|작성자:\s*|검토자:\s*",
    re.I,
)
_PROCEDURE_DETECT_STOP = _STOPWORDS | {
    "시트", "회사명", "결산일", "작성자", "검토자", "한다", "여부", "감사대응",
    "내부통제", "4000", "lassification", "연결", "COA",
}
_ACCOUNT_PROC_QUERIES: dict[str, tuple[str, ...]] = {
    "재고자산": ("재고자산 실사입회", "재고자산 저가법 NRV", "재고 Cut-off 검토"),
    "매출채권": ("매출채권 대손충당금", "매출채권 기대신용손실", "매출채권 확인 조회"),
    "유형자산": ("유형자산 감가상각", "유형자산 손상검사", "유형자산 실사"),
    "현금및예금": ("현금 예금 조회", "은행잔액 확인", "현금및예금 확인서"),
    "법인세": ("법인세 산출 검토", "이연법인세 검토"),
    "수익": ("수익인식 검토", "매출 Cut-off"),
    "리스": ("리스 회계처리 검토", "사용권자산 리스부채"),
}
_SOURCE_PROC_HINTS: tuple[tuple[str, str], ...] = (
    ("재고실사", "재고자산 실사입회"),
    ("입회", "재고자산 실사입회"),
    ("저가", "재고자산 저가법·NRV"),
    ("대손", "대손충당금 검토"),
    ("ecl", "ECL 산정·검토"),
    ("조회", "외부조회·확인"),
    ("확인서", "확인서 회신"),
    ("cut-off", "Cut-off 검토"),
    ("cutoff", "Cut-off 검토"),
    ("손상", "손상검사"),
    ("법인세", "법인세 산출 검토"),
)
_PROCEDURE_KW_LABELS: tuple[tuple[str, str], ...] = (
    ("실사입회", "재고자산 실사입회"),
    ("재고실사", "재고자산 실사입회"),
    ("저가법", "재고자산 저가법·NRV"),
    ("저가법검토", "재고자산 저가법·NRV"),
    ("NRV", "재고자산 NRV 검토"),
    ("대손", "대손충당금 검토"),
    ("기대신용손실", "ECL 산정·검토"),
    ("조회", "외부조회·확인"),
    ("확인서", "확인서 회신"),
    ("분석적절차", "분석적절차"),
    ("Cut-off", "Cut-off 검토"),
    ("기말분석", "기말분석"),
    ("손상", "손상검사"),
    ("지분법", "지분법 검토"),
    ("법인세", "법인세 산출 검토"),
    ("리스", "리스 회계처리 검토"),
    ("수익인식", "수익인식 검토"),
)


_LABEL_ACCOUNT: dict[str, str | None] = {
    "재고자산 실사입회": "재고자산",
    "재고자산 저가법·NRV": "재고자산",
    "재고자산 NRV 검토": "재고자산",
    "대손충당금 검토": "매출채권",
    "ECL 산정·검토": "매출채권",
    "법인세 산출 검토": "법인세",
    "지분법 검토": "관계기업투자",
}


def _label_fits_account(name: str, account: str) -> bool:
    req = _LABEL_ACCOUNT.get(name)
    if req is not None and req != account:
        return False
    if name.startswith("재고자산") and account != "재고자산":
        return False
    if name.startswith("매출채권") and account != "매출채권":
        return False
    if re.match(r"^\d{6,}", name):
        return False
    return True


def _source_procedure_hint(source: str) -> str | None:
    low = source.lower()
    for hint, label in _SOURCE_PROC_HINTS:
        if hint in low:
            return label
    return None


def _snippet_quality(c: Citation) -> int:
    score = 0
    snip = c.snippet
    src = c.source
    for kw, _ in _PROCEDURE_KW_LABELS:
        if kw in snip or kw.lower() in src.lower():
            score += 3
    if any(t in snip for t in ("검토", "확인", "분석", "조회", "입회", "산정", "평가", "대사", "문서화")):
        score += 2
    if _SPREADSHEET_DUMP_RE.search(snip[:180]):
        score -= 4
    digits = sum(ch.isdigit() for ch in snip[:300])
    if digits > len(snip[:300]) * 0.35:
        score -= 3
    if _source_procedure_hint(src):
        score += 2
    return score


def _procedure_label(c: Citation, account: str) -> str:
    """파일명·스니펫에서 절차 의미 중심 라벨."""
    hint = _source_procedure_hint(c.source)
    if hint:
        return hint
    hay = f"{c.source} {c.snippet}"
    for kw, label in _PROCEDURE_KW_LABELS:
        if kw in hay:
            if account == "재고자산" and "재고" not in label and kw not in (
                "실사입회", "재고실사", "저가법", "저가법검토", "NRV",
            ):
                continue
            if account == "매출채권" and kw not in ("대손", "기대신용손실", "조회", "확인서", "Cut-off"):
                if kw in ("실사입회", "재고실사", "저가법", "NRV"):
                    continue
            return label
    for line in c.snippet.split("\n"):
        line = " ".join(line.split()).strip()
        if len(line) < 12 or len(line) > 90:
            continue
        if _SPREADSHEET_DUMP_RE.search(line):
            continue
        if sum(ch.isdigit() for ch in line) > len(line) * 0.25:
            continue
        if any(t in line for t in ("검토", "확인", "분석", "조회", "입회", "산정", "평가", "대사", "문서화")):
            return line[:56]
    title = c.source.split("·")[-1].strip()
    if _FILELIKE_TITLE_RE.search(title):
        return f"{account} 표준조서 절차"
    return title[:56]


def _procedure_detect_tokens(c: Citation, account: str, name: str) -> tuple[str, ...]:
    proc_kws = [kw for kw, _ in _PROCEDURE_KW_LABELS if kw in f"{c.source} {c.snippet}"]
    kws = [
        t
        for t in _TOKEN_RE.findall(c.snippet)
        if len(t) >= 2
        and t not in _PROCEDURE_DETECT_STOP
        and not t.isdigit()
        and not re.fullmatch(r"\d{4,}", t)
    ]
    detect = tuple(dict.fromkeys(proc_kws + kws))[:6]
    if detect:
        return detect
    short = name.replace("·", " ").split()[:2]
    return tuple(short) if short else (account[:4],)


def _matches_workpaper_account(
    c: Citation,
    account: str,
    synonyms: tuple[str, ...],
    *,
    is_listed: bool,
) -> bool:
    hay = f"{c.source} {c.snippet} {c.ref}"
    for syn in synonyms:
        if syn and len(syn) >= 2 and syn in hay:
            return True
    try:
        import sheet_code_registry as scr

        scr.set_mapping_variant(is_listed)
        code = scr.sheet_code_for_account(account)
        if code:
            tokens = (
                code,
                f"_{code}_",
                f"_{code},",
                f"{code}_",
                f" {code} ",
                f"/{code}",
            )
            if any(t in hay for t in tokens):
                return True
    except Exception:  # noqa: BLE001
        pass
    return account in hay


@lru_cache(maxsize=128)
def _cached_standard_procedures(
    account: str,
    is_listed: bool,
    industry: str,
    syn_key: str,
) -> tuple[ProcedureSpec, ...]:
    """계정별 표준절차 — Hanul 예시조서·감사조서 샘플 KB 검색."""
    if not is_ready():
        return ()
    synonyms = tuple(s for s in syn_key.split("|") if s)
    queries: list[str] = list(_ACCOUNT_PROC_QUERIES.get(account, ()))
    queries.extend([
        f"{account} 감사절차 실증절차 {industry}",
        f"{account} audit program 절차",
        f"{account} 검토 확인",
    ])
    try:
        import sheet_code_registry as scr

        scr.set_mapping_variant(is_listed)
        code = scr.sheet_code_for_account(account)
        if code:
            queries.append(f"{code} {account} 감사절차")
    except Exception:  # noqa: BLE001
        pass

    cites: list[Citation] = []
    seen_src: set[str] = set()
    for q in queries:
        for c in retrieve(q, k=6, categories=WORKPAPER_CATEGORIES):
            if c.source in seen_src:
                continue
            if not _matches_workpaper_account(c, account, synonyms, is_listed=is_listed):
                continue
            if _snippet_quality(c) < -2:
                continue
            seen_src.add(c.source)
            cites.append(c)

    cites.sort(key=_snippet_quality, reverse=True)

    specs: list[ProcedureSpec] = []
    seen_name: set[str] = set()
    for c in cites:
        name = _procedure_label(c, account)
        if not _label_fits_account(name, account):
            continue
        if name in seen_name:
            continue
        if _SPREADSHEET_DUMP_RE.search(name) and _snippet_quality(c) < 1:
            continue
        seen_name.add(name)
        detect = _procedure_detect_tokens(c, account, name)
        specs.append(
            ProcedureSpec(
                name=name,
                detect_any=detect,
                basis=c.source,
                to_be=f"표준조서·실무조서 기준 「{name}」 수행·문서화를 확인하십시오.",
                snippet=_trim(c.snippet, 200),
            )
        )
    return tuple(specs[:6])


def get_standard_procedures(
    account: str,
    *,
    industry: str = "",
    is_listed: bool = True,
    k: int = 8,
    synonyms: tuple[str, ...] | None = None,
) -> list[ProcedureSpec]:
    """Hanul DB에서 계정별 표준 감사절차 프로그램 조회 (없으면 빈 리스트)."""
    syns = synonyms or (account,)
    syn_key = "|".join(dict.fromkeys(s for s in syns if s))
    _ = k
    return list(_cached_standard_procedures(account, is_listed, industry, syn_key))


def gather_citations(
    query: str,
    *,
    k_std: int = 3,
    k_qna: int = 2,
    k_case: int = 2,
    k_wp: int = 3,
    k_focus: int = 1,
) -> list[dict]:
    """계정·쟁점 질의에 대해 목적별(기준·질의회신·감리사례·절차예시·4대중점) 근거를 모은다.

    AI 심층 분석에 '인용 가능한 근거'로 제공하기 위한 구조화된 목록을 반환한다.
    각 항목: {group, source, snippet, ref}. 중복(출처+문구)은 제거한다.
    """
    plans = [
        ("기준", STANDARDS_CATEGORIES, k_std),
        ("질의회신", QNA_CATEGORIES, k_qna),
        ("감리지적사례", ENFORCEMENT_CATEGORIES, k_case),
        ("감사절차 예시", WORKPAPER_CATEGORIES, k_wp),
        ("4대중점", FOCUS_CATEGORIES, k_focus),
    ]
    out: list[dict] = []
    seen: set = set()
    for group, cats, k in plans:
        for c in retrieve(query, k=k, categories=cats):
            key = (c.source, c.snippet[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "group": group,
                    "source": c.source,
                    "snippet": _trim(c.snippet, 420),
                    "ref": c.ref,
                }
            )
    return out


def is_ready() -> bool:
    """색인 저장소가 존재하고 내용이 있는지 확인."""
    ensure_store()
    if not _sqlite_header_ok(STORE_PATH):
        return False
    try:
        con = _connect()
        cur = con.execute("SELECT count(*) FROM chunks LIMIT 1")
        return cur.fetchone()[0] > 0
    except sqlite3.Error:
        return False


def stats() -> dict:
    """색인 현황 요약."""
    if not os.path.exists(STORE_PATH):
        return {"documents": 0, "chunks": 0}
    con = _connect()
    docs = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    chunks = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    return {"documents": docs, "chunks": chunks}


def retrieve(
    query: str, k: int = 3, categories: list[str] | None = None
) -> list[Citation]:
    """질의와 관련된 근거를 FTS5(BM25) 로 검색.

    categories 를 지정하면 해당 카테고리(폴더) 자료만 대상으로 검색합니다.
    """
    if not is_ready():
        return []
    match = _build_match(query)
    if not match:
        return []
    sql = (
        "SELECT category, title, path, chunk_text, bm25(chunks) AS score "
        "FROM chunks WHERE chunks MATCH ?"
    )
    params: list = [match]
    if categories:
        placeholders = ",".join("?" for _ in categories)
        sql += f" AND category IN ({placeholders})"
        params.extend(categories)
    sql += " ORDER BY score LIMIT ?"
    params.append(k)
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    results: list[Citation] = []
    for category, title, path, chunk_text, score in rows:
        source = f"{category} · {title}" if category else title
        results.append(
            Citation(
                source=source,
                snippet=_trim(chunk_text),
                ref=resolve_source_path(path),
                score=float(score),
            )
        )
    return results


def _build_match(query: str) -> str:
    """자유 질의를 FTS5 MATCH 식(토큰 OR)으로 변환. 특수문자 안전 처리."""
    tokens = [t for t in _TOKEN_RE.findall(query) if t not in _STOPWORDS]
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    if not seen:
        return ""
    return " OR ".join(f'"{t}"' for t in seen[:12])


def _trim(text: str, limit: int = 320) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


# 사례번호 패턴 (예: KICPA-2024-14, FSS-2023-05, 2023-감리-042, 제12호)
_CASE_NO_RE = re.compile(
    r"[A-Z]{2,6}-\d{4}-\d+|\d{4}\s?-\s?[가-힣]+\s?-\s?\d+|제\s?\d+\s?호"
)


def parse_case(citation: "Citation") -> dict:
    """감리지적사례 인용에서 사례번호·주제·핵심요약을 추출."""
    title = citation.source.split("·")[-1].strip()
    m = _CASE_NO_RE.search(title) or _CASE_NO_RE.search(citation.ref)
    if m:
        number = m.group(0).replace(" ", "")
        subject = title.replace(m.group(0), "").strip(" _-").strip()
    else:
        number = title  # 번호 없는 모음집: 제목을 식별자로 사용
        subject = ""
    resolved = resolve_source_path(citation.ref)
    return {
        "number": number,
        "subject": subject,
        "brief": _brief(citation.snippet),
        "file": resolved.rsplit("/", 1)[-1] if resolved else "",
        "file_path": resolved,
        "has_number": bool(m),
    }


def _brief(text: str, limit: int = 150) -> str:
    """사례 핵심 내용을 간결하게 (문장 경계 우선)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("함.", "음.", "다.", ". "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[: idx + len(sep)].strip()
    return cut.strip() + "…"


@lru_cache(maxsize=1)
def _connect() -> sqlite3.Connection:
    ensure_store()
    con = sqlite3.connect(f"file:{STORE_PATH}?mode=ro", uri=True, check_same_thread=False)
    return con
