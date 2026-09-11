import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { AlertCircle, CheckCircle2, Loader2, Save } from "lucide-react";
import { api } from "../../services/api";

// Local, self-contained types - no dependency on shared type files.
interface RosterEntry {
  student_id: number;
  name: string;
  admission_number: string;
  score: number | null; // existing saved CA score, if any
}

interface AssessmentMeta {
  id: number;
  title: string;
  subject: string;
  class_name: string;
  max_score: number;
}

interface RosterResponse {
  assessment: AssessmentMeta;
  roster: RosterEntry[];
}

interface ApiErrorBody {
  error: string;
}

// --- assumed endpoints ---------------------------------------------------
// GET  /api/academics/roster/<assessment_id>/   -> RosterResponse
// POST /api/academics/grades/bulk-save/          body: { assessment_id, scores: [{student_id, score}] }
// Not part of academic_services.py itself (that file only covers PDF
// generation, per the ask) - see the import notes for what to add.
// ---------------------------------------------------------------------------

async function fetchRoster(assessmentId: number): Promise<RosterResponse> {
  const { data } = await api.get<RosterResponse>(`/academics/roster/${assessmentId}/`);
  return data;
}

interface SaveScoresPayload {
  assessmentId: number;
  scores: { student_id: number; score: number }[];
}

async function saveScores({ assessmentId, scores }: SaveScoresPayload): Promise<void> {
  await api.post("/academics/grades/bulk-save/", { assessment_id: assessmentId, scores });
}

export function GradeEntryGrid({ assessmentId }: { assessmentId: number }) {
  const queryClient = useQueryClient();
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["academics", "roster", assessmentId],
    queryFn: () => fetchRoster(assessmentId),
  });

  // Reset local edit buffer whenever a fresh roster comes in (new
  // assessment selected, or after a successful save + refetch).
  useEffect(() => {
    setEdits({});
  }, [data]);

  const dirtyCount = Object.keys(edits).length;

  const saveMutation = useMutation({
    mutationFn: saveScores,
    onSuccess: () => {
      setSavedAt(Date.now());
      setError("");
      queryClient.invalidateQueries({ queryKey: ["academics", "roster", assessmentId] });
    },
    onError: (err) => {
      const message = (err as AxiosError<ApiErrorBody>).response?.data?.error;
      setError(message ?? "Could not save these scores. Please try again.");
    },
  });

  const maxScore = data?.assessment.max_score ?? 100;

  const rows = useMemo(() => data?.roster ?? [], [data]);

  const setScore = (studentId: number, value: string) => {
    setSavedAt(null);
    setEdits((prev) => ({ ...prev, [studentId]: value }));
  };

  const scoreFor = (row: RosterEntry) =>
    edits[row.student_id] ?? (row.score !== null ? String(row.score) : "");

  const invalidRow = (row: RosterEntry) => {
    const raw = scoreFor(row);
    if (raw === "") return false;
    const numeric = Number(raw);
    return Number.isNaN(numeric) || numeric < 0 || numeric > maxScore;
  };

  const hasInvalidScores = rows.some(invalidRow);

  const handleSaveAll = () => {
    const scores = Object.entries(edits)
      .filter(([, raw]) => raw !== "")
      .map(([studentId, raw]) => ({ student_id: Number(studentId), score: Number(raw) }));
    if (scores.length === 0) return;
    saveMutation.mutate({ assessmentId, scores });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {data ? `${data.assessment.title} · ${data.assessment.subject}` : "Grade Entry"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {data ? `${data.assessment.class_name} · scores out of ${maxScore}` : "Continuous assessment score entry"}
          </p>
        </div>
        <button
          type="button"
          disabled={dirtyCount === 0 || hasInvalidScores || saveMutation.isPending}
          onClick={handleSaveAll}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {saveMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Saving…
            </>
          ) : (
            <>
              <Save className="h-4 w-4" /> Save {dirtyCount > 0 ? `${dirtyCount} score${dirtyCount > 1 ? "s" : ""}` : "all"}
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}
      {savedAt && !error && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <CheckCircle2 className="h-4 w-4 shrink-0" /> Scores saved.
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading roster…
        </div>
      )}
      {isError && !isLoading && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-6 text-sm text-red-700">
          Could not load the class roster. Refresh to try again.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">Admission No.</th>
                <th className="px-4 py-3 text-right">Score (/{maxScore})</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => {
                const isDirty = row.student_id in edits;
                const invalid = invalidRow(row);
                return (
                  <tr key={row.student_id} className={isDirty ? "bg-indigo-50/40" : undefined}>
                    <td className="px-4 py-2.5 font-medium text-slate-800">{row.name}</td>
                    <td className="px-4 py-2.5 text-slate-500">{row.admission_number}</td>
                    <td className="px-4 py-2.5 text-right">
                      <input
                        type="number"
                        min={0}
                        max={maxScore}
                        step="0.5"
                        value={scoreFor(row)}
                        onChange={(e) => setScore(row.student_id, e.target.value)}
                        className={`w-24 rounded-md border px-2 py-1 text-right focus:outline-none focus:ring-2 ${
                          invalid
                            ? "border-red-300 focus:ring-red-400"
                            : "border-slate-300 focus:ring-indigo-400"
                        }`}
                      />
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-8 text-center text-slate-400">
                    No students on this roster yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default GradeEntryGrid;