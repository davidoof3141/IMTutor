import { useState } from "react";
import { ApiError, onboard } from "../api/client";
import type { Theme } from "../theme";
import type {
  Industry,
  LearnerType,
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
  { value: "within_2_weeks", label: "Kurzfristig (bis 2 Wochen)" },
  { value: "1_to_3_months", label: "Mittelfristig (1–3 Monate)" },
  { value: "long_term", label: "Langfristig (über 3 Monate)" },
];

// Lerntypen nach Frederic Vester ("Denken, Lernen, Vergessen"): welcher Sinneskanal
// beim Aufnehmen von Neuem für dich am besten funktioniert.
const LEARNER_TYPE_OPTIONS: { value: LearnerType; label: string; vester: string }[] = [
  {
    value: "none",
    label: "Keine Angabe",
    vester: "Der Tutor erklärt, ohne einen bestimmten Zugang zu bevorzugen.",
  },
  {
    value: "visuell",
    label: "Visuell",
    vester:
      "Du lernst über das Sehen: Bilder, Diagramme, Tabellen und klare Gliederungen helfen dir, Neues zu behalten. Der Tutor veranschaulicht bildhaft.",
  },
  {
    value: "auditiv",
    label: "Auditiv",
    vester:
      "Du lernst über das Hören: Erklärungen, Vorträge und Merksätze bleiben dir besser im Gedächtnis als Gelesenes. Der Tutor erklärt im Vortragston.",
  },
  {
    value: "kommunikativ",
    label: "Kommunikativ",
    vester:
      "Du lernst im Austausch: Diskutieren, Nachfragen und Erklären in eigenen Worten festigen dein Wissen. Der Tutor arbeitet im Dialog.",
  },
  {
    value: "motorisch",
    label: "Motorisch",
    vester:
      "Du lernst durch Handeln: Ausprobieren, Selbermachen und Durchrechnen bringen dir mehr als Zuschauen. Der Tutor stellt kleine Aufgaben zum Mitmachen.",
  },
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

/** Kleines „i“ mit Erklärtext bei Hover und Tastaturfokus. */
function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip" tabIndex={0} role="img" aria-label={text}>
      <span aria-hidden="true">i</span>
      <span className="info-tip-text" role="tooltip">
        {text}
      </span>
    </span>
  );
}

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
  const [industry, setIndustry] = useState<Industry>("neutral");
  // Preferences: shape the wording only, never the didactic settings.
  const [simplifiedLanguage, setSimplifiedLanguage] = useState(false);
  const [style, setStyle] = useState<PresentationStyle>("balanced");
  const [learnerType, setLearnerType] = useState<LearnerType>("none");
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
        retention_horizon: retention,
        industry,
        simplified_language: simplifiedLanguage,
        presentation_style: style,
        learner_type: learnerType,
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
            und jede Einstellung anpassen. Dazu drei Vorlieben zur Darstellung. Vor jedem Kapitel
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
              label="Wissensdauer"
              description="Wie lange musst du das Gelernte parat haben? Das bestimmt, in welchem Abstand der Tutor Wiederholungen vorschlägt."
              value={retention}
              options={RETENTION_OPTIONS}
              onChange={setRetention}
            />
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
            <div className="onboarding-field">
              <div>
                <div className="field-label">Lerntyp nach Vester</div>
                <div className="field-description">
                  Vorliebe, keine Lerneinstellung: wie du Neues am liebsten aufnimmst.
                  <InfoTip text="Frederic Vester unterscheidet Lerntypen nach dem Zugang, über den man Neues am liebsten aufnimmt. Das Modell ist verbreitet, ein Nutzen für den Lernerfolg ist aber nicht belegt — die Angabe ändert nur die Darbietung." />
                </div>
              </div>
              <div className="option-group" role="radiogroup" aria-label="Lerntyp nach Vester">
                {LEARNER_TYPE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="option-check">
                    <input
                      type="radio"
                      name="learner-type"
                      checked={learnerType === opt.value}
                      onChange={() => setLearnerType(opt.value)}
                    />
                    <span>{opt.label}</span>
                    <InfoTip text={opt.vester} />
                  </label>
                ))}
              </div>
            </div>
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
