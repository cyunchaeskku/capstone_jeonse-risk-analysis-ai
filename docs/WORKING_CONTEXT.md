# Working Context

이 파일은 다음 세션에서도 빠르게 작업을 이어가기 위한 운영 메모다.
구현 세부사항보다 현재 결정 상태와 다음 액션을 짧게 유지한다.

## Project Snapshot

- 프로젝트명: AI 기반 전세사기 위험도 분석 및 법률 지식 지원 시스템
- 현재 목표: 최소 구현을 실제 챗봇 API와 프론트 연동까지 확장한다.
- 현재 단계: 최소 백엔드 부트스트랩 이후 LangChain 챗봇 연결 단계
- 마지막으로 합의한 범위: FastAPI `POST /qa`와 전역 챗봇 UI의 실제 API 연동

## Fixed Decisions

- 제안서는 제출용 문서로 유지하고 `docs/`를 구현 기준 문서로 사용한다.
- 위험 판단은 규칙 기반 엔진과 설명 계층을 분리한다.
- 법률 QA는 위험도 산정과 분리된 grounded answer 계층으로 둔다.
- 외부 법령 관련 자산으로 `korean-law-mcp`와 `legalize-kr`를 문서에 포함한다.
- 프론트엔드 기본 테마는 성균관대 컬러 `#8DC63F`와 `#124633` 기반으로 통일한다.
- `backend/app/main.py`에 최소 FastAPI 엔드포인트 `health`, `analyses`, `qa`를 구현한다.
- QA는 백엔드 무상태 방식으로 유지하고, 프론트가 최근 2턴 문맥만 전달한다.
- 챗봇은 전세 계약/위험/법률 보조에 집중하는 OpenAI 기반 LangChain 챗봇으로 구현한다.
- 법령 데이터 저장용 PostgreSQL 스키마를 확정했다: `laws`, `law_relations`, `law_articles` 3개 테이블.
- DB는 `RDB/docker-compose.yml`로 PostgreSQL 16 컨테이너를 운영하고, Alembic으로 마이그레이션을 관리한다.
- SQLAlchemy 모델은 `backend/app/models/law.py`, 엔진/세션은 `backend/app/db.py`에 정의한다.
- `korean-law-mcp`를 Claude Desktop MCP 서버로 등록 완료했다 (Remote URL, OC: cyunchaeskku).
- `scripts/make_vectorDB.py`를 추가해 `laws` + `law_articles`를 조문 단위로 LangChain FAISS 벡터DB(`vectorDB/laws_faiss`)로 생성할 수 있게 했다.
- 벡터 문서 metadata에 `citation_label`(`법령명 + 조문번호`)을 포함해 검색 결과에서 곧바로 인용 표시가 가능하다.
- `MapPage`에 주소 검색 + 지도 클릭 기반 건물 선택 흐름을 추가했고, 백엔드 `GET /building-register`로 건축물대장 요약 정보를 조회한다.
- 건축물대장은 Naver reverse geocoding 결과의 법정동코드를 사용해 조회하며, 우측 패널에는 요약 카드 우선 표시를 적용했다.
- 주소 검색은 바로 확정하지 않고 후보 목록을 스크롤로 노출한 뒤, 사용자가 후보를 클릭해서 최종 건물을 선택하는 방식으로 정리했다.
- 우측 패널 상단에 접이식 건축물대장 체크 가이드를 넣어, 전세사기 예방 관점의 핵심 확인 항목을 먼저 보여준다.

## Open Decisions

- `legalize-kr`를 초기 RAG 인덱싱 원천 데이터로 채택할지 여부
- 법령 업데이트 동기화 주기와 검증 기준
- `POST /analyses`를 비동기 작업 큐로 전환할 시점
- 파일 업로드 저장 전략과 DB 스키마 도입 방식
- 법령/판례 RAG를 언제 도입하고 어떤 데이터 소스를 우선 연결할지
- 건축물대장 응답에서 후보가 여러 개일 때 선택 우선순위를 더 정교하게 만들지 여부

## Active Documents

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/api-contract.md`
- `docs/specs/document-pipeline.md`
- `docs/specs/risk-analysis.md`
- `docs/specs/legal-qa.md`
- `backend/README.md`

## Next Recommended Steps

1. `scripts/make_vectorDB.py` 산출물(`index.faiss`, `documents.jsonl`)을 QA 검색 경로에 연결한다.
2. `legalize-kr`를 RAG 원천 데이터로 채택할지 결정하고, 채택 시 ingest 전략을 ADR로 분리한다.
3. 분석 결과 화면과 `analysis_id` 기반 후속 질문 흐름을 연결한다.

## Notes For Next Session

- `korean-law-mcp` Claude Desktop 등록 완료. CLI(`LAW_OC=cyunchaeskku korean-law ...`)로도 동작 확인됨.
- PostgreSQL 컨테이너(`jeonse_postgres`)가 로컬에 올라가 있으며 3개 테이블 마이그레이션 완료 상태.
- 다음 세션 시작 전 `docker compose -f RDB/docker-compose.yml up -d`로 컨테이너 재기동 필요할 수 있음.
- 현재 QA는 비-RAG LangChain 챗봇이며, 실제 법령 근거 회수는 아직 구현되지 않았다.
- legalize-kr ingest 전략은 결정되지 않았다.
- 지도 클릭 기반 건축물대장 조회는 좌표 → reverse geocode → 법정동코드 → 건축물대장 순으로 동작한다.
