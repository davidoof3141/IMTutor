import { useEffect, useState } from "react";
import {
  ApiError,
  BASE_URL,
  getConfig,
  getRules,
  resetDiagnosticOverrides,
  resetOverrides,
  revertDiagnosticOverrideField,
  revertOverrideField,
  setDiagnosticOverride,
  setOverride,
} from "../api/client";
import { PARAMS, type ParamKey, type ParamMeta } from "./params";
import type { ClauseCatalogue, ConfigResponse, ControlVector, LessonResponse, LessonStepKind, Rule } from "../types";

interface Props {
  config: ConfigResponse;
  learnerId: string;
  onConfigChange: (config: ConfigResponse) => void;
  lesson: LessonResponse | null;
}

const STEP_KIND_LABEL: Record<LessonStepKind, string> = {
  explain: "Erklärung",
  example: "Beispiel",
  checkpoint: "Verständnischeck",
  recap: "Zusammenfassung",
};

const PROFILE_FIELDS: { key: keyof ConfigResponse["profile"]; label: string }[] = [
  { key: "prior_knowledge_seed", label: "Dein Vorwissen (Startwert)" },
  { key: "learning_goal", label: "Dein Ziel" },
  { key: "retention_horizon", label: "Deine Wissensdauer" },
  { key: "industry", label: "Deine Branche" },
];

// Vorlieben: nicht Teil der Regelabbildung, nur Formulierung des Prompts.
const PREFERENCE_FIELDS: { key: keyof ConfigResponse["profile"]; label: string }[] = [
  { key: "simplified_language", label: "Einfache Sprache" },
  { key: "presentation_style", label: "Darstellung" },
  { key: "learner_type", label: "Lerntyp" },
];

const PROFILE_WORDS: Record<string, string> = {
  none: "Keine",
  low: "Gering",
  moderate: "Mittel",
  high: "Hoch",
  certification: "Zertifikat bestehen",
  applied: "Anwendung im Beruf",
  orientation: "Überblick gewinnen",
  within_2_weeks: "Kurzfristig (bis 2 Wochen)",
  "1_to_3_months": "Mittelfristig (1–3 Monate)",
  long_term: "Langfristig (über 3 Monate)",
  visuell: "Visuell",
  auditiv: "Auditiv",
  kommunikativ: "Kommunikativ",
  motorisch: "Motorisch",
  concise: "Knapp",
  balanced: "Ausgewogen",
  verbose: "Ausführlich",
  true: "An",
  false: "Aus",
  manufacturing: "Fertigung & Industrie",
  finance: "Banken & Versicherungen",
  public_sector: "Öffentliche Verwaltung",
  healthcare: "Gesundheitswesen",
  retail: "Handel & E-Commerce",
  it_software: "IT & Software",
  logistics: "Logistik & Transport",
  energy: "Energie & Versorgung",
  consulting: "Beratung & Dienstleistung",
  neutral: "Branchenneutral",
};

/** Klartext-Bezeichnung eines Regel-Eingangs, für die „Warum"-Sätze. */
const FIELD_WORDS: Record<string, string> = {
  prior_knowledge: "Vorwissen",
  learning_goal: "Ziel",
  retention_horizon: "Wissensdauer",
  industry: "Branche",
};

function profileWord(value: string): string {
  return PROFILE_WORDS[value] ?? value;
}

/** Die Auslöse-Bedingungen einer Regel als kompakte Liste lesbarer Angaben. */
function ruleConditions(rule: Rule): string {
  return Object.entries(rule.when)
    .map(([field, values]) => {
      const word = FIELD_WORDS[field] ?? field.replace(/_/g, " ");
      return `${word}: ${values.map(profileWord).join(" oder ")}`;
    })
    .join("; ");
}

/** Macht aus der Auslöse-Bedingung einer Regel einen lesbaren Satz. */
function whyFromRule(rule: Rule): string {
  return `Ergibt sich aus deinen Angaben — ${ruleConditions(rule)}.`;
}

/** Verständliches Wort für einen Parameterwert, aus `meta.labels`. */
function paramValueLabel(meta: ParamMeta, value: string | number): string {
  const i = meta.options.findIndex((o) => String(o) === String(value));
  return i >= 0 ? meta.labels[i] : String(value);
}

