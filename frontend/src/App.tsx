import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  abandonLesson,
  advanceLesson,
  consumeLoginLinkFromUrl,
  createLesson,
  getConfig,
  getCurriculum,
  getLesson,
  getStudyMode,
  hasPendingLoginLink,
  listConversations,
  updateStudyMode,
} from "./api/client";
import { AuthScreen } from "./auth/AuthScreen";
import { ChangePasswordScreen } from "./auth/ChangePasswordScreen";
import { useAuth } from "./auth/useAuth";
import { CurriculumPanel } from "./curriculum/CurriculumPanel";
import { HistorySidebar } from "./history/HistorySidebar";
import { LessonRail } from "./lesson/LessonRail";
import { ModeToggle } from "./mode/ModeToggle";
import { OnboardingForm } from "./onboarding/OnboardingForm";
import { OnboardingTour } from "./onboarding/OnboardingTour";
import { ProfileMenu } from "./profile/ProfileMenu";
import { SettingsView } from "./settings/SettingsView";
import { useChatModel } from "./settings/chatModel";
import { TutorSetupPanel } from "./tutor-setup/TutorSetupPanel";
import { useTheme } from "./theme";
import { ChatPanel } from "./tutor/ChatPanel";
import type {
  Chapter,
  ConfigResponse,
  LessonResponse,
  OnboardingResponse,
  StudyModeName,
  StudyModeState,
} from "./types";

type View = "session" | "settings";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator:in",
  learner: "Lernende:r",
};

