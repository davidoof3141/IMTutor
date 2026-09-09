import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, createUser } from "../api/client";
import type { User, UserRole } from "../types";

interface Props {
  onClose: () => void;
  onCreated: (user: User) => void;
}

/** Modal form for the admin "create user" shortcut: username + password, a
 * role choice, and an optional one-time-password toggle. */
export function CreateUserModal({ onClose, onCreated }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [role, setRole] = useState<UserRole>("learner");
  const [temporary, setTemporary] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const canSubmit = username.trim().length >= 3 && password.length >= 8;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy || !canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createUser(username.trim(), password, role, temporary);
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-user-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="create-user-title">Nutzer:in anlegen</h2>
          <button type="button" className="modal-close" aria-label="Schließen" onClick={onClose}>
            ✕
          </button>
        </div>

        <form className="modal-body" onSubmit={handleSubmit}>
          <label className="form-field">
            <span>Benutzername</span>
            <input
              ref={firstFieldRef}
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              minLength={3}
              maxLength={32}
              required
              disabled={busy}
            />
          </label>

          <label className="form-field">
            <span>Passwort</span>
            <div className="input-with-toggle">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                maxLength={128}
                required
                disabled={busy}
              />
              <button
                type="button"
                className="reveal-btn"
                aria-pressed={showPassword}
                aria-label={showPassword ? "Passwort verbergen" : "Passwort anzeigen"}
                title={showPassword ? "Passwort verbergen" : "Passwort anzeigen"}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
            <span className="form-hint">Mindestens 8 Zeichen.</span>
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

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={temporary}
              onChange={(e) => setTemporary(e.target.checked)}
              disabled={busy}
            />
            <span>
              Temporäres Passwort
              <span className="form-hint">
                Die Person muss das Passwort nach der ersten Anmeldung ändern.
              </span>
            </span>
          </label>

          {error && <p className="error-banner">{error}</p>}

          <div className="modal-actions">
            <button type="button" className="link-btn" onClick={onClose} disabled={busy}>
              Abbrechen
            </button>
            <button type="submit" className="invite-btn" disabled={busy || !canSubmit}>
              {busy ? "Wird angelegt …" : "Anlegen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
