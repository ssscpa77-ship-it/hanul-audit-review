"""
감사조서 자가검토 — 리뷰노트 대시보드 (MVP)

업로드한 감사조서(PDF·엑셀·워드)를 파싱하고 규칙엔진으로 점검해
리뷰노트를 생성하는 대시보드입니다.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib
import os
import re
import subprocess
import unicodedata
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

import config  # noqa: F401 — .env 로드
import sheet_code_registry
importlib.reload(sheet_code_registry)
import output_formatter
importlib.reload(output_formatter)

import ai_review
import fss_focus
import knowledge_base as kb
import note_merge
import notes_pipeline
import review_engine as re_engine
import qc_review
importlib.reload(qc_review)
importlib.reload(notes_pipeline)
from excel_export import build_review_notes_excel
from parser import parse_uploads
from review_engine import Materiality, extract_engagement, extract_materiality, run_review
from sample_data import (
    SAMPLE_ENGAGEMENT,
    SAMPLE_REVIEW_NOTES,
    count_by_importance,
    sort_notes_by_importance,
)

st.set_page_config(
    page_title="한울회계법인 · 감사조서 자가검토",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IMPORTANCE_COLORS = {
    "상": "#C00000",
    "중": "#ED7D31",
    "하": "#70AD47",
}

# 한울(Crowe) 로고 — 흰색/금색 (네이비 배경용)
LOGO_SVG = """<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 208 60" style="width:92px; flex-shrink:0;" role="img" aria-label="Crowe 한울"> <g> <path style="fill:#ffffff;" d="M111.9,19.4c-2.5-1.8-5.7-2.7-8.8-2.7c-8.4,0-13.3,5.7-13.3,13.1c0,8,5.9,13.5,13.3,13.5c2.9,0,6.1-0.8,8.6-2.3l1.8,2.7c-3.1,2-6.8,2.9-10.6,2.9c-12.1,0-18.2-7.8-18.2-16.6c0-8,6.7-16.4,18.8-16.4c3.7,0,7.4,1,10.4,3.3L111.9,19.4"></path> <path style="fill:#ffffff;" d="M120.1,25.8l1.8-1.8c1-1,2.2-1.6,3.5-1.8c1.6,0.2,2.9,1,3.9,2.2l-2,2.7c-1-0.6-2.2-1-3.3-1c-2.2,0-4.1,2.2-4.1,7.2v12.3h-4.3V23.1h4.3L120.1,25.8"></path> <path style="fill:#ffffff;" d="M127.9,34.2c-0.2-6.3,4.9-11.7,11.3-11.9c6.5-0.2,12.1,4.7,12.3,11.1c0,0.2,0,0.6,0,0.8c0,7-4.7,12.1-11.9,12.1S127.9,41.3,127.9,34.2 M132.6,34.2c0,4.3,1.6,9.4,7.2,9.4s7.2-5.1,7.2-9.4s-2-8.8-7.4-8.8S132.4,30.1,132.6,34.2"></path> <path style="fill:#ffffff;" d="M170.6,23.1c2.3,5.5,4.7,11,7,17.4c2-6.7,3.9-12.3,5.9-17.8l3.9,0.6L179,46H176c-2.3-5.7-4.9-11.3-7.2-17.8c-2.3,6.5-4.5,12.1-7,17.8H159l-8.4-22.3l4.3-1c2,5.7,3.9,11.1,5.9,17.8c2.3-6.5,4.7-11.9,7-17.4"></path> <path style="fill:#ffffff;" d="M191.1,34.6c-0.2,4.5,3.3,8.4,8.2,8.8c2.3,0,4.7-0.8,6.7-2l1.2,2.2c-2.3,1.6-5.1,2.5-8,2.7c-7.4,0-12.5-4.3-12.5-12.3c-0.4-6.1,4.3-11.1,10.6-11.5c0.4,0,0.6,0,1,0c7.2,0,9.8,6.3,9.4,12.3h-16.4V34.6z M203.2,31.9c0-3.5-1.6-6.7-5.3-6.7s-6.7,2.7-6.7,6.3v0.2h11.9V31.9z"></path> </g> <path style="fill:#FDB913;" d="M36.8,0.4c0-0.2-0.2-0.2-0.4-0.4C36.2,0,36,0.2,36,0.2L0.2,58.3C0,58.5,0,58.7,0,58.7s0.2,0,0.2-0.2l35.6-41.3C36,17,36,17,36,17s0,0.2-0.2,0.4L11.1,58.5v0.2c0,0,0.2,0,0.2-0.2l28.9-33.8c0.2-0.2,0.2-0.2,0.2-0.2s0,0.2-0.2,0.4L21.5,58.3c0,0.2,0,0.4,0,0.4s0.2,0,0.2-0.2l23.1-26.8c0.2-0.4,0.4-0.4,0.6-0.4s0.4,0.2,0.6,0.2l22.5,27c0,0.2,0.2,0.2,0.2,0.2s0-0.2-0.2-0.4L36.8,0.4"></path> </svg>"""


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display:none;}
        header[data-testid="stHeader"] {background:transparent;}
        /* 전반 배율 — 가독성 위해 표준 크기 유지 */
        .block-container {max-width:1080px; padding-top:.8rem; padding-bottom:1rem;}
        @media (min-width:901px) {
            .block-container {padding-right:168px;}
        }
        div[data-testid="stVerticalBlock"] {gap:.9rem;}

        .app-header {
            display:flex; align-items:center; gap:16px;
            background:linear-gradient(135deg,#0A2A63 0%,#123C97 100%);
            padding:12px 24px; border-radius:14px;
            box-shadow:0 6px 18px rgba(10,42,99,.26); margin-bottom:22px;
        }
        .app-header .brand-logo {display:flex; flex-direction:column; align-items:center;
            gap:4px; width:110px; flex-shrink:0;}
        .app-header .brand-firm {color:#fff; font-size:.84rem; font-weight:700; letter-spacing:.02em;}
        .app-header .brand-center {flex:1; text-align:center;}
        .app-header .brand-spacer {width:110px; flex-shrink:0;}
        .app-header .brand-title {color:#fff; font-size:1.42rem; font-weight:800; margin:0; line-height:1.2;}
        .app-header .brand-sub {color:#bcd2ff; font-size:.8rem; margin:3px 0 0;}
        .app-header .brand-version {color:#8eb4ff; font-size:.72rem; margin:2px 0 0; letter-spacing:.01em;}

        .kb-badge {display:inline-block; background:#0A2A63; color:#fff; padding:6px 16px;
            border-radius:20px; font-size:.85rem; font-weight:600; margin-top:14px;}
        .kb-badge.off {background:#8aa0c4;}

        div.stButton>button[kind="primary"], div.stDownloadButton>button[kind="primary"] {
            background:#FDB913; color:#0A2A63; border:none; font-weight:800; border-radius:10px;
        }
        div.stButton>button[kind="primary"]:hover, div.stDownloadButton>button[kind="primary"]:hover {
            background:#ffca3a; color:#0A2A63;
        }

        /* --- 메인: 감사조서 업로드 강조 --- */
        .upload-hero {
            display:flex; align-items:center; gap:10px;
            background:linear-gradient(135deg,#0A2A63 0%,#1a4da8 100%);
            color:#fff; font-size:1.05rem; font-weight:800;
            padding:9px 16px; border-radius:11px; margin-bottom:8px;
            box-shadow:0 3px 10px rgba(10,42,99,.25);
        }
        .upload-hero .badge {background:#FDB913; color:#0A2A63; font-size:.74rem;
            font-weight:800; padding:2px 9px; border-radius:11px;}
        [data-testid="stFileUploaderDropzone"] {
            background:linear-gradient(135deg,#fffef8 0%,#fff4d6 100%);
            border:3px solid #123C97; border-radius:12px; min-height:88px;
            box-shadow:0 3px 10px rgba(10,42,99,.16);
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color:#FDB913; background:#fff9e6;
            box-shadow:0 4px 16px rgba(253,185,19,.3);
        }

        /* --- 숫자 입력(중요성 금액) — 불필요한 선 제거, 가시성 개선 --- */
        [data-testid="stNumberInput"] div[data-baseweb="input"] {
            border:2px solid #9db8e6; border-radius:10px; background:#fff;
            overflow:hidden;
        }
        [data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within {
            border-color:#123C97; box-shadow:0 0 0 3px rgba(18,60,151,.12);
        }
        [data-testid="stNumberInput"] input {
            background:#fff; color:#0A2A63; font-weight:700; border:none;
        }
        [data-testid="stNumberInput"] button {
            background:#eef4ff; color:#0A2A63; border:none;
        }
        [data-testid="stNumberInput"] button:hover {
            background:#123C97; color:#fff;
        }

        /* --- 스크롤바 — 항상 표시·눈에 잘 띄게 (단일 스크롤: html/body) --- */
        html {
            font-size:16px;
            scrollbar-gutter: stable;
        }
        html, body {
            scrollbar-width:auto;
            scrollbar-color:#123C97 #dfe8f6;
        }
        ::-webkit-scrollbar {width:14px; height:14px; -webkit-appearance:none;}
        ::-webkit-scrollbar-track {background:#dfe8f6; border-radius:8px;}
        ::-webkit-scrollbar-thumb {background:#123C97; border-radius:8px;
            border:3px solid #dfe8f6; min-height:56px;}
        ::-webkit-scrollbar-thumb:hover {background:#0A2A63;}
        ::-webkit-scrollbar-thumb:active {background:#082050;}

        /* --- 오른쪽 고정 이동 패널 (JS로 parent에 주입) --- */
        .hanul-scroll-nav {
            position:fixed; right:18px; top:50%; transform:translateY(-50%);
            z-index:999999; display:flex; flex-direction:column; gap:8px;
            pointer-events:none;
        }
        .hanul-scroll-nav .hanul-nav-btn {
            pointer-events:auto; display:flex; align-items:center; justify-content:center;
            gap:6px; min-width:132px; padding:10px 14px;
            background:#fff; color:#0A2A63; border:2px solid #123C97;
            border-radius:12px; font-size:.82rem; font-weight:800;
            box-shadow:0 4px 16px rgba(10,42,99,.18); cursor:pointer;
            transition:background .15s, transform .15s, opacity .2s;
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
        }
        .hanul-scroll-nav .hanul-nav-btn:hover {
            background:#123C97; color:#fff; transform:translateX(-3px);
        }
        .hanul-scroll-nav .hanul-nav-btn.primary {
            background:linear-gradient(135deg,#0A2A63 0%,#123C97 100%);
            color:#fff; border-color:#0A2A63;
        }
        .hanul-scroll-nav .hanul-nav-btn.primary:hover {background:#082050;}
        .hanul-scroll-nav .hanul-nav-btn.hidden {opacity:0; pointer-events:none;}
        .hanul-scroll-nav .hanul-nav-sep {
            height:1px; background:#c5d4ea; margin:2px 8px; pointer-events:none;
        }
        @media (max-width:900px) {
            .hanul-scroll-nav {right:10px; top:auto; bottom:20px; transform:none;}
            .hanul-scroll-nav .hanul-nav-btn {min-width:112px; padding:9px 11px; font-size:.78rem;}
            .hanul-scroll-nav .hanul-nav-extra {display:none;}
        }

        /* 페이지 내 섹션 점프 앵커 */
        .hanul-anchor {
            display:block; height:1px; margin:0; padding:0; border:0;
            scroll-margin-top:96px;
        }

        .flow {display:flex; align-items:center; justify-content:center; flex-wrap:wrap;
            gap:8px; margin:2px 0 20px;}
        .flow-step {display:flex; align-items:center; gap:10px; text-align:left;
            background:#fff; border:1px solid #d5e2f7; border-left:4px solid #123C97;
            border-radius:10px; padding:9px 16px;
            box-shadow:0 2px 6px rgba(10,42,99,.07);}
        .flow-step .ic {font-size:1.35rem; line-height:1;}
        .flow-step .t {font-weight:800; color:#0A2A63; font-size:.95rem; line-height:1.25;}
        .flow-step .d {font-size:.78rem; color:#5b6b85; margin-top:1px; line-height:1.2;}
        .flow-arrow {color:#123C97; font-size:1.1rem; font-weight:700; padding:0 2px;}

        /* --- API 연동 · 샘플 미리보기 — 가시성 있는 색상 구분 --- */
        div[data-testid="stExpander"] details {
            background:#eaf1ff; border:2px solid #8fadde; border-radius:12px;
        }
        div[data-testid="stExpander"] summary {font-weight:700; color:#0A2A63;}
        div[data-testid="stExpander"] summary:hover {color:#123C97;}
        .st-key-sample_preview button {
            background:#fff4d6; border:2px solid #FDB913; color:#0A2A63;
            font-weight:800; border-radius:12px;
        }
        .st-key-sample_preview button:hover {
            background:#FDB913; border-color:#FDB913; color:#0A2A63;
        }
        .section-title {color:#0A2A63; font-weight:800; font-size:1.05rem; margin:2px 0 0;}

        .focus-issue-compact .fi {font-size:.78rem; line-height:1.22; color:#334155;
            margin:0; padding:0;}

        /* --- 4대 중점사항 원문보기 — 열기 버튼 --- */
        .st-key-btn_focus_source button {
            background:#fff; border:1.5px solid #c5d4ea; color:#0A2A63;
            font-weight:700; border-radius:10px; white-space:nowrap;
        }
        .st-key-btn_focus_source button:hover {
            background:#f4f7fc; border-color:#8fadde;
        }
        .focus-block {margin:0 0 10px; padding:8px 10px; border-radius:10px;
            background:#f4f7fc; border:1px solid #d8e2f0;}
        .focus-block.active {background:#eaf1ff; border-color:#8fadde;}
        .focus-block-h {font-size:.84rem; font-weight:800; color:#0A2A63; margin:0 0 4px;}
        .focus-block-src {font-size:.74rem; color:#64748b; font-weight:600; margin-left:4px;}
        .focus-issue-compact {margin:0 0 6px;}

        /* --- 결과 화면 헤더 --- */
        .result-hero {
            background:linear-gradient(135deg,#0A2A63 0%,#1a4da8 100%);
            border-radius:16px; padding:22px 28px; margin:4px 0 18px;
            box-shadow:0 8px 24px rgba(10,42,99,.22);
        }
        .result-hero .r-title {color:#fff; font-size:1.55rem; font-weight:800; margin:0; line-height:1.3;}
        .result-hero .r-meta {display:flex; flex-wrap:wrap; gap:8px; margin-top:14px;}
        .result-hero .r-pill {background:rgba(255,255,255,.14); color:#e7f0ff;
            border:1px solid rgba(255,255,255,.24); padding:5px 13px; border-radius:20px;
            font-size:.82rem; font-weight:600; white-space:nowrap;}
        .result-hero .r-pill b {color:#FDB913; font-weight:700; margin-right:4px;}

        /* --- 기본정보 카드 그리드 --- */
        .info-box {background:#fff; border:1px solid #e3ebf9; border-radius:16px;
            padding:20px 22px; box-shadow:0 3px 10px rgba(10,42,99,.05);}
        .info-head {display:flex; align-items:baseline; justify-content:space-between;
            flex-wrap:wrap; gap:6px; margin-bottom:14px;}
        .info-head .h {font-size:1.05rem; font-weight:800; color:#0A2A63;}
        .info-head .f {font-size:.8rem; color:#7c8aa5;}
        .info-grid {display:grid; grid-template-columns:repeat(3,1fr); gap:12px;}
        .info-card {background:#f6f9ff; border:1px solid #e6edfa; border-radius:12px; padding:13px 16px;}
        .info-card .lbl {font-size:.78rem; color:#6b7d9c; font-weight:600; margin-bottom:4px;}
        .info-card .val {font-size:1.02rem; color:#0A2A63; font-weight:700; line-height:1.4;}

        /* --- KPI 카드 --- */
        .kpi-grid {display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:8px 0 4px;}
        .kpi-card {background:#fff; border:1px solid #e3ebf9; border-radius:14px;
            padding:18px 14px 15px; text-align:center; box-shadow:0 3px 10px rgba(10,42,99,.06);
            position:relative; overflow:hidden;}
        .kpi-card::before {content:""; position:absolute; top:0; left:0; right:0; height:4px;}
        .kpi-card .kpi-num {font-size:2.15rem; font-weight:800; line-height:1; margin-bottom:7px;}
        .kpi-card .kpi-num .u {font-size:.9rem; font-weight:700; margin-left:2px;}
        .kpi-card .kpi-lbl {font-size:.83rem; color:#5b6b85; font-weight:600;}
        .kpi-total::before{background:#0A2A63;} .kpi-total .kpi-num{color:#0A2A63;}
        .kpi-high::before {background:#C00000;} .kpi-high .kpi-num{color:#C00000;}
        .kpi-mid::before  {background:#ED7D31;} .kpi-mid .kpi-num{color:#ED7D31;}
        .kpi-low::before  {background:#70AD47;} .kpi-low .kpi-num{color:#70AD47;}
        .kpi-tbl::before  {background:#8aa0c4;} .kpi-tbl .kpi-num{color:#43597e;}
        .kpi-card.hot {background:#fff6f6; border-color:#f2c9c9; box-shadow:0 4px 14px rgba(192,0,0,.14);}

        /* --- 시스템 상태 · 기능 카드 --- */
        .status-strip {display:flex; flex-wrap:wrap; gap:10px; margin:0 0 18px;}
        .status-chip {display:inline-flex; align-items:center; gap:6px; padding:8px 14px;
            border-radius:999px; font-size:.82rem; font-weight:700; border:1px solid;}
        .chip-on {background:#ecfdf3; color:#166534; border-color:#bbf7d0;}
        .chip-wait {background:#fffbeb; color:#92400e; border-color:#fde68a;}
        .chip-off {background:#f1f5f9; color:#64748b; border-color:#e2e8f0;}

        .mode-banner {border-radius:12px; padding:12px 16px; margin:0 0 14px; font-size:.88rem;
            display:flex; align-items:flex-start; gap:10px; line-height:1.5;}
        .mode-rule {background:#eff6ff; border:1px solid #bfdbfe; color:#1e3a5f;}
        .mode-ai {background:#f5f3ff; border:1px solid #ddd6fe; color:#4c1d95;}

        .acct-pills {display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;}
        .acct-pill {background:#0A2A63; color:#fff; padding:4px 11px; border-radius:16px;
            font-size:.78rem; font-weight:600;}

        .tier-head {font-weight:800; font-size:1.02rem; color:#0A2A63; margin:18px 0 8px;
            padding-bottom:6px; border-bottom:2px solid #e3ebf9;}
        .tier-head.t1 {color:#C00000; border-color:#f2c9c9;}
        .tier-head.t2 {color:#ED7D31; border-color:#fde0c4;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_floating_nav(*, show_sections: bool = False) -> None:
    """오른쪽 고정 이동 패널 — 스크롤 따라 표시, 맨 위·섹션 점프."""
    sections_json = (
        '[{"label":"📊 검토 요약","id":"hanul-section-summary"},'
        '{"label":"📝 리뷰노트","id":"hanul-section-notes"}]'
        if show_sections
        else "[]"
    )
    components.html(
        f"""
        <script>
        (function() {{
            const win = window.parent;
            const doc = win.document;
            const SECTIONS = {sections_json};
            const HEADER_OFFSET = 88;

            function scrollRoots() {{
                const seen = new Set();
                const out = [];
                function add(el) {{
                    if (!el || seen.has(el)) return;
                    seen.add(el);
                    out.push(el);
                }}
                add(doc.scrollingElement);
                add(doc.documentElement);
                add(doc.body);
                add(doc.querySelector('[data-testid="stAppViewContainer"]'));
                add(doc.querySelector('section.main'));
                add(doc.querySelector('.main'));
                return out;
            }}

            function currentScrollY() {{
                let y = win.scrollY || doc.documentElement.scrollTop || doc.body.scrollTop || 0;
                scrollRoots().forEach(function(r) {{
                    if (r.scrollTop > y) y = r.scrollTop;
                }});
                return y;
            }}

            function scrollAllTo(y, smooth) {{
                const behavior = smooth ? 'smooth' : 'auto';
                try {{ win.scrollTo({{ top: y, left: 0, behavior: behavior }}); }} catch (e) {{}}
                scrollRoots().forEach(function(r) {{
                    try {{
                        if (typeof r.scrollTo === 'function') {{
                            r.scrollTo({{ top: y, left: 0, behavior: behavior }});
                        }} else {{
                            r.scrollTop = y;
                        }}
                    }} catch (e) {{}}
                }});
            }}

            function findAnchor(id) {{
                let el = doc.getElementById(id)
                    || doc.querySelector('[data-hanul-anchor="' + id + '"]');
                if (el) return el;
                if (id === 'hanul-page-top') {{
                    return doc.querySelector('.app-header');
                }}
                if (id === 'hanul-section-summary') {{
                    const titles = doc.querySelectorAll('.section-title');
                    for (let i = 0; i < titles.length; i++) {{
                        if ((titles[i].textContent || '').indexOf('검토 요약') >= 0) {{
                            return titles[i];
                        }}
                    }}
                }}
                if (id === 'hanul-section-notes') {{
                    const heads = doc.querySelectorAll('h3, .tier-head');
                    for (let i = 0; i < heads.length; i++) {{
                        const t = heads[i].textContent || '';
                        if (t.indexOf('리뷰노트') >= 0) return heads[i];
                    }}
                }}
                return null;
            }}

            function scrollToAnchor(id) {{
                const el = findAnchor(id);
                if (!el) {{
                    scrollAllTo(0, true);
                    return;
                }}
                try {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }} catch (e) {{}}
                win.setTimeout(function() {{
                    const rect = el.getBoundingClientRect();
                    const y = Math.max(0, currentScrollY() + rect.top - HEADER_OFFSET);
                    scrollAllTo(y, true);
                }}, 60);
            }}

            function scrollToTop() {{
                scrollToAnchor('hanul-page-top');
                scrollAllTo(0, true);
            }}

            function injectStyles() {{
                if (doc.getElementById('hanul-scroll-nav-style')) return;
                const style = doc.createElement('style');
                style.id = 'hanul-scroll-nav-style';
                style.textContent = `
                    .hanul-scroll-nav {{
                        position:fixed; right:18px; top:50%; transform:translateY(-50%);
                        z-index:999999; display:flex; flex-direction:column; gap:8px;
                        pointer-events:none;
                    }}
                    .hanul-scroll-nav .hanul-nav-btn {{
                        pointer-events:auto; display:flex; align-items:center;
                        justify-content:center; gap:6px; min-width:132px; padding:10px 14px;
                        background:#fff; color:#0A2A63; border:2px solid #123C97;
                        border-radius:12px; font-size:.82rem; font-weight:800;
                        box-shadow:0 4px 16px rgba(10,42,99,.18); cursor:pointer;
                        text-decoration:none; box-sizing:border-box;
                        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
                    }}
                    .hanul-scroll-nav .hanul-nav-btn:hover {{
                        background:#123C97; color:#fff;
                    }}
                    .hanul-scroll-nav .hanul-nav-btn.primary {{
                        background:linear-gradient(135deg,#0A2A63 0%,#123C97 100%);
                        color:#fff; border-color:#0A2A63;
                    }}
                    .hanul-scroll-nav .hanul-nav-btn.primary:hover {{ background:#082050; }}
                    .hanul-scroll-nav .hanul-nav-btn.hidden {{
                        opacity:0; pointer-events:none;
                    }}
                    .hanul-scroll-nav .hanul-nav-sep {{
                        height:1px; background:#c5d4ea; margin:2px 8px; pointer-events:none;
                    }}
                    @media (max-width:900px) {{
                        .hanul-scroll-nav {{
                            right:10px; top:auto; bottom:20px; transform:none;
                        }}
                        .hanul-scroll-nav .hanul-nav-btn {{
                            min-width:112px; padding:9px 11px; font-size:.78rem;
                        }}
                        .hanul-scroll-nav .hanul-nav-extra {{ display:none; }}
                    }}
                `;
                doc.head.appendChild(style);
            }}

            function bindBtn(btn, handler) {{
                btn.addEventListener('click', function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    handler();
                }}, true);
            }}

            function ensureNav() {{
                injectStyles();
                let nav = doc.getElementById('hanul-scroll-nav');
                if (nav) nav.remove();
                nav = doc.createElement('nav');
                nav.id = 'hanul-scroll-nav';
                nav.className = 'hanul-scroll-nav';
                nav.setAttribute('aria-label', '페이지 이동');

                const topBtn = doc.createElement('a');
                topBtn.href = '#hanul-page-top';
                topBtn.className = 'hanul-nav-btn primary';
                topBtn.textContent = '↑ 처음으로 돌아가기';
                topBtn.title = '화면 맨 위로 이동';
                bindBtn(topBtn, scrollToTop);
                nav.appendChild(topBtn);

                SECTIONS.forEach(function(s) {{
                    const sep = doc.createElement('div');
                    sep.className = 'hanul-nav-sep hanul-nav-extra';
                    nav.appendChild(sep);
                    const btn = doc.createElement('a');
                    btn.href = '#' + s.id;
                    btn.className = 'hanul-nav-btn hanul-nav-extra';
                    btn.textContent = s.label;
                    bindBtn(btn, function() {{ scrollToAnchor(s.id); }});
                    nav.appendChild(btn);
                }});

                doc.body.appendChild(nav);
                return nav;
            }}

            function bindScroll(nav) {{
                const topBtn = nav.querySelector('.hanul-nav-btn.primary');
                const alwaysTop = SECTIONS.length > 0;
                function onScroll() {{
                    const show = currentScrollY() > 120;
                    if (topBtn) topBtn.classList.toggle('hidden', !alwaysTop && !show);
                }}
                win.addEventListener('scroll', onScroll, {{ passive: true }});
                scrollRoots().forEach(function(r) {{
                    r.addEventListener('scroll', onScroll, {{ passive: true }});
                }});
                onScroll();
            }}

            function init() {{
                ensureNav();
                bindScroll(doc.getElementById('hanul-scroll-nav'));
            }}

            if (doc.readyState === 'loading') {{
                doc.addEventListener('DOMContentLoaded', init);
            }} else {{
                init();
            }}
            win.setTimeout(init, 300);
        }})();
        </script>
        """,
        height=0,
    )


def page_anchor(anchor_id: str) -> None:
    """섹션 점프용 앵커 (스크롤 여백 포함)."""
    st.markdown(
        f'<span id="{anchor_id}" data-hanul-anchor="{anchor_id}" class="hanul-anchor"></span>',
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        f"""
        <span id="hanul-page-top" data-hanul-anchor="hanul-page-top" class="hanul-anchor"></span>
        <div class="app-header">
            <div class="brand-logo">
                {LOGO_SVG}
                <div class="brand-firm">한울회계법인</div>
            </div>
            <div class="brand-center">
                <p class="brand-title">감사조서 자가검토</p>
                <p class="brand-sub">(심리(QRM) 제출 전 자가 점검 · 규칙엔진 + Hanul DB + AI 심층 분석)</p>
                <p class="brand-version">{config.app_version_label()}</p>
            </div>
            <div class="brand-spacer"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_importance_badge(importance: str) -> str:
    color = IMPORTANCE_COLORS.get(importance, "#666666")
    return (
        f'<span style="background:{color};color:white;padding:4px 10px;'
        f'border-radius:4px;font-weight:bold;font-size:0.85em;">중요도 {importance}</span>'
    )


def render_tag(text: str, color: str = "#1F4E79") -> str:
    return (
        f'<span style="background:{color}1A;color:{color};padding:3px 9px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600;">{text}</span>'
    )


def render_system_status(*, compact: bool = False) -> None:
    """현재 연결 상태(규칙엔진·Hanul DB·AI)를 표시."""
    kb_ok = kb.is_ready()
    ai_ok = ai_review.is_configured()
    try:
        import enforcement_checklist_catalog as ecc
        enf_n = ecc.stats(is_listed=True)["checklist_rows"]
        enf_chip = f'<span class="status-chip chip-on">✓ 감리지적 체크리스트 {enf_n}항목</span>'
    except Exception:  # noqa: BLE001
        enf_chip = '<span class="status-chip chip-wait">감리지적 체크리스트</span>'
    if ai_ok:
        ai_chip = (
            f'<span class="status-chip chip-on">✓ {ai_review.provider_label()}'
            f" · {ai_review.model_name()}</span>"
        )
    else:
        ai_chip = (
            '<span class="status-chip chip-wait">OpenAI API · .env 키 입력 필요</span>'
        )
    chips = [
        f'<span class="status-chip chip-on">{config.app_version_label()}</span>',
        f'<span class="status-chip chip-on">🔗 {config.primary_access_url()}</span>',
        '<span class="status-chip chip-on">✓ 규칙엔진</span>',
        enf_chip,
        (
            f'<span class="status-chip chip-on">✓ Hanul DB · {kb.stats()["documents"]:,}건</span>'
            if kb_ok
            else '<span class="status-chip chip-off">Hanul DB 미연결</span>'
        ),
        ai_chip,
    ]
    html = "".join(chips)
    style = "" if compact else ' style="justify-content:center;"'
    st.markdown(f'<div class="status-strip"{style}>{html}</div>', unsafe_allow_html=True)


def render_ai_setup_hint() -> None:
    """OpenAI API 키 설정 UI."""
    configured = ai_review.is_configured()
    expanded = not configured
    with st.expander("🔑 OpenAI API 연동", expanded=expanded):
        if configured:
            st.success(
                f"**{ai_review.provider_label()}** 연결됨 · 모델 `{ai_review.model_name()}`"
                + (f" · 키 `{config.masked_api_key()}`" if config.masked_api_key() else "")
            )
        else:
            st.markdown(
                "[OpenAI API Keys](https://platform.openai.com/api-keys)에서 발급받은 키를 입력하면 "
                "**AI 심층 분석**이 활성화됩니다."
            )

        model_default = config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        model = st.text_input(
            "모델명",
            value=model_default,
            help="예: gpt-4o-mini, gpt-4o (공백 없이 입력)",
            key="openai_model_input",
        )
        api_key = st.text_input(
            "OpenAI API 키",
            type="password",
            placeholder="sk-proj-..." if not configured else "새 키로 변경 시 입력",
            help="`.env` 파일에 저장됩니다. git에는 올라가지 않습니다.",
            key="openai_api_key_input",
        )

        col_save, col_test = st.columns(2)
        with col_save:
            save = st.button("💾 저장 및 연동", type="primary", use_container_width=True)
        with col_test:
            test = st.button("🔌 연결 테스트", use_container_width=True, disabled=not configured)

        if save:
            key_to_save = api_key.strip() or config.get("OPENAI_API_KEY")
            if not config.valid_api_key(key_to_save):
                st.error("유효한 OpenAI API 키를 입력해 주세요.")
            else:
                try:
                    config.save_openai_settings(key_to_save, model=model.strip())
                    ok, msg = ai_review.test_connection()
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(f"키는 저장되었으나 연결 테스트 실패: {msg}")
                except ValueError as exc:
                    st.error(str(exc))

        if test and configured:
            with st.spinner("API 연결 확인 중…"):
                ok, msg = ai_review.test_connection()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        if not configured:
            st.caption(
                "또는 터미널에서 `cp .env.example .env` 후 `.env`에 직접 입력하고 앱을 재시작해도 됩니다."
            )


def _load_demo_results() -> None:
    """샘플 데이터로 결과 화면 미리보기(데모)."""
    import copy

    notes = copy.deepcopy(SAMPLE_REVIEW_NOTES)
    for n in notes:
        ref = n.get("workpaper_ref", "조서")
        n.setdefault("sheet_no", ref.split()[0] if ref else "-")
        n.setdefault("sheet_title", "매출채권 / 대손충당금")
        n.setdefault("sheet", ref)
        n.setdefault("source", "rule")
        n.setdefault("references", [])
        n.setdefault("enforcement_cases", [])

    st.session_state["engagement"] = copy.deepcopy(SAMPLE_ENGAGEMENT)
    st.session_state["engagement"]["materiality_display"] = "TE 50,000,000 (샘플)"
    st.session_state["engagement"]["is_listed"] = True
    st.session_state["notes"] = notes
    st.session_state["focus_sheet"] = [
        {"issue_no": 1, "issue_title": "국외 매출·매출채권", "status": "중점검토 필요",
         "defect": notes[0]["defect"] if notes else "", "reason": "", "basis": "", "to_be": "", "sheet": ""},
        {"issue_no": 2, "issue_title": "재고자산 평가손실", "status": "해당사항 없음",
         "defect": "", "reason": "", "basis": "", "to_be": "", "sheet": ""},
        {"issue_no": 3, "issue_title": "투자부동산", "status": "해당사항 없음",
         "defect": "", "reason": "", "basis": "", "to_be": "", "sheet": ""},
        {"issue_no": 4, "issue_title": "충당부채·우발부채", "status": "해당사항 없음",
         "defect": "", "reason": "", "basis": "", "to_be": "", "sheet": ""},
    ]
    st.session_state["doc_meta"] = {
        "tables": 12,
        "pages": 0,
        "text_len": 48000,
        "ai_used": False,
        "demo": True,
        "rule_count": len(notes),
        "ai_count": 0,
        "materiality": "TE 50,000,000 (샘플)",
        "kb_ready": kb.is_ready(),
        "include_minor": False,
        "is_listed": True,
        "by_category": {c: sum(1 for x in notes if x.get("category") == c) for c in {n.get("category", "기타") for n in notes}},
    }
    st.session_state["source_name"] = "샘플_매출채권_대손충당금_조서.xlsx"
    st.session_state["generated"] = True
    st.session_state["error"] = None
    _attach_references(notes, st.session_state["engagement"])


def render_flow() -> None:
    st.markdown(
        """
        <div class="flow">
            <div class="flow-step"><div class="ic">📤</div>
                <div><div class="t">1. 업로드</div><div class="d">감사조서 파일</div></div></div>
            <div class="flow-arrow">→</div>
            <div class="flow-step"><div class="ic">🔎</div>
                <div><div class="t">2. 분석</div><div class="d">규칙엔진 · OpenAI · Hanul DB</div></div></div>
            <div class="flow-arrow">→</div>
            <div class="flow-step"><div class="ic">📝</div>
                <div><div class="t">3. 리뷰노트</div><div class="d">중요도별 정리</div></div></div>
            <div class="flow-arrow">→</div>
            <div class="flow-step"><div class="ic">📥</div>
                <div><div class="t">4. 내려받기</div><div class="d">엑셀 저장</div></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _norm_name(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _focus_root_dir() -> str:
    return os.path.join(kb.SOURCE_DIR, "4대 중점사항 감리대상")


def _resolve_focus_pdf(is_listed: bool) -> str | None:
    """한울DB 4대 중점사항 폴더에서 상장·비상장 원문 PDF 경로를 찾는다."""
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
        # 폴더 내 PDF 1개면 그대로 사용
        pdfs = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf") and not f.startswith(".")
        ]
        return sorted(pdfs)[0] if pdfs else None

    # Hanul DB 표준 파일명(상장법인_4대 / 비상장법인_4대) 우선
    for c in sorted(candidates):
        base = _norm_name(os.path.basename(c))
        if "4대 중점사항" in base and "보도자료" not in base and "사전예고 안내" not in base:
            return c
    return sorted(candidates)[0]


def _focus_issue_summary_html(issues: list) -> str:
    rows = "".join(
        f'<div class="fi">{i.issue_no}. {i.title}</div>' for i in issues
    )
    return f'<div class="focus-issue-compact">{rows}</div>'


def _render_focus_section(
    *,
    is_listed: bool,
    block_title: str,
    src_label: str,
    issues: list,
    active: bool,
    key_prefix: str,
) -> None:
    cls = "focus-block active" if active else "focus-block"
    st.markdown(
        f'<div class="{cls}">'
        f'<div class="focus-block-h">{block_title}'
        f'<span class="focus-block-src">({src_label})</span></div>'
        f'{_focus_issue_summary_html(issues)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    pdf_path = _resolve_focus_pdf(is_listed)
    if pdf_path and os.path.isfile(pdf_path):
        dl_label = _norm_name(os.path.basename(pdf_path))
        short = "상장법인 4대 중점사항" if is_listed else "비상장법인 4대 중점사항"
        try:
            with open(pdf_path, "rb") as fh:
                data = fh.read()
            st.download_button(
                f"⬇️ {short} 원문 다운로드",
                data,
                file_name=dl_label,
                key=f"{key_prefix}_{hashlib.md5(pdf_path.encode()).hexdigest()[:10]}",
                use_container_width=True,
            )
        except OSError:
            st.caption("원문 파일을 읽을 수 없습니다.")
    else:
        st.caption("한울DB에서 원문 PDF를 찾지 못했습니다.")


def _focus_source_dialog_body(is_listed: bool) -> None:
    """4대 중점사항 원문 — 상장·비상장 요약 + 한울DB 다운로드 (dialog 본문)."""
    _render_focus_section(
        is_listed=True,
        block_title="상장 (IPO)",
        src_label="금융감독원",
        issues=fss_focus._DEFAULT_LISTED_2026,
        active=is_listed,
        key_prefix="focus_listed",
    )
    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
    _render_focus_section(
        is_listed=False,
        block_title="비상장",
        src_label="한국공인회계사회",
        issues=fss_focus._DEFAULT_UNLISTED_2026,
        active=not is_listed,
        key_prefix="focus_unlisted",
    )
    focus_dir = _focus_root_dir()
    if os.path.isdir(focus_dir) and st.button(
        "📂 한울DB 폴더 열기", key="open_focus_dir", use_container_width=True
    ):
        subprocess.Popen(["open", focus_dir])


@st.dialog("4대 중점 항목 · 한울DB", width="medium", dismissible=True)
def _focus_source_dialog(is_listed: bool) -> None:
    """4대 중점사항 원문보기 모달 — 오른쪽 상단 ✕ 닫기 제공."""
    year = datetime.date.today().year
    st.caption(f"{year}년 재무제표 중점심사 4대 회계이슈")
    _focus_source_dialog_body(is_listed)


def _render_focus_source_popover(is_listed: bool) -> None:
    """4대 중점사항 원문보기 — 버튼 클릭 시 모달(닫기 ✕) 표시."""
    if st.button(
        "📄 4대 중점사항 원문보기",
        use_container_width=True,
        key="btn_focus_source",
    ):
        _focus_source_dialog(is_listed)


def render_landing() -> None:
    """조서 업로드 전 중앙 배치 화면."""
    # 시스템 상태 칩 대신 실행 순서 플로우를 상단에 작게 배치
    render_flow()

    center = st.columns([1, 2, 1])[1]
    with center:
        with st.container(border=True):
            st.markdown(
                '<div class="upload-hero">📤 감사조서 업로드 (복수 가능)'
                '<span class="badge">MAIN</span></div>',
                unsafe_allow_html=True,
            )
            uploaded = st.file_uploader(
                "감사조서 업로드",
                type=["pdf", "xlsx", "xls", "docx"],
                accept_multiple_files=True,
                help="PDF · 엑셀 · 워드 파일을 한 번에 여러 개 올릴 수 있습니다.",
                label_visibility="collapsed",
            )
            uploads = list(uploaded or [])
            if uploads:
                st.success(f"업로드 완료: {len(uploads)}개 조서")
                for u in uploads:
                    st.caption(f"· {u.name}")

            st.markdown('<div class="section-title">검토 실행</div>', unsafe_allow_html=True)
            if config.allow_manual_materiality():
                manual_te_mn = st.number_input(
                    "중요성 금액 (TE, 백만원 단위) — 조서에서 추출 실패 시 입력",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    format="%.0f",
                    help="백만원 단위로 입력합니다. 예: 50 입력 → 50,000,000원으로 인식. "
                    "0이면 조서 본문에서 자동 추출합니다.",
                )
                # 입력은 백만원 단위, 내부 인식은 원 단위
                manual_te = manual_te_mn * 1_000_000
                if manual_te_mn > 0:
                    st.caption(f"입력된 중요성: **{manual_te:,.0f}원** ({manual_te_mn:,.0f}백만원)")
            else:
                manual_te = 0.0
            # 형식·완전성 검사는 인터페이스에서 숨김 (기본 OFF 유지)
            include_minor = False
            col_focus, col_orig = st.columns([1.2, 1], vertical_alignment="center")
            with col_focus:
                st.markdown('<div class="section-title">4대 중점 항목 리뷰</div>', unsafe_allow_html=True)
                entity_type = st.radio(
                    "기업 구분",
                    ["상장 (IPO 포함)", "비상장"],
                    horizontal=True,
                    label_visibility="collapsed",
                    help="상장(IPO)은 금융감독원, 비상장은 한국공인회계사회 4대 중점 항목을 적용합니다.",
                )
                is_listed = entity_type.startswith("상장")
            with col_orig:
                _render_focus_source_popover(is_listed)
            if is_listed:
                gaap = "K-IFRS"
                st.caption("회계기준: **K-IFRS** (상장사 기본 적용) · 금융감독원 4대 중점 항목으로 리뷰.")
            else:
                if "unlisted_gaap" not in st.session_state:
                    st.session_state["unlisted_gaap"] = "일반기업회계기준"
                gaap = st.radio(
                    "회계기준 선택",
                    ["K-IFRS", "일반기업회계기준"],
                    horizontal=True,
                    help="비상장법인은 K-IFRS 또는 일반기업회계기준 중 적용 기준을 선택합니다. "
                    "기본값은 일반기업회계기준입니다.",
                    key="unlisted_gaap",
                )
                st.caption("한국공인회계사회(한공회) 4대 중점 항목으로 리뷰.")
            ai_ready = ai_review.is_configured()
            if ai_ready:
                use_ai = st.toggle(
                    f"AI 심층 분석 사용 ({ai_review.provider_label()} + Hanul DB)",
                    value=True,
                    help="시트별 정독 · Hanul DB 근거 인용 · 중점감리 점검",
                )
            else:
                use_ai = False
                st.info(
                    "**현재 모드: 규칙엔진 + Hanul DB**  \n"
                    "조서 파싱 · 계정 식별 · 절차 누락 · 합계 재확인 · 근거·감리사례 검색이 동작합니다.  \n"
                    "위 **🔑 OpenAI API 연동** 에서 키를 입력하면 **AI 심층 분석**이 추가됩니다."
                )

            generate = st.button(
                "🔍 리뷰노트 생성",
                type="primary",
                use_container_width=True,
                disabled=(len(uploads) == 0),
            )

            if generate and uploads:
                st.caption(
                    "⏳ 대용량·다수 파일은 **1~3분** 걸릴 수 있습니다. "
                    "진행 단계가 갱신되면 정상 처리 중입니다."
                )
                with st.status("리뷰노트 생성 중…", expanded=True) as status:
                    run_analysis(
                        uploads,
                        use_ai,
                        manual_materiality=manual_te if manual_te > 0 else None,
                        include_minor=include_minor,
                        is_listed=is_listed,
                        gaap=gaap,
                        status=status,
                    )
                st.rerun()

    # API 연동과 샘플 미리보기는 맨 아래 한 줄에 배치
    col_api, col_sample = st.columns([3, 2], vertical_alignment="top")
    with col_api:
        render_ai_setup_hint()
    with col_sample:
        if st.button("👁 샘플 결과 화면 미리보기", use_container_width=True, key="sample_preview"):
            _load_demo_results()
            st.rerun()

    st.caption(
        f"{config.app_version_detail()} · "
        "본 시스템은 회계사의 전문적 판단을 보조하는 도구이며, 최종 책임은 담당 회계사에게 있습니다. "
        "관련 근거(기준·감리지적)는 검증된 자료(Hanul DB)에서만 인용합니다."
    )


def _format_source_display(source_name: str, source_files: list[str] | None) -> str:
    files = source_files or ([source_name] if source_name else [])
    if len(files) <= 1:
        return source_name or (files[0] if files else "업로드 조서")
    if len(files) <= 3:
        return ", ".join(files)
    return f"{files[0]} 외 {len(files) - 1}건"


def render_basic_info(engagement: dict, source_name: str, source_files: list[str] | None = None) -> None:
    def card(label: str, value) -> str:
        return (
            f'<div class="info-card"><div class="lbl">{label}</div>'
            f'<div class="val">{value or "—"}</div></div>'
        )

    acct_raw = engagement.get("related_account", "") or ""
    acct_parts = [a.strip() for a in acct_raw.split("/") if a.strip()]
    if acct_parts:
        pills = "".join(f'<span class="acct-pill">{a}</span>' for a in acct_parts)
        acct_html = f'<div class="acct-pills">{pills}</div>'
    else:
        acct_html = "—"

    cards = (
        card("회사명", engagement["company_name"])
        + card("감사연도", engagement["audit_year"])
        + card("작성자", engagement["preparer"])
        + card("적용 회계기준", engagement["accounting_standard"])
        + card("적용 감사기준", engagement["audit_standard"])
        + (
            '<div class="info-card"><div class="lbl">관련 계정</div>'
            f'<div class="val" style="font-weight:600;">{acct_html}</div></div>'
        )
    )
    source_label = _format_source_display(source_name, source_files)
    st.markdown(
        f"""
        <div class="info-box">
            <div class="info-head">
                <span class="h">📄 조서 기본정보</span>
                <span class="f">자동 추출 · {source_label}</span>
            </div>
            <div class="info-grid">{cards}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if source_files and len(source_files) > 1:
        st.caption("업로드 조서: " + " · ".join(source_files))


def render_results() -> None:
    engagement = st.session_state["engagement"]
    notes = sort_notes_by_importance(st.session_state["notes"])
    counts = count_by_importance(notes)
    meta = st.session_state.get("doc_meta", {})
    focus_sheet = st.session_state.get("focus_sheet", [])
    source_name = st.session_state.get("source_name", "업로드 조서")
    source_files = meta.get("source_files") or []
    source_display = _format_source_display(source_name, source_files)
    is_demo = meta.get("demo", False)

    back = st.columns([1, 3])[0]
    if back.button("← 새 조서 분석하기", use_container_width=True):
        for key in ("generated", "notes", "engagement", "doc_meta", "source_name", "focus_sheet", "parse_warning"):
            st.session_state.pop(key, None)
        st.rerun()

    if is_demo:
        st.info("👁 **샘플 결과 화면**입니다. 실제 조서를 업로드하면 동일 형식으로 리뷰노트가 생성됩니다.")

    if st.session_state.get("parse_warning"):
        st.warning(st.session_state["parse_warning"])

    render_system_status(compact=True)

    st.markdown(
        f"""
        <div class="result-hero">
            <p class="r-title">📋 {engagement['company_name']} · 감사조서 자가검토 결과</p>
            <div class="r-meta">
                <span class="r-pill"><b>감사연도</b>{engagement['audit_year']}</span>
                <span class="r-pill"><b>회계기준</b>{engagement['accounting_standard']}</span>
                <span class="r-pill"><b>감사기준</b>{engagement['audit_standard']}</span>
                <span class="r-pill"><b>대상 조서</b>{source_display}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_basic_info(engagement, source_name, source_files)
    mat_disp = meta.get("materiality") or engagement.get("materiality_display", "미확인")
    focus_bad = sum(1 for r in focus_sheet if r.get("status") in ("미비", "중점검토 필요"))
    st.markdown(
        f'<div class="mode-banner mode-rule">📊 <b>중요성:</b> {mat_disp} · '
        f'<b>4대 중점항목:</b> {"중점검토 필요 " + str(focus_bad) + "건" if focus_bad else "이상 없음"} · '
        f'Hanul DB: {"연결됨" if meta.get("kb_ready") else "미색인"}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    # --- 검토 모드 안내 ---
    if meta.get("ai_used"):
        ai_cnt = sum(1 for n in notes if n.get("source") == "ai")
        focus_cnt = sum(1 for n in notes if n.get("is_focus_related"))
        plabel = ai_review.provider_label()
        extra = f" · 중점감리 {focus_cnt}건" if focus_cnt else ""
        st.markdown(
            f'<div class="mode-banner mode-ai">🤖 <b>{plabel} ({ai_review.model_name()}) 시트별 심층 분석</b> · '
            f"Hanul DB 근거 인용 · AI 지적 {ai_cnt}건{extra}</div>",
            unsafe_allow_html=True,
        )
    else:
        kb_note = "Hanul DB 근거·감리사례 검색" if kb.is_ready() else "Hanul DB 미연결"
        st.markdown(
            f'<div class="mode-banner mode-rule">⚙️ <b>규칙엔진 + {kb_note}</b> · '
            f"시트별 계정 식별 · 절차 누락 · 합계 재확인 · "
            f".env 에 OpenAI API 키 입력 시 AI 심층 분석이 추가됩니다.</div>",
            unsafe_allow_html=True,
        )

    # --- 요약 지표 ---
    page_anchor("hanul-section-summary")
    st.markdown('<div class="section-title">검토 요약</div>', unsafe_allow_html=True)
    high_cls = "kpi-card kpi-high hot" if counts["상"] > 0 else "kpi-card kpi-high"
    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card kpi-total"><div class="kpi-num">{len(notes)}<span class="u">건</span></div>
                <div class="kpi-lbl">총 지적 건수</div></div>
            <div class="{high_cls}"><div class="kpi-num">{counts['상']}<span class="u">건</span></div>
                <div class="kpi-lbl">★★★ 즉시</div></div>
            <div class="kpi-card kpi-mid"><div class="kpi-num">{counts['중']}<span class="u">건</span></div>
                <div class="kpi-lbl">★★ 조기</div></div>
            <div class="kpi-card kpi-low"><div class="kpi-num">{counts['하']}<span class="u">건</span></div>
                <div class="kpi-lbl">★ 단기</div></div>
            <div class="kpi-card kpi-tbl"><div class="kpi-num">{meta.get('tables', 0)}<span class="u">개</span></div>
                <div class="kpi-lbl">분석한 표</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not notes:
        mode = "AI+규칙 병합" if meta.get("ai_used") else "규칙엔진만"
        st.success(
            f"점검 결과, 현재 범위에서 지적사항이 발견되지 않았습니다. "
            f"(모드: {mode} · 규칙 {meta.get('rule_count', 0)}건 · AI {meta.get('ai_count', 0)}건)"
        )
        if not meta.get("kb_ready"):
            st.warning("Hanul DB 미색인 — 표준절차·감리지적 매칭이 제한될 수 있습니다.")
        st.caption(
            f"검토 범위: 조서 {meta.get('file_count', 1)}개 · 표 {meta.get('tables', 0)}개 · "
            f"중요성 {meta.get('materiality', '미확인')} · "
            f"{'상장' if meta.get('is_listed') else '비상장'}"
            + (f" · {meta['gaap']}" if meta.get("gaap") else "")
        )
    else:
        by_cat = meta.get("by_category") or {}
        if by_cat:
            pills = " · ".join(f"{k} {v}건" for k, v in sorted(by_cat.items(), key=lambda x: -x[1]))
            st.caption(f"카테고리별: {pills}")

    # --- 4대 중점 회계이슈 ---
    if focus_sheet:
        st.markdown("### 4대 중점 회계이슈 점검결과")
        for row in focus_sheet:
            if row["status"] in ("미비", "중점검토 필요"):
                icon = "🔴"
            elif row["status"] in ("해당 없음", "해당사항 없음"):
                icon = "⚪"
            else:
                icon = "🟢"
            st.markdown(f"**{icon} {row['issue_no']}. {row['issue_title']}** — {row['status']}")
            if row.get("reason"):
                st.caption(row["reason"][:260])
            if row.get("to_be"):
                st.caption(f"✏️ {row['to_be'][:260]}")

    # --- 엑셀 다운로드 ---
    excel_bytes = build_review_notes_excel(engagement, notes, focus_sheet)
    col_dl, col_sp = st.columns([1, 3])
    with col_dl:
        st.download_button(
            label="📥 감리 리뷰노트 엑셀 내려받기",
            data=excel_bytes,
            file_name=f"감리_리뷰노트_{engagement['company_name']}_{engagement['audit_year']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
            disabled=not notes,
        )
    with col_sp:
        st.caption("표지 · 우선순위 목록 · 등급별(★★★/★★/★) 세부 시트로 구성됩니다.")

    if not notes:
        st.divider()
        render_kb_search()
        return

    st.divider()

    # --- 리뷰노트 ---
    page_anchor("hanul-section-notes")
    st.markdown("### 리뷰노트")
    st.caption("중요도 ★★★(상) → ★★(중) → ★(하) 순 · 조서번호·계정과목 기준")

    filter_imp = st.multiselect(
        "중요도 필터",
        ["상", "중", "하"],
        default=["상", "중"],
    )

    filtered = [n for n in notes if n["importance"] in filter_imp]
    if not filtered:
        st.info("선택한 조건에 해당하는 리뷰노트가 없습니다.")

    tier_labels = {
        "상": ('t1', '★★★ 즉시 수정 필요'),
        "중": ('t2', '★★ 조기 보완 필요'),
        "하": ('t3', '★ 단기 보완 (확인 권장)'),
    }
    shown_tiers: set[str] = set()
    for note in filtered:
        imp = note["importance"]
        if imp in tier_labels and imp not in shown_tiers:
            cls, label = tier_labels[imp]
            st.markdown(f'<div class="tier-head {cls}">{label}</div>', unsafe_allow_html=True)
            shown_tiers.add(imp)
        if imp in ("상", "중"):
            render_full_note(note)
        elif imp == "하" and note.get("category") == "검토요청":
            render_full_note(note)
        elif imp == "하":
            sheet_no = note.get("sheet_no") or note.get("workpaper_ref") or "-"
            msg = note.get("summary") or f"〈{sheet_no}〉 {note['defect']} — {note['to_be']}"
            st.markdown(f"- `{note['id']}` {msg}")

    st.divider()
    render_kb_search()


def render_full_note(note: dict) -> None:
    """중요도 상·중 리뷰노트를 상세 형식으로 표시."""
    imp = note["importance"]
    is_ai = note.get("source") == "ai"
    prefix = "🤖 " if is_ai else ""
    sheet_no = note.get("sheet_no") or note.get("workpaper_ref") or "-"
    sheet_title = re_engine.note_display_account(note) or note.get("sheet_title") or ""
    location = output_formatter.format_location_lines(note.get("location") or "") or note.get("location") or ""
    display_sheet = output_formatter.format_workpaper_column(note)
    with st.expander(
        f"{prefix}[{note['id']}] 〈{display_sheet}〉 {note['defect']}",
        expanded=True,
    ):
        tags = render_importance_badge(imp) + " &nbsp; " + render_tag(note["category"])
        tags += " &nbsp; " + (
            render_tag("AI 분석", "#7030A0") if is_ai else render_tag("규칙엔진", "#1F4E79")
        )
        if note.get("is_focus_related") or note.get("category") == "중점감리":
            tags += " &nbsp; " + render_tag("★ 중점감리", "#C00000")
        st.markdown(tags, unsafe_allow_html=True)

        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.markdown(f"**📑 시트명(조서번호)**  \n{display_sheet}")
        with col_b:
            st.markdown(f"**📄 계정과목**  \n{sheet_title or '—'}")
        if location:
            st.markdown(f"**📍 위치**  {location}")

        st.markdown("**🔎 리뷰사항**")
        st.write(note["defect"])
        if note.get("reason"):
            st.caption(note["reason"])

        st.markdown("**📖 리뷰근거**")
        if "근거 미확인" in note["basis"]:
            st.warning(f"{note['basis']} — Hanul DB 색인·검색 결과를 확인하세요.")
        else:
            st.info(note["basis"])

        cases = note.get("enforcement_cases")
        if cases:
            st.markdown("**⚖️ 감리지적사례**")
            primary = cases[0]
            with st.container(border=True):
                summary = primary.get("summary_line") or primary.get("brief") or ""
                head = f"**[{primary['number']}]**"
                if primary.get("subject") and primary["subject"] not in summary:
                    head += f" {primary['subject']}"
                st.markdown(head)
                if summary:
                    st.write(summary)
                if primary.get("brief") and primary["brief"] != summary:
                    st.caption(primary["brief"])
                fp = primary.get("file_path") or ""
                fname = primary.get("file") or "원문"
                if fp and os.path.isfile(fp):
                    try:
                        with open(fp, "rb") as fh:
                            st.download_button(
                                "⬇️ 원문보기 (한울DB)",
                                fh.read(),
                                file_name=fname,
                                key=f"case_dl_{note.get('id', '')}_{primary.get('number', '')}",
                                use_container_width=True,
                            )
                    except OSError:
                        st.caption(f"출처: {fname}")
                elif fname:
                    st.caption(f"출처: {fname}")
            others = [c for c in cases[1:] if c.get("has_number") and c.get("brief")]
            if others:
                nums = ", ".join(
                    f"{c['number']}" + (f"({c['subject']})" if c.get("subject") else "")
                    for c in others
                )
                st.caption(f"유사 지적사례: {nums}")

        st.markdown("**✅ 수정제안**")
        st.success(note["to_be"])


def render_kb_search() -> None:
    """지식 저장소(Hanul DB) 직접 검색."""
    st.markdown("### 지식 저장소 검색 (Hanul DB)")
    if not kb.is_ready():
        st.info("지식 저장소가 아직 색인되지 않았습니다. 색인 완료 후 검색할 수 있습니다.")
        return
    info = kb.stats()
    st.caption(
        f"색인된 자료 {info['documents']:,}건 · 조각 {info['chunks']:,}개 "
        "(기준서·해설서·질의회신·감리지적·조서양식 등)"
    )
    query = st.text_input(
        "궁금한 회계·감사 쟁점을 입력하세요",
        placeholder="예: 매출채권 대손충당금 기대신용손실 산정",
    )
    if query:
        results = kb.retrieve(query, k=6)
        if not results:
            st.warning("관련 자료를 찾지 못했습니다. 검색어를 바꿔 보세요.")
        for r in results:
            with st.container(border=True):
                st.markdown(f"📚 **{r.source}**")
                st.write(r.snippet)
                st.caption(f"출처 파일: {r.ref}")


def _renumber(notes: list[dict]) -> list[dict]:
    for i, note in enumerate(notes, start=1):
        note["id"] = f"RN-{i:03d}"
    return notes


_KO_TOKEN_RE = re.compile(r"[가-힣]{2,}")
_NUM_DUMP_RE = re.compile(r"(?:[\d,()%.\-]{2,}\s+){3,}[\d,()%.\-]{2,}")
_REF_STOPWORDS = {"흔적", "미확인", "중요", "절차", "누락", "조서", "확인", "내역", "관련", "수행"}


def _clean_snippet(text: str) -> str:
    """스니펫에서 재무제표 숫자 덤프를 접어 가독성을 높인다."""
    text = _NUM_DUMP_RE.sub("… ", text)
    return " ".join(text.split())


# 감리지적의 결론을 나타내는 표현 — 이 어절을 중심으로 핵심요지를 뽑는다
_GIST_KW_RE = re.compile(
    r"[가-힣A-Za-z0-9·%()\s]{0,24}?"
    r"(과대\s?계상|과소\s?계상|허위\s?계상|미\s?계상|누락|미인식|미확인|불일치|"
    r"왜곡\s?표시|부당\s?(?:인식|처리)|미공시|공시\s?누락|소홀)"
)


def _case_gist(text: str, limit: int = 70) -> str:
    """감리지적사례 원문에서 지적사항 핵심요지만 추출.

    예: '조회서상 금액과 회사계상 금액 불일치', '예치금 과대계상' 등
    결론 표현(과대계상·누락·불일치 등)을 중심으로 짧게 요약한다.
    """
    t = " ".join(text.split())
    gists: list[str] = []
    for m in _GIST_KW_RE.finditer(t):
        phrase = m.group(0).strip(" ,.·—-□。")
        # 문장 중간에서 잘린 앞부분 제거 (마지막 구분자 이후만)
        for sep in ("。", "□", ".", ",", ";"):
            idx = phrase.rfind(sep)
            if idx >= 0:
                phrase = phrase[idx + 1 :].strip()
        phrase = re.sub(r"^(및|또한|그리고|등)\s+", "", phrase)
        if 4 <= len(phrase) <= 40 and phrase not in gists:
            gists.append(phrase)
        if len(gists) >= 2:
            break
    if gists:
        return " · ".join(gists)[:limit]
    return kb._brief(t, limit)


def _ref_terms(note: dict) -> set[str]:
    """노트의 계정·지적 내용에서 관련성 판단용 핵심어를 추출."""
    src = f"{note.get('sheet_title', '')} {note.get('defect', '')} {note.get('reason', '')}"
    return {t for t in _KO_TOKEN_RE.findall(src) if t not in _REF_STOPWORDS}


# 지적 '주제'(실사입회·문서화·Cut-off 등) — 감리지적사례 맥락 일치용 핵심 키워드
_ISSUE_FOCUS_KW = (
    "실사입회", "실사 입회", "문서화", "실사", "입회", "증빙", "조회서", "확인서",
    "기대신용손실", "대손충당금", "기간귀속", "Cutoff", "cutoff", "Cut-off", "cut-off", "컷오프",
    "대사", "합계", "공시", "주석", "미흡", "소홀", "누락", "부족", "미기재", "생략",
    "절차누락", "위험평가", "통제테스트", "감사절차", "실재성", "완전성",
)
# 리뷰노트 지적 주제 — 감리지적사례 필터·요약에 공통 적용
_ISSUE_THEME_RULES: list[tuple[str, re.Pattern[str], dict[str, Any]]] = [
    (
        "inventory_cutoff",
        re.compile(
            r"(재고|상품|제품|원재료|재공품).{0,48}(cut.?off|컷오프|기간귀속)"
            r"|(cut.?off|컷오프|기간귀속).{0,48}(재고|상품|제품|입고|출고|선적|미착)",
            re.IGNORECASE,
        ),
        {
            "title_need": ("재고", "컷오프", "cutoff", "cut-off", "입고", "출고", "선적"),
            "title_reject": ("수익", "매출", "비용"),
            "snippet_need": ("재고", "컷오프", "cutoff", "cut-off", "입고", "출고", "선적", "기간귀속"),
            "summary_core": "재고자산 Cut-off 미수행",
        },
    ),
    (
        "revenue_cutoff",
        re.compile(
            r"(매출|수익).{0,48}(cut.?off|컷오프|기간귀속)"
            r"|(cut.?off|컷오프|기간귀속).{0,48}(매출|수익|인식시점|귀속시점)",
            re.IGNORECASE,
        ),
        {
            "title_need": ("수익", "매출", "기간귀속", "컷오프", "cutoff", "cut-off"),
            "title_reject": ("재고",),
            "snippet_need": ("매출", "수익", "기간귀속", "컷오프", "cutoff", "cut-off"),
            "summary_core": "수익(매출) Cut-off 미수행",
        },
    ),
    (
        "physical_count",
        re.compile(r"실사\s?입회|재고\s?실사|실사\s?대사|실사\s?참관", re.IGNORECASE),
        {
            "title_need": ("실사", "입회", "재고"),
            "title_reject": (),
            "snippet_need": ("실사", "입회", "재고", "수불", "집계"),
            "summary_core": "재고실사 입회·문서화 미흡",
        },
    ),
    (
        "cash_confirmation",
        re.compile(
            r"외부\s?조회|조회서|은행\s?조회|금융기관|confirmation|잔액\s?(?:확인|조회)|예금\s?잔액",
            re.IGNORECASE,
        ),
        {
            "title_need": ("현금", "예금", "조회", "은행", "금융"),
            "title_reject": ("공사", "원가", "매출", "재고", "수익"),
            "snippet_need": ("현금", "예금", "조회", "은행", "금융", "잔액", "confirmation"),
            "summary_core": "예금 잔액조회(외부조회) 미흡",
        },
    ),
    (
        "contingency_disclosure",
        re.compile(
            r"우발|약정|지급보증|소송|담보|충당|계류|보증",
            re.IGNORECASE,
        ),
        {
            "title_need": ("우발", "약정", "지급보증", "소송", "담보", "충당", "보증"),
            "title_reject": ("수익", "비용", "기간귀속", "매출", "재고", "cut-off", "cutoff", "컷오프"),
            "snippet_need": ("우발", "약정", "지급보증", "소송", "담보", "충당", "보증", "공시"),
            "summary_core": "우발부채·약정 주석 공시 미흡",
        },
    ),
    (
        "documentation",
        re.compile(r"문서화|기재\s?미|미기재|근거\s?미|설명\s?부족|근거\s?부족", re.IGNORECASE),
        {
            "title_need": ("문서", "기재", "근거", "설명", "절차"),
            "title_reject": (),
            "snippet_need": ("문서", "기재", "근거", "설명", "절차", "미흡", "소홀"),
            "summary_core": "감사절차 문서화 미흡",
        },
    ),
]
_PROCEDURE_TEMPLATE_RE = re.compile(
    r"4000_계정별|9500|(?:^|[_/])QC(?:[_/]|$)|감사절차\s?예시|Deficiency|실증절차"
    r"|_\d{4}_v\d|\.xlsx|\.xls|\.docx?|\.pdf|\.hwpx|^\d{3,}_",
    re.IGNORECASE,
)
_CASE_ACCOUNT_REJECT: dict[str, tuple[str, ...]] = {
    "현금및예금": ("공사", "원가", "건설", "장기공사", "수익인식", "매출원가", "재고자산", "재고"),
}
_CASE_ACCOUNT_ALLOW: dict[str, tuple[str, ...]] = {
    "현금및예금": ("현금", "예금", "금융", "은행", "조회"),
}
_GENERIC_ISSUE_STOP = frozenset(
    {"대한", "있으나", "없어", "없음", "하고", "하여", "되는", "에서", "으로",
     "하기", "조서를", "참조하고", "구체적", "검토할", "적정성을", "결론이",
     "문서화가", "부족하다", "절차에", "관련하여", "수행", "내역"}
)
# 지적 '주제'(실사입회·문서화 등) 매칭용 — 계정명과 구분
_WEAK_ISSUE_TERMS = frozenset(
    {"절차", "확인", "관련", "내역", "검토", "수행", "기재", "포함", "해당", "경우", "실사"}
)


def _note_issue_theme(note: dict) -> tuple[str, dict[str, Any]] | None:
    """리뷰노트의 지적 주제(재고 Cut-off·실사입회 등)를 판별."""
    src = f"{note.get('defect', '')} {note.get('reason', '')}"
    acct = re_engine.note_account(note)
    if acct == "현금및예금" and re.search(
        r"외부|조회|은행|confirmation|잔액", src, re.I
    ):
        for theme_id, pat, rules in _ISSUE_THEME_RULES:
            if theme_id == "cash_confirmation":
                return theme_id, rules
    if acct == "우발부채·약정" or re.search(
        r"우발|약정|지급보증|소송|담보|충당", src, re.I
    ):
        for theme_id, pat, rules in _ISSUE_THEME_RULES:
            if theme_id == "contingency_disclosure":
                return theme_id, rules
    for theme_id, pat, rules in _ISSUE_THEME_RULES:
        if theme_id == "documentation" and re.search(
            r"우발|약정|지급보증|소송|담보", src, re.I
        ):
            continue
        if pat.search(src):
            return theme_id, rules
    return None


def _is_procedure_template(citation) -> bool:
    """조서양식·실증절차 파일명 등 — 리뷰근거로 부적합."""
    return bool(_PROCEDURE_TEMPLATE_RE.search(citation.source))


def _format_enforcement_summary(note: dict, case: dict) -> str:
    """리뷰노트 맥락에 맞는 감리지적사례 한 줄 요약."""
    number = case.get("number") or "사례"
    themed = _note_issue_theme(note)
    if themed:
        _, rules = themed
        core = rules.get("summary_core", "감사절차 미흡")
        return f"감리지적사례 {number} {core}으로 인한 지적"
    acct = re_engine.note_account(note) or ""
    subject = case.get("subject") or case.get("brief") or "감사절차 미흡"
    if acct and acct not in subject:
        return f"감리지적사례 {number} {acct} {subject[:28]}으로 인한 지적"
    return f"감리지적사례 {number} {subject[:36]}으로 인한 지적"


def _issue_terms(note: dict) -> set[str]:
    """리뷰노트의 지적 주제어(계정명 제외) — 감리지적사례 맥락 일치용."""
    src = f"{note.get('defect', '')} {note.get('reason', '')}"
    compact = re.sub(r"\s+", "", src)
    terms: set[str] = set()
    for kw in _ISSUE_FOCUS_KW:
        k = kw.replace(" ", "")
        if k in compact or kw in src:
            terms.add(k)
    for t in _KO_TOKEN_RE.findall(src):
        if (
            len(t) >= 5
            and t not in _REF_STOPWORDS
            and t not in _GENERIC_ISSUE_STOP
            and t not in _WEAK_ISSUE_TERMS
        ):
            terms.add(t)
    acct = re_engine.note_account(note)
    if acct:
        mask = {acct}
        for name, syns in re_engine.ACCOUNT_TAXONOMY:
            if name == acct:
                mask.update(syns)
                break
        terms -= mask
    return terms


def _is_enforcement(citation) -> bool:
    hay = f"{citation.ref} {citation.source}"
    return any(cat in hay for cat in kb.ENFORCEMENT_CATEGORIES)


def _case_title_relevant(
    citation, issue_terms: set[str], note_acct: str, note: dict | None = None
) -> bool:
    """감리지적사례 파일명·제목이 리뷰노트 주제와 맞는지 확인 (목차형 청크 오탐 방지)."""
    title = citation.source.split("·")[-1].strip()
    title_compact = re.sub(r"\s+", "", title)
    title_low = title.lower()
    snippet = citation.snippet

    themed = _note_issue_theme(note) if note else None
    if themed:
        _, rules = themed
        need = rules.get("title_need") or ()
        reject = rules.get("title_reject") or ()
        if any(r in title for r in reject) and not any(n in title for n in need):
            return False
        if any(n.lower() in title_low or n in title_compact for n in need):
            return True
        sn_need = rules.get("snippet_need") or ()
        if any(k in snippet for k in sn_need):
            return True
        return False

    focus_set = {k.replace(" ", "") for k in _ISSUE_FOCUS_KW}
    # 제목에 노트의 핵심 주제어가 있으면 우선 인정
    if any(f in title_compact for f in focus_set if f in issue_terms):
        return True
    if note_acct and note_acct in title:
        return True
    for name, syns in re_engine.ACCOUNT_TAXONOMY:
        if name == note_acct and any(s in title for s in syns):
            return True
    # 제목에 '감사절차'·'실사'·'문서화' 등 절차 주제가 있고 계정도 맞으면 인정
    proc_in_title = any(k in title for k in ("감사절차", "실사", "문서화", "절차"))
    acct_in_title = note_acct and (
        note_acct in title
        or any(s in title for name, syns in re_engine.ACCOUNT_TAXONOMY if name == note_acct for s in syns)
    )
    return proc_in_title and acct_in_title


def _case_account_blocked(note_acct: str, citation) -> bool:
    """감리지적사례가 노트 계정과 다른 계정군(공사원가·수익귀속 등)인지 차단."""
    if not note_acct:
        return False
    return re_engine.is_off_account_enforcement(
        citation.source, citation.snippet, note_acct
    )


def _is_case_relevant(citation, issue_terms: set[str], note: dict) -> bool:
    """감리지적사례가 리뷰노트의 지적 주제(예: 문서화·실사입회)와 맞는지 판정."""
    if not issue_terms and not _note_issue_theme(note):
        return False
    note_acct = re_engine.note_account(note)
    if _case_account_blocked(note_acct, citation):
        return False
    if re_engine.is_off_account_text(f"{citation.source} {citation.snippet}", note_acct):
        return False
    if not _case_title_relevant(citation, issue_terms, note_acct, note):
        return False
    snippet = citation.snippet
    themed = _note_issue_theme(note)
    if themed:
        _, rules = themed
        sn_need = rules.get("snippet_need") or ()
        if any(k in snippet for k in sn_need):
            return True
        return False
    focus_set = {k.replace(" ", "") for k in _ISSUE_FOCUS_KW}
    hits = [t for t in issue_terms if t in snippet]
    if not hits:
        return False
    # 핵심 주제어(실사입회·문서화 등)가 스니펫에 함께 있어야 관련 사례로 인정
    if any(t in focus_set for t in hits):
        return True
    strong = [h for h in hits if h not in _WEAK_ISSUE_TERMS and len(h) >= 5]
    return len(strong) >= 2


def _case_gist_for_note(text: str, issue_terms: set[str], limit: int = 70) -> str:
    """지적 주제와 맞는 문장만 발췌해 감리지적 핵심요지를 요약. 해당 없으면 빈 문자열."""
    if not text or not issue_terms:
        return ""
    t = " ".join(text.split())
    parts = re.split(r"(?<=[。.])\s+|(?<=□)\s*", t)
    for part in parts:
        if len(part) < 8:
            continue
        hits = [w for w in issue_terms if w in part]
        strong = [h for h in hits if h not in _WEAK_ISSUE_TERMS]
        if not strong and len(hits) < 2:
            continue
        gist = _case_gist(part, limit)
        if gist:
            return gist
        return kb._brief(part, limit)
    # 전체 스니펫에 주제어가 뚜렷하면 fallback
    hits = [w for w in issue_terms if w in t]
    if any(h not in _WEAK_ISSUE_TERMS for h in hits) or len(hits) >= 2:
        return _case_gist(t, limit) or kb._brief(t, limit)
    return ""


def _is_relevant(citation, terms: set[str]) -> bool:
    """검색된 근거가 노트의 지적 핵심과 맥락상 일치하는지 확인.

    조서 작성자가 수긍할 수 있어야 하므로 약한 단어 1개 일치로는 부족하다.
    핵심어 2개 이상 일치하거나, 주제를 특정하는 긴 핵심어(4자 이상,
    예: 계속기업·대손충당금)가 일치해야 관련 있는 것으로 본다.
    """
    if not terms:
        return False
    hay = f"{citation.source} {citation.snippet}"
    hits = [t for t in terms if t in hay]
    if len(hits) >= 2:
        return True
    return any(len(t) >= 4 for t in hits)


def _attach_references(notes: list[dict], engagement: dict) -> None:
    """지식 저장소(Hanul DB)에서 각 지적사항의 근거와 감리지적사례를 검색해 첨부.

    노트의 실제 계정과목과 관련된 자료만 붙인다(무관한 청크·숫자 덤프 배제).
    """
    if not kb.is_ready():
        return
    # 근거·사례를 붙일 대상 카테고리 (노이즈 최소화)
    NEEDS_BASIS = {"절차누락", "증빙·절차", "주석검증", "중점감리", "감리지적체크", "중요성", "QC·품질관리", "개선제안"}
    NEEDS_CASE = {"절차누락", "중점감리", "감리지적체크", "주석검증", "증빙·절차"}
    for note in notes:
        if note.get("collateral_memo"):
            continue
        if note.get("source") == "ai" and note.get("importance") != "상":
            continue
        category = note.get("category", "")
        wants_case = category in NEEDS_CASE or (
            note.get("importance") == "상" and _note_issue_theme(note) is not None
        )
        if note.get("importance") == "하" and not wants_case:
            continue
        if category not in NEEDS_BASIS and note.get("importance") != "상":
            continue
        terms = _ref_terms(note)
        issue_terms = _issue_terms(note)
        note_acct = re_engine.note_account(note)
        query = f"{note.get('defect', '')} {note.get('reason', '')}"

        def _on_account(c) -> bool:
            # 노트 계정과 무관한 다른 계정의 근거·사례는 제외
            return not re_engine.is_off_account_text(f"{c.source} {c.snippet}", note_acct)

        note.pop("references", None)

        # 감리지적사례 — 지적 주제(문서화·실사입회·Cut-off 등)와 맥락 일치하는 경우만
        if wants_case and (issue_terms or _note_issue_theme(note)):
            deduped: list[dict] = []
            seen_no: set[str] = set()
            for c in kb.retrieve(query, k=10, categories=kb.ENFORCEMENT_CATEGORIES):
                if not _is_case_relevant(c, issue_terms, note):
                    continue
                brief = _case_gist_for_note(c.snippet, issue_terms)
                if not brief and not _note_issue_theme(note):
                    continue
                p = kb.parse_case(c)
                if p["number"] in seen_no:
                    continue
                seen_no.add(p["number"])
                p["brief"] = brief or p.get("brief", "")
                p["summary_line"] = _format_enforcement_summary(note, p)
                deduped.append(p)
            deduped.sort(key=lambda p: (not p["has_number"],))
            if deduped:
                note["enforcement_cases"] = deduped[:2]
            else:
                note.pop("enforcement_cases", None)

        # 기준서·질의회신·4대중점 — basis 보강 (리뷰근거 한 줄)
        _GENERIC_BASIS = {
            "회계감사기준", "K-IFRS", "K-IFRS/일반기준", "Hanul DB",
            "Hanul DB 자가검토_지침_템플릿 · 감리지적사례 체크리스트(필수 검토)",
        }
        basis = str(note.get("basis") or "").strip()
        if category in NEEDS_BASIS and terms:
            std_cats = (
                kb.STANDARDS_CATEGORIES
                + kb.QNA_CATEGORIES
                + kb.FOCUS_CATEGORIES
                + kb.WORKPAPER_CATEGORIES
            )
            acct_q = f"{note_acct} {query}"
            for c in kb.retrieve(acct_q, k=8, categories=std_cats):
                if not _on_account(c):
                    continue
                if category == "절차누락":
                    if not any(
                        cat in c.source for cat in kb.WORKPAPER_CATEGORIES
                    ) and not _is_relevant(c, terms):
                        continue
                elif not _is_relevant(c, terms):
                    continue
                src = c.source.split("·")[-1].strip()[:80] if "·" in c.source else c.source[:80]
                if not basis or basis in _GENERIC_BASIS or len(basis) < 12:
                    note["basis"] = src
                    if category == "절차누락" and any(
                        cat in c.source for cat in kb.WORKPAPER_CATEGORIES
                    ):
                        note["workpaper_ref"] = (
                            c.snippet[:160] + "…" if len(c.snippet) > 160 else c.snippet
                        )
                    break
                if src not in basis:
                    note["basis"] = f"{basis}; {src}"[:120]
                    break


def _count_by_category(notes: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in notes:
        cat = n.get("category") or "기타"
        out[cat] = out.get(cat, 0) + 1
    return out


def run_analysis(
    uploads,
    use_ai: bool,
    manual_materiality: float | None = None,
    include_minor: bool = False,
    is_listed: bool | None = None,
    gaap: str | None = None,
    status=None,
) -> None:
    """업로드 파일(1개 이상)을 파싱·병합하고 규칙엔진(+선택적 AI)으로 검토."""
    import time
    import traceback

    t0 = time.perf_counter()

    def _step(msg: str) -> None:
        elapsed = int(time.perf_counter() - t0)
        label = f"{msg} ({elapsed}초)" if elapsed >= 3 else msg
        if status is not None:
            status.update(label=label)

    try:
        _step("① 조서 파일 파싱 중…")
        file_items = [(u.getvalue(), u.name) for u in uploads]
        doc, parse_messages = parse_uploads(file_items)

        if doc is None:
            st.session_state["generated"] = False
            st.session_state["error"] = (
                "업로드한 조서에서 검토 가능한 내용을 찾지 못했습니다.\n"
                + "\n".join(parse_messages)
            )
            return

        parse_warning = None
        if parse_messages:
            parse_warning = "일부 파일은 제외되었습니다:\n" + "\n".join(parse_messages)

        engagement = extract_engagement(doc)
        if is_listed is not None:
            engagement["is_listed"] = is_listed
        if gaap:
            engagement["gaap"] = gaap
            engagement["accounting_standard"] = gaap
        mat = extract_materiality(doc)
        if manual_materiality and manual_materiality > 0:
            mat.te = manual_materiality
            engagement["materiality_te"] = manual_materiality
            engagement["materiality_display"] = f"TE {manual_materiality:,.0f} (수동 입력)"

        ai_label = (
            f"AI 심층 분석 예정 ({ai_review.provider_label()})"
            if use_ai and ai_review.is_configured()
            else "규칙 기반"
        )
        _step(
            f"② 규칙엔진·품질관리 점검 중… (시트 {len(doc.tables)}개 · {ai_label})"
        )

        def _rule_progress(msg: str) -> None:
            _step(f"② {msg}")

        rule_notes = run_review(
            doc,
            include_minor=include_minor,
            materiality=mat,
            is_listed=engagement.get("is_listed"),
            engagement=engagement,
            progress=_rule_progress,
        )

        ai_used = False
        ai_error = None
        ai_notes: list[dict] = []
        if use_ai and ai_review.is_configured():
            _step(f"③ 시트별 AI 심층 분석 중… ({ai_review.provider_label()} + Hanul DB)")
            bar = st.progress(0.0, text="AI 심층 분석 준비 중…")

            def _progress(frac: float, label: str) -> None:
                bar.progress(min(max(frac, 0.0), 1.0), text=label)
                _step(f"③ {label}")

            try:
                ai_notes = ai_review.run_sheet_reviews(doc, engagement, progress=_progress)
                ai_used = True
            except Exception as exc:  # noqa: BLE001 - API 오류를 사용자에게 표시
                ai_error = f"AI 분석 중 오류가 발생했습니다: {exc}"
            finally:
                bar.empty()

        if ai_used:
            notes = note_merge.merge_review_notes(ai_notes, rule_notes)
        else:
            notes = rule_notes

        _step("④ 리뷰노트 정리·근거 연결 중…")
        notes = notes_pipeline.post_process_notes(doc, notes)
        notes = output_formatter.apply_all(notes)
        notes = _renumber(notes)
        _attach_references(notes, engagement)

        if status is not None:
            status.update(label="✅ 리뷰노트 생성 완료", state="complete")

        year_s = str(engagement.get("audit_year", "2026"))
        year = int(year_s) if year_s.isdigit() else 2026
        focus_sheet = fss_focus.build_focus_sheet(
            notes, year, bool(engagement.get("is_listed")), doc=doc
        )

        source_files = doc.source_files or [doc.file_name]
        st.session_state["engagement"] = engagement
        st.session_state["notes"] = notes
        st.session_state["focus_sheet"] = focus_sheet
        st.session_state["doc_meta"] = {
            "tables": len(doc.tables),
            "pages": doc.page_count,
            "text_len": len(doc.text),
            "ai_used": ai_used,
            "rule_count": len(rule_notes),
            "ai_count": len(ai_notes),
            "materiality": engagement.get("materiality_display", "미확인"),
            "kb_ready": kb.is_ready(),
            "include_minor": include_minor,
            "is_listed": engagement.get("is_listed"),
            "gaap": engagement.get("gaap"),
            "by_category": _count_by_category(notes),
            "file_count": len(source_files),
            "source_files": source_files,
            "elapsed_sec": int(time.perf_counter() - t0),
        }
        st.session_state["source_name"] = doc.file_name
        st.session_state["generated"] = True
        st.session_state["error"] = ai_error
        if parse_warning:
            st.session_state["parse_warning"] = parse_warning
        else:
            st.session_state.pop("parse_warning", None)

    except Exception as exc:  # noqa: BLE001 - 분석 실패 시 사용자에게 원인 표시
        st.session_state["generated"] = False
        st.session_state["error"] = (
            "리뷰노트 생성 중 오류가 발생했습니다.\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "대용량 조서는 1~3분 소요될 수 있습니다. 동일 오류가 반복되면 "
            "파일 수를 줄이거나 AI 심층 분석을 끄고 다시 시도해 보십시오."
        )
        if status is not None:
            status.update(label="❌ 리뷰노트 생성 실패", state="error")
        traceback.print_exc()


def main() -> None:
    inject_theme()
    render_header()

    if st.session_state.get("error"):
        st.error(st.session_state["error"])
        st.session_state["error"] = None

    if st.session_state.get("generated"):
        render_results()
    else:
        render_landing()

    inject_floating_nav(show_sections=st.session_state.get("generated", False))


if __name__ == "__main__":
    main()
