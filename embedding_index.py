"""벡터 임베딩 색인 — semantic RAG (Phase 2).

로컬: fastembed 다국어 모델 (기본)
대안: OpenAI text-embedding-3-small (EMBEDDING_PROVIDER=openai)
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

import config as app_config

# 정성 RAG 대상 카테고리 (workpaper 수치 그리드 제외 — 별도 전처리 후 확장)
QUALITATIVE_EMBED_CATEGORIES = frozenset(
    {
        "회계감사기준",
        "한국채택국제회계기준",
        "일반기업회계기준",
        "K-IFRS 실무사례와 해설",
        "질의회신_한국회계기준원",
        "금융감독원 감리지적사례",
        "한국공인회계사회 감리지적사례",
        "4대 중점사항 감리대상",
        "자가검토_지침_템플릿",
    }
)

_DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 64


def embedding_provider() -> str:
    return app_config.get("EMBEDDING_PROVIDER", "local").lower()


def embedding_model_name() -> str:
    custom = app_config.get("EMBEDDING_MODEL", "").strip()
    if custom:
        return custom
    if embedding_provider() == "openai":
        return _DEFAULT_OPENAI_MODEL
    return _DEFAULT_LOCAL_MODEL


def should_embed_category(category: str) -> bool:
    return category in QUALITATIVE_EMBED_CATEGORIES


def init_vector_table(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS chunk_vectors ("
        "chunk_rowid INTEGER PRIMARY KEY, "
        "path TEXT NOT NULL, "
        "category TEXT NOT NULL, "
        "dim INTEGER NOT NULL, "
        "embedding BLOB NOT NULL)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_vectors_category "
        "ON chunk_vectors(category)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS embedding_meta ("
        "key TEXT PRIMARY KEY, value TEXT)"
    )
    con.commit()


def _set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO embedding_meta (key, value) VALUES (?, ?)",
        (key, value),
    )


def vector_stats(con: sqlite3.Connection) -> dict:
    try:
        n = con.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0]
        dim = con.execute(
            "SELECT dim FROM chunk_vectors LIMIT 1"
        ).fetchone()
        meta = dict(con.execute("SELECT key, value FROM embedding_meta").fetchall())
        return {
            "vectors": n,
            "dim": dim[0] if dim else 0,
            "provider": meta.get("provider", ""),
            "model": meta.get("model", ""),
        }
    except sqlite3.Error:
        return {"vectors": 0, "dim": 0, "provider": "", "model": ""}


def vectors_available(con: sqlite3.Connection) -> bool:
    try:
        return con.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def _pack_vector(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


def _unpack_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim)


@lru_cache(maxsize=1)
def _local_embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=embedding_model_name())


def _openai_client():
    from openai import OpenAI

    return OpenAI(api_key=app_config.get("OPENAI_API_KEY"))


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """텍스트 배치 → (n, dim) float32, L2 정규화."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    provider = embedding_provider()
    if provider == "openai" and app_config.valid_api_key(app_config.get("OPENAI_API_KEY")):
        client = _openai_client()
        model = embedding_model_name()
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = list(texts[i : i + _BATCH_SIZE])
            resp = client.embeddings.create(model=model, input=batch)
            out.extend([d.embedding for d in resp.data])
        mat = np.asarray(out, dtype=np.float32)
    else:
        model = _local_embedder()
        mat = np.asarray(list(model.embed(texts)), dtype=np.float32)

    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def embed_query(query: str) -> np.ndarray:
    """단일 질의 벡터 (1, dim)."""
    mat = embed_texts([query.strip() or " "])
    return mat[0] if len(mat) else np.zeros(0, dtype=np.float32)


def delete_vectors_for_path(con: sqlite3.Connection, path: str) -> None:
    con.execute("DELETE FROM chunk_vectors WHERE path = ?", (path,))


def store_chunk_vectors(
    con: sqlite3.Connection,
    rows: Iterable[tuple[int, str, str, np.ndarray]],
) -> int:
    """(chunk_rowid, path, category, vector) 저장."""
    n = 0
    for rowid, path, category, vec in rows:
        dim = int(vec.shape[0])
        con.execute(
            "INSERT OR REPLACE INTO chunk_vectors "
            "(chunk_rowid, path, category, dim, embedding) VALUES (?, ?, ?, ?, ?)",
            (rowid, path, category, dim, _pack_vector(vec)),
        )
        n += 1
    return n


