"""경계값 더미 케이스 생성. 정답은 명세(docs/전세사기위험도판별핵심로직.md)에서 손으로 도출한다.

엔진을 돌려 정답을 만들면 정확도가 영원히 100%라 아무것도 검증하지 못한다.
아래 expected는 전부 명세 §3 판정 규칙과 §4 배점표를 읽고 직접 적은 값이다.

실행: PYTHONPATH=. .venv/bin/python eval/make_synthetic.py
"""

import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "cases" / "synthetic"

# 다른 규칙이 전부 pass가 되는 중립 입력. 여기서 한 축만 흔들어 임계를 때린다.
BASELINE = {
    "listing_name": "합성 경계값 케이스",
    "deposit_krw": 100_000_000,
    "market_price_krw": 500_000_000,
    "registry_type": "aggregate_building",
    "mortgage_total_krw": 0,
    "mortgage_items": [],
    "registry_owner_name": "소유자A",
    "contract_owner_name": "소유자A",
    "critical_terms": [],
    "building_type": "공동주택",
    "detail_use": "다세대주택",
    "illegal_building_status": "absent",
    "recent_jeonse_count": 0,
    "recent_jeonse_peak_12m_count": 0,
    "households": 0,
    "recent_jeonse_data_status": "unavailable",
    "senior_deposit_krw": None,
}

BASE_CHECKS = {
    "deposit_to_market_ratio": "pass",
    "mortgage_ratio": "pass",
    "owner_mismatch": "pass",
    "rights_encumbrance": "pass",
    "residential_use": "pass",
    "illegal_building": "pass",
    "duplicate_contract": "unknown",  # 집합건물은 R7 점수 미반영
    "senior_deposit": "pass",  # 집합건물은 R8 해당 없음
}

# 일반건물은 R2가 분모를 못 구해 unknown, R8은 선순위 보증금 입력에 따라 달라진다.
GENERAL = {"registry_type": "general_building"}
GENERAL_CHECKS = {
    "deposit_to_market_ratio": "unknown",
    "mortgage_ratio": "unknown",
    "senior_deposit": "unknown",
}

