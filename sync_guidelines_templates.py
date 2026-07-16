"""Hanul DB 자가검토_지침_템플릿 → data/templates 동기화 (Streamlit Cloud 폴백용)."""

from __future__ import annotations

import shutil
from pathlib import Path

import knowledge_base as kb
import review_guidelines as rg


def sync_templates(*, source: Path | None = None, target: Path | None = None) -> list[str]:
    """Hanul DB xlsx를 repo data/templates/ 로 복사. 복사된 파일 경로 목록 반환."""
    src_root = source or (Path(kb.SOURCE_DIR) / rg.GUIDELINES_DB_SUBDIR)
    dst_root = target or (Path(__file__).resolve().parent / "data" / "templates")
    dst_root.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for key, fname in rg.TEMPLATE_FILES.items():
        src = src_root / fname
        if not src.is_file():
            print(f"  [skip] {key}: {src} 없음")
            continue
        dst = dst_root / fname
        shutil.copy2(src, dst)
        copied.append(str(dst))
        print(f"  [ok] {fname}")
    return copied


if __name__ == "__main__":
    print(f"동기화: {Path(kb.SOURCE_DIR) / rg.GUIDELINES_DB_SUBDIR}")
    print(f"    → {Path(__file__).resolve().parent / 'data/templates'}")
    files = sync_templates()
    print(f"\n완료: {len(files)}개 파일")
