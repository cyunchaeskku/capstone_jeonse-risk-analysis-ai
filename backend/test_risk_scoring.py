import unittest

from backend.app.main import (
    _build_score_breakdown,
    _compute_risk_score,
    _grade_with_burden_floor,
    _risk_grade,
)
from backend.app.schemas import ListingCheckResult


def _check(code: str, status: str) -> ListingCheckResult:
    return ListingCheckResult(code=code, title=code, status=status, reason="test")


class RiskScoringTest(unittest.TestCase):
    def test_warn_and_fail_contributions_are_exposed(self):
        checks = [
            _check("mortgage_ratio", "warn"),
            _check("owner_mismatch", "fail"),
            _check("senior_deposit", "unknown"),
        ]

        breakdown = {item["code"]: item for item in _build_score_breakdown(checks)}

        self.assertEqual(_compute_risk_score(checks), 30)
        self.assertEqual(_risk_grade(30), "risk")
        self.assertEqual(breakdown["mortgage_ratio"], {"code": "mortgage_ratio", "max_points": 30, "added_points": 15})
        self.assertEqual(breakdown["owner_mismatch"], {"code": "owner_mismatch", "max_points": 15, "added_points": 15})
        self.assertEqual(breakdown["senior_deposit"], {"code": "senior_deposit", "max_points": 30, "added_points": 0})

    def test_score_is_capped_at_100(self):
        checks = [
            _check("mortgage_ratio", "fail"),
            _check("rights_encumbrance", "fail"),
            _check("duplicate_contract", "fail"),
            _check("senior_deposit", "fail"),
        ]

        self.assertEqual(_compute_risk_score(checks), 100)

    def test_burden_floor_lifts_grade_without_inventing_points(self):
        # §0-2. 담보 여력 3종이 전부 unknown이면 safe로 표기하지 않는다.
        checks = [
            _check("deposit_to_market_ratio", "unknown"),
            _check("mortgage_ratio", "unknown"),
            _check("senior_deposit", "unknown"),
        ]

        score = _compute_risk_score(checks)

        self.assertEqual(score, 0)
        self.assertEqual(_risk_grade(score), "safe")
        self.assertEqual(_grade_with_burden_floor(score, checks), "caution")
        # 바닥은 점수를 건드리지 않는다 → 내역 합계와 총점이 어긋나지 않는다
        self.assertEqual(sum(item["added_points"] for item in _build_score_breakdown(checks)), score)

    def test_burden_floor_skipped_when_any_burden_rule_judged(self):
        checks = [
            _check("deposit_to_market_ratio", "pass"),
            _check("mortgage_ratio", "unknown"),
            _check("senior_deposit", "unknown"),
        ]

        self.assertEqual(_grade_with_burden_floor(_compute_risk_score(checks), checks), "safe")


if __name__ == "__main__":
    unittest.main()
