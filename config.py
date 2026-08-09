"""앱 설정 — .env · Streamlit secrets."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


_ENV_PATH = _ROOT / ".env"
_EXAMPLE_PATH = _ROOT / ".env.example"


def _parse_env_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _format_env_lines(values: dict[str, str], template_text: str) -> str:
    """`.env.example` 순서·주석을 유지하며 값만 갱신."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in template_text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                lines.append(f"{key}={values[key]}")
                seen.add(key)
                continue
        lines.append(raw)
    for key, val in values.items():
        if key not in seen:
            lines.append(f"{key}={val}")
    return "\n".join(lines).rstrip() + "\n"


def _load_dotenv(*, override: bool = False) -> None:
    if not _ENV_PATH.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_PATH, override=override)
    except ImportError:
        for key, val in _parse_env_lines(_ENV_PATH.read_text(encoding="utf-8")).items():
            if override or key not in os.environ:
                os.environ[key] = val


def reload_env() -> None:
    """`.env` 변경 후 환경 변수를 다시 읽습니다."""
    _load_dotenv(override=True)


def env_file_exists() -> bool:
    return _ENV_PATH.is_file()


_load_dotenv()


def get(name: str, default: str = "") -> str:
    val = os.environ.get(name)
    if val:
        return val.strip()
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:  # noqa: BLE001
        pass
    return default


