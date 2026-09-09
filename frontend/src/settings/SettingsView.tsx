import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, createUser, listUsers, setUserRole, setUserStatus } from "../api/client";
import type { User, UserRole, UserStatus } from "../types";
import { CHAT_MODELS, CHAT_MODEL_GROUPS } from "./chatModel";

interface Props {
  chatModel: string;
  onChatModelChange: (id: string) => void;
  currentUserId: string;
}

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Administrator:in",
  learner: "Lernende:r",
};

const STATUS_LABEL: Record<UserStatus, string> = {
  pending: "Wartet auf Freigabe",
  approved: "Freigegeben",
  rejected: "Abgelehnt",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("de-DE");
}

export function SettingsView({ chatModel, onChatModelChange, currentUserId }: Props) {
  const current = CHAT_MODELS.find((m) => m.id === chatModel);

  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("admin");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listUsers()
      .then(setUsers)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, []);

  useEffect(refresh, [refresh]);

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createUser(newUsername.trim(), newPassword, newRole);
      setUsers((list) => [...(list ?? []), created]);
      setNewUsername("");
      setNewPassword("");
      setNewRole("admin");
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setCreating(false);
    }
  }

  async function run(userId: string, action: () => Promise<User>) {
    setBusyId(userId);
    setError(null);
    try {
      const updated = await action();
      setUsers((list) => (list ?? []).map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="settings-view">
      <div className="settings-shell">
        <div className="settings-kicker">Admin-Einstellungen</div>
        <h1 className="settings-title">Einstellungen</h1>

        <section className="settings-card">
          <h2>Chat-Modell</h2>
          <p className="settings-card-desc">
            Legt fest, welches Modell die Antworten des Tutors erzeugt. Die Regeln der
            Makro-Adaption bleiben davon unberührt.
          </p>
          <select
            className="model-select"
            aria-label="Chat-Modell"
            value={chatModel}
            onChange={(e) => onChatModelChange(e.target.value)}
          >
            {CHAT_MODEL_GROUPS.map((group) => (
              <optgroup label={group.provider} key={group.provider}>
                {group.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {current && (
            <p className="model-current">
              {current.blurb} <span className="model-slug">{current.id}</span>
            </p>
          )}
          <p className="settings-card-link">
            <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer noopener">
              Alle Modelle im OpenRouter-Katalog ansehen ↗
            </a>
          </p>
        </section>

        <section className="settings-card">
          <div className="settings-card-head">
            <div>
              <h2>Nutzerverwaltung</h2>
              <p className="settings-card-desc">
                Neue Registrierungen müssen hier freigegeben werden, bevor sich die Person anmelden
                kann.
              </p>
            </div>
            <button type="button" className="link-btn" onClick={refresh} disabled={busyId !== null}>
              Aktualisieren
            </button>
          </div>

          {error && <p className="error-banner">{error}</p>}

          <form className="create-user-form" onSubmit={(e) => void handleCreateUser(e)}>
            <input
              type="text"
              placeholder="Benutzername"
              aria-label="Benutzername"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              minLength={3}
              maxLength={32}
              required
              disabled={creating}
            />
            <input
              type="password"
              placeholder="Passwort"
              aria-label="Passwort"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              maxLength={128}
              required
              disabled={creating}
            />
            <select
              aria-label="Rolle"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as UserRole)}
              disabled={creating}
            >
              <option value="admin">Administrator:in</option>
              <option value="learner">Lernende:r</option>
            </select>
            <button type="submit" className="invite-btn" disabled={creating}>
              {creating ? "Wird angelegt …" : "Nutzer:in anlegen"}
            </button>
          </form>
          {createError && <p className="error-banner">{createError}</p>}

          <div className="user-table-wrap">
            <table className="user-table">
              <thead>
                <tr>
                  <th>Benutzername</th>
                  <th>Rolle</th>
                  <th>Status</th>
                  <th>Registriert</th>
                  <th aria-label="Aktionen" />
                </tr>
              </thead>
              <tbody>
                {users === null && (
                  <tr>
                    <td colSpan={5} className="user-status">
                      Wird geladen …
                    </td>
                  </tr>
                )}
                {users?.length === 0 && (
                  <tr>
                    <td colSpan={5} className="user-status">
                      Noch keine Nutzer:innen.
                    </td>
                  </tr>
                )}
                {users?.map((u) => {
                  const isSelf = u.id === currentUserId;
                  const busy = busyId === u.id;
                  return (
                    <tr key={u.id}>
                      <td>
                        {u.username}
                        {isSelf && <span className="user-self"> (du)</span>}
                      </td>
                      <td>
                        {isSelf ? (
                          <span className={"role-badge" + (u.role === "admin" ? " is-admin" : "")}>
                            {ROLE_LABEL[u.role]}
                          </span>
                        ) : (
                          <select
                            className="role-select"
                            aria-label={`Rolle von ${u.username}`}
                            value={u.role}
                            disabled={busy}
                            onChange={(e) =>
                              void run(u.id, () =>
                                setUserRole(u.id, e.target.value as UserRole),
                              )
                            }
                          >
                            <option value="learner">Lernende:r</option>
                            <option value="admin">Administrator:in</option>
                          </select>
                        )}
                      </td>
                      <td className={"user-status status-" + u.status}>{STATUS_LABEL[u.status]}</td>
                      <td className="user-status">{formatDate(u.created_at)}</td>
                      <td>
                        {isSelf ? null : (
                          <div className="user-actions">
                            {u.status !== "approved" && (
                              <button
                                type="button"
                                className="link-btn"
                                disabled={busy}
                                onClick={() =>
                                  void run(u.id, () => setUserStatus(u.id, "approved"))
                                }
                              >
                                Freigeben
                              </button>
                            )}
                            {u.status !== "rejected" && (
                              <button
                                type="button"
                                className="link-btn is-danger"
                                disabled={busy}
                                onClick={() =>
                                  void run(u.id, () => setUserStatus(u.id, "rejected"))
                                }
                              >
                                Ablehnen
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
