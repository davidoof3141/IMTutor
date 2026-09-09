import { useEffect, useMemo, useState } from "react";
import { ApiError, listConversations } from "../api/client";
import type { Chapter, Conversation } from "../types";

interface Props {
  learnerId: string;
  curriculum: Chapter[];
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onClose: () => void;
}

const dayFmt = new Intl.DateTimeFormat("de-DE", {
  weekday: "short",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const timeFmt = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });

function chapterLabel(conversation: Conversation, curriculum: Chapter[]): string {
  if (conversation.mode !== "training" || !conversation.chapter_number) return "Freie Erkundung";
  const chapter = curriculum.find((c) => c.number === conversation.chapter_number);
  if (!chapter) return `Kapitel ${conversation.chapter_number}`;
  const section = chapter.sections.find((s) => s.number === conversation.section_number);
  return `Kapitel ${chapter.number}: ${chapter.title}` + (section ? ` – ${section.number}` : "");
}

interface DayGroup {
  key: string;
  label: string;
  conversations: Conversation[];
}

function groupByDay(conversations: Conversation[]): DayGroup[] {
  const groups = new Map<string, DayGroup>();
  for (const conversation of conversations) {
    const date = new Date(conversation.last_message_at);
    const key = date.toISOString().slice(0, 10);
    let group = groups.get(key);
    if (!group) {
      group = { key, label: dayFmt.format(date), conversations: [] };
      groups.set(key, group);
    }
    group.conversations.push(conversation);
  }
  return [...groups.values()].sort((a, b) => b.key.localeCompare(a.key));
}

export function HistorySidebar({
  learnerId,
  curriculum,
  activeConversationId,
  onSelect,
  onClose,
}: Props) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    listConversations(learnerId)
      .then((r) => {
        if (!cancelled) setConversations(r);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [learnerId]);

  const groups = useMemo(
    () => (conversations ? groupByDay(conversations) : []),
    [conversations],
  );

  return (
    <>
      <div className="history-backdrop" onClick={onClose} />
      <aside
        className="history-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="Gesprächsverlauf"
      >
        <header className="history-header">
          <h2>Gesprächsverlauf</h2>
          <button
            type="button"
            className="history-close"
            aria-label="Verlauf schließen"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className="history-body">
          {error && <p className="error-banner">{error}</p>}
          {!error && conversations === null && (
            <p className="history-hint">Verlauf wird geladen …</p>
          )}
          {!error && conversations !== null && conversations.length === 0 && (
            <p className="history-hint">Noch keine Gespräche.</p>
          )}

          {groups.map((group) => (
            <section key={group.key} className="history-day">
              <h3 className="history-day-label">{group.label}</h3>
              {group.conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  className={
                    "history-turn" +
                    (conversation.id === activeConversationId ? " is-active" : "")
                  }
                  onClick={() => onSelect(conversation.id)}
                >
                  <div className="history-turn-meta">
                    <span className="history-chapter">
                      {chapterLabel(conversation, curriculum)}
                    </span>
                    <span className="history-time">
                      {timeFmt.format(new Date(conversation.last_message_at))}
                    </span>
                  </div>
                  <p className="history-prompt">
                    {conversation.title ?? "Neues Gespräch"}
                  </p>
                  <p className="history-completion">
                    {conversation.message_count}{" "}
                    {conversation.message_count === 1 ? "Nachricht" : "Nachrichten"}
                  </p>
                </button>
              ))}
            </section>
          ))}
        </div>
      </aside>
    </>
  );
}
