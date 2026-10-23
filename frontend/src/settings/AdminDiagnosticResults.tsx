import { useEffect, useState } from "react";
import { ApiError, getDiagnosticResults } from "../api/client";
import type { DiagnosticResultRow, PriorKnowledge } from "../types";

const LEVEL_WORDS: Record<PriorKnowledge, string> = {
  none: "Keine",
  low: "Gering",
  moderate: "Mittel",
  high: "Hoch",
};

const LEVEL_ORDER: PriorKnowledge[] = ["none", "low", "moderate", "high"];

function comparison(row: DiagnosticResultRow): { label: string } {
  const diff = LEVEL_ORDER.indexOf(row.quiz_level) - LEVEL_ORDER.indexOf(row.self_estimate);
  if (diff === 0) return { label: "Passt" };
  if (diff > 0) return { label: "Besser als gedacht" };
  return { label: "Überschätzt" };
}

export function AdminDiagnosticResults() {
  const [rows, setRows] = useState<DiagnosticResultRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiagnosticResults()
      .then((res) => setRows(res.results))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, []);

  if (error) return <p className="error-banner">{error}</p>;
  if (!rows) return <p className="user-status">Wird geladen …</p>;
  if (rows.length === 0) return <p className="stat-empty">Noch kein Quiz abgeschlossen.</p>;

  return (
    <div className="user-table-wrap">
      <table className="user-table">
        <thead>
          <tr>
            <th>Nutzer:in</th>
            <th>Kapitel</th>
            <th>Richtig</th>
            <th>Selbsteinschätzung</th>
            <th>Quiz-Ergebnis</th>
            <th>Vergleich</th>
            <th>Abgeschlossen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.username}:${row.chapter_id}`}>
              <td>{row.username}</td>
              <td>
                {row.chapter_id}
                {row.chapter_title ? ` ${row.chapter_title}` : ""}
              </td>
              <td>
                {row.correct_count}
                {row.item_count !== null ? ` / ${row.item_count}` : ""}
              </td>
              <td>{LEVEL_WORDS[row.self_estimate]}</td>
              <td>{LEVEL_WORDS[row.quiz_level]}</td>
              <td>{comparison(row).label}</td>
              <td className="user-status">{new Date(row.taken_at).toLocaleString("de-DE")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
