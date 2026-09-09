import { useState } from "react";
import { ApiError } from "../api/client";
import type { Theme } from "../theme";

interface Props {
  theme: Theme;
  username: string;
  onToggleTheme: () => void;
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>;
  onLogout: () => void;
}

/**
 * Shown instead of the app when the signed-in account still holds a one-time
 * password handed out by an admin. It cannot be dismissed -- the only ways
 * out are setting a new password or logging out.
 */
export function ChangePasswordScreen({ theme, username, onToggleTheme, onSubmit, onLogout }: Props) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && confirm !== newPassword;
  const canSubmit =
    currentPassword.length >= 8 &&
    newPassword.length >= 8 &&
    newPassword === confirm &&
    newPassword !== currentPassword;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(currentPassword, newPassword);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
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
            <button type="button" className="link-btn" onClick={onLogout}>
              Abmelden
            </button>
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

      <div className="auth-shell">
        <form className="auth-card" onSubmit={handleSubmit}>
          <h1>Neues Passwort festlegen</h1>
          <p>
            Das Konto <strong>{username}</strong> wurde mit einem temporären Passwort angelegt.
            Bitte vergib jetzt ein eigenes Passwort, um fortzufahren.
          </p>
          <label className="auth-field">
            <span>Temporäres Passwort</span>
            <input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              minLength={8}
              maxLength={128}
              required
            />
          </label>
          <label className="auth-field">
            <span>Neues Passwort</span>
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              maxLength={128}
              required
            />
            <span className="auth-hint">Mindestens 8 Zeichen, verschieden vom temporären Passwort.</span>
          </label>
          <label className="auth-field">
            <span>Neues Passwort bestätigen</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              minLength={8}
              maxLength={128}
              required
            />
            {mismatch && <span className="auth-hint">Die Passwörter stimmen nicht überein.</span>}
          </label>

          {error && <p className="error-banner">{error}</p>}

          <button type="submit" className="primary" disabled={busy || !canSubmit}>
            {busy ? "Bitte warten …" : "Passwort speichern"}
          </button>
        </form>
      </div>
    </div>
  );
}
