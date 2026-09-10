import { Fragment, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ApiError,
  fetchAttachmentObjectUrl,
  fetchBookImageObjectUrl,
  getBookPdfObjectUrl,
  getChapterIntro,
  getConversationMessages,
  getFollowUpSuggestions,
  streamChatMessage,
  uploadAttachment,
} from "../api/client";
import type { Attachment, BookImageRef, StudyModeState } from "../types";

// Generic fallback shown above the input before the learner has said anything.
// In training mode the chapter/section's own pre-generated starter questions
// (from the intro manifest) are used instead; this is what's shown in free
// exploration and if a manifest entry has no starters. The LLM only takes
// over once there's a real reply to base follow-ups on (see `suggestions`).
const STARTER_QUESTIONS = [
  "Kannst du mir das Thema kurz erklären?",
  "Welche Grundbegriffe sollte ich zuerst kennen?",
  "Kannst du mir ein Praxisbeispiel geben?",
];

const ACCEPTED_ATTACHMENT_TYPES =
  "image/png,image/jpeg,image/webp,application/pdf,text/plain,text/markdown";

interface Message {
  role: "learner" | "tutor";
  text: string;
  attachments?: Attachment[];
  bookImages?: BookImageRef[];
  pageRefs?: number[];
}

function PageReferences({
  pages,
  onOpenPage,
}: {
  pages: number[];
  onOpenPage: (page: number) => void;
}) {
  return (
    <div className="chat-page-refs">
      <span className="chat-page-refs-label">Quellen:</span>
      {pages.map((page) => (
        <button
          key={page}
          type="button"
          className="chat-page-ref"
          onClick={() => onOpenPage(page)}
        >
          S. {page}
        </button>
      ))}
    </div>
  );
}

/** Shows the textbook PDF (fetched once, cached as a blob URL) in an
 * in-app modal, jumped to `page` -- `#page=N` is honored by the browser's
 * built-in PDF viewer inside the iframe too. */
function PdfModal({ page, onClose }: { page: number; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getBookPdfObjectUrl()
      .then((u) => {
        if (!cancelled) setUrl(u);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="pdf-modal-backdrop" onClick={onClose}>
      <div className="pdf-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pdf-modal-header">
          <span>Informationsmanagement &middot; Helmut Krcmar &middot; 6. Auflage</span>
          <button
            type="button"
            className="pdf-modal-close"
            aria-label="Schließen"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        {error && <p className="error-banner">Die PDF konnte nicht geladen werden.</p>}
        {url && (
          <iframe
            className="pdf-modal-frame"
            src={`${url}#page=${page}`}
            title={`Lehrbuch, Seite ${page}`}
          />
        )}
      </div>
    </div>
  );
}

function BookFigure({ image }: { image: BookImageRef }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    fetchBookImageObjectUrl(image.id)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
      })
      .catch(() => {
        // Best-effort -- the reply text still stands on its own.
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image.id]);

  if (!url) return null;
  return (
    <figure className="chat-book-figure">
      <img src={url} alt={`Abbildung, S. ${image.page}`} />
      <figcaption>S. {image.page}</figcaption>
    </figure>
  );
}

function AttachmentChip({
  learnerId,
  attachment,
  onRemove,
}: {
  learnerId: string;
  attachment: Attachment;
  onRemove?: () => void;
}) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  useEffect(() => {
    if (attachment.kind !== "image") return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetchAttachmentObjectUrl(learnerId, attachment.id)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setThumbUrl(url);
      })
      .catch(() => {
        // Best-effort thumbnail; the filename chip below still identifies it.
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [learnerId, attachment.id, attachment.kind]);

  async function handleDownload() {
    try {
      const url = await fetchAttachmentObjectUrl(learnerId, attachment.id);
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // Download is best-effort; nothing else to surface here.
    }
  }

  return (
    <div className="chat-attachment-chip">
      {attachment.kind === "image" ? (
        thumbUrl ? (
          <img className="chat-attachment-thumb" src={thumbUrl} alt={attachment.filename} />
        ) : (
          <span className="chat-attachment-thumb chat-attachment-thumb-loading" />
        )
      ) : (
        <button type="button" className="chat-attachment-doc" onClick={() => void handleDownload()}>
          {attachment.filename}
        </button>
      )}
      {onRemove && (
        <button
          type="button"
          className="chat-attachment-remove"
          aria-label={`${attachment.filename} entfernen`}
          onClick={onRemove}
        >
          ×
        </button>
      )}
    </div>
  );
}

interface Props {
  learnerId: string;
  focusLabel?: string | null;
  model?: string;
  studyMode: StudyModeState;
  /** The conversation being shown. `null` means a fresh, unsaved thread. */
  conversationId: string | null;
  /** Fired with the real id once the first turn of a fresh thread is saved. */
  onConversationResolved: (id: string) => void;
  onNewConversation: () => void;
  newConversationDisabled: boolean;
  historyOpen: boolean;
  onToggleHistory: () => void;
}

