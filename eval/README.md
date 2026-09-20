# 평가 데이터셋

규칙 엔진 정확도 측정용 라벨링 케이스. 케이스 하나가 JSON 파일 하나다.

```
cases/real/       실제 사례. 경매 기록·등기부 등 외부 근거로 라벨링
cases/synthetic/  경계값 더미. 임계 동작 검증용
validate.py       전 케이스 스키마 검증
```

테스트(`backend/tests/`)와 분리한다. 테스트는 pass/fail이고 평가는 지표 산출이다.

다만 CI에서는 `run_rules_eval.py`가 **기준선 아래로 떨어질 때만** exit 1을 낸다
(`BASELINE_*` 상수). 지표가 오르내리는 것 자체는 막지 않고, 규칙을 고치다 정확도를
떨어뜨리거나 미탐을 만든 경우만 잡는다. 의도적으로 기준선을 바꿀 땐 상수를 같이 올린다.

## 케이스 스키마

| 필드 | 필수 | 내용 |
|---|---|---|
| `case_id` | ✓ | 파일명과 동일 |
| `description` | ✓ | 한 줄 요약 |
| `label_source` | ✓ | `auction_outcome` / `expert_judgment` / `synthetic_boundary` |
| `payload` | ✓ | `RiskAssessRequest` 그대로. 그대로 엔진에 들어간다 |
| `expected.grade` | ✓ | 정답 등급. `safe` / `caution` / `risk` / `high_risk` |
| `expected.rationale` | ✓ | 그 등급인 근거. 엔진 출력이 아니라 외부 사실로 적는다 |
| `expected.checks` | ✓ | 규칙별 정답 status. **모르면 `null`** — 하네스가 집계에서 뺀다 |
| `provenance` | 실제 사례만 | 값마다 실측/추론/가정/미확인 구분 |
| `outcome` | 실제 사례만 | 경매 결과 등 라벨의 근거가 된 사실 |
| `notes` | | 자유 기술 |

## provenance를 적는 이유

같은 케이스 안에서도 값마다 신뢰도가 다르다. 하임빌 건은 보증금이 **실측**(실거래가 2건),
근저당 0은 **추론**(최선순위가 가압류라는 사실에서 도출), 건축물 용도는 **미확인**이었다.

이걸 기록하지 않으면 나중에 라벨을 의심할 때 되짚을 수 없고, 보고서에서 "실제 사례로
검증했다"는 주장의 강도도 구분해 쓸 수 없다.

## expected.checks에 null을 허용하는 이유

확인하지 못한 항목을 억지로 라벨링하면 없는 오답이 생긴다. `null`은 "정답을 모른다"는
뜻이고, 하네스는 해당 규칙을 그 케이스에서만 집계 대상에서 제외한다.

## 규칙 코드

엔진이 반환하는 `code` 값을 쓴다. R7이 `duplicate_contract`를 반환하는 것은 현재 구현
그대로이며, 데이터셋도 구현을 따른다.

| 코드 | 규칙 |
|---|---|
| `deposit_to_market_ratio` | R1 전세가율 |
| `mortgage_ratio` | R2 근저당 비율 (R2-b 보증금 합산 포함) |
| `owner_mismatch` | R3 임대인·소유자 일치 |
| `rights_encumbrance` | R4 권리침해 등기 |
| `residential_use` | R5 주거용 여부 |
| `illegal_building` | R6 위반건축물 |
| `duplicate_contract` | R7 전세 거래 집중도 |
| `senior_deposit` | R8 선순위 보증금 |

## 계약 시점 복원 규칙

경매 물건의 등기부에는 경매개시결정과 이후의 압류가 이미 올라와 있다. 그대로 넣으면
R4가 `fail`이 되어 결과를 보고 결과를 맞히는 순환논증이 된다.

**임차인 전입일자보다 늦게 접수된 등기는 전부 제외한다.** 평가 질문은 "계약할 때 이
시스템을 썼다면 막을 수 있었는가"이기 때문이다.
