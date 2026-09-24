import { useEffect, useState } from "react";
import { ApiError, getAdminStats } from "../api/client";
import type { AdminStats as AdminStatsData } from "../types";
import { REASON_LABELS } from "../tutor/reasonLabels";

const KIND_LABEL: Record<string, string> = {
  personalized: "Personalisiert",
  generic: "Generisch",
};

const FIELD_LABEL: Record<string, string> = {
  explanation_depth: "Detailtiefe",
  example_density: "Beispiele",
  concreteness: "Konkret oder abstrakt",
  example_domain: "Branche der Beispiele",
  register: "Ton",
  assessment_frequency: "Zwischenfragen",
};

function BarRow({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="stat-bar-row">
      <span className="stat-bar-label">{label}</span>
      <div className="stat-bar-track">
        <div className="stat-bar-fill" style={{ width: `${Math.max(pct, count > 0 ? 4 : 0)}%` }} />
      </div>
      <span className="stat-bar-count">{count}</span>
    </div>
  );
}

export function AdminStats() {
  const [stats, setStats] = useState<AdminStatsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminStats()
      .then(setStats)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, []);

  if (error) return <p className="error-banner">{error}</p>;
  if (!stats) return <p className="user-status">Wird geladen …</p>;

  const reasonMax = Math.max(1, ...stats.reason_counts.map((r) => r.count));
  const fieldMax = Math.max(1, ...stats.override_changes_by_field.map((f) => f.count));
  const personalized = stats.preference_by_kind.find((k) => k.kind === "personalized")?.count ?? 0;
  const generic = stats.preference_by_kind.find((k) => k.kind === "generic")?.count ?? 0;
  const decidedTotal = personalized + generic;
  const personalizedPct = decidedTotal > 0 ? Math.round((personalized / decidedTotal) * 100) : 0;

  return (
    <div className="admin-stats">
      <div className="stat-tiles">
        <div className="stat-tile">
          <span className="stat-tile-label">Vergleiche entschieden</span>
          <span className="stat-tile-value">{stats.comparisons_decided}</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile-label">Noch offen</span>
          <span className="stat-tile-value">{stats.comparisons_pending}</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile-label">Einstellungsänderungen</span>
          <span className="stat-tile-value">{stats.override_changes_total}</span>
        </div>
      </div>

      <div className="stat-block">
        <h3>Personalisiert vs. generisch bevorzugt</h3>
        {decidedTotal === 0 ? (
          <p className="stat-empty">Noch keine Vergleiche entschieden.</p>
        ) : (
          <>
            <div className="stat-split-bar" role="img" aria-label={`${personalizedPct}% personalisiert bevorzugt`}>
              <div className="stat-split-seg is-personalized" style={{ width: `${personalizedPct}%` }} />
              <div className="stat-split-seg is-generic" style={{ width: `${100 - personalizedPct}%` }} />
            </div>
            <div className="stat-split-legend">
              <span className="stat-legend-item is-personalized">
                {KIND_LABEL.personalized} — {personalized} ({personalizedPct}%)
              </span>
              <span className="stat-legend-item is-generic">
                {KIND_LABEL.generic} — {generic} ({100 - personalizedPct}%)
              </span>
            </div>
          </>
        )}
      </div>

      <div className="stat-block">
        <h3>Genannte Gründe</h3>
        {stats.reason_counts.length === 0 ? (
          <p className="stat-empty">Noch keine Gründe erfasst.</p>
        ) : (
          <div className="stat-bar-list">
            {stats.reason_counts.map((r) => (
              <BarRow
                key={r.reason}
                label={REASON_LABELS[r.reason as keyof typeof REASON_LABELS] ?? r.reason}
                count={r.count}
                max={reasonMax}
              />
            ))}
          </div>
        )}
      </div>

      <div className="stat-block">
        <h3>Geänderte Parameter (Scrutability-Interface)</h3>
        {stats.override_changes_by_field.length === 0 ? (
          <p className="stat-empty">Noch keine Einstellungen geändert.</p>
        ) : (
          <div className="stat-bar-list">
            {stats.override_changes_by_field.map((f) => (
              <BarRow key={f.field} label={FIELD_LABEL[f.field] ?? f.field} count={f.count} max={fieldMax} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
