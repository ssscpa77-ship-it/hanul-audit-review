# 듀얼 RAG 설계 — 교수님 자문의견 반영 (hanul-002)

> 작성: 2026-07-15 · 버전 v0.9 설계안  
> 목적: 심리노트 자동화의 RAG 전략 이원화 및 A/B 검증 체계 수립

---

## 1. 교수님 의견 요약

| 자료 성격 | 권장 방식 | hanul-002 대응 |
|-----------|-----------|----------------|
| **정성적 근거** (K-IFRS 조문, 질의회신, 감리지적 해설) | VectorDB semantic RAG | `rag_strategy.retrieve_qualitative()` → Phase2 벡터, 현재 FTS 폴백 |
| **정량적 판단** (중요성 대비 금액, 회수기간, 이상치) | 추출 → 계산 → 규칙 (RAG 아님) | `quantitative_extract` + `review_engine` 규칙 |
| **내부 모범 조서** (숫자+서술 혼재) | 서술/수치 분리 파싱 후 이원 저장 | `workpaper_segment` |
| **A/B 검증** | (a) Vector only (b) 파일만 (c) 하이브리드 | `ab_experiment.py` |

---

## 2. 현재 vs 목표 아키텍처

### 현재 (v0.8)

```
업로드 → parser (평탄화) → FTS RAG ─┬→ 규칙엔진 (계산 혼재)
                                    ├→ AI 리뷰
                                    └→ QC / 4대중점
```

### 목표 (v0.9+)

```
업로드
  → workpaper_segment (서술 / 수치 그리드 분리)
       ├─[정성 브랜치] rag_strategy (semantic RAG)
       │     → ai_review (서술 블록 + 인용 근거)
       └─[정량 브랜치] quantitative_extract → facts JSON/표
             → review_engine (계산·중요성·대사 — RAG 미사용)
  → note_merge → notes_pipeline → 리뷰노트
  → ab_experiment (variant A/B/C vs QRM 골든셋 채점)
```

---

## 3. 모듈 구조 (신규)

| 파일 | 역할 |
|------|------|
| `rag_strategy.py` | 자료 성격별 검색 라우팅 (qualitative / workpaper-narrative / no-rag) |
| `workpaper_segment.py` | 시트 내 서술·수치·헤더 영역 분리 |
| `quantitative_extract.py` | 금액·합계·계정·기간 구조화 추출 |
| `dual_review_pipeline.py` | 이원 파이프라인 오케스트레이션 |
| `ab_experiment.py` | A/B/C variant 실행·QRM 대조 채점 |

---

## 4. RAG 이원화 상세

### 4.1 정성적 RAG (Vector / Semantic)

**대상 카테고리** (`knowledge_base.py`):

- 회계감사기준, K-IFRS, 일반기업회계기준, K-IFRS 실무사례
- 질의회신_한국회계기준원
- 금융감독원·한공회 감리지적사례 (서술형 해설)
- 4대 중점사항 (보도자료·유의사항)

**검색 질의 예**: "유사한 과거 지적사례", "수익인식 관련 기준 해석"

**Phase 1 (현재)**: FTS5 BM25 + 카테고리 필터 (`retrieve_qualitative`)  
**Phase 2 (완료)**: `embedding_index.py` + `build_index.py --embed` → hybrid RRF (`retrieve_hybrid`)

### 4.2 정량적 파이프라인 (Non-RAG)

**처리 흐름**: `표/셀 → to_number → AmountFact → 규칙 판단`

| 판단 유형 | 규칙 위치 | 입력 |
|-----------|-----------|------|
| 합계·부분합 검증 | `review_engine._verify_table_totals` | AmountGrid |
| FS·주석 대사 | `_check_cross_fs_totals` | 구조화 facts |
| 중요성 대비 금액 | `Materiality.min_calc_threshold` | TE/PM/CTT + 잔액 |
| 회수기간·이상치 | `quantitative_extract.detect_anomalies` (신규) | 시계열 금액 |

**원칙**: 벡터 검색 결과를 정량 판단에 사용하지 않음.

### 4.3 모범 조서 (Workpaper) 전처리

```
한울 예시조서 / 감사조서 샘플
  → segment_sheet()
       narrative_blocks[]  → 임베딩·RAG (서술·절차·결론)
       amount_grids[]      → quantitative_facts 테이블 (금액만)
```

