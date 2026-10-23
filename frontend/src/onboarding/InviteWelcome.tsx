import { useState } from "react";

function storageKey(userId: string): string {
  return `itm-invite-welcome-seen:${userId}`;
}

export function hasSeenInviteWelcome(userId: string): boolean {
  try {
    return localStorage.getItem(storageKey(userId)) === "1";
  } catch {
    return true; // fail closed -- don't nag if storage is unavailable
  }
}

interface Props {
  userId: string;
  onClose: () => void;
}

/** One-time welcome for link-invited study participants: what the study is,
 * how long it takes, and what is expected of them. */
export function InviteWelcome({ userId, onClose }: Props) {
  const [open, setOpen] = useState(() => !hasSeenInviteWelcome(userId));

  function close() {
    try {
      localStorage.setItem(storageKey(userId), "1");
    } catch {
      // ignore
    }
    setOpen(false);
    onClose();
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="invite-welcome-title">
        <div className="modal-header">
          <h2 id="invite-welcome-title">Willkommen beim ITM Tutor</h2>
        </div>
        <div className="modal-body">
          <p>
            Schön, dass du mitmachst! Der ITM Tutor ist ein KI-Tutor, der dir beim Lernen des
            Stoffs aus dem Buch hilft. In dieser Testversion vergleichen wir zwei Antworten auf
            jede deiner Fragen und möchten von dir wissen, welche dir besser weiterhilft.
          </p>
          <p>
            <strong>Dauer:</strong> Die Teilnahme dauert etwa 15–20 Minuten.
          </p>
          <p>
            <strong>Deine Aufgabe:</strong> Stelle bitte mindestens <strong>2 Fragen pro
            Unterkapitel</strong> (4.1, 4.2 und 4.3) und wähle jeweils die Antwort, die dir
            besser gefällt.
            Du kannst dafür eigene Fragen eintippen oder einen der vorgeschlagenen
            Fragevorschläge (die Kacheln über dem Eingabefeld) anklicken.
          </p>
          <p>
            <strong>Wichtig:</strong> Du musst die Fragen, die dir der Tutor stellt, nicht
            beantworten. Stelle einfach weitere Fragen oder Folgefragen denn bei dieser
            Studie geht es um deine persönliche Präferenz, nicht um dein Wissen.
          </p>
          <p>
            <strong>Zum Einstieg:</strong> Zuerst richtest du kurz dein Lernprofil ein
            (ein paar Fragen zu dir und deinen Vorlieben). Danach folgt ein kurzer
            Diagnosetest, damit sich der Tutor auf dein Vorwissen einstellen kann.
          </p>
          <div className="modal-actions">
            <button type="button" className="invite-btn" onClick={close}>
              Los geht's
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
