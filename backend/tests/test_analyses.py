import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import rate_limit
from backend.app.db import engine, get_db
from backend.app.main import app
from backend.app.models import Analysis

RISK_PAYLOAD = {
    "listing_name": "테스트빌라 101호",
    "deposit_krw": 200_000_000,
    "market_price_krw": 300_000_000,
    "registry_type": "aggregate_building",
    "mortgage_total_krw": 0,
    "mortgage_items": [],
    "registry_owner_name": "홍길동",
    "contract_owner_name": "홍길동",
    "critical_terms": [],
    "building_type": "공동주택",
    "detail_use": "다세대주택",
    "illegal_building_status": "absent",
    "recent_jeonse_count": 0,
    "recent_jeonse_peak_12m_count": 0,
    "households": 8,
    "recent_jeonse_data_status": "complete",
    "senior_deposit_krw": None,
}


class AnalysesTest(unittest.TestCase):
    """test_auth와 같은 방식으로 바깥 트랜잭션을 롤백해 DB를 원상복구한다."""

    EMAIL = "analyses.user@example.com"
    PASSWORD = "password123"

    def setUp(self):
        rate_limit.reset()
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: self.db
        # 실제 LLM 호출을 막는다. 저장 경로만 검증한다.
        self.llm = patch("backend.app.main._generate_risk_assessment_explanation", return_value="설명")
        self.llm.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.llm.stop()
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def token(self, email=None):
        email = email or self.EMAIL
        self.client.post(
            "/auth/signup", json={"email": email, "password": self.PASSWORD, "name": "홍길동"}
        )
        response = self.client.post("/auth/login", json={"email": email, "password": self.PASSWORD})
        return response.json()["token"]

    def assess(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/risk/assess", json=RISK_PAYLOAD, headers=headers)

    def test_logged_in_assessment_is_linked_to_user(self):
        token = self.token()
        response = self.assess(token)
        self.assertEqual(response.status_code, 200)
        analysis_id = response.json()["analysis_id"]

        row = self.db.get(Analysis, analysis_id)
        self.assertIsNotNone(row.user_id)
        self.assertEqual(row.listing_name, RISK_PAYLOAD["listing_name"])
        self.assertEqual(row.risk_grade, response.json()["risk_grade"])
        self.assertEqual(row.result["analysis_id"], analysis_id)

        listed = self.client.get("/analyses", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual([item["analysis_id"] for item in listed.json()], [analysis_id])

        detail = self.client.get(
            f"/analyses/{analysis_id}", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["request"]["deposit_krw"], RISK_PAYLOAD["deposit_krw"])

    def test_anonymous_assessment_is_saved_without_user(self):
        response = self.assess()
        self.assertEqual(response.status_code, 200)

        row = self.db.get(Analysis, response.json()["analysis_id"])
        self.assertIsNone(row.user_id)

    def test_invalid_token_falls_back_to_anonymous(self):
        response = self.assess("not-a-real-token")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.get(Analysis, response.json()["analysis_id"]).user_id)

    def test_other_users_record_is_not_readable(self):
        mine = self.assess(self.token()).json()["analysis_id"]
        other = self.token("other.user@example.com")

        self.assertEqual(self.client.get("/analyses", headers={"Authorization": f"Bearer {other}"}).json(), [])
        detail = self.client.get(f"/analyses/{mine}", headers={"Authorization": f"Bearer {other}"})
        self.assertEqual(detail.status_code, 404)

    def test_listing_requires_login(self):
        self.assertEqual(self.client.get("/analyses").status_code, 401)

    def test_chatbot_reads_stored_analysis(self):
        analysis_id = self.assess().json()["analysis_id"]
        from backend.app.chatbot import _format_analysis_context
        from backend.app.main import _chat_analysis_context

        context = _chat_analysis_context(self.db.get(Analysis, analysis_id))
        self.assertEqual(context.analysis_id, analysis_id)
        self.assertEqual(context.explanation, "설명")
        self.assertTrue(context.risk_factors)

        # 챗봇 프롬프트까지 실제로 이어지는지 확인한다.
        prompt = _format_analysis_context(context)
        self.assertIn(analysis_id, prompt)
        self.assertIn("설명", prompt)


if __name__ == "__main__":
    unittest.main()