def index_path_vectors(
    con: sqlite3.Connection,
    path: str,
    *,
    category: str | None = None,
) -> int:
    """한 문서 path 의 청크 임베딩 생성·저장."""
    if category and not should_embed_category(category):
        delete_vectors_for_path(con, path)
        return 0

    chunk_rows = con.execute(
        "SELECT rowid, chunk_text, category FROM chunks WHERE path = ?",
        (path,),
    ).fetchall()
    if not chunk_rows:
        delete_vectors_for_path(con, path)
        return 0

    texts: list[str] = []
    meta: list[tuple[int, str]] = []
    for rowid, text, cat in chunk_rows:
        if not should_embed_category(cat):
            continue
        texts.append(str(text))
        meta.append((int(rowid), cat))

    if not texts:
        delete_vectors_for_path(con, path)
        return 0

    delete_vectors_for_path(con, path)
    mat = embed_texts(texts)
    rows = [
        (rowid, path, cat, mat[i])
        for i, (rowid, cat) in enumerate(meta)
    ]
    return store_chunk_vectors(con, rows)


def build_all_vectors(
    con: sqlite3.Connection,
    *,
    limit: int | None = None,
    progress_every: int = 50,
) -> dict:
    """기존 FTS 청크 전체에 임베딩 생성 (정성 카테고리만)."""
    init_vector_table(con)
    paths = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT path FROM chunks WHERE category IN ("
            + ",".join("?" * len(QUALITATIVE_EMBED_CATEGORIES))
            + ")",
            tuple(QUALITATIVE_EMBED_CATEGORIES),
        ).fetchall()
    ]
    if limit:
        paths = paths[:limit]

    total_vecs = 0
    for i, path in enumerate(paths, 1):
        cat_row = con.execute(
            "SELECT category FROM chunks WHERE path = ? LIMIT 1", (path,)
        ).fetchone()
        cat = cat_row[0] if cat_row else ""
        total_vecs += index_path_vectors(con, path, category=cat)
        if i % progress_every == 0 or i == len(paths):
            con.commit()
            print(f"  [임베딩] {i}/{len(paths)} 문서 · 벡터 {total_vecs}건", flush=True)

    _set_meta(con, "provider", embedding_provider())
    _set_meta(con, "model", embedding_model_name())
    con.commit()
    return {"documents": len(paths), "vectors": total_vecs}


@lru_cache(maxsize=2)
def _load_vector_matrix(
    store_path: str,
    categories_key: str,
) -> tuple[np.ndarray, list[tuple[int, str, str, str]]]:
    """카테고리 필터된 벡터 행렬 + 메타 (rowid, path, category, title)."""
    cats = tuple(categories_key.split("\x1f")) if categories_key else ()
    con = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        if cats:
            placeholders = ",".join("?" * len(cats))
            sql = (
                "SELECT v.chunk_rowid, v.embedding, v.dim, v.path, v.category, c.title, c.chunk_text "
                "FROM chunk_vectors v "
                "JOIN chunks c ON c.rowid = v.chunk_rowid "
                f"WHERE v.category IN ({placeholders})"
            )
            rows = con.execute(sql, cats).fetchall()
        else:
            rows = con.execute(
                "SELECT v.chunk_rowid, v.embedding, v.dim, v.path, v.category, c.title, c.chunk_text "
                "FROM chunk_vectors v JOIN chunks c ON c.rowid = v.chunk_rowid"
            ).fetchall()
    finally:
        con.close()

    if not rows:
        return np.zeros((0, 0), dtype=np.float32), []

    dim = int(rows[0][2])
    mat = np.vstack([_unpack_vector(r[1], dim) for r in rows])
    meta = [
        (int(r[0]), str(r[3]), str(r[4]), str(r[5]), str(r[6]))
        for r in rows
    ]
    return mat, meta


def search_semantic(
    store_path: str,
    query: str,
    *,
    k: int = 6,
    categories: Sequence[str] | None = None,
) -> list[tuple[float, int, str, str, str, str]]:
    """코사인 유사도 검색 → (score, rowid, path, category, title, chunk_text)."""
    q = embed_query(query)
    if q.size == 0:
        return []

    cat_key = "\x1f".join(categories) if categories else ""
    mat, meta = _load_vector_matrix(store_path, cat_key)
    if mat.size == 0:
        return []

    scores = mat @ q
    top_idx = np.argsort(scores)[::-1][:k]
    out: list[tuple[float, int, str, str, str, str]] = []
    for idx in top_idx:
        i = int(idx)
        if i < 0 or i >= len(meta):
            continue
        rowid, path, cat, title, text = meta[i]
        out.append((float(scores[i]), rowid, path, cat, title, text))
    return out


def clear_vector_cache() -> None:
    _load_vector_matrix.cache_clear()
