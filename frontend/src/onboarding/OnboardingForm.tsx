import { useState } from "react";
import { ApiError, onboard } from "../api/client";
import type { Theme } from "../theme";
import type {
  Industry,
  LearningGoal,
  OnboardingResponse,
  PresentationStyle,
  PriorKnowledge,
  RetentionHorizon,
} from "../types";

interface Props {
  onComplete: (result: OnboardingResponse) => void;
  theme: Theme;
  onToggleTheme: () => void;
}

const PRIOR_KNOWLEDGE_OPTIONS: { value: PriorKnowledge; label: string }[] = [
  { value: "none", label: "Keine" },
  { value: "low", label: "Gering" },
  { value: "moderate", label: "Mittel" },
  { value: "high", label: "Hoch" },
];

const GOAL_OPTIONS: { value: LearningGoal; label: string }[] = [
  { value: "certification", label: "Zertifikat bestehen" },
  { value: "applied", label: "Anwendung im Beruf" },
  { value: "orientation", label: "Überblick gewinnen" },
];

const RETENTION_OPTIONS: { value: RetentionHorizon; label: string }[] = [
  { value: "within_2_weeks", label: "Innerhalb von 2 Wochen" },
  { value: "1_to_3_months", label: "1 bis 3 Monate" },
  { value: "long_term", label: "Langfristig" },
];

const STYLE_OPTIONS: { value: PresentationStyle; label: string }[] = [
  { value: "concise", label: "Knapp" },
  { value: "balanced", label: "Ausgewogen" },
  { value: "verbose", label: "Ausführlich" },
];

// Kompakte, IT-management-relevante Branchenliste. "neutral" ist die
// Rückfalloption und zugleich der Default der Regelbasis.
const INDUSTRY_OPTIONS: { value: Industry; label: string }[] = [
  { value: "manufacturing", label: "Fertigung & Industrie" },
  { value: "finance", label: "Banken & Versicherungen" },
  { value: "public_sector", label: "Öffentliche Verwaltung" },
  { value: "healthcare", label: "Gesundheitswesen" },
  { value: "retail", label: "Handel & E-Commerce" },
  { value: "it_software", label: "IT & Software" },
  { value: "logistics", label: "Logistik & Transport" },
  { value: "energy", label: "Energie & Versorgung" },
  { value: "consulting", label: "Beratung & Dienstleistung" },
  { value: "neutral", label: "Branchenneutral" },
];

interface FieldProps<T extends string> {
  label: string;
  description: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  /** Render as a `<select>` instead of a button group -- for fields with
   *  more options than fit comfortably as inline buttons (e.g. industry). */
  dropdown?: boolean;
}

