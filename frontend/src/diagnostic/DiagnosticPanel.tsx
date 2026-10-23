import { useState } from "react";
import {
  ApiError,
  submitDiagnostic,
} from "../api/client";
import { PARAMS } from "../tutor-setup/params";
import type { DiagnosticItem, DiagnosticResult } from "../types";

const LEVEL_WORDS: Record<string, string> = {
  none: "Keine",
  low: "Gering",
  moderate: "Mittel",
  high: "Hoch",
};

interface QuizProps {
  learnerId: string;
  title: string;
  items: DiagnosticItem[];
  onSubmitted: (result: DiagnosticResult) => void;
}

/** Wissenscheck VOR dem Unterricht. Keine Rückmeldung zu einzelnen Antworten:
 *  das Ergebnis bestimmt nur das Vorwissen dieses Kapitels (Tabellen-Lookup). */
export function DiagnosticQuiz({ learnerId, title, items, onSubmitted }: QuizProps) {
  const [answers, setAnswers] = useState<(number | null)[]>(() => items.map(() => null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const complete = answers.every((a) => a !== null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!complete) return;
    setBusy(true);
    setError(null);
    try {
      onSubmitted(await submitDiagnostic(learnerId, answers as number[]));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="diagnostic" onSubmit={handleSubmit}>
      <div className="kicker">Wissenscheck</div>
      <h2>{title}</h2>
      <p className="muted-note">
        {items.length} kurze Fragen, bevor es losgeht. Das Ergebnis stellt nur ein, wie der Tutor
        dieses Kapitel erklärt — es wird nicht bewertet. „Ich weiß es nicht“ ist jederzeit eine
        gültige Antwort. Du kannst den Check nicht wiederholen.
      </p>
      {items.map((item, i) => (
        <fieldset className="diagnostic-item" key={i}>
          <legend>
            {i + 1}. {item.stem}
          </legend>
          {item.options.map((opt, j) => (
            <label className="option-check" key={j}>
              <input
                type="radio"
                name={`diag-${i}`}
                checked={answers[i] === j}
                onChange={() => setAnswers((prev) => prev.map((a, k) => (k === i ? j : a)))}
              />
              <span>{opt.text}</span>
            </label>
          ))}
        </fieldset>
      ))}
      {error && <p className="error-banner">{error}</p>}
      <div className="onboarding-actions">
        <button type="submit" className="primary" disabled={!complete || busy}>
          {busy ? "Wird ausgewertet …" : "Check abschließen →"}
        </button>
      </div>
    </form>
  );
}

interface SummaryProps {
  learnerId: string;
  title: string;
  result: DiagnosticResult;
  onResultChange: (result: DiagnosticResult) => void;
  onContinue: () => void;
}

/** Ergebnis und Kapitel-Einstellungen, mit Override je Feld (DR6), vor dem Unterricht. */
export function DiagnosticSummary({
  title,
  result,
  onContinue,
}: SummaryProps) {
  return (
    <div className="diagnostic">
      <div className="kicker">Dein Start in dieses Kapitel</div>
      <h2>{title}</h2>
      <p>
        {result.correct_count} von {result.item_count} richtig → Vorwissen für dieses Kapitel:{" "}
        <strong>{LEVEL_WORDS[result.prior_knowledge]}</strong>. Dein Startwert aus dem Profil war{" "}
        {LEVEL_WORDS[result.experience_seed]}; er bleibt unverändert und gilt weiter für Kapitel
        ohne Check.
      </p>
      <p className="muted-note">
        So ist dein Tutor für dieses Kapitel eingestellt. Während des Unterrichts ändert sich
        nichts mehr automatisch.
      </p>
      <div className="setting-list">
        {PARAMS.map((meta) => {
          const value = result.effective[meta.key];
          const changed = meta.key in result.override;
          return (
            <div className="setting" key={meta.key}>
              <div className="setting-head">
                <span className="setting-name">{meta.name}</span>
                <span
                  className={
                    "setting-tag " +
                    (changed
                      ? "is-changed"
                      : result.attribution[meta.key] !== "default"
                        ? "is-rule"
                        : "is-default")
                  }
                >
                  {changed
                    ? "Von dir geändert"
                    : result.attribution[meta.key] !== "default"
                      ? "Aus deinen Angaben"
                      : "Standard"}
                </span>
              </div>
              <div className="setting-control">
                {meta.labels[meta.options.findIndex((o) => String(o) === String(value))] ??
                  String(value)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="onboarding-actions">
        <button type="button" className="primary" onClick={onContinue}>
          Weiter zum Unterricht →
        </button>
      </div>
    </div>
  );
}
