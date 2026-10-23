import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  consumeLoginLinkFromUrl,
  consumeGroupJoinFromUrl,
  getComparisonProgress,
  getToken,
  hasPendingGroupJoin,
  getConfig,
  getCurriculum,
  getDiagnostic,
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
import { DiagnosticQuiz, DiagnosticSummary } from "./diagnostic/DiagnosticPanel";
import { HistorySidebar } from "./history/HistorySidebar";
import { ModeToggle } from "./mode/ModeToggle";
import { OnboardingForm } from "./onboarding/OnboardingForm";
import { SectionDoneNotice, QUESTIONS_PER_SECTION } from "./onboarding/SectionDoneNotice";
import { InviteWelcome, hasSeenInviteWelcome } from "./onboarding/InviteWelcome";
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
  DiagnosticResult,
  DiagnosticStatus,
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
  // A shared group link (?join=...) is only spent when this browser has no
  // session yet -- otherwise a refresh or second click would burn a sign-up.
  const [linkLogin, setLinkLogin] = useState<"idle" | "checking" | "failed">(() =>
    hasPendingLoginLink() || (hasPendingGroupJoin() && !getToken()) ? "checking" : "idle",
  );
  const [linkLoginError, setLinkLoginError] = useState<string | null>(null);
  const linkConsumedRef = useRef(false);

  useEffect(() => {
    if (linkConsumedRef.current) return;
    linkConsumedRef.current = true;
    const joinToken = consumeGroupJoinFromUrl();
    const token = consumeLoginLinkFromUrl();
    const [useJoin, secret] = token ? [false, token] : [true, joinToken];
    if (!secret || (useJoin && getToken())) return;
    (useJoin ? auth.joinWithGroupLink(secret) : auth.loginWithLink(secret))
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
  const [setupOpen, setSetupOpen] = useState(false);
  // The per-chapter diagnostic for one (mode, chapter, section) selection,
  // tagged with the selection it was loaded for so a stale answer for a
  // previous selection is never shown.
  const [diagnostic, setDiagnostic] = useState<{ sel: string; status: DiagnosticStatus } | null>(
    null,
  );
  // Selection whose result summary is on screen (set right after submitting).
  const [summaryFor, setSummaryFor] = useState<string | null>(null);
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
  const [welcomeDone, setWelcomeDone] = useState(false);
  const [comparisonProgress, setComparisonProgress] = useState<Record<string, number>>({});

  // Subchapter whose 2 questions were just completed -> "continue" notice.
  const [finishedSection, setFinishedSection] = useState<string | null>(null);
  const [advanceError, setAdvanceError] = useState<string | null>(null);
  const comparisonProgressRef = useRef(comparisonProgress);
  comparisonProgressRef.current = comparisonProgress;

  function refreshComparisonProgress(announceFor?: string | null) {
    if (!dualMode || !learnerId) return;
    getComparisonProgress(learnerId)
      .then((next) => {
        if (
          announceFor &&
          (comparisonProgressRef.current[announceFor] ?? 0) < QUESTIONS_PER_SECTION &&
          (next[announceFor] ?? 0) >= QUESTIONS_PER_SECTION
        ) {
          setFinishedSection(announceFor);
        }
        setComparisonProgress(next);
      })
      .catch(() => {
        // Best-effort -- progress display just stays as it was.
      });
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refreshComparisonProgress(), [dualMode, learnerId]);

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
    if (changed) {
      openConversation(null);
      setFinishedSection(null);
    }
  }

  async function handleContinueToNextSection(nextSection: string) {
    if (!learnerId) return;
    setAdvanceError(null);
    try {
      handleSelectionChange(
        await updateStudyMode(learnerId, {
          mode: "training",
          chapter_number: "4",
          section_number: nextSection,
        }),
      );
    } catch (err) {
      setAdvanceError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    }
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
        // Other failures leave the lesson as it was; lessons aren't started from
        // the UI any more, so there is no panel to show an error in.
        if (err instanceof ApiError && err.status === 404) setLesson(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeConversationId, chatEpoch]);

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

  // Diagnostic + config for the current training selection. The chapter-level
  // vector differs per chapter, so the tutor-setup panel is re-read too.
  const selKey =
    studyMode?.mode === "training" && studyMode.chapter_number
      ? `${studyMode.chapter_number}:${studyMode.section_number ?? ""}`
      : null;
  useEffect(() => {
    if (!learnerId || selKey === null) return;
    getDiagnostic(learnerId)
      .then((status) => setDiagnostic({ sel: selKey, status }))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar."),
      );
    getConfig(learnerId)
      .then(setConfig)
      .catch(() => {
        // Das Panel behält seinen letzten Stand.
      });
  }, [learnerId, selKey]);

  function handleDiagnosticResult(sel: string, result: DiagnosticResult) {
    setDiagnostic((prev) =>
      prev && prev.sel === sel ? { sel, status: { ...prev.status, result } } : prev,
    );
    if (learnerId) {
      void getConfig(learnerId)
        .then(setConfig)
        .catch(() => {
          // Das Panel behält seinen letzten Stand.
        });
    }
  }

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
      <>
        <OnboardingForm
          onComplete={handleOnboardingComplete}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        {auth.user.has_login_link && (
          <InviteWelcome userId={auth.user.id} onClose={() => setWelcomeDone(true)} />
        )}
      </>
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

  const currentDiagnostic = diagnostic && diagnostic.sel === selKey ? diagnostic.status : null;
  // Instruction (lesson + chat) waits for the chapter's diagnostic, then for
  // the learner to confirm the summary screen.
  const diagnosticPending = currentDiagnostic?.required === true && !currentDiagnostic.result;
  const summaryOpen = currentDiagnostic?.result != null && summaryFor === selKey;
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
                <ModeToggle
                  mode={studyMode.mode}
                  onChange={handleModeChange}
                  disabledModes={dualMode ? ["exploration"] : []}
                />
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

      {dualMode && (
        <div className="demo-banner" role="note">
          <strong>Demo-Showcase:</strong> Du nutzt eine Testversion des ITM Tutors mit
          eingeschränktem Zugang – nicht alle Kapitel und Funktionen sind freigeschaltet.
        </div>
      )}

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
              comparisonProgress={comparisonProgress}
            />
          </aside>
        )}

        <main className="chat-main">
          {error && <p className="error-banner">{error}</p>}
          {selKey !== null && diagnosticPending && currentDiagnostic && (
            <DiagnosticQuiz
              learnerId={learnerId}
              title={focusLabel ?? "Dieses Kapitel"}
              items={currentDiagnostic.items}
              onSubmitted={(result) => {
                handleDiagnosticResult(selKey, result);
                setSummaryFor(selKey);
              }}
            />
          )}
          {selKey !== null && summaryOpen && currentDiagnostic?.result && (
            <DiagnosticSummary
              title={focusLabel ?? "Dieses Kapitel"}
              result={currentDiagnostic.result}
              onContinue={() => setSummaryFor(null)}
            />
          )}
          {dualMode && finishedSection !== null && finishedSection === studyMode.section_number && (
            <SectionDoneNotice
              section={finishedSection}
              error={advanceError}
              onContinue={(next) => void handleContinueToNextSection(next)}
              onDismiss={() => setFinishedSection(null)}
            />
          )}
          {!diagnosticPending && !summaryOpen && (
            <ChatPanel
              key={chatEpoch}
              learnerId={learnerId}
              focusLabel={focusLabel}
              model={chatModel}
              studyMode={studyMode}
              conversationId={activeConversationId}
              dualMode={dualMode}
              onComparisonDecided={() => refreshComparisonProgress(studyMode.section_number)}
              onConversationResolved={setActiveConversationId}
              onNewConversation={() => openConversation(null)}
              newConversationDisabled={activeConversationId === null}
              historyOpen={historyOpen}
              onToggleHistory={() => setHistoryOpen((open) => !open)}
            />
          )}
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

      {dualMode && <InviteWelcome userId={auth.user.id} onClose={() => setWelcomeDone(true)} />}
      {!inSettings && (!dualMode || welcomeDone || hasSeenInviteWelcome(auth.user.id)) && (
        <OnboardingTour learnerId={learnerId} dualMode={dualMode} />
      )}
    </div>
  );
}

export default App;
