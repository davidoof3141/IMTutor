import { useState } from "react";

interface Props {
  username: string;
  link: string;
  onClose: () => void;
}

/** Shows a freshly (re-)generated login link once. The raw token only ever
 * exists in this response -- the server keeps just its hash -- so this is
 * the only place it can be copied from. */
export function LinkResultModal({ username, link, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API unavailable -- the field itself is still selectable
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="link-result-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="link-result-title">Link für {username}</h2>
          <button type="button" className="modal-close" aria-label="Schließen" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          <label className="form-field">
            <span>Anmeldelink</span>
            <div className="link-result-field">
              <input type="text" readOnly value={link} onFocus={(e) => e.target.select()} />
              <button type="button" className="link-btn copy-btn" onClick={() => void handleCopy()}>
                {copied ? "Kopiert ✓" : "Kopieren"}
              </button>
            </div>
            <span className="link-warning">
              Dieser Link wird nur jetzt angezeigt. Über ihn kann sich die Person ohne Passwort
              anmelden -- an sie weitergeben, nicht öffentlich teilen.
            </span>
          </label>

          <div className="modal-actions">
            <button type="button" className="invite-btn" onClick={onClose}>
              Fertig
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
