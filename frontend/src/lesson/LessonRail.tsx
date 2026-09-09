import { useState } from "react";
import type { LessonResponse, LessonStep, LessonStepKind, StudyModeState } from "../types";

interface Props {
  studyMode: StudyModeState;
  lesson: LessonResponse | null;
  busy: boolean;
  error: string | null;
  onCreate: () => void;
  onAdvance: () => void;
  onAbandon: () => void;
}

const KIND_LABEL: Record<LessonStepKind, string> = {
  explain: "Erklärung",
  example: "Beispiel",
  checkpoint: "Verständnischeck",
  recap: "Zusammenfassung",
};

function stepPosition(steps: LessonStep[], index: number): { position: number; total: number } {
  const kind = steps[index].kind;
  const sameKind = steps.filter((s) => s.kind === kind);
  const position = sameKind.findIndex((s) => s.index === index) + 1;
  return { position, total: sameKind.length };
}

/** "explanation_depth=4" -> "explanation_depth = 4"; the fixed "always" for
 * recap stays as a plain sentence. */
function formatRationale(raw: string | undefined): string {
  if (!raw) return "";
  if (raw === "always") return "Fester Bestandteil jeder Lektion.";
  return raw.replace("=", " = ");
}

export function LessonRail({ studyMode, lesson, busy, error, onCreate, onAdvance, onAbandon }: Props) {
  const [openStep, setOpenStep] = useState<number | null>(null);

  if (studyMode.mode !== "training" || !studyMode.chapter_number) {
    return null;
  }

  if (!lesson) {
    return (
      <div className="panel lesson-rail">
        <div className="lesson-rail-head">
          <span className="lesson-rail-title">Lektion</span>
        </div>
        <p className="muted-note">Noch keine Lektion für dieses Kapitel gestartet.</p>
        <button
          type="button"
          className="primary lesson-start-btn"
          disabled={busy}
          onClick={onCreate}
        >
          {busy ? "Wird geplant …" : "Lektion starten"}
        </button>
        {error && <p className="error-banner">{error}</p>}
      </div>
    );
  }

  const { plan, rationale, current_step: currentStep, status } = lesson;

  return (
    <div className="panel lesson-rail">
      <div className="lesson-rail-head">
        <span className="lesson-rail-title">Lektion</span>
        {status === "active" && (
          <button
            type="button"
            className="link-btn is-danger"
            disabled={busy}
            onClick={onAbandon}
          >
            Abbrechen
          </button>
        )}
      </div>

      <ol className="lesson-steps">
        {plan.steps.map((step) => {
          const state = step.index < currentStep ? "done" : step.index === currentStep ? "active" : "pending";
          const { position, total } = stepPosition(plan.steps, step.index);
          const isOpen = openStep === step.index;
          return (
            <li key={step.index} className={`lesson-step is-${state}`}>
              <button
                type="button"
                className="lesson-step-row"
                aria-expanded={isOpen}
                onClick={() => setOpenStep(isOpen ? null : step.index)}
              >
                <span className="lesson-step-marker" aria-hidden="true">
                  {state === "done" ? "✓" : step.index + 1}
                </span>
                <span className="lesson-step-label">
                  {KIND_LABEL[step.kind]} {position}/{total} · S. {step.section_ref}
                </span>
              </button>
              {isOpen && (
                <p className="lesson-step-rationale">
                  {KIND_LABEL[step.kind]} {position} von {total} —{" "}
                  {formatRationale(rationale[String(step.index)])} (S. {step.page_start}–
                  {step.page_end})
                </p>
              )}
            </li>
          );
        })}
      </ol>

      {status === "completed" && <p className="lesson-complete-banner">Lektion abgeschlossen</p>}
      {status === "abandoned" && <p className="muted-note">Lektion abgebrochen.</p>}

      {status === "active" ? (
        <button type="button" className="primary lesson-advance-btn" disabled={busy} onClick={onAdvance}>
          {busy ? "…" : "Weiter"}
        </button>
      ) : (
        <button type="button" className="lesson-start-btn" disabled={busy} onClick={onCreate}>
          Neue Lektion starten
        </button>
      )}
      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}
