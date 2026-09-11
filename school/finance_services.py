"""Standalone Paystack integration. No Django views/urls are touched here.

Reads its own config straight from the environment (PAYSTACK_SECRET_KEY,
optionally PAYSTACK_CURRENCY) so nothing needs to be added to settings.py.
"""

import hashlib
import hmac
import os
import uuid
from decimal import Decimal

import requests
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

PAYSTACK_BASE_URL = "https://api.paystack.co"


def _secret_key() -> str:
    key = os.environ.get("PAYSTACK_SECRET_KEY")
    if not key:
        raise ValidationError("PAYSTACK_SECRET_KEY is not configured in this environment.")
    return key


def initialize_paystack_transaction(invoice, email: str, callback_url: str | None = None, amount=None) -> dict:
    """Ask Paystack for a checkout link covering an invoice's outstanding balance.

    Args:
        invoice: an ``Invoice`` instance.
        email: the payer's email (required by Paystack).
        callback_url: where Paystack should redirect after checkout, e.g.
            ``https://your-frontend.vercel.app/finance/callback``.
        amount: optional partial-payment amount; defaults to the full
            outstanding balance (``invoice.total`` minus prior payments).

    Returns:
        ``{"authorization_url": ..., "access_code": ..., "reference": ...}``
        — redirect the browser to ``authorization_url`` (or feed
        ``access_code`` to Paystack Inline/Popup).

    Raises:
        ValidationError: bad amount, or Paystack rejected the request.
    """
    paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    outstanding = invoice.total - paid
    amount = Decimal(str(amount)) if amount is not None else outstanding
    if amount <= 0:
        raise ValidationError("This invoice has no outstanding balance to pay.")
    if amount > outstanding:
        raise ValidationError("Amount exceeds the invoice's outstanding balance.")

    reference = f"INV-{invoice.number}-{uuid.uuid4().hex[:10].upper()}"
    payload = {
        "email": email,
        "amount": int(amount * 100),  # Paystack expects the smallest currency subunit (kobo/cents).
        "reference": reference,
        "currency": os.environ.get("PAYSTACK_CURRENCY", "NGN"),
        "metadata": {"invoice_id": invoice.id, "invoice_number": invoice.number},
    }
    if callback_url:
        payload["callback_url"] = callback_url

    response = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers={"Authorization": f"Bearer {_secret_key()}"},
        timeout=15,
    )
    body = response.json()
    if not response.ok or not body.get("status"):
        raise ValidationError(body.get("message", "Could not start a Paystack transaction."))

    return {
        "authorization_url": body["data"]["authorization_url"],
        "access_code": body["data"]["access_code"],
        "reference": body["data"]["reference"],
    }


def verify_paystack_transaction(reference: str, invoice=None, received_by=None) -> dict:
    """Confirm a transaction with Paystack and, if genuinely successful, record the Payment.

    Call this from your callback view (after redirect) and/or your webhook
    handler for ``charge.success`` — it's idempotent, so it's safe to call
    from both without double-crediting the invoice.

    Args:
        reference: the Paystack transaction reference to verify.
        invoice: pass explicitly if you have it; otherwise it's looked up
            from the ``invoice_id`` stashed in metadata during initialize.
        received_by: optional ``User`` to attribute the payment to.

    Returns:
        ``{"status": "success"|"already_recorded"|<paystack status>,
           "payment_id": int|None, "amount": Decimal|None}``
    """
    from .models import Payment  # local import: keeps this file importable without an app registry
    from .services import record_payment

    existing = Payment.objects.filter(reference=reference).first()
    if existing:
        return {"status": "already_recorded", "payment_id": existing.id, "amount": existing.amount}

    response = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers={"Authorization": f"Bearer {_secret_key()}"},
        timeout=15,
    )
    body = response.json()
    if not response.ok or not body.get("status"):
        raise ValidationError(body.get("message", "Could not verify this transaction with Paystack."))

    data = body["data"]
    if data.get("status") != "success":
        return {"status": data.get("status", "failed"), "payment_id": None, "amount": None}

    # Trust Paystack's own reported amount over anything the client claims.
    amount = Decimal(data["amount"]) / 100
    invoice = invoice or _invoice_from_metadata(data)
    if invoice is None:
        raise ValidationError("Could not determine which invoice this payment belongs to.")

    payment = record_payment(
        invoice=invoice,
        amount=amount,
        method="ONLINE",
        reference=reference,
        received_by=received_by,
        paid_at=timezone.now(),
    )
    return {"status": "success", "payment_id": payment.id, "amount": amount}


def _invoice_from_metadata(paystack_data: dict):
    from .models import Invoice

    invoice_id = (paystack_data.get("metadata") or {}).get("invoice_id")
    if not invoice_id:
        return None
    return Invoice.objects.filter(pk=invoice_id).first()


def verify_webhook_signature(request_body: bytes, signature_header: str | None) -> bool:
    """Validate Paystack's ``x-paystack-signature`` header before trusting a webhook payload.

    Call this first, on the *raw* request body, before parsing JSON or
    calling ``verify_paystack_transaction``:

        if not verify_webhook_signature(request.body, request.headers.get("x-paystack-signature")):
            return HttpResponseForbidden()
    """
    if not signature_header:
        return False
    computed = hmac.new(_secret_key().encode(), request_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature_header)