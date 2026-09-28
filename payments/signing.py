import hashlib
import hmac

from django.conf import settings

SIGNATURE_HEADER = "X-Webhook-Signature"


def sign(raw_body: bytes) -> str:
    digest = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def is_valid_signature(raw_body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(sign(raw_body), signature)
