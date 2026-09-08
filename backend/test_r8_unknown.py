import unittest

from backend.app.main import _run_senior_deposit_check


class SeniorDepositCheckTest(unittest.TestCase):
    def test_unknown_is_distinct_from_confirmed_zero(self):
        unknown = _run_senior_deposit_check(None, 0, 10_000, 100_000, "general_building")
        confirmed_zero = _run_senior_deposit_check(0, 0, 10_000, 100_000, "general_building")

        self.assertEqual(unknown.status, "unknown")
        self.assertEqual(confirmed_zero.status, "pass")


if __name__ == "__main__":
    unittest.main()
