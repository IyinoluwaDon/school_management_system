import { useEffect, useState } from "react";
import { AxiosError } from "axios";
import { Armchair, Sparkles } from "lucide-react";
import { api } from "../../services/api";
import { useAuthStore } from "../../store/auth";
import type { ApiError, GenerateSeatingResult, Role, SeatingPlan } from "../../types";

interface PaperOption {
  id: number;
  subject: string;
  examination: string;
  exam_date: string;
  room: string;
  candidate_count: number;
}

const SCHEDULING_ROLES: Role[] = ["SUPER_ADMIN", "PRINCIPAL"];
// Deterministic colour per class so the same class always renders the same
// swatch across halls, without needing a fixed palette keyed by name.
const CLASS_TONES = ["mint", "blue", "gold", "purple"];
const toneForClass = (classId: number) => CLASS_TONES[classId % CLASS_TONES.length];

export function SeatingView() {
  const role = useAuthStore((state) => state.user?.role);
  const canGenerate = role ? SCHEDULING_ROLES.includes(role) : false;

  const [papers, setPapers] = useState<PaperOption[]>([]);
  const [paperId, setPaperId] = useState<number | null>(null);
  const [plan, setPlan] = useState<SeatingPlan | null>(null);
  const [summary, setSummary] = useState<GenerateSeatingResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.get<{ results: PaperOption[] }>("/exams/papers/").then((res) => {
      setPapers(res.data.results);
      if (res.data.results.length) setPaperId(res.data.results[0].id);
    }).catch(() => setError("Could not load exam papers."));
  }, []);

  const loadPlan = (currentPaperId: number) => {
    setLoading(true);
    setError("");
    return api.get<SeatingPlan>(`/scheduling/seating/${currentPaperId}/`)
      .then((res) => setPlan(res.data))
      .catch(() => setError("Could not load the seating plan for this paper."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (paperId) loadPlan(paperId);
  }, [paperId]);

  const generate = async () => {
    if (!paperId) return;
    setGenerating(true);
    setError("");
    setSummary(null);
    try {
      const response = await api.post<GenerateSeatingResult>("/scheduling/generate-seating/", { paper_id: paperId });
      setSummary(response.data);
      await loadPlan(paperId);
    } catch (err) {
      const message = (err as AxiosError<ApiError>).response?.data?.error;
      setError(message ?? "Could not seat every candidate with the current halls.");
    } finally {
      setGenerating(false);
    }
  };

  return <div className="scheduling-panel">
    <div className="scheduling-controls">
      <label>Exam paper<select value={paperId ?? ""} onChange={(e) => setPaperId(Number(e.target.value))}>{papers.map((p) => <option key={p.id} value={p.id}>{p.examination} · {p.subject} ({p.exam_date}) — {p.candidate_count} candidates</option>)}</select></label>
      {canGenerate && <button type="button" className="primary-button" onClick={generate} disabled={generating}><Sparkles size={16} /> {generating ? "Seating…" : "Generate seating"}</button>}
    </div>

    {error && <div className="alert error">{error}</div>}
    {summary && <div className="alert success">Seated {summary.seated} candidate(s) across {summary.rooms_used} hall(s).{summary.unresolved_adjacencies > 0 ? ` ${summary.unresolved_adjacencies} pair(s) of same-class neighbours were unavoidable.` : " No two same-class candidates ended up beside or behind each other."}</div>}

    {loading ? <p className="muted">Loading seating plan…</p> : !plan || plan.halls.length === 0 ? (
      <div className="empty-state"><Armchair size={28} /><strong>No seating plan yet for this paper.</strong><span>{canGenerate ? "Use \u201CGenerate seating\u201D to allocate seats." : "Ask an administrator to generate one."}</span></div>
    ) : (
      <div className="seating-halls">{plan.halls.map((hall) => {
        const rows = hall.rows ?? Math.max(...hall.seats.map((s) => s.row), 1);
        const columns = hall.columns ?? Math.max(...hall.seats.map((s) => s.column), 1);
        const bySeat = new Map(hall.seats.map((s) => [`${s.row}-${s.column}`, s]));
        return <div className="seating-hall" key={hall.room}>
          <div className="panel-heading"><div><span className="eyebrow">Hall</span><h3>{hall.room}</h3></div><span className="muted">{hall.seats.length} seated</span></div>
          <div className="seat-grid" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
            {Array.from({ length: rows * columns }, (_, index) => {
              const row = Math.floor(index / columns) + 1;
              const column = (index % columns) + 1;
              const seat = bySeat.get(`${row}-${column}`);
              return <div key={index} className={seat ? `seat filled ${toneForClass(seat.class_id)}` : "seat"} title={seat ? `${seat.name} · ${seat.class}` : "Empty"}>{seat ? seat.admission_number.slice(-3) : ""}</div>;
            })}
          </div>
        </div>;
      })}</div>
    )}
  </div>;
}
