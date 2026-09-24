import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, buildLoginLinkUrl, createLinkUser } from "../api/client";
import type { LinkUserResponse, UserRole } from "../types";
import { LinkResultModal } from "./LinkResultModal";

interface Props {
  onClose: () => void;
  onCreated: (result: LinkUserResponse) => void;
}

/** Modal for the admin "create link user" shortcut: no password is set at
 * all -- the account is reached only through the generated login link. */
export function CreateLinkUserModal({ onClose, onCreated }: Props) {
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<UserRole>("learner");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LinkUserResponse | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !result) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, result]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createLinkUser(username.trim() || null, role);
      onCreated(created);
      setResult(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <LinkResultModal
        username={result.user.username}
        link={buildLoginLinkUrl(result.link_token)}
        onClose={onClose}
      />
    );
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-link-user-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="create-link-user-title">Nutzer:in mit Link anlegen</h2>
          <button type="button" className="modal-close" aria-label="Schließen" onClick={onClose}>
            ✕
          </button>
        </div>

        <form className="modal-body" onSubmit={handleSubmit}>
          <label className="form-field">
            <span>Benutzername (optional)</span>
            <input
              ref={firstFieldRef}
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              minLength={3}
              maxLength={32}
              placeholder="wird sonst automatisch vergeben"
              disabled={busy}
            />
          </label>

          <label className="form-field">
            <span>Rolle</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              disabled={busy}
            >
              <option value="learner">Lernende:r</option>
              <option value="admin">Administrator:in</option>
            </select>
          </label>

          <span className="form-hint">
            Es wird kein Passwort vergeben -- die Person meldet sich ausschließlich über den
            erzeugten Link an.
          </span>

          {error && <p className="error-banner">{error}</p>}

          <div className="modal-actions">
            <button type="button" className="link-btn" onClick={onClose} disabled={busy}>
              Abbrechen
            </button>
            <button type="submit" className="invite-btn" disabled={busy}>
              {busy ? "Wird angelegt …" : "Link erzeugen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