function App() {
  const { theme, toggleTheme } = useTheme();
  const { model: chatModel, setModel: setChatModel } = useChatModel();
  const auth = useAuth();

  // A magic-link visit (?login_link=...) signs the visitor in before anything
  // else renders; "checking" briefly shows the splash instead of a flash of
  // the login screen while that request is in flight. The presence check is
  // read-only (safe during render); consuming the token rewrites the URL and
  // must happen exactly once, guarded against StrictMode's double effect.
  const [linkLogin, setLinkLogin] = useState<"idle" | "checking" | "failed">(() =>
    hasPendingLoginLink() ? "checking" : "idle",
  );
  const [linkLoginError, setLinkLoginError] = useState<string | null>(null);
  const linkConsumedRef = useRef(false);

  useEffect(() => {
    if (linkConsumedRef.current) return;
    linkConsumedRef.current = true;
    const token = consumeLoginLinkFromUrl();
    if (!token) return;
    auth
      .loginWithLink(token)
      .then(() => setLinkLogin("idle"))
      .catch((err) => {
        setLinkLogin("failed");
        setLinkLoginError(
          err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.",
        );
      });
    // Runs once on mount to consume the token from the initial URL only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [curriculum, setCurriculum] = useState<Chapter[]>([]);
  const [studyMode, setStudyMode] = useState<StudyModeState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("session");
  const [setupOpen, setSetupOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  // null = a fresh, unsaved thread; the server assigns an id on the first turn.
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  // Bumped on every deliberate thread switch so ChatPanel remounts with a clean
  // slate; NOT bumped when a fresh thread's id arrives mid-conversation.
  const [chatEpoch, setChatEpoch] = useState(0);
  // null while no lesson exists for the active conversation -- a plain chat
  // thread, or none loaded yet. Re-fetched whenever the thread or chatEpoch
  // changes, so a lesson action's own openConversation() call (below) is
  // what refreshes this after create/advance/abandon.
  const [lesson, setLesson] = useState<LessonResponse | null>(null);
  const [lessonBusy, setLessonBusy] = useState(false);
  const [lessonError, setLessonError] = useState<string | null>(null);
  const [scheduleCollapsed, setScheduleCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("itm-schedule-collapsed") === "1";
    } catch {
      return false;
    }
  });

  const learnerId = auth.learnerId;
  const isAdmin = auth.user?.role === "admin";
  // Link-invited accounts take part in the personalized-vs-generic chat
  // comparison instead of getting a single reply per turn.
  const dualMode = auth.user?.has_login_link ?? false;

  function openConversation(id: string | null) {
    setActiveConversationId(id);
    setChatEpoch((epoch) => epoch + 1);
    setHistoryOpen(false);
    // Cleared here (the event that caused the change) rather than in the
    // lesson-fetch effect below, so that effect never needs a synchronous
    // setState of its own -- it only ever sets state from its async result.
    setLesson(null);
  }

  // A different chapter/section (or mode) means a different lesson: start a
  // fresh thread so the previous lesson's chat doesn't bleed into the new one.
  // Wraps the raw setStudyMode passed to the curriculum picker; the initial
  // getStudyMode load and the mode toggle use setStudyMode directly.
  function handleSelectionChange(next: StudyModeState) {
    const changed =
      !studyMode ||
      next.mode !== studyMode.mode ||
      next.chapter_number !== studyMode.chapter_number ||
      next.section_number !== studyMode.section_number;
    setStudyMode(next);
    if (changed) openConversation(null);
  }

  function toggleScheduleCollapsed() {
    setScheduleCollapsed((collapsed) => {
      const next = !collapsed;
      try {
        localStorage.setItem("itm-schedule-collapsed", next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  }

  useEffect(() => {
    if (auth.status !== "authed") return;
    getCurriculum()
      .then((r) => setCurriculum(r.chapters))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, [auth.status]);

  useEffect(() => {
    if (!learnerId) return;
    // Resume the learner's most recent thread; a brand-new learner starts fresh.
    listConversations(learnerId)
      .then((list) => openConversation(list[0]?.id ?? null))
      .catch(() => openConversation(null));
  }, [learnerId]);

  useEffect(() => {
    if (activeConversationId === null) return;
    let cancelled = false;
    getLesson(activeConversationId)
      .then((l) => {
        if (!cancelled) setLesson(l);
      })
      .catch((err) => {
        if (cancelled) return;
        // 404 just means this thread has no lesson -- an ordinary chat, not an error.
        if (err instanceof ApiError && err.status === 404) {
          setLesson(null);
        } else {
          setLessonError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeConversationId, chatEpoch]);

  async function handleCreateLesson() {
    if (!learnerId) return;
    setLessonBusy(true);
    setLessonError(null);
    try {
      const created = await createLesson(learnerId);
      openConversation(created.plan.conversation_id);
    } catch (err) {
      setLessonError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setLessonBusy(false);
    }
  }

  async function handleAdvanceLesson() {
    if (activeConversationId === null) return;
    setLessonBusy(true);
    setLessonError(null);
    try {
      await advanceLesson(activeConversationId);
      openConversation(activeConversationId);
    } catch (err) {
      setLessonError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setLessonBusy(false);
    }
  }

  async function handleAbandonLesson() {
    if (activeConversationId === null) return;
    setLessonBusy(true);
    setLessonError(null);
    try {
      await abandonLesson(activeConversationId);
      openConversation(activeConversationId);
    } catch (err) {
      setLessonError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setLessonBusy(false);
    }
  }

  useEffect(() => {
    if (!learnerId) return;
    getConfig(learnerId)
      .then(setConfig)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
    getStudyMode(learnerId)
      .then(setStudyMode)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }, [learnerId]);

  function handleModeChange(mode: StudyModeName) {
    if (!learnerId || !studyMode) return;
    void updateStudyMode(learnerId, {
      mode,
      chapter_number: studyMode.chapter_number,
      section_number: studyMode.section_number,
    })
      .then(setStudyMode)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
  }

  function handleLogout() {
    setConfig(null);
    setStudyMode(null);
    setCurriculum([]);
    setView("session");
    setError(null);
    setActiveConversationId(null);
    setHistoryOpen(false);
    auth.logout();
  }

  function handleOnboardingComplete(result: OnboardingResponse) {
    auth.setLearnerId(result.profile.learner_id);
    setConfig({
      profile: result.profile,
      derived: result.derived,
      override: {},
      effective: result.derived,
      attribution: result.attribution,
    });
  }

  if (auth.status === "loading" || linkLogin === "checking") {
    return <div className="app-splash" aria-busy="true" />;
  }

  if (!auth.user) {
    return (
      <AuthScreen
        theme={theme}
        onToggleTheme={toggleTheme}
        onLogin={auth.login}
        onRegister={auth.register}
        linkError={linkLogin === "failed" ? linkLoginError : null}
      />
    );
  }

  if (auth.user.must_change_password) {
    return (
      <ChangePasswordScreen
        theme={theme}
        username={auth.user.username}
        onToggleTheme={toggleTheme}
        onSubmit={auth.changePassword}
        onLogout={handleLogout}
      />
    );
  }

  if (!learnerId || !config || !studyMode) {
    return (
      <OnboardingForm
        onComplete={handleOnboardingComplete}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  const selectedChapter = curriculum.find((c) => c.number === studyMode.chapter_number);
  const selectedSection = selectedChapter?.sections.find(
    (s) => s.number === studyMode.section_number,
  );
  const focusLabel =
    studyMode.mode === "training" && selectedChapter
      ? `Kapitel ${selectedChapter.number}: ${selectedChapter.title}` +
        (selectedSection ? ` – ${selectedSection.number} ${selectedSection.title}` : "")
      : null;

  const showSchedule = studyMode.mode === "training";
  const inSettings = view === "settings" && isAdmin;

  return (
    <div className="app-root">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="header-left">
            <div className="logo">
              <span className="logo-mark">IT</span>
              <span className="logo-wordmark">
                ITM<span className="accent">Tutor</span>
              </span>
            </div>
            {inSettings ? (
              <button type="button" className="back-btn" onClick={() => setView("session")}>
                ← Zurück zur Sitzung
              </button>
            ) : (
              <span data-tour="mode-toggle">
                <ModeToggle mode={studyMode.mode} onChange={handleModeChange} />
              </span>
            )}
          </div>
          <div className="header-right">
            {!inSettings && (
              <button
                type="button"
                data-tour="scrutability"
                className={"setup-toggle" + (setupOpen ? " active" : "")}
                aria-pressed={setupOpen}
                aria-label="So ist dein Tutor eingestellt"
                title="So ist dein Tutor eingestellt"
                onClick={() => setSetupOpen((open) => !open)}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                  <path
                    d="M4 7h10M18 7h2M4 17h2M10 17h10"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                  <circle cx="16" cy="7" r="2.6" stroke="currentColor" strokeWidth="2" />
                  <circle cx="8" cy="17" r="2.6" stroke="currentColor" strokeWidth="2" />
                </svg>
              </button>
            )}
            <ProfileMenu
              theme={theme}
              onToggleTheme={toggleTheme}
              username={auth.user.username}
              roleLabel={ROLE_LABELS[auth.user.role] ?? auth.user.role}
              isAdmin={!!isAdmin}
              onOpenSettings={() => setView("settings")}
              onLogout={handleLogout}
            />
          </div>
        </div>
      </header>

      {inSettings && (
        <SettingsView chatModel={chatModel} onChatModelChange={setChatModel} currentUserId={auth.user.id} />
      )}

      <div
        hidden={inSettings}
        className={
          "app-body" +
          (setupOpen ? " with-olm" : "") +
          (showSchedule ? " with-schedule" : "") +
          (showSchedule && scheduleCollapsed ? " schedule-collapsed" : "")
        }
      >
        {showSchedule && (
          <aside className="schedule-rail">
            <CurriculumPanel
              learnerId={learnerId}
              curriculum={curriculum}
              studyMode={studyMode}
              onStudyModeChange={handleSelectionChange}
              collapsed={scheduleCollapsed}
              onToggleCollapsed={toggleScheduleCollapsed}
              dualMode={dualMode}
            />
            {!scheduleCollapsed && (
              <LessonRail
                studyMode={studyMode}
                lesson={lesson}
                busy={lessonBusy}
                error={lessonError}
                onCreate={() => void handleCreateLesson()}
                onAdvance={() => void handleAdvanceLesson()}
                onAbandon={() => void handleAbandonLesson()}
              />
            )}
          </aside>
        )}

        <main className="chat-main">
          {error && <p className="error-banner">{error}</p>}
          <ChatPanel
            key={chatEpoch}
            learnerId={learnerId}
            focusLabel={focusLabel}
            model={chatModel}
            studyMode={studyMode}
            conversationId={activeConversationId}
            dualMode={dualMode}
            onConversationResolved={setActiveConversationId}
            onNewConversation={() => openConversation(null)}
            newConversationDisabled={activeConversationId === null}
            historyOpen={historyOpen}
            onToggleHistory={() => setHistoryOpen((open) => !open)}
          />
        </main>

        {setupOpen && (
          <aside className="olm-pane">
            <TutorSetupPanel
              config={config}
              learnerId={learnerId}
              onConfigChange={setConfig}
              lesson={lesson}
            />
          </aside>
        )}
      </div>

      {historyOpen && !inSettings && (
        <HistorySidebar
          learnerId={learnerId}
          curriculum={curriculum}
          activeConversationId={activeConversationId}
          onSelect={openConversation}
          onClose={() => setHistoryOpen(false)}
        />
      )}

      {!inSettings && <OnboardingTour learnerId={learnerId} dualMode={dualMode} />}
    </div>
  );
}

export default App;
