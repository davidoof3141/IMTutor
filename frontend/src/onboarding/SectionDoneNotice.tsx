/** Questions (with a picked answer) required per subchapter. */
export const QUESTIONS_PER_SECTION = 2;

const SECTION_ORDER = ["4.1", "4.2", "4.3"];

interface Props {
  section: string;
  error: string | null;
  onContinue: (nextSection: string) => void;
  onDismiss: () => void;
}

/** Shown once a link-invited participant has asked their 2 questions in a
 * subchapter: points them to the next subchapter, or thanks them after the
 * last one. */
export function SectionDoneNotice({ section, error, onContinue, onDismiss }: Props) {
  const next = SECTION_ORDER[SECTION_ORDER.indexOf(section) + 1];

  return (
    <div className="section-done-notice" role="status">
      <div className="section-done-text">
        {next ? (
          <>
            <strong>Unterkapitel {section} geschafft ✓</strong> Du hast {QUESTIONS_PER_SECTION} Fragen
            gestellt. Du kannst jetzt mit Unterkapitel {next} weitermachen.
          </>
        ) : (
          <>
            <strong>Geschafft ✓</strong> Du hast in allen Unterkapiteln {QUESTIONS_PER_SECTION} Fragen
            gestellt. Vielen Dank für deine Teilnahme!
          </>
        )}
        {error && <span className="section-done-error"> {error}</span>}
      </div>
      <div className="section-done-actions">
        {next && (
          <button type="button" className="invite-btn" onClick={() => onContinue(next)}>
            Weiter zu {next}
          </button>
        )}
        <button type="button" className="link-btn" onClick={onDismiss}>
          Schließen
        </button>
      </div>
    </div>
  );
}
