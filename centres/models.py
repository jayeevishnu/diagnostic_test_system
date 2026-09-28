from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


class DiagnosticTest(TimeStampedModel):
    """A test from the master catalogue (e.g. CBC, Lipid Profile). Prices are per centre."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class DiagnosticCentre(TimeStampedModel):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    is_active = models.BooleanField(default=True)
    tests = models.ManyToManyField(DiagnosticTest, through="CentreTest", related_name="centres")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "address", "city"], name="uniq_centre_name_location"),
        ]

    def __str__(self):
        return f"{self.name}, {self.city}"


class CentreTest(TimeStampedModel):
    """A test offered by a centre, at that centre's price."""

    centre = models.ForeignKey(DiagnosticCentre, on_delete=models.CASCADE, related_name="offerings")
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="offerings")
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["test__name"]
        constraints = [
            models.UniqueConstraint(fields=["centre", "test"], name="uniq_centre_test"),
            models.CheckConstraint(condition=Q(price__gt=0), name="centre_test_price_positive"),
        ]

    def __str__(self):
        return f"{self.test.name} @ {self.centre.name}: {self.price}"
