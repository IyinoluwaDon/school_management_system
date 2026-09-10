from django.test import TestCase

from .models import User


class JWTAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="principal1", password="strong-password", role="PRINCIPAL",
            first_name="Ama", last_name="Okafor",
        )

    def test_token_obtain_returns_access_refresh_and_user_payload(self):
        response = self.client.post(
            "/api/token/", {"username": "principal1", "password": "strong-password"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["role"], "PRINCIPAL")
        self.assertEqual(data["user"]["full_name"], "Ama Okafor")
        self.assertTrue(data["user"]["digital_token"].startswith("SCH-"))

    def test_token_obtain_rejects_bad_credentials(self):
        response = self.client.post(
            "/api/token/", {"username": "principal1", "password": "wrong-password"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_current_user_requires_a_valid_bearer_token(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

        login = self.client.post(
            "/api/token/", {"username": "principal1", "password": "strong-password"},
            content_type="application/json",
        ).json()
        response = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {login['access']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "principal1")

    def test_token_refresh_issues_a_new_access_token(self):
        login = self.client.post(
            "/api/token/", {"username": "principal1", "password": "strong-password"},
            content_type="application/json",
        ).json()
        response = self.client.post(
            "/api/token/refresh/", {"refresh": login["refresh"]}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