CASES = [
    # ── R1 전세가율: ratio > 0.80 → fail ─────────────────────────────────
    (
        "r1-ratio-at-threshold",
        "전세가율 정확히 80.0%. 명세는 초과(>)라 경계값은 fail이 아니다.",
        {"deposit_krw": 400_000_000},
        "safe",
        {},
        "400/500 = 0.80. 명세 R1은 `ratio > 0.80`이므로 등호는 pass. R2-b도 `> 0.80`이라 동일.",
    ),
    (
        "r1-ratio-just-above",
        "전세가율 81%. R1과 R2-b가 같은 임계를 공유해 동시에 켜진다.",
        {"deposit_krw": 405_000_000},
        "risk",
        {"deposit_to_market_ratio": "fail", "mortgage_ratio": "fail"},
        "405/500 = 0.81. R1 fail(15). 근저당 0이라 R2-b도 (0+405)/500 = 0.81 > 0.80 → fail(30). 합 45 → 위험. 오버라이드는 1.0 초과가 아니라 미발동.",
    ),
    (
        "r1-market-price-missing",
        "시세 미확보. R1·R2가 함께 unknown이 되어 점수가 0이 된다.",
        {"market_price_krw": 0},
        "safe",
        {"deposit_to_market_ratio": "unknown", "mortgage_ratio": "unknown"},
        "명세 §7 예외처리: 시세 미확보 시 R1 unknown, 점수 미가산. R2도 분모가 없어 unknown. 결과적으로 안전으로 표시된다.",
    ),
    # ── R2 근저당: >0.60 fail / 0.40~0.60 warn ──────────────────────────
    (
        "r2-ratio-at-warn-lower-bound",
        "근저당 비율 정확히 40%. 명세는 초과부터 warn.",
        {"mortgage_total_krw": 200_000_000, "mortgage_items": [{"amount_krw": 200_000_000, "shared_property_count": 1}]},
        "safe",
        {},
        "200/500 = 0.40. 명세 R2는 `0.40 < ratio`부터 warn이므로 등호는 pass. 합산 (200+100)/500 = 0.60 ≤ 0.80.",
    ),
    (
        "r2-ratio-warn",
        "근저당 비율 50%. warn은 가중치 절반만 가산된다.",
        {"mortgage_total_krw": 250_000_000, "mortgage_items": [{"amount_krw": 250_000_000, "shared_property_count": 1}]},
        "caution",
        {"mortgage_ratio": "warn"},
        "250/500 = 0.50 → warn. 명세 §4-2에 따라 30 // 2 = 15점 → 주의(15~29). 합산 (250+100)/500 = 0.70 ≤ 0.80.",
    ),
    (
        "r2-ratio-fail-standalone",
        "근저당 단독 64%. 보증금을 낮춰 R2-b가 아닌 단독 기준으로 fail시킨다.",
        {"deposit_krw": 50_000_000, "mortgage_total_krw": 320_000_000, "mortgage_items": [{"amount_krw": 320_000_000, "shared_property_count": 1}]},
        "risk",
        {"mortgage_ratio": "fail"},
        "320/500 = 0.64 > 0.60 → fail(30) → 위험(30~59). 합산은 (320+50)/500 = 0.74로 0.80 이하라 R2-b는 미발동. R1도 50/500 = 0.10으로 pass.",
    ),
    (
        "r2b-combined-only",
        "근저당 단독으로는 pass인데 보증금 합산으로 fail. R2-b가 존재하는 이유.",
        {"deposit_krw": 205_000_000, "mortgage_total_krw": 200_000_000, "mortgage_items": [{"amount_krw": 200_000_000, "shared_property_count": 1}]},
        "risk",
        {"mortgage_ratio": "fail"},
        "근저당 단독 200/500 = 0.40으로 pass 구간. 그러나 합산 (200+205)/500 = 0.81 > 0.80 → fail(30). R1은 205/500 = 0.41로 pass. R2-b가 없으면 0점으로 통과했을 입력.",
    ),
    (
        "r2-shared-collateral-allocation",
        "공동담보 4건에 걸린 근저당. 민법 368① 비례배분 후 판정해야 한다.",
        {"mortgage_total_krw": 600_000_000, "mortgage_items": [{"amount_krw": 600_000_000, "shared_property_count": 4}]},
        "safe",
        {},
        "원문 600M을 4건으로 배분하면 150M. 150/500 = 0.30 → pass. 배분하지 않으면 600/500 = 1.20으로 fail이 되어 건물 전체 부채가 호실 하나에 잘못 걸린다.",
    ),
    (
        "r2-general-building-unknown",
        "일반건물은 호실 시세가 없어 R2를 판정하지 않는다.",
        GENERAL,
        "safe",
        GENERAL_CHECKS,
        "명세 R2는 집합건물 전제. 일반건물은 분모(호실 시세)를 구할 수 없어 unknown. R8도 선순위 보증금 미입력이라 unknown.",
    ),
    (
        "r2-registry-type-unknown",
        "등기부 미제출. 등기 기반 규칙이 전부 unknown으로 빠진다.",
        {"registry_type": "unknown"},
        "safe",
        {"mortgage_ratio": "unknown", "rights_encumbrance": "unknown", "senior_deposit": "unknown"},
        "명세 §2 원칙: 모르면 unknown, 점수 0. R2·R4·R8이 등기부를 요구하므로 셋 다 unknown이 되고 총점 0이 된다.",
    ),
    # ── R3 소유자 일치 ──────────────────────────────────────────────────
    (
        "r3-owner-mismatch",
        "계약서 임대인이 등기부 소유자와 다름. 오버라이드 대상.",
        {"contract_owner_name": "소유자B"},
        "high_risk",
        {"owner_mismatch": "fail"},
        "명세 R3: 불일치 → fail(15). §4-5 오버라이드 2항에 해당해 점수와 무관하게 고위험.",
    ),
    (
        "r3-contract-name-missing",
        "계약서 임대인명 미입력. 한쪽이 없으면 대조 불가.",
        {"contract_owner_name": ""},
        "safe",
        {"owner_mismatch": "unknown"},
        "명세 R3: 어느 한쪽 없음 → unknown. 점수 미가산.",
    ),
    (
        "r3-joint-owner-partial",
        "공동소유 2인 중 1인만 계약 당사자.",
        {"registry_owner_name": "소유자A 소유자B", "contract_owner_name": "소유자A"},
        "high_risk",
        {"owner_mismatch": "fail"},
        "명세 R3 공동소유 항: 전원이 포함되어야 pass, 일부만이면 fail. 오버라이드 발동.",
    ),
    (
        "r3-joint-owner-complete",
        "공동소유 2인 전원이 계약 당사자.",
        {"registry_owner_name": "소유자A 소유자B", "contract_owner_name": "소유자A 소유자B"},
        "safe",
        {},
        "명세 R3 공동소유 항: 전원 포함 → pass.",
    ),
    # ── R4 권리침해 ─────────────────────────────────────────────────────
    (
        "r4-active-attachment",
        "말소되지 않은 가압류.",
        {"critical_terms": [{"term": "가압류", "is_cancelled": False}]},
        "high_risk",
        {"rights_encumbrance": "fail"},
        "명세 R4: 말소되지 않은 항목이 하나라도 있으면 fail(30) + 오버라이드 1항 → 고위험.",
    ),
    (
        "r4-cancelled-term-ignored",
        "말소된 가압류는 무시한다.",
        {"critical_terms": [{"term": "가압류", "is_cancelled": True}]},
        "safe",
        {},
        "명세 R4는 '말소되지 않은' 항목만 대상. 말소 확인된 건은 pass.",
    ),
    (
        "r4-cancellation-unknown-is-active",
        "말소 여부 불명. 보수적으로 유효한 것으로 본다.",
        {"critical_terms": [{"term": "압류", "is_cancelled": None}]},
        "high_risk",
        {"rights_encumbrance": "fail"},
        "명세 §2 원칙(모르면 안전 쪽으로 넘기지 않는다)에 따라 말소 불명은 유효로 간주 → fail + 오버라이드.",
    ),
    (
        "r4-trust-registration",
        "신탁등기. R3가 pass여도 처분 권한이 수탁자에게 있다.",
        {"critical_terms": [{"term": "신탁", "is_cancelled": False}]},
        "high_risk",
        {"rights_encumbrance": "fail"},
        "명세 R4 신탁 특칙: 신탁이 유효하면 등기부상 소유자와 계약해도 무효가 될 수 있어 R3와 무관하게 fail + 오버라이드.",
    ),
    # ── R5 건축물 용도 ──────────────────────────────────────────────────
    (
        "r5-non-residential",
        "근린생활시설 사무소. 주거 키워드 없음.",
        {"building_type": "제2종근린생활시설", "detail_use": "사무소"},
        "caution",
        {"residential_use": "fail"},
        "명세 R5: 주거 키워드 미포함 → fail(15) → 주의(15~29). 근생빌라 유형.",
    ),
    (
        "r5-use-info-missing",
        "건축물 용도 정보 없음.",
        {"building_type": "", "detail_use": ""},
        "safe",
        {"residential_use": "unknown"},
        "명세 R5: 정보 없음 → unknown.",
    ),
    (
        "r5-business-officetel-known-defect",
        "업무용 오피스텔. 명세가 '알려진 결함'으로 지목한 입력.",
        {"building_type": "업무시설", "detail_use": "업무용 오피스텔"},
        "caution",
        {"residential_use": "fail"},
        "명세 R5 '알려진 결함' 항: 키워드 목록에 `오피스텔`이 있어 업무용 오피스텔이 pass로 빠진다. `업무` 포함 시 제외하는 예외가 필요하다고 명시돼 있으므로, 의도된 판정은 fail(15) → 주의. 현재 구현은 pass를 반환할 것으로 예상되며 그 차이를 잡기 위한 케이스다.",
    ),
    # ── R6 위반건축물 ───────────────────────────────────────────────────
    (
        "r6-violation-present",
        "건축물대장 위반건축물 표시 있음.",
        {"illegal_building_status": "present"},
        "caution",
        {"illegal_building": "fail"},
        "명세 R6: 위반 표시 존재 → fail(15) → 주의. 보증보험 가입 거절 사유.",
    ),
    (
        "r6-status-unclear",
        "건축물대장 미확인.",
        {"illegal_building_status": "unclear"},
        "safe",
        {"illegal_building": "unknown"},
        "명세 §2 원칙: 확인 못 한 항목을 pass로 넘기지 않고 unknown으로 남긴다.",
    ),
    # ── R7 전세 거래 집중도 (일반건물 전용) ──────────────────────────────
    (
        "r7-concentration-warn",
        "일반건물, 12개월 신규 전세 3건 / 10세대 = 30%. 임계 동시 충족.",
        {**GENERAL, "households": 10, "recent_jeonse_count": 5, "recent_jeonse_peak_12m_count": 3, "recent_jeonse_data_status": "complete"},
        "safe",
        {**GENERAL_CHECKS, "duplicate_contract": "warn"},
        "명세 R7: `peak >= 3` 이고 `비율 >= 30%`면 warn. 25 // 2 = 12점. 등급 구간 0~14가 안전이라 R7 단독 warn은 안전을 벗어나지 못한다.",
    ),
    (
        "r7-below-count-threshold",
        "비율은 넘지만 건수가 2건이라 미달.",
        {**GENERAL, "households": 5, "recent_jeonse_count": 2, "recent_jeonse_peak_12m_count": 2, "recent_jeonse_data_status": "complete"},
        "safe",
        {**GENERAL_CHECKS, "duplicate_contract": "pass"},
        "명세 R7은 건수와 비율을 모두 만족해야 warn. 2/5 = 40%로 비율은 넘지만 3건 미만이라 pass.",
    ),
    (
        "r7-aggregate-building-not-scored",
        "집합건물은 거래 집중도를 점수에 반영하지 않는다.",
        {"households": 10, "recent_jeonse_count": 8, "recent_jeonse_peak_12m_count": 5, "recent_jeonse_data_status": "complete"},
        "safe",
        {},
        "명세 R7: 집합건물은 호실별 소유자가 달라 건물 전체 거래량을 점수에 반영하지 않고 참고 정보로만 제공 → unknown.",
    ),
    # ── R8 선순위 보증금 (일반건물 전용) ─────────────────────────────────
    (
        "r8-senior-deposit-fail",
        "다가구 선순위 보증금 합산 83%.",
        {**GENERAL, "deposit_krw": 100_000_000, "market_price_krw": 600_000_000, "mortgage_total_krw": 100_000_000, "senior_deposit_krw": 300_000_000},
        "caution",
        {**GENERAL_CHECKS, "senior_deposit": "fail"},
        "명세 R8: (300+100+100)/600 = 0.833 > 0.80 → fail(25) → 주의(15~29). R1은 100/600 = 0.167로 pass.",
    ),
    (
        "r8-senior-deposit-pass",
        "같은 구조에서 선순위 보증금만 낮춰 안전 구간.",
        {**GENERAL, "deposit_krw": 100_000_000, "market_price_krw": 600_000_000, "mortgage_total_krw": 100_000_000, "senior_deposit_krw": 200_000_000},
        "safe",
        {**GENERAL_CHECKS, "senior_deposit": "pass"},
        "(200+100+100)/600 = 0.667 ≤ 0.80 → pass.",
    ),
    (
        "r8-senior-deposit-unknown",
        "다가구인데 선순위 보증금을 확인하지 못함.",
        {**GENERAL, "senior_deposit_krw": None},
        "safe",
        GENERAL_CHECKS,
        "명세 R8: 선순위 보증금 미확보 → unknown. 다가구에서 가장 위험한 항목이 점수 0으로 빠지는 구조적 한계를 드러내는 케이스.",
    ),
]


def build(case_id, description, overrides, grade, check_deltas, rationale) -> dict:
    return {
        "case_id": case_id,
        "description": description,
        "label_source": "synthetic_boundary",
        "expected": {
            "grade": grade,
            "rationale": rationale,
            "checks": {**BASE_CHECKS, **check_deltas},
        },
        "payload": {**BASELINE, **overrides, "listing_name": f"[합성] {description}"},
        "notes": "정답은 docs/전세사기위험도판별핵심로직.md의 판정 규칙과 배점표에서 손으로 도출했다. 엔진 출력이 아니다.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for row in CASES:
        case = build(*row)
        path = OUT_DIR / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(CASES)}건 생성 → {OUT_DIR}")


if __name__ == "__main__":
    main()