색인 시 (`build_index.py` 확장 예정):

- narrative chunk → `chunks` FTS + (Phase2) `chunks_vec`
- amount grid → `quant_facts` SQLite 테이블 (비임베딩)

---

## 5. A/B 테스트 설계 (교수님 5번 피드백)

### Variant 정의

| ID | 이름 | RAG | 조서 컨텍스트 | 구조화 추출 |
|----|------|-----|---------------|-------------|
| **A** | `vector_only` | FTS/Vector (정성 카테고리만) | 최소 (쿼리만) | 없음 |
| **B** | `file_context_only` | 없음 | 업로드 조서 전문 | 없음 |
| **C** | `structured_hybrid` | 정성 RAG | 서술 블록만 | 수치 facts + 규칙 |

### 채점 방식

1. QRM 심리역 **실제 리뷰노트** (또는 `golden_set_catalog` + 확장 케이스)를 정답셋으로 등록
2. 동일 조서·동일 질의에 대해 A/B/C 실행
3. 지표:
   - **Recall@Tier1**: 필수 지적 항목 적중률
   - **Precision**: 불필요 지적(False Positive) 비율
   - **근거 일치도**: 인용 출처·사례번호 일치
   - **정량 판단 일치**: 합계오류·중요성 이상 탐지 일치 (Variant C만)

### 실행

```bash
# 골든셋 4대중점 (기존)
python3 golden_set_regression.py

# A/B 3-variant 비교 (신규)
python3 ab_experiment.py --fixture golden --variants A,B,C
```

환경 변수: `REVIEW_VARIANT=structured_hybrid` (Streamlit·배치)

---

## 6. 구현 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| **0** | 설계 문서 + 모듈 골격 | ✅ 본 문서 |
| **1** | `workpaper_segment` + `quantitative_extract` 연동 | ✅ v0.9 골격 |
| **2** | `dual_review_pipeline` → `notes_pipeline` 연결 | ✅ 메타 주입 |
| **3** | `ab_experiment` 골든셋 채점 | ✅ 기본 harness |
| **4** | `build_index` 벡터 임베딩 + hybrid search | ✅ Phase 2 (`embedding_index`, `--embed`, RRF) |
| **5** | QRM 실제 리뷰노트 정답셋 import UI | 🔲 Phase 2 |
| **6** | Streamlit A/B 비교 대시보드 | ✅ Phase 3 (`ab_dashboard.py` + 앱 탭) |

---

## 7. 설정 (`.env` / Streamlit Secrets)

```toml
REVIEW_VARIANT = "structured_hybrid"   # vector_only | file_context_only | structured_hybrid
RAG_MODE = "hybrid"                  # fts | vector | hybrid
DUAL_RAG_ENABLED = "true"
EMBEDDING_PROVIDER = "local"         # local (fastembed) | openai
# EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

### 색인 (벡터 포함)

```bash
# 신규 FTS + 임베딩 (정성 카테고리만)
python3 build_index.py --embed

# 기존 DB에 임베딩만 추가
python3 build_index.py --embed-all

# 검증용 소규모
python3 build_index.py --embed-all --embed-limit 30

# 클라우드 배포용 gzip 재생성
gzip -9 -k -f kb_store/hanul_kb.sqlite
```

---

## 8. 심리노트 필드 확장 (향후)

리뷰노트 dict에 파이프라인 출처 태그 추가:

```python
{
  "category": "절차누락",
  "pipeline": "quant_rules",      # quant_rules | qual_rag | qual_ai
  "rag_variant": "structured_hybrid",
  "evidence_type": "structured", # narrative | structured | citation
}
```

A/B 채점·QRM 대조 시 variant별 성능 분리에 사용.

---

## 9. 결론

교수님 의견대로 **「정성 = RAG / 정량 = 추출·계산」** 이원화는 기술적으로 가능하며,  
현재 코드베이스의 `review_engine` 규칙·`parser` 표 추출·`golden_set` 인프라를 기반으로  
**점진적 마이그레이션**이 적합합니다. v0.9에서 골격을 반영하고, 벡터 RAG·QRM 정답셋은 Phase 2에서 완성합니다.
