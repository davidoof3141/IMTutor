import { useState } from "react";
import { ApiError, onboard } from "../api/client";
import type { Theme } from "../theme";
import type {
  Goal,
  LearnerType,
  OnboardingResponse,
  PriorExperience,
  Role,
  StudyTime,
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

const STUDY_TIME_OPTIONS: { value: StudyTime; label: string }[] = [
  { value: "under_2h", label: "Unter 2 Std./Woche" },
  { value: "2_to_4h", label: "2–4 Std./Woche" },
  { value: "over_4h", label: "Über 4 Std./Woche" },
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
}

function OnboardingField<T extends string>({
  label,
  description,
  value,
  options,
  onChange,
}: FieldProps<T>) {
  return (
    <div className="onboarding-field">
      <div>
        <div className="field-label">{label}</div>
        <div className="field-description">{description}</div>
      </div>
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
    </div>
  );
}

export function OnboardingForm({ onComplete, theme, onToggleTheme }: Props) {
  const [role, setRole] = useState<Role>("practitioner");
  const [priorExperience, setPriorExperience] = useState<PriorExperience>("none");
  const [goal, setGoal] = useState<Goal>("applied_competence");
  const [studyTime, setStudyTime] = useState<StudyTime>("2_to_4h");
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
        study_time: studyTime,
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
              label="Lernzeit"
              description="Wie viel Zeit kannst du pro Woche lernen?"
              value={studyTime}
              options={STUDY_TIME_OPTIONS}
              onChange={setStudyTime}
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
