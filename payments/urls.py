from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet, PaymentWebhookView

router = DefaultRouter()
router.include_root_view = False
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("payments/webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
    *router.urls,
]
