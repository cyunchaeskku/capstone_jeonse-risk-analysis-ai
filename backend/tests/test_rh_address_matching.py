import asyncio
import unittest

import httpx

from backend.app.main import _extract_dong_and_jibun, _fetch_month, _is_matching_rh_address, _previous_12m_period


class RhAddressMatchingTest(unittest.TestCase):
    def test_matches_only_same_dong_and_jibun(self):
        dong, jibun = _extract_dong_and_jibun("서울특별시 구로구 고척동 76-32")

        self.assertTrue(_is_matching_rh_address(dong, jibun, "고척동", "76-32"))
        self.assertFalse(_is_matching_rh_address(dong, jibun, "고척동", "76-31"))
        self.assertFalse(_is_matching_rh_address(dong, jibun, "개봉동", "76-32"))

    def test_previous_period_is_the_prior_twelve_months(self):
        self.assertEqual(_previous_12m_period("202509"), ("202409", "202508"))
        self.assertEqual(_previous_12m_period("201709"), ("201609", "201708"))

    def test_debug_raw_transactions_only_include_selected_dong(self):
        class Response:
            status_code = 200
            text = """<response><header><resultCode>000</resultCode></header><body><items>
                <item><umdNm>고척동</umdNm><jibun>76-32</jibun><mhouseNm>대상</mhouseNm></item>
                <item><umdNm>개봉동</umdNm><jibun>76-32</jibun><mhouseNm>다른 건물</mhouseNm></item>
            </items></body></response>"""

        class Client:
            async def get(self, *args, **kwargs):
                return Response()

        diagnostics = {"raw_transactions": []}
        asyncio.run(_fetch_month(Client(), "service", "method", "mhouseNm", "excluUseAr", "11530", "202608", "", "", diagnostics=diagnostics, debug_dong="고척동"))

        self.assertEqual(len(diagnostics["raw_transactions"]), 1)
        self.assertEqual(diagnostics["raw_transactions"][0]["item"]["umdNm"], "고척동")

    def test_request_timeout_is_recorded_without_raising(self):
        class Client:
            async def get(self, *args, **kwargs):
                raise httpx.ReadTimeout("timed out")

        diagnostics = {"errors": []}
        result = asyncio.run(_fetch_month(Client(), "service", "method", "mhouseNm", "excluUseAr", "11530", "202608", "", "", diagnostics=diagnostics))

        self.assertEqual(result, [])
        self.assertEqual(diagnostics["request_error_count"], 1)
        self.assertEqual(diagnostics["errors"][0]["error_type"], "ReadTimeout")


if __name__ == "__main__":
    unittest.main()
