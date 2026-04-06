# ADR 0002: Risk Engine Approach

## Status

Proposed

## Context

전세사기 위험 판단은 설명 가능성과 일관성이 중요하다.

## Decision

- 초기 버전의 위험 판단은 규칙 기반 엔진으로 구현한다.
- LLM은 판단 결과 설명 계층에만 사용한다.
- 규칙 결과와 설명 결과를 분리된 출력으로 유지한다.

## Consequences

- 판단 근거를 명확히 추적할 수 있다.
- 규칙 추가와 검증이 쉬워진다.
- 복합적인 사례에서는 규칙 설계 비용이 커질 수 있다.

## Alternatives Considered

- LLM 중심 위험 분류
- 규칙과 모델 점수 결합형 하이브리드 엔진
