# AI 기반 전세 계약 사기 예방 및 법률 지원 시스템

![system architecture diagram](img/architecture_diagram.png)

이 프로젝트는 전세 계약 과정에서 발생할 수 있는 사기 위험을 줄이고, 사용자가 계약 전후에 필요한 정보를 빠르게 확인할 수 있도록 돕는 시스템이다.  
핵심 목표는 다음 세 가지다.

1. 계약 전 매물·지역 탐색 단계에서 위험 신호를 찾는다.
2. 실제 매물 정보를 입력하면 해당 매물의 위험도를 분석한다.
3. 계약 당일 또는 계약 직전에 확인해야 할 항목을 안내한다.

## 주요 기능

### 1. 지역 기반 사전 탐색

사용자가 거주를 고려하는 동네 주변의 데이터를 지도와 함께 분석해 인사이트를 제공한다.

- 위반건축물 분포 확인
- 특정 유형의 위험 매물 밀집 여부 확인
- 지역별 위험 신호 요약
- 추후 항목 확장 가능한 구조의 경고 문구 제공

예시:

- "이 주변은 위반건축물이 많다."
- "이 주변은 특정 위험 유형의 매물이 많이 분포한다."
- "이 지역은 사전 검토가 필요한 위험 신호가 많다."

### 2. 실제 매물 위험 분석

사용자가 실제 매물 정보를 입력하면, 해당 매물의 위험 요소를 분석한다.

- 등기부등본 기반 확인 항목
- 실제 주소와 등록 정보 일치 여부 확인
- 권리관계, 소유 구조, 계약 관련 위험 신호 점검
- 분석 결과 요약 및 설명 제공

### 3. 계약 전 체크리스트 및 Q&A

계약하러 가기 전에 반드시 확인해야 할 항목을 안내한다.

- 상황별 체크리스트 제공
- 챗봇 기반 질문 응답
- 계약 단계별 주의사항 안내
- 사용자가 놓치기 쉬운 항목에 대한 보조 설명

## 개발 상태

이 저장소는 초기 설계와 구현을 병행하는 단계다.  
현재는 문서 중심으로 시스템 경계와 기능 범위를 정리하고 있으며, 세부 기능은 점진적으로 확장할 예정이다.

## 실행 방법

### Frontend

`frontend/` 디렉터리에서 실행한다.

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버 주소:

```text
http://localhost:5173
```

### Backend

저장소 루트에서 실행한다.

```bash
export OPENAI_API_KEY=your_api_key
uvicorn backend.app.main:app --reload
```

기본 개발 서버 주소:

```text
http://localhost:8000
```

## 디렉터리 구조

- `frontend/`: 사용자 화면
- `backend/`: API 서버
- `docs/`: 설계 문서, 기능 스펙, ADR, 작업 컨텍스트
- `RDB/`: 데이터베이스 관련 설정
- `scripts/`: 벡터 DB 생성 및 보조 스크립트

## 문서 구조

- `docs/제안서.md`: 제출용 제안 문서
- `docs/architecture.md`: 시스템 구조와 책임 경계
- `docs/domain-model.md`: 핵심 엔티티와 데이터 의미
- `docs/api-contract.md`: 프론트엔드/백엔드 인터페이스 계약
- `docs/specs/`: 기능 단위 상세 스펙
- `docs/adr/`: 기술 의사결정 기록
- `docs/WORKING_CONTEXT.md`: 다음 세션을 위한 작업 컨텍스트

## 외부 데이터 및 레퍼런스

- `korean-law-mcp`
  - URL: `https://github.com/chrisryugj/korean-law-mcp`
  - 역할: 법령 검색, 조문 조회, QA 보조 컨텍스트 제공
- `legalize-kr`
  - URL: `https://github.com/legalize-kr/legalize-kr/tree/main`
  - 역할: 법령 원문 수집, 전처리, RAG 인덱싱용 원천 데이터

## 기술 스택

| 구분 | 기술 | 용도 |
| --- | --- | --- |
| Frontend | React | UI 구현 |
| Frontend | Tailwind CSS | 스타일 |
| Backend | FastAPI (Python) | API 서버 |
| Backend | REST API | 공공 데이터 연동 |
| RDB | PostgreSQL | 분석 이력 저장 |
| Vector DB | FAISS | 법률 문서 벡터 인덱스 저장 및 유사도 검색 |
| AI / LLM | GPT-5.4 nano (OpenAI API) | 규칙 기반 결과 설명, QA 응답 보조 |
| AI / LLM | text-embedding-3-small | 법률 문서 벡터 임베딩 |
| RAG | LangChain | 검색 증강 생성 파이프라인 |
| 문서 파싱 | PyMuPDF | PDF 텍스트 추출 |
| 문서 파싱 | Upstage Document Parse API | 고정밀 문서 파싱 |
| 인프라 | Docker | 컨테이너 관리 |

## 현재 구현 메모

- 분석 API는 메모리 기반 최소 구현이다.
- 전역 챗봇은 `frontend`에서 `backend`의 `POST /qa`를 호출한다.
- QA는 현재 LangChain + OpenAI 기반의 최소 구현이며, 법령 기반 RAG는 후속 단계에서 확장한다.
