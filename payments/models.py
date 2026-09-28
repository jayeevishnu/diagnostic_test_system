import uuid

from django.db import models
from django.db.models import Q

from bookings.models import Booking
from common.models import TimeStampedModel


def generate_provider_reference():
    return f"sim_{uuid.uuid4().hex}"


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # The id the (simulated) payment provider knows this payment by; webhooks reference it.
    provider_reference = models.CharField(max_length=64, unique=True, default=generate_provider_reference)
    # Optional client-supplied Idempotency-Key, so retried POST /payments/ calls don't double-charge.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
            # Database-level guarantees against double payment, whatever the code path:
            models.UniqueConstraint(
                fields=["booking"], condition=Q(status="SUCCESS"), name="one_successful_payment_per_booking"
            ),
            models.UniqueConstraint(
                fields=["booking"], condition=Q(status="PENDING"), name="one_pending_payment_per_booking"
            ),
            models.UniqueConstraint(
                fields=["booking", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_payment_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.provider_reference} [{self.status}]"

    @property
    def is_final(self):
        return self.status != self.Status.PENDING


class WebhookEvent(models.Model):

    class Result(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        IGNORED = "IGNORED", "Ignored (no state change)"

    event_id = models.CharField(max_length=100, unique=True)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="webhook_events")
    status = models.CharField(max_length=10, choices=Payment.Status.choices)
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    result = models.CharField(max_length=10, choices=Result.choices)
    note = models.CharField(max_length=255, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_id} -> {self.status} ({self.result})"
