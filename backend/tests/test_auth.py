import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import rate_limit
from backend.app.db import engine, get_db
from backend.app.main import app
from backend.app.models import User, UserSession


class AuthTest(unittest.TestCase):
    """DB를 건드리는 테스트라, 바깥 트랜잭션을 롤백해서 원상태로 되돌린다.

    join_transaction_mode="create_savepoint"가 있어야 앱 코드의 commit()이
    세이브포인트만 커밋하고 바깥 트랜잭션은 열린 채로 남는다.
    """

    EMAIL = "test.user@example.com"
    PASSWORD = "password123"

    def setUp(self):
        # 시도 횟수는 프로세스 전역이라 테스트 간에 새어 나간다.
        rate_limit.reset()
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def signup(self, **overrides):
        payload = {"email": self.EMAIL, "password": self.PASSWORD, "name": "홍길동"}
        payload.update(overrides)
        return self.client.post("/auth/signup", json=payload)

    def login(self, **overrides):
        payload = {"email": self.EMAIL, "password": self.PASSWORD}
        payload.update(overrides)
        return self.client.post("/auth/login", json=payload)

    def test_signup_login_me(self):
        self.assertEqual(self.signup().status_code, 201)

        response = self.login()
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], self.EMAIL)
        self.assertEqual(me.json()["name"], "홍길동")

    def test_duplicate_email_differing_only_in_case(self):
        self.assertEqual(self.signup().status_code, 201)
        self.assertEqual(self.signup(email=self.EMAIL.upper()).status_code, 409)

    def test_wrong_password_and_unknown_email_are_indistinguishable(self):
        self.signup()

        wrong = self.login(password="wrong-password-123")
        unknown = self.login(email="nobody@example.com")

        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json()["detail"], unknown.json()["detail"])

    def test_password_is_stored_as_argon2id_hash(self):
        self.signup()

        user = self.db.scalar(select(User).where(User.email == self.EMAIL))
        self.assertNotEqual(user.password_hash, self.PASSWORD)
        self.assertNotIn(self.PASSWORD, user.password_hash)
        self.assertTrue(user.password_hash.startswith("$argon2id$"))

    def test_session_token_is_stored_as_hash(self):
        self.signup()
        token = self.login().json()["token"]

        session = self.db.scalars(select(UserSession)).one()
        self.assertNotEqual(session.token_hash, token)
        self.assertEqual(len(session.token_hash), 64)

    def test_logout_invalidates_the_token(self):
        self.signup()
        token = self.login().json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        self.assertEqual(self.client.post("/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)

    def test_expired_session_is_rejected(self):
        self.signup()
        token = self.login().json()["token"]

        session = self.db.scalars(select(UserSession)).one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.db.commit()

        response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 401)

    def test_missing_token_is_rejected(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_short_password_is_rejected(self):
        self.assertEqual(self.signup(password="1234567").status_code, 422)

    def test_repeated_failures_lock_the_account(self):
        self.signup()

        for _ in range(rate_limit.EMAIL_MAX):
            self.assertEqual(self.login(password="wrong-password-123").status_code, 401)

        blocked = self.login(password="wrong-password-123")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

        # 차단은 비밀번호가 맞아도 유지된다.
        self.assertEqual(self.login().status_code, 429)

    def test_successful_login_clears_the_failure_count(self):
        self.signup()

        for _ in range(rate_limit.EMAIL_MAX - 1):
            self.assertEqual(self.login(password="wrong-password-123").status_code, 401)
        self.assertEqual(self.login().status_code, 200)

        # 초기화되지 않았다면 여기서 429가 나온다.
        self.assertEqual(self.login(password="wrong-password-123").status_code, 401)

    def test_ip_limit_blocks_before_hashing(self):
        # 이메일을 매번 바꿔 계정 잠금이 아니라 IP 한도에 걸리게 한다.
        for i in range(rate_limit.IP_MAX):
            self.assertEqual(self.login(email=f"nobody{i}@example.com").status_code, 401)

        self.assertEqual(self.login(email="nobody-last@example.com").status_code, 429)
        # 가입도 같은 한도를 공유한다.
        self.assertEqual(self.signup().status_code, 429)


if __name__ == "__main__":
    unittest.main()
