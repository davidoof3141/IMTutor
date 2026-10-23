import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  buildGroupJoinUrl,
  createGroupLink,
  listGroupLinks,
  revokeGroupLink,
  type GroupLink,
} from "../api/client";
import { LinkResultModal } from "./LinkResultModal";

function statusOf(link: GroupLink): string {
  if (link.revoked) return "Deaktiviert";
  if (new Date(link.expires_at) <= new Date()) return "Abgelaufen";
  if (link.uses >= link.max_uses) return "Voll";
  return "Aktiv";
}

/** Admin card for shared sign-up links: one URL for a whole group, where each
 * visitor gets their own test account. The cap on sign-ups, the expiry and the
 * revoke button are what bound the cost of a link that leaks. */
export function GroupLinks() {
  const [links, setLinks] = useState<GroupLink[] | null>(null);
  const [label, setLabel] = useState("");
  const [maxUses, setMaxUses] = useState(30);
  const [days, setDays] = useState(14);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ label: string; url: string } | null>(null);

  const refresh = useCallback(() => {
    listGroupLinks()
      .then(setLinks)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, []);

  useEffect(refresh, [refresh]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await createGroupLink(label.trim(), maxUses, days);
      setCreated({ label: result.link.label, url: buildGroupJoinUrl(result.token) });
      setLabel("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(id: string) {
    setError(null);
    try {
      await revokeGroupLink(id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    }
  }

  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <div>
          <h2>Gruppenlinks</h2>
          <p className="settings-card-desc">
            Ein Link für eine ganze Gruppe: Jede Person, die ihn öffnet, bekommt ein eigenes
            Testkonto. Die maximale Anzahl an Konten begrenzt, was ein weitergeleiteter Link
            kosten kann.
          </p>
        </div>
      </div>

      <form className="group-link-form" onSubmit={handleCreate}>
        <label className="form-field">
          <span>Bezeichnung</span>
          <input
            type="text"
            value={label}
            maxLength={80}
            placeholder="z. B. Kurs A"
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <label className="form-field">
          <span>Max. Konten</span>
          <input
            type="number"
            min={1}
            max={500}
            value={maxUses}
            onChange={(e) => setMaxUses(Number(e.target.value))}
          />
        </label>
        <label className="form-field">
          <span>Gültig (Tage)</span>
          <input
            type="number"
            min={1}
            max={90}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </label>
        <button
          type="submit"
          className="invite-btn"
          disabled={busy || maxUses < 1 || days < 1}
        >
          Gruppenlink erstellen
        </button>
      </form>

      {error && <p className="error-banner">{error}</p>}

      {links && links.length > 0 && (
        <div className="user-table-wrap">
          <table className="user-table">
            <thead>
              <tr>
                <th>Bezeichnung</th>
                <th>Konten</th>
                <th>Läuft ab</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {links.map((link) => (
                <tr key={link.id}>
                  <td>{link.label || "–"}</td>
                  <td>
                    {link.uses} / {link.max_uses}
                  </td>
                  <td>{new Date(link.expires_at).toLocaleDateString("de-DE")}</td>
                  <td>{statusOf(link)}</td>
                  <td>
                    {statusOf(link) === "Aktiv" && (
                      <button
                        type="button"
                        className="link-btn is-danger"
                        onClick={() => void handleRevoke(link.id)}
                      >
                        Deaktivieren
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {created && (
        <LinkResultModal
          username=""
          title={created.label ? `Gruppenlink: ${created.label}` : "Gruppenlink"}
          warning="Dieser Link wird nur jetzt angezeigt. Er kann an die ganze Gruppe geschickt werden; jede Person bekommt damit ein eigenes Konto. Geht er verloren oder in falsche Hände, deaktiviere ihn in der Liste."
          link={created.url}
          onClose={() => setCreated(null)}
        />
      )}
    </section>
  );
}
