import { FormEvent, useEffect, useRef, useState } from "react";
import { CheckCircle2, Keyboard, ScanLine, ShieldCheck, UserRound, XCircle } from "lucide-react";
import { api } from "../../services/api";
import type { AttendanceScanResult } from "../../types";

export function ScannerPage() {
  const [token, setToken] = useState("");
  const [result, setResult] = useState<AttendanceScanResult | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setResult(null);
    try { const response = await api.post<AttendanceScanResult>("/attendance/scan/", { barcode_token: token, device_id: "web-station" }); setResult(response.data); setToken(""); }
    catch { setError("This barcode could not be verified. Check the token and try again."); }
    finally { inputRef.current?.focus(); }
  };
  return <section><div className="section-heading"><div><span className="eyebrow">Front desk / attendance</span><h2>Barcode scanner</h2><p className="muted">Scan an ID card to record arrival and verify identity.</p></div><span className="live-pill"><span /> Live</span></div><div className="scanner-grid"><div className="scanner-card"><div className="scanner-visual"><ScanLine size={42} /><span>Ready to scan</span><small>Connect a USB scanner or type a token below</small></div><form onSubmit={submit} className="scan-form"><label>Barcode token<input ref={inputRef} value={token} onChange={(e) => setToken(e.target.value)} placeholder="SCH-..." autoComplete="off" required /></label><button className="primary-button" type="submit"><ScanLine size={18} /> Verify scan</button></form>{error && <div className="alert error"><XCircle size={18} />{error}</div>}<div className="scanner-help"><Keyboard size={17} /><span>USB scanners behave like keyboards. Keep this field focused for instant scans.</span></div></div><div className={result ? "verification-card verified" : "verification-card"}>{result ? <><div className="verification-icon"><CheckCircle2 size={28} /></div><span className="eyebrow">Verified identity</span><h3>{result.name}</h3><p>{result.class ?? result.department}</p><div className="result-status"><strong>{result.status}</strong><span>{result.duplicate ? "Already recorded today" : "Attendance recorded now"}</span></div><div className="anti-fraud"><ShieldCheck size={17} /><span>Visual verification recommended at the gate</span></div></> : <><UserRound size={42} /><h3>Awaiting scan</h3><p>The verified profile, class, and attendance status will appear here.</p></>}</div></div></section>;
}
