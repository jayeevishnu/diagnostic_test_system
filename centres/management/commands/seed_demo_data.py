from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from centres.models import CentreTest, DiagnosticCentre, DiagnosticTest

TESTS = [
    ("CBC", "Complete Blood Count", "Measures red cells, white cells and platelets."),
    ("LIPID", "Lipid Profile", "Cholesterol and triglycerides."),
    ("TSH", "Thyroid Stimulating Hormone", "Screens thyroid function."),
    ("HBA1C", "HbA1c", "Average blood sugar over ~3 months."),
    ("VITD", "Vitamin D (25-OH)", "Vitamin D level."),
    ("XRAY-CHEST", "Chest X-Ray", "Radiograph of the chest."),
]

CENTRES = [
    ("HealthFirst Diagnostics", "12 MG Road", "Bengaluru", "560001",
     {"CBC": "350", "LIPID": "800", "TSH": "450", "HBA1C": "600"}),
    ("CarePlus Labs", "45 Park Street", "Kolkata", "700016",
     {"CBC": "300", "VITD": "1200", "XRAY-CHEST": "500"}),
    ("MediScan Centre", "8 Linking Road, Bandra", "Mumbai", "400050",
     {"CBC": "400", "LIPID": "850", "HBA1C": "650", "XRAY-CHEST": "550", "VITD": "1300"}),
]


class Command(BaseCommand):
    help = "Seed demo diagnostic tests, centres and an admin user (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        tests = {}
        for code, name, description in TESTS:
            tests[code], _ = DiagnosticTest.objects.update_or_create(
                code=code, defaults={"name": name, "description": description}
            )

        for name, address, city, pincode, offerings in CENTRES:
            centre, _ = DiagnosticCentre.objects.update_or_create(
                name=name, address=address, city=city, defaults={"pincode": pincode}
            )
            for code, price in offerings.items():
                CentreTest.objects.update_or_create(
                    centre=centre, test=tests[code], defaults={"price": Decimal(price), "is_available": True}
                )

        User = get_user_model()
        if not User.objects.filter(email="admin@example.com").exists():
            User.objects.create_superuser("admin@example.com", "Admin@12345")
            self.stdout.write("Created admin user admin@example.com / Admin@12345")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(TESTS)} tests and {len(CENTRES)} centres."
        ))
