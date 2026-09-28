from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("accounts.urls")),
    path("", include("centres.urls")),
    path("", include("bookings.urls")),
    path("", include("payments.urls")),
]

handler404 = "common.views.not_found"
handler500 = "common.views.server_error"
