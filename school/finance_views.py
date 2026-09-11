import json
from django.http import JsonResponse
from accounts.authentication import jwt_login_required
from .finance_services import initialize_paystack_transaction
from .models import Invoice

@jwt_login_required
def invoices_api(request):
    # Fetches invoices for the logged-in user
    invoices = Invoice.objects.filter(student__user=request.user)
    
    results = []
    for inv in invoices:
        paid_amount = sum(p.amount for p in inv.payments.all()) if inv.payments.exists() else 0
        balance = inv.total - paid_amount
        
        results.append({
            "id": inv.id,
            "number": inv.number,
            "term": str(inv.term),
            "status": inv.status,
            "total": str(inv.total),
            "paid": str(paid_amount),
            "balance": str(balance),
            "due_date": inv.due_date.isoformat() if inv.due_date else None
        })
        
    return JsonResponse({"results": results})

@jwt_login_required
def paystack_initialize_api(request):
    # Triggers the Paystack checkout window
    payload = json.loads(request.body)
    invoice = Invoice.objects.get(pk=payload["invoice_id"])
    return JsonResponse(initialize_paystack_transaction(invoice, email=request.user.email))