"""Payment business logic.

Locking rule: always lock the Booking row first, then the Payment row. Every path that
changes a booking or its payments (pay, webhook, cancel) takes the booking lock, so they
are serialised per booking and can't deadlock each other.
"""

import hashlib
import json
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from bookings.models import Booking
from common.exceptions import Conflict

from . import gateway
from .models import Payment, WebhookEvent

logger = logging.getLogger(__name__)


def _apply_payment_result(payment, booking, new_status, failure_reason=""):
    """Move a PENDING payment to a final status and update its booking.

    Returns (applied: bool, note: str). Final payments are never changed again, and a
    booking is never pulled out of CANCELLED or CONFIRMED by a payment result.
    """
    if payment.status == new_status:
        return False, f"Payment already {new_status}."
    if payment.is_final:
        return False, f"Payment is already final ({payment.status}); {new_status} ignored."

    payment.status = new_status
    payment.failure_reason = failure_reason if new_status == Payment.Status.FAILED else ""
    payment.save(update_fields=["status", "failure_reason", "updated_at"])

    if booking.status == Booking.Status.CANCELLED:
        if new_status == Payment.Status.SUCCESS:
            # Money captured for a cancelled booking - would be refunded in a real system.
            logger.warning("Payment %s succeeded for cancelled booking %s; refund required.",
                           payment.provider_reference, booking.id)
        return True, "Booking is cancelled; booking status unchanged."

    target = Booking.Status.CONFIRMED if new_status == Payment.Status.SUCCESS else Booking.Status.FAILED
    if booking.status != target and booking.can_transition_to(target):
        booking.transition_to(target)
        booking.save(update_fields=["status", "updated_at"])
    return True, ""


def _lock_user_booking(user, booking_id):
    booking = Booking.objects.select_for_update().filter(pk=booking_id, user=user).first()
    if booking is None:
        # Same response whether the booking doesn't exist or belongs to someone else.
        raise NotFound("Booking not found.")
    return booking


def create_payment(*, user, booking_id, forced_outcome=None, idempotency_key=None):
    """Pay for a booking. Returns (payment, created)."""
    with transaction.atomic():
        booking = _lock_user_booking(user, booking_id)

        if idempotency_key:
            existing = booking.payments.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False  # replay of a request we already handled

        if booking.status == Booking.Status.CONFIRMED:
            raise Conflict("This booking is already paid.")
        if booking.status == Booking.Status.CANCELLED:
            raise Conflict("Cannot pay for a cancelled booking.")
        if booking.appointment_at <= timezone.now():
            raise ValidationError({"booking_id": "The appointment time has already passed."})
        if booking.payments.filter(status=Payment.Status.PENDING).exists():
            raise Conflict("A payment for this booking is already in progress.")

        if booking.status == Booking.Status.FAILED:  # retrying after a failed attempt
            booking.transition_to(Booking.Status.PENDING)
            booking.save(update_fields=["status", "updated_at"])

        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    booking=booking, amount=booking.amount, idempotency_key=idempotency_key or None
                )
        except IntegrityError:
            # Only reachable if the DB constraints catch something the checks above missed.
            raise Conflict("A payment for this booking is already in progress or completed.")

        # In a real integration the provider call would happen outside the DB transaction;
        # the simulated gateway is instant, so keeping it inside keeps the flow atomic.
        result = gateway.charge(payment, forced_outcome)
        if result.status != Payment.Status.PENDING:
            _apply_payment_result(payment, booking, result.status, result.failure_reason)

    logger.info("Payment %s for booking %s -> %s", payment.provider_reference, booking.id, payment.status)
    return payment, True


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def process_webhook(*, data, raw_body):
    """Apply a provider webhook exactly once. Returns (outcome, event).

    outcome is "processed", "ignored" (valid event, no state change) or "duplicate".
    """
    event_id = data["event_id"]
    body_hash = payload_hash(raw_body)

    # Fast path for re-deliveries, no locks needed.
    existing = WebhookEvent.objects.filter(event_id=event_id).first()
    if existing:
        return _duplicate(existing, body_hash)

    booking_id = (
        Payment.objects.filter(provider_reference=data["payment_reference"])
        .values_list("booking_id", flat=True)
        .first()
    )
    if booking_id is None:
        raise NotFound("Unknown payment_reference.")

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        payment = Payment.objects.select_for_update().get(provider_reference=data["payment_reference"])

        # Re-check under the lock: a concurrent delivery of the same event may have won the race.
        existing = WebhookEvent.objects.filter(event_id=event_id).first()
        if existing:
            return _duplicate(existing, body_hash)

        if "amount" in data and data["amount"] != payment.amount:
            raise ValidationError({"amount": "Amount does not match the payment."})

        # Record the event *before* applying it. The unique event_id is the final guard:
        # if a concurrent request (e.g. same event_id sent for another payment, so under
        # another booking lock) inserted it first, we bail out without changing anything.
        try:
            with transaction.atomic():
                event = WebhookEvent.objects.create(
                    event_id=event_id,
                    payment=payment,
                    status=data["status"],
                    payload=json.loads(raw_body),
                    payload_hash=body_hash,
                    result=WebhookEvent.Result.IGNORED,
                )
        except IntegrityError:
            event = None

        if event is not None:
            applied, note = _apply_payment_result(
                payment, booking, data["status"], data.get("failure_reason") or "Failed at provider (simulated)."
            )
            event.result = WebhookEvent.Result.APPLIED if applied else WebhookEvent.Result.IGNORED
            event.note = note
            event.save(update_fields=["result", "note"])

    if event is None:
        return _duplicate(WebhookEvent.objects.get(event_id=event_id), body_hash)

    logger.info("Webhook %s for %s -> %s (%s)", event_id, payment.provider_reference, data["status"], event.result)
    return ("processed" if applied else "ignored"), event


def _duplicate(event, body_hash):
    if event.payload_hash != body_hash:
        raise Conflict("event_id was already used with a different payload.")
    return "duplicate", event
