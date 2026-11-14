"""Smoke tests proving the site boots and core routes respond."""

from django.test import TestCase


class HomeViewTests(TestCase):
    def test_home_page_returns_200(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_home_page_renders_site_name(self) -> None:
        response = self.client.get("/")
        self.assertContains(response, "OSS Economic Calendar")

    def test_admin_login_reachable(self) -> None:
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