function OnboardingField<T extends string>({
  label,
  description,
  value,
  options,
  onChange,
  dropdown = false,
}: FieldProps<T>) {
  return (
    <div className="onboarding-field">
      <div>
        <div className="field-label">{label}</div>
        <div className="field-description">{description}</div>
      </div>
      {dropdown ? (
        <select
          className="field-select"
          aria-label={label}
          value={value}
          onChange={(e) => onChange(e.target.value as T)}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      ) : (
        <div className="option-group" role="radiogroup" aria-label={label}>
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={value === opt.value}
              className={"option" + (value === opt.value ? " active" : "")}
              onClick={() => onChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function OnboardingForm({ onComplete, theme, onToggleTheme }: Props) {
  // Mapping inputs (each starts on the explicit default the server also uses).
  const [priorKnowledge, setPriorKnowledge] = useState<PriorKnowledge>("none");
  const [goal, setGoal] = useState<LearningGoal>("applied");
  const [retention, setRetention] = useState<RetentionHorizon>("1_to_3_months");
  const [examDate, setExamDate] = useState("");
  const [industry, setIndustry] = useState<Industry>("neutral");
  // Preferences: shape the wording only, never the didactic settings.
  const [simplifiedLanguage, setSimplifiedLanguage] = useState(false);
  const [style, setStyle] = useState<PresentationStyle>("balanced");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await onboard({
        prior_knowledge_seed: priorKnowledge,
        learning_goal: goal,
        // A date wins over the band; the server turns it into a band once.
        ...(examDate ? { exam_date: examDate } : { retention_horizon: retention }),
        industry,
        simplified_language: simplifiedLanguage,
        presentation_style: style,
      });
      onComplete(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="onboarding-root">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="header-left">
            <div className="logo">
              <span className="logo-mark">IT</span>
              <span className="logo-wordmark">
                ITM<span className="accent">Tutor</span>
              </span>
            </div>
          </div>
          <div className="header-right">
            <button
              type="button"
              className="theme-toggle"
              aria-label={theme === "dark" ? "Zum Hellmodus wechseln" : "Zum Dunkelmodus wechseln"}
              onClick={onToggleTheme}
            >
              {theme === "dark" ? "☾" : "☀"}
            </button>
          </div>
        </div>
      </header>

      <div className="onboarding-shell">
        <div className="onboarding-intro">
          <div className="kicker">Lernprofil einrichten</div>
          <h1>Richte dein Lernprofil ein</h1>
          <p>
            Vier Fragen stellen deinen Tutor ein. Jede Antwort steuert eine Einstellung, an die
            sich der Tutor hält — du kannst später jederzeit nachvollziehen, wie sie zustande kam,
            und jede Einstellung anpassen. Dazu zwei Vorlieben zur Darstellung. Vor jedem Kapitel
            folgt ein kurzer Wissenscheck, der dein Vorwissen für dieses Kapitel genauer bestimmt.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="onboarding-card">
            <OnboardingField
              label="Vorwissen"
              description="Wie viel Erfahrung hast du allgemein im IT-Management? Das ist nur dein Startwert — pro Kapitel prüft ein kurzer Check genauer."
              value={priorKnowledge}
              options={PRIOR_KNOWLEDGE_OPTIONS}
              onChange={setPriorKnowledge}
            />
            <OnboardingField
              label="Ziel"
              description="Was möchtest du mit diesem Kurs erreichen?"
              value={goal}
              options={GOAL_OPTIONS}
              onChange={setGoal}
            />
            <OnboardingField
              label="Behalten"
              description="Wie lange sollst du den Stoff parat haben?"
              value={retention}
              options={RETENTION_OPTIONS}
              onChange={(v) => {
                setRetention(v);
                setExamDate("");
              }}
            />
            <div className="onboarding-field">
              <div>
                <div className="field-label">Oder Prüfungstermin</div>
                <div className="field-description">
                  Optional. Wir ordnen den Termin einmalig einer der Stufen oben zu und speichern
                  nur die Stufe, nicht das Datum.
                </div>
              </div>
              <input
                type="date"
                className="field-select"
                aria-label="Prüfungstermin"
                value={examDate}
                onChange={(e) => setExamDate(e.target.value)}
              />
            </div>
            <OnboardingField
              label="Branche"
              description="In welchem Umfeld arbeitest du? Die Beispiele des Tutors kommen aus dieser Branche."
              value={industry}
              options={INDUSTRY_OPTIONS}
              onChange={setIndustry}
              dropdown
            />
            <div className="onboarding-field">
              <div>
                <div className="field-label">Einfache Sprache</div>
                <div className="field-description">
                  Vorliebe, keine Lerneinstellung: kürzere Sätze, Fachbegriffe kurz erklärt.
                </div>
              </div>
              <label className="option-check">
                <input
                  type="checkbox"
                  checked={simplifiedLanguage}
                  onChange={(e) => setSimplifiedLanguage(e.target.checked)}
                />
                <span>Einfache Sprache verwenden</span>
              </label>
            </div>
            <OnboardingField
              label="Darstellung"
              description="Vorliebe, keine Lerneinstellung: wie lang die Antworten ausfallen sollen."
              value={style}
              options={STYLE_OPTIONS}
              onChange={setStyle}
            />
          </div>

          {error && <p className="error-banner">{error}</p>}

          <div className="onboarding-actions">
            <button type="submit" className="primary" disabled={submitting}>
              {submitting ? "Wird eingerichtet …" : "Sitzung starten →"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
