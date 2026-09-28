from django.contrib import admin

from .models import Payment, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["provider_reference", "booking", "amount", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["provider_reference", "booking__id"]
    list_select_related = ["booking"]


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["event_id", "payment", "status", "result", "received_at"]
    list_filter = ["result", "status"]
    search_fields = ["event_id", "payment__provider_reference"]
    list_select_related = ["payment"]
