from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from bookings.models import Booking
from centres.models import DiagnosticCentre
from common.testing import BaseAPITestCase


class BookingTests(BaseAPITestCase):
    def test_create_booking_uses_server_side_price(self):
        booking = self.create_booking(amount="1.00")  # client-supplied amount is ignored
        self.assertEqual(booking["status"], "PENDING")
        self.assertEqual(booking["amount"], "499.00")
        self.assertEqual(booking["centre"]["id"], self.centre.id)
        self.assertEqual(booking["test"]["code"], "CBC")

    def test_price_change_does_not_affect_existing_booking(self):
        booking = self.create_booking()
        self.offering.price = Decimal("999.00")
        self.offering.save()
        self.assertEqual(self.client.get(f"/bookings/{booking['id']}/").data["amount"], "499.00")

    def test_requires_authentication(self):
        response = self.client.post("/bookings/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_validation_errors(self):
        self.login(self.user)
        other_centre = DiagnosticCentre.objects.create(name="Empty Lab", address="x", city="Pune")
        base = {"centre_id": self.centre.id, "test_id": self.test_cbc.id, "appointment_at": self.future().isoformat()}
        cases = {
            "past time": {**base, "appointment_at": (timezone.now() - timedelta(hours=1)).isoformat()},
            "too far ahead": {**base, "appointment_at": self.future(days=365).isoformat()},
            "bad date": {**base, "appointment_at": "tomorrow"},
            "missing centre": {"test_id": self.test_cbc.id, "appointment_at": base["appointment_at"]},
            "unknown centre": {**base, "centre_id": 99999},
            "test not offered": {**base, "centre_id": other_centre.id},
            "non-int id": {**base, "test_id": "abc"},
        }
        for name, payload in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.post("/bookings/", payload, format="json").status_code, 400)

    def test_duplicate_booking_same_slot_conflicts(self):
        slot = self.future().isoformat()
        self.create_booking(appointment_at=slot)
        response = self.client.post(
            "/bookings/",
            {"centre_id": self.centre.id, "test_id": self.test_cbc.id, "appointment_at": slot},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_users_only_see_their_own_bookings(self):
        booking = self.create_booking(user=self.user)
        self.login(self.other)
        self.assertEqual(self.client.get("/bookings/").data["count"], 0)
        self.assertEqual(self.client.get(f"/bookings/{booking['id']}/").status_code, 404)
        self.assertEqual(self.client.post(f"/bookings/{booking['id']}/cancel/").status_code, 404)
        self.login(self.admin)
        self.assertEqual(self.client.get(f"/bookings/{booking['id']}/").status_code, 200)

    def test_invalid_booking_ids_return_404(self):
        self.login(self.user)
        self.assertEqual(self.client.get("/bookings/not-a-uuid/").status_code, 404)
        self.assertEqual(self.client.get("/bookings/00000000-0000-0000-0000-000000000000/").status_code, 404)
        self.assertEqual(self.client.post("/bookings/not-a-uuid/cancel/").status_code, 404)

    def test_bookings_cannot_be_edited_or_deleted(self):
        booking = self.create_booking()
        url = f"/bookings/{booking['id']}/"
        self.assertEqual(self.client.patch(url, {"status": "CONFIRMED"}, format="json").status_code, 405)
        self.assertEqual(self.client.put(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(Booking.objects.get(pk=booking["id"]).status, "PENDING")

    def test_cancel(self):
        booking = self.create_booking()
        response = self.client.post(f"/bookings/{booking['id']}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(self.client.post(f"/bookings/{booking['id']}/cancel/").status_code, 409)

    def test_status_filter(self):
        self.create_booking()
        self.assertEqual(self.client.get("/bookings/?status=pending").data["count"], 1)
        self.assertEqual(self.client.get("/bookings/?status=CONFIRMED").data["count"], 0)
        self.assertEqual(self.client.get("/bookings/?status=bogus").status_code, 400)
