"""공개 URL 직접 다운로드용 — PDF·엑셀 export (터널·모바일 호환)."""

from __future__ import annotations

import os
import shutil
import unicodedata
from pathlib import Path

import knowledge_base as kb

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "share" / "exports"
EXPORT_REVIEW = EXPORT_DIR / "latest_review.xlsx"
FOCUS_LISTED = EXPORT_DIR / "focus_listed.pdf"
FOCUS_UNLISTED = EXPORT_DIR / "focus_unlisted.pdf"
CASE_DIR = EXPORT_DIR / "cases"


def _norm_name(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _focus_root_dir() -> str:
    return os.path.join(kb.SOURCE_DIR, "4대 중점사항 감리대상")


def resolve_focus_pdf(is_listed: bool) -> str | None:
    """Hanul DB-SSS 4대 중점사항 원문 PDF 경로."""
    root = _focus_root_dir()
    if not os.path.isdir(root):
        return None

    if is_listed:
        folder_keys = ("상장(IPO)", "상장", "금융감독원")
        file_keys = ("상장법인_4대", "상장법인", "중점심사 회계이슈")
    else:
        folder_keys = ("비상장", "한국공인회계사회")
        file_keys = ("비상장법인_4대", "비상장법인", "중점 점검분야")

    folder_path: str | None = None
    for d in sorted(os.listdir(root)):
        if d.startswith("."):
            continue
        full = os.path.join(root, d)
        if not os.path.isdir(full):
            continue
        nd = _norm_name(d)
        if is_listed:
            if "비상장" in nd:
                continue
            if any(k in nd for k in folder_keys):
                folder_path = full
                break
        else:
            if "비상장" in nd and any(k in nd for k in folder_keys):
                folder_path = full
                break

    if not folder_path:
        return None

    candidates: list[str] = []
    for f in os.listdir(folder_path):
        if f.startswith(".") or not f.lower().endswith(".pdf"):
            continue
        nf = _norm_name(f)
        if any(k in nf for k in file_keys):
            candidates.append(os.path.join(folder_path, f))

    if not candidates:
        pdfs = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf") and not f.startswith(".")
        ]
        return sorted(pdfs)[0] if pdfs else None

    for c in sorted(candidates):
        base = _norm_name(os.path.basename(c))
        if "4대 중점사항" in base and "보도자료" not in base and "사전예고 안내" not in base:
            return c
    return sorted(candidates)[0]


def publish_focus_pdf(is_listed: bool) -> Path | None:
    """원문 PDF를 exports 폴더에 복사 (게이트웨이 직접 서빙)."""
    src = resolve_focus_pdf(is_listed)
    if not src or not os.path.isfile(src):
        return None
    dest = FOCUS_LISTED if is_listed else FOCUS_UNLISTED
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def publish_case_file(file_path: str, note_id: str, case_no: str) -> Path | None:
    """감리지적 원문을 exports/cases 에 복사."""
    resolved = kb.resolve_source_path(file_path)
    if not resolved or not os.path.isfile(resolved):
        return None
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(resolved).suffix or ".bin"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in f"{note_id}_{case_no}")[:80]
    dest = CASE_DIR / f"{safe}{ext}"
    shutil.copy2(resolved, dest)
    return dest


def direct_url(base: str, name: str) -> str:
    return f"{base.rstrip('/')}/download/{name}"