export function ChatPanel({
  learnerId,
  focusLabel,
  model,
  studyMode,
  conversationId,
  onConversationResolved,
  onNewConversation,
  newConversationDisabled,
  historyOpen,
  onToggleHistory,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(conversationId !== null);
  const [error, setError] = useState<string | null>(null);
  // A chapter/section overview pinned above the thread in training mode --
  // fetched fresh whenever the training-mode selection changes, and kept
  // visible for the whole lesson (App starts a fresh thread when the
  // selection changes, so it never outlives its chapter). Deliberately not
  // part of `messages`: it never reaches the backend and never shows up in
  // conversation history. Tagged with the selection it was fetched for, so a
  // stale response for a since-abandoned chapter is never rendered --
  // render-time derivation instead of clearing it reactively (see
  // `introText`).
  const [preview, setPreview] = useState<
    { key: string; text: string; starters: string[] } | null
  >(null);
  // Follow-up question chips shown above the input. [] once a send is in
  // flight (cleared alongside the draft) until the new reply's dynamic
  // batch arrives.
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [pdfModalPage, setPdfModalPage] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // The thread whose messages are already loaded, so the turn we just sent in a
  // fresh thread doesn't trigger a redundant refetch when its id arrives. App
  // remounts this component (via `key`) on every deliberate thread switch, so
  // the empty starting state is the clear.
  const loadedRef = useRef<string | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (conversationId === null || conversationId === loadedRef.current) return;

    let cancelled = false;
    getConversationMessages(learnerId, conversationId)
      .then((msgs) => {
        if (cancelled) return;
        setMessages(
          msgs.map((m) => ({
            role: m.role,
            text: m.text,
            attachments: m.attachments ?? [],
            bookImages: m.book_images ?? [],
            pageRefs: m.page_refs ?? [],
          })),
        );
        loadedRef.current = conversationId;
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Der Verlauf konnte nicht geladen werden.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId, learnerId]);

  // Derived at render time rather than mirrored into state, so the effect
  // below never needs a synchronous state update of its own -- no branch
  // ever needs to "clear" `preview`, since a stale fetch just won't match
  // `previewKey` once the selection has moved on.
  const inTrainingChapter = studyMode.mode === "training" && !!studyMode.chapter_number;
  const previewKey = `${studyMode.chapter_number ?? ""}:${studyMode.section_number ?? ""}`;
  const intro = inTrainingChapter && preview?.key === previewKey ? preview : null;
  const introText = intro?.text ?? null;

  useEffect(() => {
    // Wait for a resumed thread's real history to resolve first (purely so
    // the fetch doesn't race an unmount); the intro stays pinned regardless
    // of whether the thread has messages.
    if (!inTrainingChapter || loading) return;

    let cancelled = false;
    getChapterIntro(learnerId)
      .then((r) => {
        if (!cancelled) setPreview({ key: previewKey, text: r.text, starters: r.starters });
      })
      .catch(() => {
        // Best-effort -- the learner can still just start typing.
      });
    return () => {
      cancelled = true;
    };
  }, [learnerId, loading, inTrainingChapter, previewKey]);

  function appendToLastTutor(chunk: string) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, text: last.text + chunk };
      return next;
    });
  }

  async function handleFilesSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length === 0) return;

    setUploading(true);
    setError(null);
    try {
      for (const file of files) {
        const attachment = await uploadAttachment(learnerId, file, conversationId);
        setPendingAttachments((prev) => [...prev, attachment]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Datei konnte nicht hochgeladen werden.");
    } finally {
      setUploading(false);
    }
  }

  function removePendingAttachment(id: string) {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  async function sendMessage(text: string) {
    if (!text || sending) return;

    const attachments = pendingAttachments;
    const attachmentIds = attachments.map((a) => a.id);

    setMessages((prev) => [
      ...prev,
      { role: "learner", text, attachments },
      { role: "tutor", text: "" },
    ]);
    setSuggestions([]);
    setDraft("");
    setPendingAttachments([]);
    setSending(true);
    setError(null);

    try {
      const { conversationId: resolvedId, bookImages, pageRefs } = await streamChatMessage(
        learnerId,
        text,
        model,
        conversationId,
        attachmentIds,
        appendToLastTutor,
      );
      if (bookImages.length > 0 || pageRefs.length > 0) {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, bookImages, pageRefs };
          return next;
        });
      }
      if (resolvedId && resolvedId !== conversationId) {
        loadedRef.current = resolvedId;
        onConversationResolved(resolvedId);
      }
      const suggestionsFor = resolvedId || conversationId;
      if (suggestionsFor) {
        getFollowUpSuggestions(learnerId, suggestionsFor)
          .then((r) => setSuggestions(r.questions))
          .catch(() => {
            // Best-effort -- the learner can still just type their own.
          });
      }
    } catch (err) {
      // Drop the empty tutor bubble and show the error instead.
      setMessages((prev) =>
        prev[prev.length - 1]?.role === "tutor" && prev[prev.length - 1].text === ""
          ? prev.slice(0, -1)
          : prev,
      );
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setSending(false);
    }
  }

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    void sendMessage(draft.trim());
  }

  function handleSuggestionClick(question: string) {
    void sendMessage(question);
  }

  function starterQuestions(): string[] {
    if (!inTrainingChapter) return STARTER_QUESTIONS;
    // Still fetching the intro: show nothing rather than flash the generic set.
    if (!intro) return [];
    return intro.starters.length > 0 ? intro.starters : STARTER_QUESTIONS;
  }
  const suggestionList = messages.length === 0 ? starterQuestions() : suggestions;
  const suggestionChips = suggestionList.length > 0 && (
    <div className="chat-suggestions">
      {suggestionList.map((question, i) => (
        <button
          key={i}
          type="button"
          className="chat-suggestion-chip"
          disabled={sending}
          onClick={() => handleSuggestionClick(question)}
        >
          {question}
        </button>
      ))}
    </div>
  );

  return (
    <div className="panel chat-panel">
      <p className="focus-banner">
        {focusLabel ? `Thema: ${focusLabel}` : "Freie Erkundung"}
      </p>
      <div className="chat-messages" ref={scrollRef}>
        {loading && (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Verlauf wird geladen …</p>
        )}
        {!loading && introText && (
          <div className="chat-message tutor chat-intro">
            <span className="chat-intro-label">Einführung</span>
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{introText}</ReactMarkdown>
            </div>
          </div>
        )}
        {!loading && inTrainingChapter && !introText && messages.length === 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Einführung wird geladen …</p>
        )}
        {!loading && messages.length === 0 && !inTrainingChapter && (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            Stell dem Tutor eine Frage, um zu beginnen.
          </p>
        )}
        {!loading && messages.length === 0 && suggestionChips}
        {messages.map((m, i) => {
          const streaming = sending && i === messages.length - 1 && m.role === "tutor";
          const isLastFinishedTutorMessage =
            i === messages.length - 1 && m.role === "tutor" && !streaming;
          return (
            <Fragment key={i}>
              <div className={`chat-message ${m.role}` + (streaming ? " streaming" : "")}>
                {m.attachments && m.attachments.length > 0 && (
                  <div className="chat-message-attachments">
                    {m.attachments.map((a) => (
                      <AttachmentChip key={a.id} learnerId={learnerId} attachment={a} />
                    ))}
                  </div>
                )}
                {m.role === "tutor" ? (
                  m.text ? (
                    <div className="markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                    </div>
                  ) : (
                    streaming && "…"
                  )
                ) : (
                  m.text
                )}
                {m.role === "tutor" && m.bookImages && m.bookImages.length > 0 && (
                  <div className="chat-book-figures">
                    {m.bookImages.map((img) => (
                      <BookFigure key={img.id} image={img} />
                    ))}
                  </div>
                )}
                {m.role === "tutor" && m.pageRefs && m.pageRefs.length > 0 && (
                  <PageReferences pages={m.pageRefs} onOpenPage={setPdfModalPage} />
                )}
              </div>
              {isLastFinishedTutorMessage && suggestionChips}
            </Fragment>
          );
        })}
      </div>
      {error && <p className="error-banner">{error}</p>}
      {pendingAttachments.length > 0 && (
        <div className="chat-pending-attachments">
          {pendingAttachments.map((a) => (
            <AttachmentChip
              key={a.id}
              learnerId={learnerId}
              attachment={a}
              onRemove={() => removePendingAttachment(a.id)}
            />
          ))}
        </div>
      )}
      <form className="chat-input-row" onSubmit={handleSend}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Nachricht schreiben …"
          disabled={sending}
        />
        <button type="submit" className="primary" disabled={sending || !draft.trim()}>
          Senden
        </button>
      </form>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_ATTACHMENT_TYPES}
        multiple
        hidden
        onChange={(e) => void handleFilesSelected(e)}
      />
      <div className="chat-quick-actions">
        <button
          type="button"
          className="chat-quick-btn"
          disabled={newConversationDisabled}
          onClick={onNewConversation}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          Neuer Chat
        </button>
        <button
          type="button"
          className="chat-quick-btn"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
            <path
              d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          {uploading ? "Wird hochgeladen …" : "Anhängen"}
        </button>
        <button
          type="button"
          className={"chat-quick-btn" + (historyOpen ? " active" : "")}
          aria-pressed={historyOpen}
          onClick={onToggleHistory}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
            <path
              d="M3.5 12a8.5 8.5 0 1 0 2.5-6M3.5 4v5h5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M12 7.5V12l3 2"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Verlauf
        </button>
      </div>
      {pdfModalPage !== null && (
        <PdfModal page={pdfModalPage} onClose={() => setPdfModalPage(null)} />
      )}
    </div>
  );
}