def _valid_key(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if v in ("sk-your-key-here", "sk-...", "your-key-here"):
        return False
    return True


def valid_api_key(value: str) -> bool:
    return _valid_key(value)


def masked_api_key() -> str:
    key = get("OPENAI_API_KEY")
    if not _valid_key(key):
        return ""
    if len(key) <= 11:
        return "sk-***"
    return f"{key[:7]}…{key[-4:]}"


def save_openai_settings(api_key: str, model: str = "", provider: str = "openai") -> None:
    """OpenAI API 설정을 `.env`에 저장하고 즉시 반영."""
    key = (api_key or "").strip()
    if not _valid_key(key):
        raise ValueError("유효한 OpenAI API 키를 입력해 주세요.")

    template = (
        _EXAMPLE_PATH.read_text(encoding="utf-8")
        if _EXAMPLE_PATH.is_file()
        else "AI_PROVIDER=openai\nOPENAI_API_KEY=\nOPENAI_MODEL=gpt-4o-mini\n"
    )
    values = _parse_env_lines(template)
    if _ENV_PATH.is_file():
        values.update(_parse_env_lines(_ENV_PATH.read_text(encoding="utf-8")))

    values["AI_PROVIDER"] = provider or "openai"
    values["OPENAI_API_KEY"] = key
    if model.strip():
        values["OPENAI_MODEL"] = model.strip()
    values.setdefault("OPENAI_MODEL", "gpt-4o-mini")
    values.setdefault("ALLOW_MANUAL_MATERIALITY", "true")
    values.setdefault("FSS_FOCUS_ISSUES_YEAR", "2026")
    values.setdefault(
        "FSS_FOCUS_ISSUES_LISTED",
        "국외매출채권,재고자산평가손실,투자부동산,충당부채우발부채",
    )
    values.setdefault("FALLBACK_TO_HARDCODED_PROCEDURES", "true")

    _ENV_PATH.write_text(_format_env_lines(values, template), encoding="utf-8")
    os.environ["AI_PROVIDER"] = values["AI_PROVIDER"]
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_MODEL"] = values["OPENAI_MODEL"]
    reload_env()


def get_bool(name: str, default: bool = False) -> bool:
    val = get(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_int(name: str, default: int = 0) -> int:
    val = get(name, "")
    try:
        return int(val)
    except ValueError:
        return default


def ai_provider() -> str | None:
    pref = get("AI_PROVIDER", "").lower()
    openai_ok = _valid_key(get("OPENAI_API_KEY"))
    azure_ok = _valid_key(get("AZURE_OPENAI_API_KEY")) and bool(get("AZURE_OPENAI_ENDPOINT"))
    if pref == "openai" and openai_ok:
        return "openai"
    if pref == "azure" and azure_ok:
        return "azure"
    if openai_ok:
        return "openai"
    if azure_ok:
        return "azure"
    return None


def ai_model_name() -> str:
    p = ai_provider()
    if p == "azure":
        return get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    if p == "openai":
        return get("OPENAI_MODEL", "gpt-4o-mini")
    return ""


def ai_provider_label() -> str:
    p = ai_provider()
    if p == "openai":
        return "OpenAI API"
    if p == "azure":
        return "Azure OpenAI"
    return "AI"


def ai_is_configured() -> bool:
    return ai_provider() is not None


def allow_manual_materiality() -> bool:
    return get_bool("ALLOW_MANUAL_MATERIALITY", True)


def fallback_to_hardcoded_procedures() -> bool:
    return get_bool("FALLBACK_TO_HARDCODED_PROCEDURES", True)


def review_variant() -> str:
    """A/B variant: vector_only | file_context_only | structured_hybrid."""
    return get("REVIEW_VARIANT", "structured_hybrid")


def rag_mode() -> str:
    """RAG mode: fts | vector | hybrid."""
    return get("RAG_MODE", "hybrid")


def embedding_provider() -> str:
    """local (fastembed) | openai."""
    return get("EMBEDDING_PROVIDER", "local")


def embedding_model() -> str:
    return get("EMBEDDING_MODEL", "")


def dual_rag_enabled() -> bool:
    return get_bool("DUAL_RAG_ENABLED", True)


def multi_agent_review_enabled() -> bool:
    """Claude Hanul DB 멀티에이전트 파이프라인 — 기본 ON (MULTI_AGENT_REVIEW=0 으로 끌 수 있음)."""
    return get_bool("MULTI_AGENT_REVIEW", True)


# ── 앱 버전 (UI·엑셀 표지 등) ─────────────────────────────────────
APP_VERSION = "0.9.1"
APP_RELEASE_LABEL = "멀티에이전트·필수절차 카탈로그 반영"
APP_BUILD_DATE = "2026-08-09"


def app_version_label() -> str:
    """짧은 버전 라벨 — 헤더·상태칩용."""
    return f"v{APP_VERSION} · {APP_RELEASE_LABEL}"


def app_version_detail() -> str:
    """상세 버전 — 툴팁·표지용."""
    return f"{app_version_label()} (빌드 {APP_BUILD_DATE})"


def server_port() -> int:
    return get_int("STREAMLIT_SERVER_PORT", 8505)


def _lan_ips() -> list[str]:
    import socket

    ips: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ips.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def deployment_access_urls() -> list[str]:
    """사내 테스트·배포용 접속 URL 목록 (도메인 없이 IP·localhost)."""
    base = get("APP_BASE_URL", "").strip().rstrip("/")
    if base:
        return [base]
    port = server_port()
    urls = [f"http://localhost:{port}"]
    for ip in _lan_ips():
        urls.append(f"http://{ip}:{port}")
    return list(dict.fromkeys(urls))


def primary_access_url() -> str:
    """동료에게 공유할 대표 접속 URL."""
    for url in deployment_access_urls():
        if "localhost" not in url and "127.0.0.1" not in url:
            return url
    return deployment_access_urls()[0]


def public_share_base() -> str:
    """카톡·터널 공개 URL (직접 다운로드 링크용)."""
    env = os.environ.get("PUBLIC_SHARE_URL", "").strip().rstrip("/")
    if env:
        return env
    stable = _ROOT / ".tunnel.url.stable"
    if stable.is_file():
        return stable.read_text(encoding="utf-8").strip().rstrip("/")
    current = _ROOT / ".tunnel.url"
    if current.is_file():
        return current.read_text(encoding="utf-8").strip().rstrip("/")
    return ""
