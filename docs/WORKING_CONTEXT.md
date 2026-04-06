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
- `backend/app/main.py`에 최소 FastAPI 엔드포인트 `health`, `analyses`, `qa`를 구현한다.
- 초기 백엔드 저장소는 메모리 기반으로 두고 후속 단계에서 DB로 확장한다.
- QA는 백엔드 무상태 방식으로 유지하고, 프론트가 최근 2턴 문맥만 전달한다.
- 챗봇은 전세 계약/위험/법률 보조에 집중하는 OpenAI 기반 LangChain 챗봇으로 구현한다.

## Open Decisions

- `korean-law-mcp`를 실시간 조회 경로로 쓸지 여부
- `legalize-kr`를 초기 RAG 인덱싱 원천 데이터로 채택할지 여부
- 법령 업데이트 동기화 주기와 검증 기준
- `POST /analyses`를 비동기 작업 큐로 전환할 시점
- 파일 업로드 저장 전략과 DB 스키마 도입 방식
- 법령/판례 RAG를 언제 도입하고 어떤 데이터 소스를 우선 연결할지

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

1. OpenAI API 키를 환경 변수로 설정하고 챗봇 응답 품질을 점검한다.
2. QA 레이어에 실제 법령/판례 검색을 붙일지 RAG 방향을 결정한다.
3. 분석 결과 화면과 `analysis_id` 기반 후속 질문 흐름을 연결한다.

## Notes For Next Session

- 외부 법령 데이터 소스 2개가 문서에 반영되어 있다.
- 구현 전, MCP 연동과 법령 저장소 ingest 전략을 ADR로 분리하는 것이 적절하다.
- 현재 QA는 비-RAG LangChain 챗봇이며, 실제 법령 근거 회수는 아직 구현되지 않았다.
