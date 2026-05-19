# AGENTS.md

## 목적

이 파일은 이 저장소에서 작업하는 agent가 가장 먼저 읽어야 하는 컨텍스트 문서다.
변경 작업 전 이 문서를 읽고, 필요하면 아래에 연결된 문서와 코드 경로를 추가로 확인한다.

## 프로젝트

- 이름: AI 기반 전세사기 위험도 분석 및 법률 지식 지원 시스템
- 저장소 루트: `capstone_jeonse-risk-analysis-ai`
- 제품 목표: 사용자가 전세계약 체결 전에 위험 신호를 확인하고, 규칙 기반 판단 결과를 이해하며, 전세/법률 관련 질문에 근거 기반 답변을 받을 수 있게 한다.
- 현재 구현 상태: 문서만 있는 단계가 아니다. React 프론트엔드, FastAPI 백엔드, PostgreSQL 법령 스키마, 법령 수집 스크립트, 로컬 FAISS 법령 벡터 인덱스가 존재한다.

## 기준 문서

구현 기준은 아래 문서다.

- `README.md`: 사용자용 프로젝트 개요와 실행 방법
- `docs/WORKING_CONTEXT.md`: 현재 결정 사항, 미결정 사항, 다음 작업
- `docs/architecture.md`: 모듈 경계와 아키텍처 원칙
- `docs/domain-model.md`: 핵심 도메인 엔티티와 데이터 의미
- `docs/api-contract.md`: 프론트엔드/백엔드 API 계약
- `docs/specs/risk-analysis.md`: deterministic 위험 분석과 매물 점검 규칙
- `docs/specs/document-pipeline.md`: 문서 파싱과 정규화 범위
- `docs/specs/legal-qa.md`: 챗봇/RAG 동작 기준
- `docs/adr/`: 주요 기술 의사결정 기록
- `backend/README.md`, `RDB/README.md`, `scripts/README.md`: 구현/운영 세부 문서

`docs/제안서.md`는 제출용 제안서다. `docs/` 스펙이나 코드와 충돌하면 구현 기준으로 보지 않는다.

## 현재 코드 구조

- `frontend/`: Vite + React + Tailwind UI
  - `src/App.jsx`: `/`, `/analysis/new`, `/chatbot`, `/listing-check` 라우트 정의
  - `src/pages/HomePage.jsx`: 서비스 소개/개요 화면
  - `src/pages/AnalysisNewPage.jsx`: 새 분석 화면. 등기부등본 PDF 업로드 후 채권최고액과 LLM 특이사항 추출 결과 표시
  - `src/pages/ListingCheckPage.jsx`: 실제 구현된 매물 점검 화면. Naver 지도, 장소 검색, 건축물대장 후보, 최근 전세 거래, AI 점검 결과 패널 포함
  - `src/context/ChatbotContext.jsx`: 전역 챗봇 상태. 최근 2턴만 백엔드로 전송
  - `src/ui/ChatbotPanel.jsx`, `FloatingChatbot.jsx`: 챗봇 UI와 출처 표시
- `backend/`: FastAPI 앱
  - `app/main.py`: API endpoint, Naver/Data.go.kr 연동, 매물 점검 규칙과 설명 orchestration
  - `app/services.py`: `POST /analyses`용 메모리 기반 demo 분석 서비스
  - `app/chatbot.py`: LangGraph QA router, simple/legal branch, FAISS 검색, OpenAI 답변 생성
  - `app/registry_parser.py`: 등기사항증명서 PDF 텍스트 추출과 `채권최고액` deterministic parsing
  - `app/registry_inspector.py`: 등기 텍스트 기반 표제부/갑구/을구 LLM 특이사항 추출
  - `app/schemas.py`: Pydantic request/response contract
  - `app/settings.py`: 환경 변수와 기본값
  - `app/db.py`, `app/models/law.py`: SQLAlchemy 설정과 법령 테이블 모델
  - `app/data/lawd_cd_map.json`: LAWD code 보조 데이터
- `RDB/`: 법령 데이터용 PostgreSQL 16 Docker Compose와 Alembic migration
- `scripts/`: 법령 수집과 FAISS 생성 스크립트
  - `ingest_laws.py`: `korean-law` CLI로 법령을 PostgreSQL에 저장
  - `make_vectorDB.py`: PostgreSQL 법령/조문 데이터를 `vectorDB/laws_faiss`로 변환
  - `law_targets.yaml`: 수집 대상 법령 목록
