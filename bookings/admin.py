from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "centre", "test", "appointment_at", "amount", "status", "created_at"]
    list_filter = ["status", "centre"]
    search_fields = ["id", "user__email"]
    list_select_related = ["user", "centre", "test"]
    readonly_fields = ["amount", "created_at", "updated_at"]
