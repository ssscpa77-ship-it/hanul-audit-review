# Streamlit Community Cloud 배포 (0원 · URL 고정)

교수님 검증용 **2~4주** — `https://앱이름.streamlit.app` 주소가 **고정**됩니다.  
맥을 끄거나 재부팅해도 접속 가능합니다.

---

## 사전 준비

| 항목 | 내용 |
|------|------|
| GitHub 계정 | 무료 |
| Git LFS | `brew install git git-lfs` |
| KB 파일 | `kb_store/hanul_kb.sqlite` (약 131MB, LFS로 업로드) |
| OpenAI 키 | Streamlit Secrets에 등록 (선택·AI 기능용) |

---

## 1단계 — 배포 준비 (Mac)

```bash
cd /Users/admin/Desktop/ABC05CEO/hanul-002
chmod +x deploy/prepare_streamlit_cloud.sh
./deploy/prepare_streamlit_cloud.sh
```

---

## 2단계 — GitHub 비공개 저장소

1. [github.com/new](https://github.com/new) → **Private** 저장소 생성  
   이름 예: `hanul-audit-review`
2. 터미널에서:

```bash
cd /Users/admin/Desktop/ABC05CEO/hanul-002
git commit -m "Streamlit Cloud 배포"
git remote add origin https://github.com/본인아이디/hanul-audit-review.git
git push -u origin main
```

> KB가 100MB를 넘으므로 **Git LFS**가 자동 적용됩니다 (`.gitattributes` 포함).

---

## 3단계 — Streamlit Cloud 연결

1. [share.streamlit.io](https://share.streamlit.io) → GitHub 로그인  
2. **New app**  
   - Repository: `본인아이디/hanul-audit-review`  
   - Branch: `main`  
   - Main file path: **`app.py`**  
3. **Advanced settings** → **Secrets** → 아래 형식으로 입력:

```toml
OPENAI_API_KEY = "sk-실제키"
OPENAI_MODEL = "gpt-4o-mini"
AI_PROVIDER = "openai"
FSS_FOCUS_ISSUES_YEAR = "2026"
FALLBACK_TO_HARDCODED_PROCEDURES = "true"
```

(`.streamlit/secrets.toml.example` 참고)

4. **Deploy** 클릭 → 5~10분 후 완료

---

## 4단계 — 고정 URL (교수님 전달)

배포 후 주소 예:

| 용도 | URL |
|------|-----|
| **앱 (고정)** | `https://hanul-audit-review.streamlit.app` |
| (이름은 앱 설정 시 변경 가능) | |

카톡 메시지 예:

```
[ABC 5기 신성섭 · 감사조서 Smart Reviewer]

▶ 접속 (고정)
https://hanul-audit-review.streamlit.app

※ PC·Chrome/Safari 권장
※ 검증용 샘플 조서로 테스트 부탁드립니다.
```

> Streamlit Cloud에는 별도 **소개 랜딩 페이지**(카톡 OG)는 없고, 앱 첫 화면이 바로 열립니다.

---

## 코드 수정 후 재배포

```bash
git add -A
git commit -m "업데이트"
git push
```

Streamlit Cloud가 **자동으로** 다시 배포합니다. URL은 동일합니다.

---

## 맥 터널과 비교

| | Quick Tunnel | **Streamlit Cloud** |
|--|--------------|---------------------|
| 비용 | 0원 | **0원** |
| URL | 자주 변경 | **고정** |
| 맥 필요 | 항상 켜짐 | **불필요** |
| KB | 로컬 | **Git LFS 포함** |

---

## 문제 해결

| 증상 | 조치 |
|------|------|
| Deploy 실패 · LFS | GitHub에서 LFS 용량 확인, `git lfs push origin main` |
| KB 없음 | `VENV/bin/python build_index.py` 후 다시 push |
| AI 안 됨 | Secrets에 `OPENAI_API_KEY` 확인 |
| 앱 느림 | 무료 플랜 — 첫 접속 시 깨어남(수십 초) 가능 |

---

## 보안

- 저장소는 **Private** 권장  
- API 키는 **Secrets**에만 저장 (`.env`는 git에 올리지 않음)
