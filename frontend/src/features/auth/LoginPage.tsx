import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import { api } from "../../services/api";
import { useAuthStore } from "../../store/auth";
import type { TokenPair } from "../../types";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const setSession = useAuthStore((state) => state.setSession);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await api.post<TokenPair>("/token/", { username, password });
      const { access, refresh, user } = response.data;
      setSession(user, access, refresh);
      navigate((location.state as { from?: Location } | null)?.from?.pathname ?? "/dashboard");
    } catch {
      setError("Incorrect username or password. Check your details and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="auth-page"><div className="auth-art"><div className="brand"><span className="brand-mark">N</span><strong>Northstar</strong></div><div className="auth-quote"><span>THE FUTURE OF</span><h1>Learning,<br /><em>together.</em></h1><p>A calm, connected workspace for every learner, teacher, and family.</p></div></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}><span className="eyebrow">Welcome back</span><h1>Sign in to your portal</h1><p className="muted">Use your school account to continue.</p><label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your username" autoComplete="username" required /></label><label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" required /></label><div className="form-row"><label className="checkbox"><input type="checkbox" /> Remember me</label><a href="#">Forgot password?</a></div>{error && <div className="alert error"><AlertCircle size={18} />{error}</div>}<button className="primary-button" type="submit" disabled={submitting}>{submitting ? <><Loader2 size={17} className="spin" /> Signing in…</> : <>Sign in <span>→</span></>}</button></form></div></div>;
}
