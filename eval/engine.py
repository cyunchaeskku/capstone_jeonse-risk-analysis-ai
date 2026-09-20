"""규칙 엔진 호출부. LLM·HTTP 없이 판정부만 돌린다.

`/risk/assess` 엔드포인트는 설명 생성을 위해 LLM을 부르지만 판정에는 관여하지 않는다.
평가는 판정만 필요하므로 규칙 함수를 직접 호출한다.
"""

from backend.app.main import (
    _collect_override_reasons,
    _compute_risk_score,
    _grade_with_burden_floor,
    _run_deposit_to_market_check,
    _run_illegal_building_check,
    _run_jeonse_concentration_check,
    _run_mortgage_ratio_check,
    _run_owner_mismatch_check,
    _run_residential_use_check,
    _run_rights_encumbrance_check,
    _run_senior_deposit_check,
)
from backend.app.schemas import ListingCheckResult, RiskAssessRequest


def run_checks(payload: RiskAssessRequest) -> list[ListingCheckResult]:
    return [
        _run_deposit_to_market_check(
            payload.deposit_krw, payload.market_price_krw, payload.registry_type
        ),
        _run_mortgage_ratio_check(
            payload.mortgage_items,
            payload.deposit_krw,
            payload.market_price_krw,
            payload.registry_type,
        ),
        _run_owner_mismatch_check(payload.contract_owner_name, payload.registry_owner_name),
        _run_rights_encumbrance_check(payload.critical_terms, payload.registry_type),
        _run_residential_use_check(
            {"building_type": payload.building_type, "detail_use": payload.detail_use}
        ),
        _run_illegal_building_check(payload.illegal_building_status),
        _run_jeonse_concentration_check(
            payload.recent_jeonse_count,
            payload.recent_jeonse_peak_12m_count,
            payload.households,
            payload.recent_jeonse_data_status,
            payload.registry_type,
        ),
        _run_senior_deposit_check(
            payload.senior_deposit_krw,
            payload.mortgage_total_krw,
            payload.deposit_krw,
            payload.market_price_krw,
            payload.registry_type,
        ),
    ]


def assess(payload: RiskAssessRequest) -> dict:
    checks = run_checks(payload)
    score = _compute_risk_score(checks)
    score_grade = _grade_with_burden_floor(score, checks)
    overrides = _collect_override_reasons(checks, payload)
    return {
        "checks": {c.code: c.status for c in checks},
        "reasons": {c.code: c.reason for c in checks},
        "score": score,
        "score_grade": score_grade,
        "overrides": overrides,
        "grade": "high_risk" if overrides else score_grade,
    }
