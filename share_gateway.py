"""카톡 공유 URL — 랜딩(OG) + Streamlit 역프록시 (단일 URL).

교수님께 전달한 공개 URL 하나로 랜딩·앱이 모두 동작합니다.
코드·KB 갱신 후 Streamlit만 재시작되면 동일 URL에서 최신 버전이 반영됩니다.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession, ClientConnectorError, ClientTimeout, WSMsgType, web

ROOT = Path(__file__).resolve().parent
SHARE_DIR = ROOT / "share"
EXPORT_REVIEW = SHARE_DIR / "exports" / "latest_review.xlsx"
FOCUS_LISTED = SHARE_DIR / "exports" / "focus_listed.pdf"
FOCUS_UNLISTED = SHARE_DIR / "exports" / "focus_unlisted.pdf"
CASE_DIR = SHARE_DIR / "exports" / "cases"
TEMPLATE = SHARE_DIR / "share_landing.html"
OG_IMAGE = SHARE_DIR / "share_og.png"

GATEWAY_PORT = int(os.environ.get("SHARE_GATEWAY_PORT", "8506"))
STREAMLIT_PORT = int(os.environ.get("STREAMLIT_SERVER_PORT", "8505"))
STREAMLIT_ORIGIN = os.environ.get("STREAMLIT_ORIGIN", f"http://127.0.0.1:{STREAMLIT_PORT}")

BOT_UA = re.compile(
    r"kakao|kakaotalk|kakaostory|facebookexternalhit|twitterbot|slackbot|telegram|discord|"
    r"googlebot|bingbot|yeti|linkedinbot|whatsapp|daumoa",
    re.I,
)
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
SKIP_TO_BACKEND = HOP_BY_HOP | {
    "host",
    "content-length",
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
}


def _app_version_info() -> dict:
    try:
        import config
        import knowledge_base as kb

        info = {
            "version": config.app_version_label(),
            "build": config.APP_BUILD_DATE,
            "kb_ready": kb.is_ready(),
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        if kb.is_ready():
            s = kb.stats()
            info["kb_documents"] = s.get("documents", 0)
            info["kb_chunks"] = s.get("chunks", 0)
        return info
    except Exception as exc:  # noqa: BLE001
        return {"version": "unknown", "error": str(exc)}


def _render_landing(host_header: str) -> bytes:
    share_base = f"https://{host_header}".rstrip("/")
    html = TEMPLATE.read_text(encoding="utf-8")
    ver = _app_version_info()
    html = html.replace("{{SHARE_URL}}", share_base + "/?share=1")
    html = html.replace("{{OG_IMAGE_URL}}", share_base + "/share_og.png")
    html = html.replace("{{APP_URL}}", share_base + "/?app=1")
    html = html.replace("{{VERSION_LABEL}}", ver.get("version", ""))
    html = html.replace(
        "{{KB_LABEL}}",
        f"Hanul DB {ver.get('kb_documents', 0):,}건"
        if ver.get("kb_ready")
        else "Hanul DB 연결 대기",
    )
    return html.encode("utf-8")


def _forward_headers(request: web.Request, *, to_backend: bool = False) -> dict[str, str]:
    client_host = request.headers.get("Host", "")
    out: dict[str, str] = {}
    skip = SKIP_TO_BACKEND if to_backend else HOP_BY_HOP
    for key, val in request.headers.items():
        if key.lower() in skip:
            continue
        out[key] = val
    if to_backend:
        out["Host"] = f"127.0.0.1:{STREAMLIT_PORT}"
    out["X-Forwarded-Host"] = client_host
    out["X-Forwarded-Proto"] = "https" if client_host else request.scheme
    out["X-Forwarded-For"] = request.remote or ""
    return out


def _streamlit_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", STREAMLIT_PORT), timeout=1.5):
            return True
    except OSError:
        return False


def _maintenance_html() -> bytes:
    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>잠시 후 다시 시도</title></head>"
        "<body style='font-family:sans-serif;background:#0a2a63;color:#fff;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh'>"
        "<div style='text-align:center;max-width:420px;padding:24px'>"
        "<h2>서버를 준비 중입니다</h2>"
        "<p>잠시 후 새로고침하거나 아래 링크로 다시 접속해 주세요.</p>"
        "<p><a href='/' style='color:#fdb913'>랜딩으로 돌아가기</a></p>"
        "</div></body></html>"
    ).encode("utf-8")


def _ws_protocols(request: web.Request) -> tuple[str, ...]:
    raw = request.headers.get("Sec-WebSocket-Protocol", "")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _streamlit_rel(request: web.Request, *, path_qs: str | None = None) -> str:
    """Streamlit으로 넘길 경로 — 게이트웨이 전용 ?app=1 제거."""
    if path_qs is not None:
        if path_qs.startswith("/?") and "app=1" in path_qs:
            return "/"
        return path_qs
    if request.query.get("app") == "1":
        return request.path or "/"
    return request.rel_url.path_qs


async def _proxy_http(request: web.Request, *, path_qs: str | None = None) -> web.StreamResponse:
    if not _streamlit_up():
        return web.Response(
            body=_maintenance_html(),
            status=503,
            content_type="text/html",
            charset="utf-8",
            headers={"Cache-Control": "no-cache", "Retry-After": "5"},
        )
    rel = _streamlit_rel(request, path_qs=path_qs)
    target = f"{STREAMLIT_ORIGIN}{rel}"
    headers = _forward_headers(request, to_backend=True)
    body = await request.read()

    try:
        async with ClientSession(auto_decompress=False) as session:
            async with session.request(
                request.method,
                target,
                headers=headers,
                data=body if body else None,
                allow_redirects=False,
                timeout=ClientTimeout(total=120),
            ) as resp:
                excluded = HOP_BY_HOP | {"content-encoding", "content-length"}
                out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
                payload = await resp.read()
                return web.Response(body=payload, status=resp.status, headers=out_headers)
    except (ClientConnectorError, asyncio.TimeoutError, OSError):
        return web.Response(
            body=_maintenance_html(),
            status=503,
            content_type="text/html",
            charset="utf-8",
            headers={"Cache-Control": "no-cache", "Retry-After": "5"},
        )


async def _proxy_websocket(request: web.Request, *, path_qs: str | None = None) -> web.WebSocketResponse:
    if not _streamlit_up():
        raise web.HTTPServiceUnavailable(text="Streamlit starting")
    rel = _streamlit_rel(request, path_qs=path_qs)
    ws_target = STREAMLIT_ORIGIN.replace("http://", "ws://").replace("https://", "wss://")
    ws_target = f"{ws_target}{rel}"
    protocols = _ws_protocols(request)

    ws_server = web.WebSocketResponse(protocols=protocols, heartbeat=30)
    await ws_server.prepare(request)

    async with ClientSession() as session:
        async with session.ws_connect(
            ws_target,
            headers=_forward_headers(request, to_backend=True),
            protocols=protocols,
            heartbeat=30,
            autoping=True,
        ) as ws_client:

            async def client_to_server() -> None:
                try:
                    async for msg in ws_server:
                        if msg.type == WSMsgType.TEXT:
                            await ws_client.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await ws_client.send_bytes(msg.data)
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                            break
                except Exception:  # noqa: BLE001
                    pass

            async def server_to_client() -> None:
                try:
                    async for msg in ws_client:
                        if msg.type == WSMsgType.TEXT:
                            await ws_server.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await ws_server.send_bytes(msg.data)
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                            break
                except Exception:  # noqa: BLE001
                    pass

            await asyncio.gather(client_to_server(), server_to_client())

    return ws_server


async def handle_review_download(_request: web.Request) -> web.Response:
    """Streamlit 버튼 대신 HTTP 직접 다운로드 (터널·카톡 브라우저 호환)."""
    if not EXPORT_REVIEW.is_file():
        return web.Response(
            text="엑셀 파일이 아직 없습니다. 앱에서 조서 업로드 후 리뷰를 실행하세요.",
            status=404,
            content_type="text/plain; charset=utf-8",
        )
    return web.FileResponse(
        EXPORT_REVIEW,
        headers={
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": 'attachment; filename="hanul_review_note.xlsx"',
            "Cache-Control": "no-cache",
        },
    )


async def handle_pdf_download(path: Path, filename: str) -> web.Response:
    if not path.is_file():
        return web.Response(
            text="PDF 파일을 찾을 수 없습니다. 앱에서 한 번 새로고침 후 다시 시도하세요.",
            status=404,
            content_type="text/plain; charset=utf-8",
        )
    return web.FileResponse(
        path,
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


async def handle_landing(request: web.Request) -> web.Response:
    return web.Response(
        body=_render_landing(request.host),
        content_type="text/html",
        charset="utf-8",
        headers={"Cache-Control": "no-cache"},
    )


async def route(request: web.Request) -> web.StreamResponse:
    path = request.path.rstrip("/") or "/"

    if path == "/health":
        return web.Response(text="ok")
    if path == "/version":
        return web.json_response(_app_version_info())
    if path in ("/share_og.png", "/og-image.png"):
        if not OG_IMAGE.is_file():
            raise web.HTTPNotFound()
        return web.Response(
            body=OG_IMAGE.read_bytes(),
            content_type="image/png",
            headers={"Cache-Control": "public, max-age=300"},
        )
    if path == "/download/review-notes.xlsx":
        return await handle_review_download(request)
    if path == "/download/focus-listed.pdf":
        return await handle_pdf_download(FOCUS_LISTED, "hanul_focus_listed.pdf")
    if path == "/download/focus-unlisted.pdf":
        return await handle_pdf_download(FOCUS_UNLISTED, "hanul_focus_unlisted.pdf")
    if path.startswith("/download/cases/"):
        name = path.rsplit("/", 1)[-1]
        if not name or ".." in name:
            raise web.HTTPNotFound()
        return await handle_pdf_download(CASE_DIR / name, name)

    if path in ("/", "/share"):
        if request.query.get("app") == "1":
            qs = request.rel_url.query_string
            path_qs = "/" + (f"?{qs}" if qs else "")
            if request.headers.get("Upgrade", "").lower() == "websocket":
                return await _proxy_websocket(request, path_qs=path_qs)
            return await _proxy_http(request, path_qs=path_qs)
        if BOT_UA.search(request.headers.get("User-Agent", "")):
            return await handle_landing(request)
        return await handle_landing(request)

    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await _proxy_websocket(request)
    return await _proxy_http(request)


@web.middleware
async def _error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:  # noqa: BLE001
        return web.Response(
            body=_maintenance_html(),
            status=503,
            content_type="text/html",
            charset="utf-8",
        )


def main() -> None:
    app = web.Application(middlewares=[_error_middleware])
    app.router.add_route("*", "/{path:.*}", route)
    print(f"Unified gateway 0.0.0.0:{GATEWAY_PORT} → {STREAMLIT_ORIGIN}")
    web.run_app(app, host="0.0.0.0", port=GATEWAY_PORT, print=lambda *_a, **_k: None)


if __name__ == "__main__":
    main()
