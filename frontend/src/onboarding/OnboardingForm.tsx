import { useState } from "react";
import { ApiError, onboard } from "../api/client";
import type { Theme } from "../theme";
import type {
  Goal,
  Industry,
  LearnerType,
  OnboardingResponse,
  PriorExperience,
  Role,
} from "../types";

interface Props {
  onComplete: (result: OnboardingResponse) => void;
  theme: Theme;
  onToggleTheme: () => void;
}

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "practitioner", label: "Praktiker:in" },
  { value: "analyst", label: "Analyst:in" },
  { value: "academic", label: "Wissenschaft" },
];

const PRIOR_EXPERIENCE_OPTIONS: { value: PriorExperience; label: string }[] = [
  { value: "none", label: "Keine" },
  { value: "low", label: "Gering" },
  { value: "moderate", label: "Mittel" },
  { value: "high", label: "Hoch" },
];

const GOAL_OPTIONS: { value: Goal; label: string }[] = [
  { value: "certification", label: "Zertifikat bestehen" },
  { value: "applied_competence", label: "Anwendung im Beruf" },
  { value: "orientation", label: "Überblick gewinnen" },
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

const LEARNER_TYPE_OPTIONS: { value: LearnerType; label: string }[] = [
  { value: "visuell", label: "Visuell" },
  { value: "auditiv", label: "Auditiv" },
  { value: "kommunikativ", label: "Kommunikativ" },
  { value: "motorisch", label: "Motorisch" },
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
  const [role, setRole] = useState<Role>("practitioner");
  const [priorExperience, setPriorExperience] = useState<PriorExperience>("none");
  const [goal, setGoal] = useState<Goal>("applied_competence");
  const [industry, setIndustry] = useState<Industry>("neutral");
  const [learnerType, setLearnerType] = useState<LearnerType>("kommunikativ");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await onboard({
        role,
        prior_experience: priorExperience,
        goal,
        industry,
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
            Fünf Fragen stellen deinen Tutor ein. Jede Antwort steuert eine Einstellung, an die
            sich der Tutor hält — du kannst später jederzeit nachvollziehen, wie sie zustande kam,
            und jede Einstellung anpassen.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="onboarding-card">
            <OnboardingField
              label="Rolle"
              description="Was beschreibt dich am besten?"
              value={role}
              options={ROLE_OPTIONS}
              onChange={setRole}
            />
            <OnboardingField
              label="Vorwissen"
              description="Wie vertraut bist du mit Informationsmanagement?"
              value={priorExperience}
              options={PRIOR_EXPERIENCE_OPTIONS}
              onChange={setPriorExperience}
            />
            <OnboardingField
              label="Ziel"
              description="Was möchtest du mit diesem Kurs erreichen?"
              value={goal}
              options={GOAL_OPTIONS}
              onChange={setGoal}
            />
            <OnboardingField
              label="Branche"
              description="In welchem Umfeld arbeitest du? Die Beispiele des Tutors kommen aus dieser Branche."
              value={industry}
              options={INDUSTRY_OPTIONS}
              onChange={setIndustry}
              dropdown
            />
            <OnboardingField
              label="Lerntyp"
              description="Wie nimmst du neuen Stoff am liebsten auf?"
              value={learnerType}
              options={LEARNER_TYPE_OPTIONS}
              onChange={setLearnerType}
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
