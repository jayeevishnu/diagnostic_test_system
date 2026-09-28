from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from common.exceptions import Conflict

from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer


class BookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Bookings of the authenticated user.

    Users only ever see their own bookings (others' return 404, so ids don't leak);
    staff can see all. Bookings can't be edited or deleted - only cancelled.
    Filters: ?status=PENDING|CONFIRMED|FAILED|CANCELLED
    """

    def get_serializer_class(self):
        return BookingCreateSerializer if self.action == "create" else BookingSerializer

    def get_queryset(self):
        qs = Booking.objects.select_related("centre", "test").prefetch_related("payments")
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        if status_filter := self.request.query_params.get("status"):
            status_filter = status_filter.upper()
            if status_filter not in Booking.Status.values:
                raise ValidationError({"status": f"Must be one of {', '.join(Booking.Status.values)}."})
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """POST /bookings/{id}/cancel/ - only the booking's owner may cancel it."""
        with transaction.atomic():
            # Row lock so a concurrent payment/webhook can't race with the cancellation.
            # DRF's get_object_or_404 also turns malformed UUIDs into a 404.
            booking = get_object_or_404(
                Booking.objects.select_for_update(), pk=pk, user=request.user
            )
            if booking.status == Booking.Status.CANCELLED:
                raise Conflict("Booking is already cancelled.")
            if booking.appointment_at <= timezone.now():
                raise Conflict("Past appointments cannot be cancelled.")
            booking.transition_to(Booking.Status.CANCELLED)
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=["status", "cancelled_at", "updated_at"])

        booking = self.get_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking).data, status=status.HTTP_200_OK)