- `vectorDB/laws_faiss/`: LangChain FAISS 법령 인덱스 산출물
- `data/address_code.csv`: 매물 검색에서 사용하는 법정동 코드 CSV
- `docs/연구보고서/`: 주차별 연구 기록

## 구현된 사용자 흐름

### 전역 법률 챗봇

1. 프론트엔드 `ChatbotProvider`가 챗봇 메시지를 전역으로 저장한다.
2. 프론트엔드는 `POST /qa`로 `question`과 최근 user/assistant 2턴을 보낸다.
3. 백엔드 `ChatbotService`가 LangGraph로 질문을 분류한다.
4. 단순 질문은 OpenAI로 바로 답변한다.
5. 법령 질문은 `vectorDB/laws_faiss`에서 출처를 검색한 뒤, 검색된 context 기반으로만 답변한다.
6. 응답은 `answer`, `references`, `sources`, `route`, `scope`, 면책 문구를 포함한다.

### 매물 점검

1. 사용자는 `/listing-check`에서 건물명/주소를 입력하고 매물 유형 `apt`, `offi`, `rh`, `sh` 중 하나를 선택한다.
2. 프론트엔드는 Naver Local Search 기반 `GET /places/search`를 호출한다.
3. 사용자가 장소 후보를 선택한다.
4. 프론트엔드는 `GET /listing-checks/search`를 호출한다.
5. 백엔드는 `data/address_code.csv`로 법정동 코드를 찾고, 실패 시 Naver geocode/reverse-geocode로 보완한다.
6. 백엔드는 `apis.data.go.kr`의 건축물대장 API와 최근 부동산 거래 API를 호출한다.
7. 프론트엔드는 Naver 지도, 건축물대장 후보, 최근 전세 거래, 시세, 전세가율 preview를 표시한다.
8. 사용자가 `POST /listing-checks/analyze`를 실행한다.
9. 백엔드는 deterministic rule을 적용하고, LLM은 구조화된 결과 설명에만 사용한다.

현재 매물 점검 v1 규칙:

- `deposit_to_market_ratio`: 보증금 / 시세 > 0.8이면 fail
- `residential_use`: 건축물대장 용도가 주거용으로 확인되지 않으면 fail
- `위반건축물 여부`: v1에서는 의도적으로 숨김/제외

### Demo 분석 API

`POST /analyses`, `GET /analyses/{analysis_id}`는 아직 메모리 기반 최소 demo endpoint다.
보증금 규모와 문서 존재 여부만으로 위험도를 분류한다. 현재 주요 매물 점검 구현과 별개다.

### 등기부등본 파싱/특이사항 추출

1. 사용자는 `/analysis/new`에서 등기부등본 PDF를 업로드한다.
2. 프론트엔드는 `POST /registry/inspect`로 PDF를 보낸다.
3. 백엔드는 PDF text layer 또는 embedded ToUnicode CMap 기반으로 텍스트를 추출한다.
4. `registry_parser`는 `채권최고액`을 deterministic regex로 추출한다. 여러 금액이 있으면 현재는 마지막 등장 금액을 유효 후보값으로 반환한다.
5. `registry_inspector`는 추출 텍스트를 OpenAI 모델에 전달해 표제부, 갑구, 을구 특이사항을 JSON으로 추출한다.
6. LLM 결과는 보고서용 특이사항/안내로만 사용한다. 위험도 공식 계산 값은 parser 또는 사용자 입력으로만 처리한다.

## API 목록

현재 백엔드 endpoint:

- `GET /`
- `GET /health`
- `POST /analyses`
- `POST /registry/parse`
- `POST /registry/inspect`
- `GET /analyses/{analysis_id}`
- `GET /places/search`
- `GET /geocode`
- `GET /building-register`
- `GET /jeonse-data`
- `GET /listing-checks/search`
- `POST /listing-checks/analyze`
- `POST /qa`

endpoint shape이 바뀌면 `docs/api-contract.md`를 함께 맞춘다.

## 실행과 환경 변수

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
export OPENAI_API_KEY=your_api_key
export DATA_GO_KR_API_KEY=your_api_key
export NAVER_MAPS_CLIENT_ID=your_client_id
export NAVER_MAPS_CLIENT_SECRET=your_client_secret
export NAVER_SEARCH_CLIENT_ID=your_client_id
export NAVER_SEARCH_CLIENT_SECRET=your_client_secret
export VECTOR_DB_PATH=vectorDB/laws_faiss
uvicorn backend.app.main:app --reload
```

PostgreSQL:

```bash
docker compose -f RDB/docker-compose.yml up -d
alembic -c RDB/alembic.ini upgrade head
```

주요 기본값:

- 프론트엔드 dev server: `http://localhost:5173`
- 백엔드 dev server: `http://localhost:8000`
- PostgreSQL URL 기본값: `postgresql+psycopg://postgres:postgres@localhost:5432/jeonse_db`
- OpenAI model 기본값: `gpt-4.1-nano`
- Embedding model 기본값: `text-embedding-3-small`
- FAISS index 기본값: `vectorDB/laws_faiss`

