# ADR 0002: QA Routing with LangGraph

## Status

Accepted

## Context

전세 관련 QA에는 단순 대화와 법령 근거가 필요한 질문이 섞인다. 모든 질문에 벡터 검색을 강제하면 불필요한 검색 비용이 생기고, 단순 질문의 응답 품질도 떨어질 수 있다.

## Decision

- `POST /qa` 내부에 LangGraph 기반 라우팅을 둔다.
- 질문을 먼저 분류해 단순 질문은 검색 없이 답변한다.
- 법령/근거가 필요한 질문만 `vectorDB/laws_faiss`의 로컬 FAISS 인덱스를 검색한다.
- 검색 결과는 `references`와 구조화된 `sources`로 함께 반환한다.
- 기존 `/qa` 응답 계약은 유지하고, 프론트는 추가 출처 필드를 선택적으로 표시한다.

## Consequences

- 단순 질문에 대한 응답 지연과 검색 비용을 줄일 수 있다.
- 법령 질문은 출처 표시가 가능한 구조로 정리된다.
- 분류 규칙과 검색 품질은 후속 개선 대상으로 남는다.

## Alternatives Considered

- 모든 질문에 항상 벡터 검색 수행
- LLM 단일 프롬프트로만 라우팅과 답변을 처리
- 외부 관리형 벡터 데이터베이스 즉시 도입
