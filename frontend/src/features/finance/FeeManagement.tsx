import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { AlertCircle, CheckCircle2, CreditCard, Loader2, ReceiptText } from "lucide-react";
import { api } from "../../services/api";

// Local, self-contained types so this file has zero dependency on shared
// type files. Adjust field names here if your serializer differs.
interface Invoice {
  id: number;
  number: string;
  term: string;
  status: "OPEN" | "PARTIAL" | "PAID" | "VOID";
  total: string; // Decimal fields come back as strings from Django's JSON encoder
  paid: string;
  balance: string;
  due_date: string | null;
}

interface InitializePaymentResponse {
  authorization_url: string;
  access_code: string;
  reference: string;
}

interface ApiErrorBody {
  error: string;
}

// --- assumed endpoints ---------------------------------------------------
// GET  /api/finance/invoices/                 -> { results: Invoice[] }
// POST /api/finance/paystack/initialize/       body: { invoice_id }
//      -> InitializePaymentResponse (redirect the browser to authorization_url)
// These aren't part of finance_services.py itself - see the import notes
// for the two-line view + url you'll need to expose them.
// ---------------------------------------------------------------------------

async function fetchInvoices(): Promise<Invoice[]> {
  const { data } = await api.get<{ results: Invoice[] }>("/finance/invoices/");
  return data.results;
}

async function initializePayment(invoiceId: number): Promise<InitializePaymentResponse> {
  const { data } = await api.post<InitializePaymentResponse>("/finance/paystack/initialize/", {
    invoice_id: invoiceId,
  });
  return data;
}

const STATUS_BADGE: Record<Invoice["status"], string> = {
  OPEN: "bg-slate-100 text-slate-700",
  PARTIAL: "bg-amber-100 text-amber-700",
  PAID: "bg-emerald-100 text-emerald-700",
  VOID: "bg-red-100 text-red-700",
};

function formatCurrency(value: string) {
  const amount = Number(value);
  return Number.isFinite(amount) ? `₦${amount.toLocaleString("en-NG", { minimumFractionDigits: 2 })}` : value;
}

export function FeeManagement() {
  const queryClient = useQueryClient();
  const [payingInvoiceId, setPayingInvoiceId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const { data: invoices, isLoading, isError } = useQuery({
    queryKey: ["finance", "invoices"],
    queryFn: fetchInvoices,
  });

  const payMutation = useMutation({
    mutationFn: initializePayment,
    onMutate: (invoiceId: number) => {
      setError("");
      setPayingInvoiceId(invoiceId);
    },
    onSuccess: (data) => {
      // Paystack completes the flow on their hosted checkout page, then
      // redirects back to your callback_url (wire that up server-side in
      // initialize_paystack_transaction's `callback_url` argument).
      window.location.href = data.authorization_url;
    },
    onError: (err) => {
      const message = (err as AxiosError<ApiErrorBody>).response?.data?.error;
      setError(message ?? "Could not start checkout. Please try again.");
      setPayingInvoiceId(null);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["finance", "invoices"] });
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Fee Management</h1>
        <p className="mt-1 text-sm text-slate-500">Outstanding balances and payment history for this account.</p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading invoices…
        </div>
      )}

      {isError && !isLoading && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-6 text-sm text-red-700">
          Could not load invoices. Refresh to try again.
        </div>
      )}

      {!isLoading && !isError && invoices?.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-slate-500">
          <ReceiptText className="h-6 w-6" />
          <p className="text-sm font-medium">No invoices yet</p>
        </div>
      )}

      <div className="space-y-3">
        {invoices?.map((invoice) => {
          const balance = Number(invoice.balance);
          const canPay = invoice.status !== "PAID" && invoice.status !== "VOID" && balance > 0;
          const isPayingThis = payMutation.isPending && payingInvoiceId === invoice.id;

          return (
            <div
              key={invoice.id}
              className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-900">{invoice.number}</span>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_BADGE[invoice.status]}`}>
                    {invoice.status}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-500">
                  {invoice.term} · Due {invoice.due_date ?? "—"}
                </p>
                <div className="mt-3 flex gap-6 text-sm">
                  <div>
                    <p className="text-slate-400">Total</p>
                    <p className="font-medium text-slate-900">{formatCurrency(invoice.total)}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">Paid</p>
                    <p className="font-medium text-slate-900">{formatCurrency(invoice.paid)}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">Balance</p>
                    <p className="font-semibold text-slate-900">{formatCurrency(invoice.balance)}</p>
                  </div>
                </div>
              </div>

              <button
                type="button"
                disabled={!canPay || payMutation.isPending}
                onClick={() => payMutation.mutate(invoice.id)}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isPayingThis ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Starting checkout…
                  </>
                ) : invoice.status === "PAID" ? (
                  <>
                    <CheckCircle2 className="h-4 w-4" /> Paid
                  </>
                ) : (
                  <>
                    <CreditCard className="h-4 w-4" /> Pay Now
                  </>
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default FeeManagement;