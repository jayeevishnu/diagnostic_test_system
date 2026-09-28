import json
from unittest import mock

from bookings.models import Booking
from common.testing import BaseAPITestCase
from payments.models import Payment, WebhookEvent
from payments.signing import sign


class PaymentTests(BaseAPITestCase):
    def pay(self, booking_id, outcome=None, key=None):
        data = {"booking_id": booking_id}
        if outcome:
            data["simulate_outcome"] = outcome
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return self.client.post("/payments/", data, format="json", **headers)

    def test_successful_payment_confirms_booking(self):
        booking = self.create_booking()
        response = self.pay(booking["id"], "SUCCESS")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "SUCCESS")
        self.assertEqual(response.data["amount"], "499.00")
        self.assertEqual(response.data["booking_status"], "CONFIRMED")

    def test_failed_payment_marks_booking_failed_and_can_be_retried(self):
        booking = self.create_booking()
        failed = self.pay(booking["id"], "FAILED")
        self.assertEqual(failed.data["status"], "FAILED")
        self.assertEqual(failed.data["booking_status"], "FAILED")
        self.assertTrue(failed.data["failure_reason"])

        retry = self.pay(booking["id"], "SUCCESS")
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(retry.data["booking_status"], "CONFIRMED")
        self.assertEqual(Payment.objects.filter(booking_id=booking["id"]).count(), 2)

    def test_random_outcome_when_not_forced(self):
        booking = self.create_booking()
        with mock.patch("payments.gateway.random.random", return_value=0.99):
            self.assertEqual(self.pay(booking["id"]).data["status"], "FAILED")

    def test_cannot_pay_twice(self):
        booking = self.create_booking()
        self.pay(booking["id"], "SUCCESS")
        self.assertEqual(self.pay(booking["id"], "SUCCESS").status_code, 409)
        self.assertEqual(Payment.objects.filter(booking_id=booking["id"]).count(), 1)

    def test_cannot_start_second_payment_while_one_pending(self):
        booking = self.create_booking()
        self.assertEqual(self.pay(booking["id"], "PENDING").status_code, 201)
        self.assertEqual(self.pay(booking["id"], "SUCCESS").status_code, 409)

    def test_idempotency_key_replays_original_payment(self):
        booking = self.create_booking()
        first = self.pay(booking["id"], "FAILED", key="abc-123")
        replay = self.pay(booking["id"], "SUCCESS", key="abc-123")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(replay.data["status"], "FAILED")
        self.assertEqual(Payment.objects.count(), 1)

    def test_cannot_pay_cancelled_booking(self):
        booking = self.create_booking()
        self.client.post(f"/bookings/{booking['id']}/cancel/")
        self.assertEqual(self.pay(booking["id"], "SUCCESS").status_code, 409)

    def test_cannot_pay_someone_elses_booking(self):
        booking = self.create_booking(user=self.user)
        self.login(self.other)
        self.assertEqual(self.pay(booking["id"], "SUCCESS").status_code, 404)
        self.assertEqual(Booking.objects.get(pk=booking["id"]).status, "PENDING")

    def test_invalid_payment_requests(self):
        self.login(self.user)
        self.assertEqual(self.pay("not-a-uuid").status_code, 400)
        self.assertEqual(self.pay("00000000-0000-0000-0000-000000000000").status_code, 404)
        booking = self.create_booking()
        self.assertEqual(self.pay(booking["id"], "MAYBE").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.pay(booking["id"]).status_code, 401)

    def test_users_only_see_their_own_payments(self):
        booking = self.create_booking()
        payment_id = self.pay(booking["id"], "SUCCESS").data["id"]
        self.login(self.other)
        self.assertEqual(self.client.get("/payments/").data["count"], 0)
        self.assertEqual(self.client.get(f"/payments/{payment_id}/").status_code, 404)


class WebhookTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        booking = self.create_booking()
        self.booking_id = booking["id"]
        response = self.client.post(
            "/payments/", {"booking_id": self.booking_id, "simulate_outcome": "PENDING"}, format="json"
        )
        self.payment_ref = response.data["provider_reference"]
        self.client.force_authenticate(None)  # webhooks carry no user JWT

    def send(self, status="SUCCESS", event_id="evt_1", signature=None, **extra):
        body = json.dumps(
            {"event_id": event_id, "payment_reference": self.payment_ref, "status": status, **extra}
        ).encode()
        return self.client.post(
            "/payments/webhook/",
            body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=signature if signature is not None else sign(body),
        )

    def booking_status(self):
        return Booking.objects.get(pk=self.booking_id).status

    def test_success_webhook_confirms_booking(self):
        response = self.send("SUCCESS")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result"], "processed")
        self.assertEqual(response.data["payment_status"], "SUCCESS")
        self.assertEqual(self.booking_status(), "CONFIRMED")

    def test_failed_webhook_fails_booking(self):
        self.send("FAILED", failure_reason="Insufficient funds")
        self.assertEqual(self.booking_status(), "FAILED")
        self.assertEqual(Payment.objects.get().failure_reason, "Insufficient funds")

    def test_repeated_event_is_idempotent(self):
        first = self.send("SUCCESS", event_id="evt_dup")
        for _ in range(3):
            again = self.send("SUCCESS", event_id="evt_dup")
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.data["result"], "duplicate")
        self.assertEqual(first.data["result"], "processed")
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(self.booking_status(), "CONFIRMED")

    def test_reused_event_id_with_different_payload_conflicts(self):
        self.send("SUCCESS", event_id="evt_x")
        self.assertEqual(self.send("FAILED", event_id="evt_x").status_code, 409)
        self.assertEqual(self.booking_status(), "CONFIRMED")

    def test_late_contradicting_event_does_not_corrupt_state(self):
        self.send("SUCCESS", event_id="evt_ok")
        response = self.send("FAILED", event_id="evt_late_fail")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["result"], "ignored")
        self.assertEqual(Payment.objects.get().status, "SUCCESS")
        self.assertEqual(self.booking_status(), "CONFIRMED")

    def test_same_status_new_event_id_is_noop(self):
        self.send("SUCCESS", event_id="evt_a")
        self.assertEqual(self.send("SUCCESS", event_id="evt_b").data["result"], "ignored")
        self.assertEqual(self.booking_status(), "CONFIRMED")

    def test_success_after_cancellation_keeps_booking_cancelled(self):
        Booking.objects.filter(pk=self.booking_id).update(status=Booking.Status.CANCELLED)
        self.send("SUCCESS")
        self.assertEqual(Payment.objects.get().status, "SUCCESS")
        self.assertEqual(self.booking_status(), "CANCELLED")

    def test_rejects_bad_signature(self):
        self.assertEqual(self.send(signature="sha256=deadbeef").status_code, 401)
        self.assertEqual(self.send(signature="").status_code, 401)
        self.assertEqual(self.booking_status(), "PENDING")
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_invalid_payloads(self):
        self.assertEqual(self.send(status="MAYBE").status_code, 400)
        self.assertEqual(self.send(amount="1.00").status_code, 400)  # amount mismatch
        self.payment_ref = "sim_unknown"
        self.assertEqual(self.send().status_code, 404)
        self.assertEqual(WebhookEvent.objects.count(), 0)
        self.assertEqual(self.booking_status(), "PENDING")

    def test_malformed_json(self):
        body = b"{not json"
        response = self.client.post(
            "/payments/webhook/", body, content_type="application/json", HTTP_X_WEBHOOK_SIGNATURE=sign(body)
        )
        self.assertEqual(response.status_code, 400)
