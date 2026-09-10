import { useEffect, useMemo, useState } from "react";
import { AxiosError } from "axios";
import { CalendarRange, RefreshCcw, Sparkles } from "lucide-react";
import { api } from "../../services/api";
import { useAuthStore } from "../../store/auth";
import type { ApiError, GenerateTimetableResult, Role, TimetableEntry } from "../../types";

interface TermOption { id: number; name: string; session: string }
interface ClassOption { id: number; name: string }

const DAY_LABELS: Record<number, string> = { 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday" };
const SCHEDULING_ROLES: Role[] = ["SUPER_ADMIN", "PRINCIPAL"];

export function TimetableView() {
  const role = useAuthStore((state) => state.user?.role);
  const canGenerate = role ? SCHEDULING_ROLES.includes(role) : false;

  const [terms, setTerms] = useState<TermOption[]>([]);
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [termId, setTermId] = useState<number | null>(null);
  const [classId, setClassId] = useState<number | "">("");
  const [entries, setEntries] = useState<TimetableEntry[]>([]);
  const [summary, setSummary] = useState<GenerateTimetableResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.get<{ results: TermOption[] }>("/terms/").then((res) => {
      setTerms(res.data.results);
      if (res.data.results.length) setTermId(res.data.results[0].id);
    }).catch(() => setError("Could not load terms."));
    api.get<{ results: ClassOption[] }>("/classes/").then((res) => {
      setClasses(res.data.results);
      if (res.data.results.length) setClassId(res.data.results[0].id);
    }).catch(() => {});
  }, []);

  const loadTimetable = (currentTermId: number, currentClassId: number | "") => {
    setLoading(true);
    setError("");
    const query = currentClassId ? `?class=${currentClassId}` : "";
    return api.get<{ results: TimetableEntry[] }>(`/timetable/${currentTermId}/${query}`)
      .then((res) => setEntries(res.data.results))
      .catch(() => setError("Could not load the timetable for this term."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!termId) return;
    loadTimetable(termId, classId);
  }, [termId, classId]);

  const periods = useMemo(() => Array.from(new Set(entries.map((e) => e.start))).sort(), [entries]);

  const generate = async () => {
    if (!termId) return;
    setGenerating(true);
    setError("");
    setSummary(null);
    try {
      const response = await api.post<GenerateTimetableResult>("/scheduling/generate-timetable/", { term_id: termId });
      setSummary(response.data);
      await loadTimetable(termId, classId);
    } catch (err) {
      const message = (err as AxiosError<ApiError>).response?.data?.error;
      setError(message ?? "Could not generate a timetable with the current data.");
    } finally {
      setGenerating(false);
    }
  };

  const cellFor = (day: number, start: string) => entries.find((e) => e.weekday === day && e.start === start);

  return <div className="scheduling-panel">
    <div className="scheduling-controls">
      <label>Term<select value={termId ?? ""} onChange={(e) => setTermId(Number(e.target.value))}>{terms.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.session}</option>)}</select></label>
      <label>Class<select value={classId} onChange={(e) => setClassId(e.target.value ? Number(e.target.value) : "")}>{classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <button type="button" className="icon-button" aria-label="Refresh timetable" onClick={() => termId && loadTimetable(termId, classId)}><RefreshCcw size={16} /></button>
      {canGenerate && <button type="button" className="primary-button" onClick={generate} disabled={generating}><Sparkles size={16} /> {generating ? "Generating…" : "Generate timetable"}</button>}
    </div>

    {error && <div className="alert error">{error}</div>}
    {summary && <div className="alert success">Built {summary.entries_created} periods across {summary.rooms_used} room(s) in {summary.solve_time_seconds}s.{summary.difficult_subject_day_clashes > 0 && ` ${summary.difficult_subject_day_clashes} difficult-subject clash(es) could not be fully spread out.`}</div>}

    {loading ? <p className="muted">Loading timetable…</p> : entries.length === 0 ? (
      <div className="empty-state"><CalendarRange size={28} /><strong>No timetable yet for this term.</strong><span>{canGenerate ? "Use \u201CGenerate timetable\u201D to build one from the assigned subjects." : "Ask an administrator to generate one."}</span></div>
    ) : (
      <div className="timetable-scroll"><table className="timetable-table"><thead><tr><th>Period</th>{Object.values(DAY_LABELS).map((d) => <th key={d}>{d}</th>)}</tr></thead><tbody>
        {periods.map((start) => <tr key={start}><td className="timetable-period">{start.slice(0, 5)}</td>{Object.keys(DAY_LABELS).map((day) => {
          const entry = cellFor(Number(day), start);
          return <td key={day}>{entry ? <div className="timetable-cell"><strong>{entry.subject}</strong><small>{entry.teacher}</small>{entry.room && <span className="timetable-room">{entry.room}</span>}</div> : <span className="timetable-empty">—</span>}</td>;
        })}</tr>)}
      </tbody></table></div>
    )}
  </div>;
}
