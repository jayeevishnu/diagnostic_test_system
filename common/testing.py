from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from centres.models import CentreTest, DiagnosticCentre, DiagnosticTest

User = get_user_model()


class BaseAPITestCase(APITestCase):
    """Shared fixtures: two users, an admin, a centre offering one test."""

    def setUp(self):
        cache.clear()  # reset throttling counters between tests
        self.user = User.objects.create_user("alice@example.com", "Str0ng!Pass")
        self.other = User.objects.create_user("bob@example.com", "Str0ng!Pass")
        self.admin = User.objects.create_superuser("admin@example.com", "Str0ng!Pass")

        self.test_cbc = DiagnosticTest.objects.create(code="CBC", name="Complete Blood Count")
        self.centre = DiagnosticCentre.objects.create(name="Lab One", address="1 Main St", city="Pune")
        self.offering = CentreTest.objects.create(centre=self.centre, test=self.test_cbc, price=Decimal("499.00"))

    def future(self, days=2):
        return (timezone.now() + timedelta(days=days)).replace(microsecond=0)

    def login(self, user):
        self.client.force_authenticate(user)

    def create_booking(self, user=None, **overrides):
        self.login(user or self.user)
        payload = {"centre_id": self.centre.id, "test_id": self.test_cbc.id, "appointment_at": self.future().isoformat()}
        payload.update(overrides)
        response = self.client.post("/bookings/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data
