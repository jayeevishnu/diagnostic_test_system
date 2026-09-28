from common.testing import BaseAPITestCase


class AuthTests(BaseAPITestCase):
    def test_signup_returns_user_and_tokens(self):
        response = self.client.post(
            "/auth/signup/",
            {"email": "New.User@Example.com", "password": "Sup3r!Secret", "first_name": "New"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["user"]["email"], "new.user@example.com")
        self.assertIn("access", response.data["tokens"])
        self.assertNotIn("password", response.data["user"])

    def test_signup_without_name(self):
        response = self.client.post(
            "/auth/signup/", {"email": "noname@example.com", "password": "Sup3r!Secret"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["user"]["first_name"], "")

    def test_signup_validation(self):
        cases = [
            {"email": "not-an-email", "password": "Sup3r!Secret", "first_name": "X"},
            {"email": "x@example.com", "password": "123", "first_name": "X"},       # weak password
            {"email": "ALICE@example.com", "password": "Sup3r!Secret", "first_name": "A"},  # duplicate
            {"password": "Sup3r!Secret"},                                           # missing email
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/auth/signup/", payload, format="json")
                self.assertEqual(response.status_code, 400)

    def test_login_and_use_jwt(self):
        response = self.client.post(
            "/auth/login/", {"email": "Alice@Example.com", "password": "Str0ng!Pass"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        token = response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        me = self.client.get("/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "alice@example.com")

    def test_login_wrong_password(self):
        response = self.client.post("/auth/login/", {"email": "alice@example.com", "password": "nope"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_protected_endpoint_requires_token(self):
        self.assertEqual(self.client.get("/auth/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertEqual(self.client.get("/bookings/").status_code, 401)
