import { useState } from "react";
import { ApiError } from "../api/client";
import type { Theme } from "../theme";

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
  onLogin: (username: string, password: string) => Promise<void>;
  onRegister: (username: string, password: string) => Promise<{ status: string }>;
  /** Set when a login-link URL failed to sign the visitor in automatically. */
  linkError?: string | null;
}

type Mode = "login" | "register";

export function AuthScreen({ theme, onToggleTheme, onLogin, onRegister, linkError }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setRegistered(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await onLogin(username.trim(), password);
      } else {
        await onRegister(username.trim(), password);
        setRegistered(true);
        setPassword("");
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.",
      );
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = username.trim().length >= 3 && password.length >= 8;

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

      <div className="auth-shell">
        {linkError && <p className="error-banner">{linkError}</p>}
        <div className="segmented auth-tabs" role="tablist" aria-label="Anmelden oder registrieren">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={"segmented-option" + (mode === "login" ? " active" : "")}
            onClick={() => switchMode("login")}
          >
            Anmelden
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={"segmented-option" + (mode === "register" ? " active" : "")}
            onClick={() => switchMode("register")}
          >
            Registrieren
          </button>
        </div>

        {registered ? (
          <div className="auth-card">
            <h1>Fast geschafft</h1>
            <p>
              Dein Konto <strong>{username.trim()}</strong> wurde angelegt und wartet nun auf die
              Freigabe durch eine:n Administrator:in. Danach kannst du dich anmelden.
            </p>
            <button type="button" className="primary" onClick={() => switchMode("login")}>
              Zur Anmeldung
            </button>
          </div>
        ) : (
          <form className="auth-card" onSubmit={handleSubmit}>
            <h1>{mode === "login" ? "Anmelden" : "Konto erstellen"}</h1>
            <label className="auth-field">
              <span>Benutzername</span>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                maxLength={32}
                required
              />
            </label>
            <label className="auth-field">
              <span>Passwort</span>
              <input
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
              {mode === "register" && (
                <span className="auth-hint">Mindestens 8 Zeichen.</span>
              )}
            </label>

            {error && <p className="error-banner">{error}</p>}

            <button type="submit" className="primary" disabled={busy || !canSubmit}>
              {busy
                ? "Bitte warten …"
                : mode === "login"
                  ? "Anmelden"
                  : "Registrieren"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
