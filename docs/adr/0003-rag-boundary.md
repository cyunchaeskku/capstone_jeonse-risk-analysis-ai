# ADR 0003: RAG Boundary

## Status

Proposed

## Context

법률 및 판례 검색 기능과 위험 설명 기능이 혼합되면 시스템 책임 경계가 흐려질 수 있다.

## Decision

- RAG는 법률 및 판례 기반 질의응답에 우선 적용한다.
- 위험도 설명은 분석 결과와 규칙 근거를 바탕으로 생성한다.
- QA 응답은 참고 정보이며 위험 판정 결과를 덮어쓰지 않는다.

## Consequences

- 시스템 책임 분리가 명확해진다.
- 분석 결과와 QA 결과 간 충돌을 줄일 수 있다.
- 향후 위험 설명 고도화 시 추가 설계가 필요할 수 있다.

## Alternatives Considered

- 모든 설명 계층에 통합 RAG 사용
- QA 없이 분석 결과 설명만 제공
