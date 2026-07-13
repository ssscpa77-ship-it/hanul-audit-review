"""Hanul DB 색인 빌더.

원본 자료 폴더의 문서를 텍스트로 추출·청크한 뒤 SQLite FTS5 저장소에 색인합니다.
이미 색인된(수정되지 않은) 파일은 건너뛰므로, 중단 후 다시 실행하면 이어서 진행됩니다.

사용법:
    VENV/bin/python build_index.py               # 전체 색인
    VENV/bin/python build_index.py --limit 30    # 앞 30개만 (검증용)
    VENV/bin/python build_index.py --retry-empty  # OCR 포함·내용없음(empty)만 재색인
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
import unicodedata

import kb_extract as ke
import knowledge_base as kb

_MAX_CHARS = 2_000_000  # 문서당 텍스트 상한
_MAX_CHUNKS = 400  # 문서당 청크 상한


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS documents ("
        "path TEXT PRIMARY KEY, category TEXT, title TEXT, "
        "mtime REAL, n_chunks INTEGER, chars INTEGER, status TEXT)"
    )
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
        "chunk_text, path UNINDEXED, category UNINDEXED, title UNINDEXED, "
        "tokenize='unicode61')"
    )
    con.commit()


def _reset_db(con: sqlite3.Connection) -> None:
    con.execute("DROP TABLE IF EXISTS documents")
    con.execute("DROP TABLE IF EXISTS chunks")
    con.commit()


def _iter_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.startswith("."):
                continue
            if ke.ext_of(name) in ke.SUPPORTED_EXTS:
                yield os.path.join(dirpath, name)


def _nfc(text: str) -> str:
    """macOS 파일명(NFD)을 NFC 로 정규화 — 한글 비교·검색 일관성 확보."""
    return unicodedata.normalize("NFC", text)


def _category_of(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    return _nfc(parts[0]) if len(parts) > 1 else "기타"


def _already_indexed(con: sqlite3.Connection, path: str, mtime: float) -> bool:
    row = con.execute(
        "SELECT mtime FROM documents WHERE path = ? AND status = 'ok'", (path,)
    ).fetchone()
    return bool(row and abs(row[0] - mtime) < 1.0)


def _empty_indexed_paths(con: sqlite3.Connection) -> list[str]:
    """이전 색인에서 내용없음(empty)으로 기록된 경로."""
    rows = con.execute("SELECT path FROM documents WHERE status = 'empty'").fetchall()
    return [r[0] for r in rows if os.path.isfile(r[0])]


def build(
    root: str,
    limit: int | None = None,
    reset: bool = False,
    *,
    retry_empty: bool = False,
) -> None:
    os.makedirs(kb.STORE_DIR, exist_ok=True)
    con = sqlite3.connect(kb.STORE_PATH)
    if reset:
        _reset_db(con)
    _init_db(con)

    all_files = sorted(_iter_files(root))
    if retry_empty:
        empty_only = set(_empty_indexed_paths(con))
        all_files = [p for p in all_files if p in empty_only]
        print(f"[재색인] empty 문서 {len(all_files)}건 (OCR: {'가능' if ke.ocr_available() else '비활성'})", flush=True)
    if limit:
        all_files = all_files[:limit]
    total = len(all_files)
    print(f"[색인 시작] 대상 폴더: {root}")
    print(f"[색인 시작] 지원 파일 {total}개 발견\n", flush=True)

    indexed = skipped = failed = chunk_total = 0
    t0 = time.time()

    for i, path in enumerate(all_files, start=1):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue

        if _already_indexed(con, path, mtime):
            skipped += 1
        else:
            category = _category_of(path, root)
            title = _nfc(os.path.splitext(os.path.basename(path))[0])
            text = ke.extract_text(path)[:_MAX_CHARS]
            chunks = ke.chunk_text(text)[:_MAX_CHUNKS]

            con.execute("DELETE FROM chunks WHERE path = ?", (path,))
            con.execute("DELETE FROM documents WHERE path = ?", (path,))
            if chunks:
                con.executemany(
                    "INSERT INTO chunks (chunk_text, path, category, title) "
                    "VALUES (?, ?, ?, ?)",
                    [(c, path, category, title) for c in chunks],
                )
                status = "ok"
                indexed += 1
                chunk_total += len(chunks)
            else:
                status = "empty"  # 추출 실패(스캔 이미지 등)
                failed += 1
            con.execute(
                "INSERT INTO documents (path, category, title, mtime, n_chunks, chars, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (path, category, title, mtime, len(chunks), len(text), status),
            )

        if i % 25 == 0 or i == total:
            con.commit()
            rate = i / max(time.time() - t0, 0.1)
            print(
                f"  진행 {i}/{total} | 색인 {indexed} · 건너뜀 {skipped} · "
                f"내용없음 {failed} · 청크 {chunk_total} | {rate:.1f}건/초",
                flush=True,
            )

    con.commit()
    con.close()
    dt = time.time() - t0
    print(
        f"\n[색인 완료] 색인 {indexed} · 건너뜀 {skipped} · 내용없음 {failed} · "
        f"총 청크 {chunk_total} · 소요 {dt/60:.1f}분"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Hanul DB 색인 빌더")
    ap.add_argument("--limit", type=int, default=None, help="처리할 파일 수 제한(검증용)")
    ap.add_argument("--reset", action="store_true", help="기존 색인 삭제 후 새로 생성")
    ap.add_argument(
        "--retry-empty",
        action="store_true",
        help="status=empty 문서만 재추출·재색인 (스캔 PDF OCR 포함)",
    )
    ap.add_argument("--path", default=kb.SOURCE_DIR, help="원본 자료 폴더 경로")
    args = ap.parse_args()

    if not os.path.isdir(args.path):
        print(f"[오류] 자료 폴더를 찾을 수 없습니다: {args.path}", file=sys.stderr)
        sys.exit(1)

    build(args.path, limit=args.limit, reset=args.reset, retry_empty=args.retry_empty)


if __name__ == "__main__":
    main()
