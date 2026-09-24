import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { BookImageRef, ReasonTag, VariantLabel } from "../types";
import { REASON_LABELS, REASON_ORDER } from "./reasonLabels";

export interface ComparisonVariantState {
  text: string;
  done: boolean;
}

export interface ComparisonState {
  comparisonId: string | null;
  conversationId: string | null;
  a: ComparisonVariantState;
  b: ComparisonVariantState;
  bookImages: BookImageRef[];
  pageRefs: number[];
  picked: VariantLabel | null;
  reasons: Set<ReasonTag>;
  otherReason: string;
  submitting: boolean;
  error: string | null;
}

interface Props {
  comparison: ComparisonState;
  onPick: (variant: VariantLabel) => void;
  onToggleReason: (reason: ReasonTag) => void;
  onOtherReasonChange: (value: string) => void;
  onConfirm: () => void;
}

function VariantColumn({
  label,
  variant,
  picked,
  bothDone,
  onPick,
}: {
  label: string;
  variant: ComparisonVariantState;
  picked: boolean;
  bothDone: boolean;
  onPick: () => void;
}) {
  return (
    <div className={"comparison-column" + (picked ? " picked" : "")}>
      <div className="chat-message tutor comparison-variant">
        <span className="chat-intro-label">{label}</span>
        {variant.text ? (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{variant.text}</ReactMarkdown>
          </div>
        ) : (
          !variant.done && "…"
        )}
      </div>
      <button
        type="button"
        className={"invite-btn comparison-pick-btn" + (picked ? " is-picked" : "")}
        disabled={!bothDone}
        onClick={onPick}
      >
        {picked ? "Ausgewählt ✓" : "Diese Antwort bevorzugen"}
      </button>
    </div>
  );
}

/** The side-by-side personalized-vs-generic reply for one turn, shown to
 * link-invited accounts (see backend app/api/chat.py's /compare route).
 * Nothing here is added to the conversation until a favorite and at least
 * one reason are picked. */
export function ComparisonTurn({
  comparison,
  onPick,
  onToggleReason,
  onOtherReasonChange,
  onConfirm,
}: Props) {
  const bothDone = comparison.a.done && comparison.b.done;
  const canConfirm =
    comparison.picked !== null &&
    comparison.reasons.size > 0 &&
    (!comparison.reasons.has("other") || comparison.otherReason.trim().length > 0) &&
    !comparison.submitting;

  return (
    <div className="comparison-turn">
      <span className="comparison-label">
        Zwei Antworten im Vergleich -- wähle deine bevorzugte
      </span>
      <div className="comparison-columns">
        <VariantColumn
          label="Antwort A"
          variant={comparison.a}
          picked={comparison.picked === "a"}
          bothDone={bothDone}
          onPick={() => onPick("a")}
        />
        <VariantColumn
          label="Antwort B"
          variant={comparison.b}
          picked={comparison.picked === "b"}
          bothDone={bothDone}
          onPick={() => onPick("b")}
        />
      </div>

      {comparison.picked !== null && (
        <div className="comparison-reasons-panel">
          <span className="comparison-label">Warum bevorzugst du diese Antwort?</span>
          <div className="comparison-reasons">
            {REASON_ORDER.map((reason) => (
              <button
                key={reason}
                type="button"
                className={"reason-chip" + (comparison.reasons.has(reason) ? " active" : "")}
                aria-pressed={comparison.reasons.has(reason)}
                onClick={() => onToggleReason(reason)}
                disabled={comparison.submitting}
              >
                {REASON_LABELS[reason]}
              </button>
            ))}
          </div>
          {comparison.reasons.has("other") && (
            <input
              type="text"
              className="comparison-other-input"
              placeholder="Was hat konkret gefehlt oder überzeugt?"
              value={comparison.otherReason}
              onChange={(e) => onOtherReasonChange(e.target.value)}
              maxLength={500}
              disabled={comparison.submitting}
            />
          )}
          {comparison.error && <p className="error-banner">{comparison.error}</p>}
          <div className="comparison-confirm-row">
            <button
              type="button"
              className="primary"
              disabled={!canConfirm}
              onClick={onConfirm}
            >
              {comparison.submitting ? "Wird gespeichert …" : "Bestätigen"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
