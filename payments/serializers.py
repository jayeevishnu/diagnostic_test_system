from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)
    booking_status = serializers.CharField(source="booking.status", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "booking_id", "booking_status", "amount", "status",
            "provider_reference", "failure_reason", "created_at", "updated_at",
        ]
        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    # Lets the caller choose the simulated result; omitted -> random outcome.
    simulate_outcome = serializers.ChoiceField(choices=Payment.Status.values, required=False)


class WebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=100)
    payment_reference = serializers.CharField(max_length=64)
    status = serializers.ChoiceField(choices=[Payment.Status.SUCCESS, Payment.Status.FAILED])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    failure_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
