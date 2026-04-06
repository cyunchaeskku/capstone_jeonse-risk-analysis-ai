# AI 기반 전세사기 위험도 분석 및 법률 지식 지원 시스템

![system architecture diagram](img/architecture_diagram.png)

## Frontend 실행

`frontend/` 디렉터리에서 아래 순서로 실행한다.

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버 주소:

```text
http://localhost:5173
```

## Backend 실행

저장소 루트에서 아래처럼 실행한다.

```bash
export OPENAI_API_KEY=your_api_key
uvicorn backend.app.main:app --reload
```

기본 개발 서버 주소:

```text
http://localhost:8000
```

## 디렉터리 구조

- `frontend/`: React + Tailwind CSS 기반 사용자 화면
- `backend/`: FastAPI 기반 최소 API 서버

## 문서 구조

- `docs/제안서.md`: 제안 및 제출용 문서
- `docs/architecture.md`: 시스템 전체 구조와 책임 경계
- `docs/domain-model.md`: 핵심 엔티티와 데이터 의미
- `docs/api-contract.md`: 프론트엔드/백엔드 인터페이스 계약
- `docs/specs/`: 기능 단위 상세 스펙
- `docs/adr/`: 주요 기술 의사결정 기록
- `docs/WORKING_CONTEXT.md`: 다음 세션을 위한 작업 컨텍스트

## 외부 데이터 및 레퍼런스

- `korean-law-mcp`: 한국 법령 정보 조회용 MCP 서버
  - URL: `https://github.com/chrisryugj/korean-law-mcp`
  - 예상 역할: 법령 검색, 조문 조회, QA 보조 컨텍스트 제공
- `legalize-kr`: 대한민국 법령 Git 저장소
  - URL: `https://github.com/legalize-kr/legalize-kr/tree/main`
  - 예상 역할: 법령 원문 수집, 전처리, RAG 인덱싱용 원천 데이터

### 기술 스택

| 구분            | 기술                         | 용도                        |
| ------------- | -------------------------- | ------------------------- |
| **Frontend**  | React                      | UI 구현                    |
|               | Tailwind CSS               | 스타일                       |
| **Backend**   | FastAPI (Python)           | API 서버                    |
|               | REST API                   | 공공 데이터 연동 (law.go.kr 등)   |
| **RDB**       | PostgreSQL                 | 분석 이력 저장                  |
| **Vector DB** | FAISS                      | 법률 문서 벡터 인덱스 저장 및 유사도 검색  |
| **AI / LLM**  | GPT-5.4 nano (OpenAI API)    | Rule 결과 자연어 설명, RAG 답변 생성 |
|               | text-embedding-3-small     | 법률 문서 벡터 임베딩              |
| **RAG**       | LangChain                  | RAG 파이프라인 구성              |
| **문서 파싱**     | PyMuPDF                    | PDF 텍스트 추출                |
|               | Upstage Document Parse API | 고정밀 문서 파싱                 |
| **인프라**       | Docker                     | 컨테이너 관리                   |

## 현재 구현 메모

- 분석 API는 메모리 기반 최소 구현이다.
- 전역 챗봇은 `frontend`에서 `backend`의 `POST /qa`를 호출한다.
- QA는 LangChain + OpenAI 기반의 비-RAG 챗봇이며, 최근 2턴 문맥만 함께 전달한다.
