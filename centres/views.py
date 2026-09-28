from django.db.models import Prefetch, Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.permissions import IsAdminOrReadOnly

from .models import CentreTest, DiagnosticCentre, DiagnosticTest
from .serializers import (
    CentreTestSerializer,
    DiagnosticCentreSerializer,
    DiagnosticTestSerializer,
    OfferingSerializer,
    available_offerings,
)


def _int_param(request, name):
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError({name: "Must be an integer."})


class DiagnosticTestViewSet(viewsets.ModelViewSet):
    """Master catalogue of diagnostic tests. Public read, admin write.

    Filters: ?search=<name or code>
    """

    serializer_class = DiagnosticTestSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = DiagnosticTest.objects.all()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__iexact=search))
        return qs


class DiagnosticCentreViewSet(viewsets.ModelViewSet):
    """Diagnostic centres with the tests they offer. Public read, admin write.

    Filters: ?city=<city>, ?test=<test id>, ?search=<name>
    """

    serializer_class = DiagnosticCentreSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "tests"):
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        qs = DiagnosticCentre.objects.prefetch_related(
            Prefetch(
                "offerings",
                queryset=CentreTest.objects.filter(is_available=True).select_related("test"),
                to_attr="available_offerings",
            )
        )
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)

        params = self.request.query_params
        if city := params.get("city", "").strip():
            qs = qs.filter(city__iexact=city)
        if search := params.get("search", "").strip():
            qs = qs.filter(name__icontains=search)
        if (test_id := _int_param(self.request, "test")) is not None:
            qs = qs.filter(offerings__test_id=test_id, offerings__is_available=True).distinct()
        return qs

    @action(detail=True, methods=["get"])
    def tests(self, request, pk=None):
        """GET /centres/{id}/tests/ - tests available at this centre with prices."""
        centre = self.get_object()
        return Response(OfferingSerializer(available_offerings(centre), many=True).data)


class CentreTestViewSet(viewsets.ModelViewSet):
    """Admin management of which tests a centre offers and at what price.

    Filters: ?centre=<centre id>, ?test=<test id>
    """

    serializer_class = CentreTestSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = CentreTest.objects.select_related("centre", "test").order_by("centre_id", "test__name")
        if (centre_id := _int_param(self.request, "centre")) is not None:
            qs = qs.filter(centre_id=centre_id)
        if (test_id := _int_param(self.request, "test")) is not None:
            qs = qs.filter(test_id=test_id)
        return qs
