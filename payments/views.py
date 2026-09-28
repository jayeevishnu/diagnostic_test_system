from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer, WebhookSerializer
from .signing import SIGNATURE_HEADER, is_valid_signature


class PaymentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """POST /payments/ runs a simulated payment for one of the user's bookings.

    Send an `Idempotency-Key` header to make retries safe: repeating a request with the
    same key returns the original payment (200) instead of charging again.
    """

    throttle_scope = "payments"

    def get_serializer_class(self):
        return PaymentCreateSerializer if self.action == "create" else PaymentSerializer

    def get_queryset(self):
        return Payment.objects.filter(booking__user=self.request.user).select_related("booking")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 64:
            raise ValidationError({"Idempotency-Key": "Must be at most 64 characters."})

        payment, created = services.create_payment(
            user=request.user,
            booking_id=serializer.validated_data["booking_id"],
            forced_outcome=serializer.validated_data.get("simulate_outcome"),
            idempotency_key=idempotency_key,
        )
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentWebhookView(APIView):
    """POST /payments/webhook/ - status updates from the (simulated) payment provider.

    Authenticated by an HMAC-SHA256 signature of the raw body, not by a user JWT.
    Idempotent: re-delivering the same event_id is acknowledged but not re-applied.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        raw_body = request.body  # read before request.data so the exact signed bytes are used
        if not is_valid_signature(raw_body, request.headers.get(SIGNATURE_HEADER)):
            return Response({"detail": "Invalid or missing webhook signature."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        outcome, event = services.process_webhook(data=serializer.validated_data, raw_body=raw_body)
        return Response(
            {
                "result": outcome,
                "event_id": event.event_id,
                "payment_reference": event.payment.provider_reference,
                "payment_status": event.payment.status,
                "booking_status": event.payment.booking.status,
            },
            status=status.HTTP_200_OK,
        )
