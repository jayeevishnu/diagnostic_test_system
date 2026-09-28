import json
import urllib.error
import urllib.request
import uuid

from django.core.management.base import BaseCommand

from payments.signing import SIGNATURE_HEADER, sign


class Command(BaseCommand):
    help = "Act as the payment provider: send a signed webhook to a running server."

    def add_arguments(self, parser):
        parser.add_argument("payment_reference")
        parser.add_argument("status", choices=["SUCCESS", "FAILED"])
        parser.add_argument("--event-id", help="Reuse an event id to test idempotency (default: random).")
        parser.add_argument("--url", default="http://127.0.0.1:8000/payments/webhook/")

    def handle(self, *args, **opts):
        body = json.dumps({
            "event_id": opts["event_id"] or f"evt_{uuid.uuid4().hex}",
            "payment_reference": opts["payment_reference"],
            "status": opts["status"],
        }).encode()
        request = urllib.request.Request(
            opts["url"],
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", SIGNATURE_HEADER: sign(body)},
        )
        self.stdout.write(f"POST {opts['url']}\n{body.decode()}")
        try:
            with urllib.request.urlopen(request) as response:
                self.stdout.write(f"{response.status} {response.read().decode()}")
        except urllib.error.HTTPError as exc:
            self.stdout.write(self.style.ERROR(f"{exc.code} {exc.read().decode()}"))
