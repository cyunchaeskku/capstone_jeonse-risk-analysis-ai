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

### `POST /registry/parse`

- 목적: 업로드한 부동산 등기사항증명서 PDF에서 위험 분석 입력값을 추출한다
- 초기 구현:
  - PDF text layer 또는 embedded ToUnicode CMap 기반 텍스트 추출
  - `채권최고액` 금액 추출
  - 여러 금액이 있으면 마지막으로 등장한 금액을 현재 유효 후보값으로 반환
- 요청:
  - `multipart/form-data`
  - `file`: PDF 파일
- 응답 필드:
  - `filename`
  - `max_claim_amount_krw`
  - `max_claim_amounts[]` (`amount_krw`, `raw_text`, `page`)
  - `status` (`parsed`, `needs_review`)
  - `message`

### `POST /registry/inspect`

- 목적: 업로드한 등기사항증명서 PDF에서 deterministic 추출값과 LLM 기반 특이사항을 함께 반환한다
- 동작:
  - `POST /registry/parse`와 같은 PDF 텍스트 추출 및 `채권최고액` 추출을 먼저 수행한다
  - 추출 텍스트를 LLM에 전달해 표제부, 갑구, 을구 특이사항을 JSON으로 추출한다
  - LLM은 위험도 공식 계산이나 최종 계약 판단을 하지 않는다
- 요청:
  - `multipart/form-data`
  - `file`: PDF 파일
- 응답 필드:
  - `filename`
  - `max_claim_amount_krw`
  - `max_claim_amounts[]`
  - `inspection.property_section`
  - `inspection.ownership_section`
  - `inspection.rights_section`
  - `inspection.findings[]`
  - `inspection.needs_human_review`
  - `status` (`inspected`, `needs_review`)
  - `message`

### `GET /analyses/{analysisId}`

- 목적: 분석 결과를 조회한다
- 초기 구현 응답:
  - `overall_risk`
  - `risk_factors`
  - `explanation`
  - `references`

### `POST /risk/assess`

- 목적: R1~R8 마법사 입력을 deterministic 규칙으로 판정한다
- R8 입력:
  - `senior_deposit_krw`: 확인한 선순위 보증금 합계. 확인하지 못했으면 `null`, 실제로 없음을 확인했으면 `0`
- R8 응답:
  - 일반건물에서 `senior_deposit_krw`가 `null`이면 `senior_deposit` 검사는 `unknown`
- 점수 응답:
  - `risk_score` / `score_max`: 위험 점수와 상한(현재 100점)
  - `score_grade`: 점수만 기준으로 한 구간 등급. `risk_grade`는 고위험 오버라이드까지 반영한 최종 등급
  - `score_ranges[]`: 현재 점수 구간의 최소·최대 점수와 등급
  - `score_breakdown[]`: R1~R8별 `max_points`와 이번 결과에서 더해진 `added_points`

### `POST /qa`

- 목적: 법률 및 판례 기반 질문을 처리한다
- 동작:
  - `text/event-stream` SSE 응답으로 답변 토큰을 순차 전송한다
  - `token` 이벤트는 `{ "text": "..." }`를 전송한다
  - `done` 이벤트는 `references`, `sources`, `disclaimer`, `scope`, `route`를 전송한다
  - `sources[].content`는 선택한 출처의 상세 보기에 사용하는 전체 인덱스 본문이다
  - `sources[].official_url`은 법령이면 국가법령정보센터 현행 조문, 판례면 해당 판례 원문 링크다
  - 판례 `sources[]`에는 사건명, 사건번호, 선고법원, 선고일, 판결유형, 검색된 구간을 포함한다
  - `error` 이벤트는 `code`, `message`, `action_hint`을 전송한다
  - 백엔드는 무상태이며 최근 대화 문맥은 요청에 포함한다
- 요청 필드:
  - `question`
  - `analysis_id`
  - `history[]`

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

### `POST /listing-checks/analyze`

- 목적: 선택한 매물 정보 기준으로 규칙 기반 점검 결과와 설명을 반환한다
- 초기 구현 규칙:
  - 보증금 / 시세 값이 80% 초과인지 점검
  - 건축물 용도가 주거용인지 점검
- 중요 제약:
  - `위반건축물 여부`는 v1에서 표시하지 않는다
  - LLM은 재판정하지 않고, 구조화된 규칙 결과를 설명만 한다
- 요청 필드:
  - `property_type`
  - `listing_name`
  - `deposit_krw`
  - `market_price_krw` (선택, 없으면 mock provider 사용)
  - `selected_rent_item`
  - `selected_building`
  - `extra_signals`
- 응답 필드:
  - `checks[]` (`code`, `title`, `status`, `reason`, `evidence`)
  - `summary` (`overall_status`, `triggered_checks`)
  - `llm_explanation`

### `GET /listing-checks/search`

- 목적: 주소/건물명 단일 검색으로 점검에 필요한 후보 데이터를 한 번에 조회한다
- 동작:
  - 지오코딩으로 대상 위치를 찾는다
  - 같은 위치 기준 건축물대장 후보를 조회한다
  - 연립/다세대 전월세는 `umdNm`과 `jibun`이 모두 같은 거래만 최근 1년부터 1년씩 최대 10년 전까지 조회한다
  - 그 외 유형은 같은 검색어 기준 최근 1년 거래 내역을 조회한다
  - 최근 거래 1건을 시세(임시)로 반환한다
- 요청 필드:
  - `query` (주소 또는 건물명)
  - `property_type`
- 응답 필드:
  - `location`
  - `building`
  - `rent` (`lookup_status`: `complete` / `partial` / `unavailable`, 최근 3년 `concentration` 포함)
  - `market_price`

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
