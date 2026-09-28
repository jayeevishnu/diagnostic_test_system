import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from centres.models import DiagnosticCentre, DiagnosticTest
from common.models import TimeStampedModel


class InvalidTransition(Exception):
    pass


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending payment"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Payment failed"
        CANCELLED = "CANCELLED", "Cancelled"

    # Allowed state machine. FAILED -> PENDING happens when the user retries payment.
    TRANSITIONS = {
        Status.PENDING: {Status.CONFIRMED, Status.FAILED, Status.CANCELLED},
        Status.FAILED: {Status.PENDING, Status.CONFIRMED, Status.CANCELLED},
        Status.CONFIRMED: {Status.CANCELLED},
        Status.CANCELLED: set(),
    }

    # UUIDs so booking ids can't be enumerated.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    centre = models.ForeignKey(DiagnosticCentre, on_delete=models.PROTECT, related_name="bookings")
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="bookings")
    appointment_at = models.DateTimeField()
    # Snapshot of the centre's price at booking time; later price changes don't affect it.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="booking_user_created_idx"),
            models.Index(fields=["centre", "appointment_at"], name="booking_centre_slot_idx"),
            models.Index(fields=["status"], name="booking_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="booking_amount_positive"),
            # A user can't hold two live bookings for the same test/centre/slot
            # (guards against double-submits even under concurrent requests).
            models.UniqueConstraint(
                fields=["user", "centre", "test", "appointment_at"],
                condition=~Q(status="CANCELLED"),
                name="uniq_live_booking_per_slot",
            ),
        ]

    def __str__(self):
        return f"{self.id} {self.test_id}@{self.centre_id} [{self.status}]"

    def can_transition_to(self, new_status):
        return new_status in self.TRANSITIONS[self.status]

    def transition_to(self, new_status):
        if new_status == self.status:
            return
        if not self.can_transition_to(new_status):
            raise InvalidTransition(f"Cannot move booking from {self.status} to {new_status}.")
        self.status = new_status
