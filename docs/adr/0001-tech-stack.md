# ADR 0001: Tech Stack Baseline

## Status

Proposed

## Context

프로젝트 초기 단계에서 프론트엔드, 백엔드, 저장소, 검색 계층의 기본 스택을 고정할 필요가 있다.

## Decision

- Frontend: React
- Backend: FastAPI
- RDB: PostgreSQL
- Vector Index: FAISS
- LLM API: OpenAI API

## Consequences

- 빠른 프로토타이핑이 가능하다.
- Python 기반 데이터 처리와 백엔드 로직을 일관되게 유지할 수 있다.
- 벡터 인덱스 운영 방식은 추후 서비스 규모에 따라 재검토가 필요할 수 있다.

## Alternatives Considered

- Next.js 기반 단일 저장소 구성
- Node.js 백엔드 기반 구현
- 관리형 벡터 데이터베이스 사용