export function TutorSetupPanel({ config, learnerId, onConfigChange, lesson }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busyField, setBusyField] = useState<string | null>(null);
  const [catalogue, setCatalogue] = useState<ClauseCatalogue | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);

  useEffect(() => {
    getRules(config.profile.ruleset_version)
      .then((r) => {
        setCatalogue(r.catalogue);
        setRules(r.ruleset.rules);
      })
      .catch(() => {
        // Ohne den Regeltext funktioniert das Panel weiterhin — es zeigt nur weniger „Warum".
      });
  }, [config.profile.ruleset_version]);

  async function withBusy(field: string, action: () => Promise<ConfigResponse>) {
    setBusyField(field);
    setError(null);
    try {
      onConfigChange(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusyField(null);
    }
  }

  // While the current chapter has a diagnostic, edits here belong to that
  // chapter (its summary-screen overrides win over the global ones); the
  // diagnostic endpoints return a different shape, so re-read the config.
  const chapterOverride = config.chapter_diagnostic?.override ?? {};
  const inChapter = config.chapter_diagnostic != null;
  const shownOverride: Record<string, unknown> = { ...config.override, ...chapterOverride };

  function handleChange(key: ParamKey, rawValue: string) {
    const isNumeric = typeof config.effective[key] === "number";
    const value = isNumeric ? Number(rawValue) : rawValue;
    const patch = { [key]: value } as Partial<ControlVector>;
    void withBusy(key, async () => {
      if (!inChapter) return setOverride(learnerId, patch);
      await setDiagnosticOverride(learnerId, patch);
      return getConfig(learnerId);
    });
  }

  function handleRevert(key: ParamKey) {
    void withBusy(key, async () => {
      if (key in chapterOverride) {
        await revertDiagnosticOverrideField(learnerId, key);
        return getConfig(learnerId);
      }
      return revertOverrideField(learnerId, key);
    });
  }

  function handleResetAll() {
    void withBusy("__all__", async () => {
      if (inChapter) await resetDiagnosticOverrides(learnerId);
      return resetOverrides(learnerId);
    });
  }

  const hasAnyChange = Object.keys(shownOverride).length > 0;
  const firedRuleIds = Array.from(
    new Set(Object.values(config.attribution).filter((id) => id !== "default")),
  );

  return (
    <div className="panel setup-panel">
      <h2>So ist dein Tutor eingestellt</h2>
      <p className="setup-intro">
        Jede Einstellung unten ergibt sich aus den vier Fragen, die du am Anfang beantwortet hast
        (und, pro Kapitel, aus dem kurzen Wissenscheck davor).
        Du kannst alles ändern — der Tutor übernimmt es sofort, und „Auf Vorschlag zurücksetzen“
        stellt den Ausgangswert wieder her.
      </p>

      <div className="setup-section">
        <h3>Deine Angaben</h3>
        <ul className="answer-list">
          {PROFILE_FIELDS.map((f) => (
            <li key={f.key}>
              <span className="answer-label">{f.label}</span>
              <span className="answer-value">{profileWord(String(config.profile[f.key]))}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="setup-section">
        <h3>Deine Vorlieben</h3>
        <p className="muted-note">
          Diese beiden Angaben ändern nur die Formulierung, nicht die Einstellungen unten.
        </p>
        <ul className="answer-list">
          {PREFERENCE_FIELDS.map((f) => (
            <li key={f.key}>
              <span className="answer-label">{f.label}</span>
              <span className="answer-value">{profileWord(String(config.profile[f.key]))}</span>
            </li>
          ))}
        </ul>
      </div>

      {config.chapter_diagnostic && (
        <div className="setup-section">
          <h3>Wissenscheck dieses Kapitels</h3>
          <p className="muted-note">
            {config.chapter_diagnostic.correct_count} richtig → Vorwissen für dieses Kapitel:{" "}
            {profileWord(config.chapter_diagnostic.prior_knowledge)} (Startwert war:{" "}
            {profileWord(config.chapter_diagnostic.experience_seed)}). Der Startwert bleibt
            unverändert und gilt für Kapitel ohne Check.
          </p>
        </div>
      )}

      <div className="setup-section">
        <h3>Der Unterrichtsstil deines Tutors</h3>
        <div className="setting-list">
          {PARAMS.map((meta) => {
            const value = config.effective[meta.key];
            const changed = meta.key in shownOverride;
            const ruleId = config.attribution[meta.key];
            const fromRule = !changed && ruleId !== "default";
            const clause = catalogue?.clauses?.[meta.key]?.[String(value)];
            const rule = rules.find((r) => r.id === ruleId);

            let why: string;
            if (changed) {
              why = "Von dir selbst eingestellt.";
            } else if (fromRule && rule) {
              why = whyFromRule(rule);
            } else if (fromRule) {
              why = "An deine Angaben angepasst.";
            } else {
              why = "Standardeinstellung — deine Angaben erforderten keine Änderung.";
            }

            return (
              <div className="setting" key={meta.key}>
                <div className="setting-head">
                  <span className="setting-name">{meta.name}</span>
                  <span
                    className={
                      "setting-tag " +
                      (changed ? "is-changed" : fromRule ? "is-rule" : "is-default")
                    }
                  >
                    {changed ? "Von dir geändert" : fromRule ? "Aus deinen Angaben" : "Standard"}
                  </span>
                </div>
                <p className="setting-blurb">{meta.blurb}</p>
                <div className="setting-control">
                  <select
                    aria-label={meta.name}
                    value={String(value)}
                    disabled={busyField === meta.key}
                    onChange={(e) => handleChange(meta.key, e.target.value)}
                  >
                    {meta.options.map((opt, i) => (
                      <option key={opt} value={opt}>
                        {meta.labels[i]}
                      </option>
                    ))}
                  </select>
                  {changed && (
                    <button
                      type="button"
                      className="link-btn"
                      disabled={busyField === meta.key}
                      onClick={() => handleRevert(meta.key)}
                    >
                      Auf Vorschlag zurücksetzen
                    </button>
                  )}
                </div>
                <p className="setting-why">{why}</p>
                {clause && <p className="setting-clause">Anweisung an den Tutor: „{clause}“</p>}
              </div>
            );
          })}
        </div>
        <div className="setup-reset">
          <button
            type="button"
            disabled={!hasAnyChange || busyField === "__all__"}
            onClick={handleResetAll}
          >
            Alles auf Vorschlag zurücksetzen
          </button>
        </div>
      </div>

      <details className="setup-tech">
        <summary>Technische Details</summary>
        <div className="setup-section">
          <h3>Angewandte Regeln</h3>
          {firedRuleIds.length === 0 ? (
            <p className="muted-note">Keine — jeder Parameter steht auf dem Standardwert.</p>
          ) : (
            <ul className="rule-list">
              {firedRuleIds.map((id) => (
                <li key={id}>
                  <span className="rule-chip">{id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="setup-section">
          <h3>Vorgeschlagener (abgeleiteter) Vektor</h3>
          <table className="kv-table">
            <tbody>
              {PARAMS.map((p) => (
                <tr key={p.key}>
                  <td>{p.key}</td>
                  <td>
                    {String(config.derived[p.key])}
                    <span className="rule-chip" style={{ marginLeft: 8 }}>
                      {config.attribution[p.key]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="setup-section">
          <h3>Aktuell wirksam</h3>
          <table className="kv-table">
            <tbody>
              {PARAMS.map((p) => (
                <tr key={p.key}>
                  <td>{p.key}</td>
                  <td>
                    {String(config.effective[p.key])}
                    {p.key in shownOverride && (
                      <span className="override-badge" style={{ marginLeft: 8 }}>
                        geändert
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="setup-section">
          <h3>Aktive Lektion</h3>
          {!lesson ? (
            <p className="muted-note">Keine Lektion in diesem Gespräch.</p>
          ) : (
            <>
              {lesson.vector_drifted && (
                <p className="drift-banner">
                  Die Einstellungen haben sich seit Planerstellung geändert. Der Plan bleibt
                  unverändert — Änderungen wirken erst in der nächsten Lektion.
                </p>
              )}
              <table className="kv-table">
                <tbody>
                  <tr>
                    <td>Status</td>
                    <td>{lesson.status}</td>
                  </tr>
                  <tr>
                    <td>Kapitel</td>
                    <td>
                      {lesson.plan.chapter_ref}
                      {lesson.plan.section_ref ? `.${lesson.plan.section_ref}` : ""}
                    </td>
                  </tr>
                  <tr>
                    <td>Fortschritt</td>
                    <td>
                      {lesson.current_step + 1} / {lesson.plan.steps.length}
                    </td>
                  </tr>
                  <tr>
                    <td>planner_version</td>
                    <td>{lesson.plan.planner_version}</td>
                  </tr>
                </tbody>
              </table>
              <table className="kv-table" style={{ marginTop: 8 }}>
                <tbody>
                  {lesson.plan.steps.map((step) => (
                    <tr key={step.index}>
                      <td>
                        {step.index}. {STEP_KIND_LABEL[step.kind]}
                      </td>
                      <td>
                        <span className="rule-chip">
                          {lesson.rationale[String(step.index)] ?? ""}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
        <div className="setup-section">
          <h3>Wie deine Angaben die Einstellungen ergeben</h3>
          <table className="mapping-table">
            <tbody>
              {PARAMS.map((meta) => {
                const ruleId = config.attribution[meta.key];
                const fromRule = ruleId !== "default";
                const rule = rules.find((r) => r.id === ruleId);
                return (
                  <tr key={meta.key}>
                    <td>
                      <span className="mapping-param">{meta.name}</span>
                      <span className="mapping-value">
                        {paramValueLabel(meta, config.derived[meta.key])}
                      </span>
                    </td>
                    <td>
                      {fromRule ? (
                        <>
                          <span>{rule ? ruleConditions(rule) : "—"}</span>
                          <span className="mapping-rule">{ruleId}</span>
                        </>
                      ) : (
                        <span className="muted-note">
                          Standard — keine deiner Angaben hat diesen Wert verändert
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rules.length === 0 && (
            <p className="muted-note">
              Der Regeltext konnte nicht geladen werden — die Bedingungen bleiben ausgeblendet.
            </p>
          )}
        </div>
        <div className="setup-section">
          <h3>Zum Nachvollziehen</h3>
          <ul className="setup-links">
            <li>
              <a
                href={`${BASE_URL}/api/rules?version=${encodeURIComponent(
                  config.profile.ruleset_version,
                )}`}
                target="_blank"
                rel="noreferrer noopener"
              >
                Regelsatz &amp; Klauselkatalog als JSON ↗
              </a>
            </li>
            <li>
              <a
                href={`${BASE_URL}/api/export/${encodeURIComponent(learnerId)}`}
                target="_blank"
                rel="noreferrer noopener"
              >
                Vollständiges Interaktionsprotokoll als JSON ↗
              </a>
            </li>
          </ul>
        </div>
      </details>

      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}
