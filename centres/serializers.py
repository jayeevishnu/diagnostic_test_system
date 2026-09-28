from rest_framework import serializers

from .models import CentreTest, DiagnosticCentre, DiagnosticTest


class DiagnosticTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticTest
        fields = ["id", "code", "name", "description"]

    def validate_code(self, value):
        return value.strip().upper()


class OfferingSerializer(serializers.ModelSerializer):
    """A centre's test offering, shown nested inside a centre."""

    test = DiagnosticTestSerializer(read_only=True)

    class Meta:
        model = CentreTest
        fields = ["id", "test", "price", "is_available"]


class CentreTestSerializer(serializers.ModelSerializer):
    """Admin-facing serializer for adding/updating a test offered by a centre."""

    test_detail = DiagnosticTestSerializer(source="test", read_only=True)

    class Meta:
        model = CentreTest
        # (centre, test) uniqueness is validated by DRF from the model's UniqueConstraint.
        fields = ["id", "centre", "test", "test_detail", "price", "is_available"]


class DiagnosticCentreSerializer(serializers.ModelSerializer):
    tests = serializers.SerializerMethodField()

    class Meta:
        model = DiagnosticCentre
        fields = ["id", "name", "address", "city", "pincode", "phone", "is_active", "tests"]

    def get_tests(self, centre):
        return OfferingSerializer(available_offerings(centre), many=True).data


def available_offerings(centre):
    """Use the viewset's prefetched list when present (no N+1); fall back to a query otherwise."""
    offerings = getattr(centre, "available_offerings", None)
    if offerings is None:
        offerings = centre.offerings.filter(is_available=True).select_related("test")
    return offerings
