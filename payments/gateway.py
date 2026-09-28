"""A fake payment provider. No money moves; it just decides an outcome."""

import random
from dataclasses import dataclass

from django.conf import settings

from .models import Payment


@dataclass(frozen=True)
class ChargeResult:
    status: str
    failure_reason: str = ""


def charge(payment, forced_outcome=None):
    """Simulate charging `payment`.

    `forced_outcome` lets clients/tests pick the result deterministically:
      SUCCESS / FAILED - settle immediately.
      PENDING          - leave the payment open; the final status arrives via the webhook.
    Without it, the outcome is random with SIMULATED_PAYMENT_SUCCESS_RATE.
    """
    outcome = forced_outcome
    if outcome is None:
        succeeded = random.random() < settings.SIMULATED_PAYMENT_SUCCESS_RATE
        outcome = Payment.Status.SUCCESS if succeeded else Payment.Status.FAILED

    if outcome == Payment.Status.FAILED:
        return ChargeResult(Payment.Status.FAILED, "Card declined (simulated).")
    return ChargeResult(outcome)
