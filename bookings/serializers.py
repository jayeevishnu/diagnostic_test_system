from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from centres.models import CentreTest
from common.exceptions import Conflict

from .models import Booking


class BookingPaymentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    created_at = serializers.DateTimeField()


class BookingSerializer(serializers.ModelSerializer):
    centre = serializers.SerializerMethodField()
    test = serializers.SerializerMethodField()
    payments = BookingPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "user", "centre", "test", "appointment_at", "amount",
            "status", "payments", "cancelled_at", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_centre(self, booking):
        c = booking.centre
        return {"id": c.id, "name": c.name, "address": c.address, "city": c.city}

    def get_test(self, booking):
        t = booking.test
        return {"id": t.id, "code": t.code, "name": t.name}


class BookingCreateSerializer(serializers.Serializer):
    centre_id = serializers.IntegerField(min_value=1)
    test_id = serializers.IntegerField(min_value=1)
    appointment_at = serializers.DateTimeField()

    def validate_appointment_at(self, value):
        now = timezone.now()
        if value <= now:
            raise serializers.ValidationError("Appointment must be in the future.")
        if value > now + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Appointments can be booked at most {settings.BOOKING_MAX_DAYS_AHEAD} days ahead."
            )
        return value

    def validate(self, attrs):
        # Price always comes from the database, never from the client.
        offering = (
            CentreTest.objects.select_related("centre", "test")
            .filter(
                centre_id=attrs["centre_id"],
                test_id=attrs["test_id"],
                is_available=True,
                centre__is_active=True,
            )
            .first()
        )
        if offering is None:
            raise serializers.ValidationError(
                {"test_id": "This test is not available at the selected centre."}
            )
        attrs["offering"] = offering
        return attrs

    def create(self, validated_data):
        offering = validated_data["offering"]
        try:
            with transaction.atomic():
                return Booking.objects.create(
                    user=self.context["request"].user,
                    centre=offering.centre,
                    test=offering.test,
                    appointment_at=validated_data["appointment_at"],
                    amount=offering.price,
                )
        except IntegrityError:
            raise Conflict("You already have a booking for this test at this centre and time.")

    def to_representation(self, booking):
        return BookingSerializer(booking, context=self.context).data