## 데이터와 외부 의존성

- OpenAI API: 챗봇 답변, 매물 점검 자연어 설명, 등기부등본 특이사항 추출, vector build용 embedding
- Naver Maps API: geocoding, reverse geocoding
- Naver Local Search API: 장소/건물 후보 검색
- Data.go.kr APIs:
  - 건축물대장 title info
  - 아파트/오피스텔/연립·다세대/단독·다가구 전월세 데이터
  - 아파트/오피스텔/연립·다세대/단독·다가구 매매 데이터
- `korean-law-mcp`: 법령 조회 후보이자 CLI 기반 법령 ingest 의존성
- `legalize-kr`: 향후 법령 원문 ingestion 후보. 아직 primary source로 채택되지 않음
- PostgreSQL: 법령 metadata/articles/relations 저장
- FAISS: QA용 로컬 법령 article retrieval

## 데이터베이스 상태

법령 데이터 schema는 `backend/app/models/law.py`와 `RDB/alembic/versions/b714fd4ea8de_create_law_tables.py`에 있다.

테이블:

- `laws`
- `law_articles`
- `law_relations`

현재 앱은 PostgreSQL을 법령 데이터 수집과 vector build 지원에 사용한다.
일반 사용자 분석 이력은 아직 process memory에만 저장된다.

## 작업 규칙

- LLM을 위험 점수의 최종 판단 주체로 보지 않는다.
- ADR이 바꾸지 않는 한 위험 판단은 deterministic rule 기반으로 유지한다.
- LLM은 구조화된 위험 결과 설명에는 사용할 수 있지만 rule status를 바꾸면 안 된다.
- legal QA와 risk evaluation logic은 분리한다.
- QA는 analysis context를 질문 이해에만 사용할 수 있고, 위험도를 재판정하면 안 된다.
- 외부 법령 source는 spec/ADR이 source-of-truth로 승격하기 전까지 integration dependency로 취급한다.
- architecture, API shape, risk rule, data flow, storage를 바꿀 때는 docs를 먼저 또는 함께 갱신한다.
- 주요 기술 결정은 `docs/adr/`에 기록한다.
- `docs/WORKING_CONTEXT.md`는 짧고 최신으로 유지한다.
- 작업트리의 기존 사용자 변경을 보존한다. 관련 없는 변경을 되돌리지 않는다.
- 토큰 절약을 위해 한국어 응답도 caveman style로 짧게 한다.

## 초기 버전 비목표

- 완전 자율 법률 판단
- LLM-only 위험 분류
- legal QA 출력과 deterministic risk score 혼합
- demo `/analyses` risk logic을 production-grade risk analysis로 간주
- 공공 API 데이터가 없거나 불완전할 때 불확실성 숨기기

## 알려진 gap과 risk

- `/analyses`는 memory-backed라 서버 재시작 시 데이터가 사라진다.
- 등기부등본 PDF 업로드와 기초 parsing은 연결됐지만, 계약서/건축물대장 등 전체 문서 pipeline은 end-to-end로 연결되지 않았다.
- 등기부등본 LLM 특이사항 추출은 text 기반이라 실선 말소 여부 같은 시각적 정보 판단은 불확실할 수 있다.
- 매물 점검 검색은 외부 API key/config/quota/data coverage 문제로 실패할 수 있다.
- Market price logic은 최근 거래 데이터를 우선 사용한다. fallback/mock/provider production rule은 더 명확히 해야 한다.
- 법령 index freshness와 legal source update cadence는 미결정이다.
- `legalize-kr` 채택 여부는 미결정이다.
- 자동화 test suite는 아직 성숙하게 보이지 않는다.

## 세션 handoff

큰 작업 세션을 끝내기 전 아래를 갱신한다.

1. `docs/WORKING_CONTEXT.md`
2. 관련 `docs/specs/` 문서
3. API가 바뀌었으면 `docs/api-contract.md`
4. 기술 결정이 있었으면 ADR 문서
5. repo 구조나 현재 구현 상태가 바뀌었으면 이 `AGENTS.md`
