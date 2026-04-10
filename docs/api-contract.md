# API Contract

## 목적

이 문서는 프론트엔드와 백엔드 사이의 인터페이스 계약 초안을 관리한다.
구현 시작 전 요청/응답 스키마를 먼저 고정하는 데 사용한다.

## 원칙

- API는 프론트엔드 UI 흐름 기준으로 설계한다.
- 내부 구현 세부사항은 응답 포맷에 노출하지 않는다.
- 모든 분석 결과는 근거와 함께 반환한다.

## 예상 엔드포인트

### `POST /analyses`

- 목적: 사용자 입력과 업로드 문서를 받아 분석을 시작한다
- 초기 구현:
  - 동기 처리
  - 메모리 저장
  - 단순 규칙 기반 더미 위험도 산정
- 요청 필드:
  - `property.address`
  - `property.deposit_krw`
  - `property.monthly_rent_krw`
  - `property.building_type`
  - `contract`
  - `documents[]`
- 응답 필드:
  - `analysis_id`
  - `status`
  - `normalized_summary`

### `GET /analyses/{analysisId}`

- 목적: 분석 결과를 조회한다
- 초기 구현 응답:
  - `overall_risk`
  - `risk_factors`
  - `explanation`
  - `references`

### `POST /qa`

- 목적: 법률 및 판례 기반 질문을 처리한다
- 초기 구현:
  - LangChain + OpenAI 기반 비-RAG 챗봇 응답
  - 백엔드는 무상태이며 최근 대화 문맥은 요청에 포함한다
- 요청 필드:
  - `question`
  - `analysis_id`
  - `history[]`
- 응답 필드:
  - `answer`
  - `references`
  - `disclaimer`
  - `scope`

### `GET /health`

- 목적: 서버 상태 확인
- 초기 구현 응답:
  - `status`

### `GET /geocode`

- 목적: 사용자가 입력한 주소를 지도 좌표로 변환한다
- 초기 구현 응답:
  - `result.x`
  - `result.y`
  - `result.address`

### `GET /building-register`

- 목적: 지도에서 선택한 좌표를 기준으로 건축물대장 정보를 조회한다
- 초기 UI 흐름:
  - 주소 검색 후 후보 목록을 보여준다
  - 사용자가 후보를 클릭해 최종 건물을 선택한다
- 요청 필드:
  - `lat`
  - `lng`
- 초기 구현 응답:
  - `location`
  - `total_count`
  - `matched_count`
  - `selected`
  - `candidates`
  - `candidates`는 스크롤 가능한 후보 목록 렌더링을 위한 요약 배열이다

## 공통 응답 규칙

- 오류 응답은 코드, 메시지, 사용자 조치 힌트를 포함한다.
- 문서 기반 응답은 근거 출처를 포함한다.
- 위험도 응답은 사람이 읽을 수 있는 설명과 구조화 필드를 함께 제공한다.

## 결정 필요 항목

- 동기 처리와 비동기 처리 중 초기 방식
- 파일 업로드를 직접 받을지 presigned upload를 사용할지 여부
- 인증 도입 시점과 방식

## 현재 구현 메모

- 초기 버전은 `backend/app/main.py` 기준 FastAPI 앱으로 제공한다.
- 데이터는 프로세스 메모리에만 저장되므로 서버 재시작 시 사라진다.
- 위험도 로직은 API 연결 확인용 최소 예시이며, 실제 규칙 세트는 별도 스펙 확장이 필요하다.
- QA는 실제 RAG 없이 OpenAI 기반 챗봇으로 먼저 연결하며, 출처 배열은 추후 RAG 확장을 고려한 자리표시자다.
- 지도 페이지는 주소 검색과 지도 클릭을 모두 지원하며, 건축물대장은 좌표 선택 후 우측 패널에 요약 카드로 노출한다.
