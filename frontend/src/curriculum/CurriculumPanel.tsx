import { useState } from "react";
import { ApiError, updateStudyMode } from "../api/client";
import type { Chapter, StudyModeState } from "../types";

interface Props {
  learnerId: string;
  curriculum: Chapter[];
  studyMode: StudyModeState;
  onStudyModeChange: (state: StudyModeState) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Link-invited accounts only get a fixed slice of the curriculum
   * unlocked (see LOCKED_CHAPTER/LOCKED_SECTIONS below) -- everything else
   * shows locked rather than disappearing, so the book's full structure
   * stays visible. Must mirror app/api/study_mode.py's
   * LINK_USER_ALLOWED_CHAPTER/LINK_USER_ALLOWED_SECTIONS on the backend,
   * which is what actually enforces this. */
  dualMode: boolean;
}

const UNLOCKED_CHAPTER = "3";
const UNLOCKED_SECTIONS = new Set(["3.1", "3.2", "3.3"]);

function Chevron({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M4.5 2.5 8 6l-3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LockIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <rect x="4" y="11" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
      <path
        d="M7.5 11V7.5a4.5 4.5 0 0 1 9 0V11"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function CurriculumPanel({
  learnerId,
  curriculum,
  studyMode,
  onStudyModeChange,
  collapsed,
  onToggleCollapsed,
  dualMode,
}: Props) {
  const [expanded, setExpanded] = useState<string | null>(studyMode.chapter_number);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function isChapterLocked(chapter: Chapter): boolean {
    return dualMode && chapter.number !== UNLOCKED_CHAPTER;
  }

  function isSectionLocked(sectionNumber: string): boolean {
    return dualMode && !UNLOCKED_SECTIONS.has(sectionNumber);
  }

  async function apply(chapterNumber: string, sectionNumber: string | null) {
    setBusy(true);
    setError(null);
    try {
      onStudyModeChange(
        await updateStudyMode(learnerId, {
          mode: "training",
          chapter_number: chapterNumber,
          section_number: sectionNumber,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Der Server ist nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  function handleChapterClick(chapter: Chapter) {
    if (isChapterLocked(chapter)) return;
    setExpanded(expanded === chapter.number ? null : chapter.number);
    if (studyMode.chapter_number !== chapter.number) {
      void apply(chapter.number, null);
    }
  }

  function handleSectionClick(chapter: Chapter, sectionNumber: string) {
    if (isSectionLocked(sectionNumber)) return;
    void apply(chapter.number, sectionNumber);
  }

  if (collapsed) {
    return (
      <div className="panel schedule-panel is-collapsed">
        <button
          type="button"
          className="rail-toggle"
          onClick={onToggleCollapsed}
          aria-label="Lernplan einblenden"
          title="Lernplan einblenden"
        >
          <Chevron />
        </button>
        <ul className="collapsed-chapters">
          {curriculum.map((chapter) => {
            const isSelected = studyMode.chapter_number === chapter.number;
            const locked = isChapterLocked(chapter);
            return (
              <li key={chapter.number}>
                <button
                  type="button"
                  className={
                    "collapsed-chapter" + (isSelected ? " selected" : "") + (locked ? " is-locked" : "")
                  }
                  disabled={busy || locked}
                  aria-current={isSelected ? "true" : undefined}
                  aria-label={`${chapter.number}. ${chapter.title}` + (locked ? " (gesperrt)" : "")}
                  title={
                    locked
                      ? `${chapter.number}. ${chapter.title} — für dieses Konto nicht freigeschaltet`
                      : `${chapter.number}. ${chapter.title}`
                  }
                  onClick={() => void apply(chapter.number, null)}
                >
                  {chapter.number}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className="panel schedule-panel">
      <div className="schedule-head">
        <span className="schedule-title">Lernplan</span>
        <button
          type="button"
          className="rail-toggle is-open"
          onClick={onToggleCollapsed}
          aria-label="Lernplan ausblenden"
          title="Lernplan ausblenden"
        >
          <Chevron />
        </button>
      </div>
      {dualMode && (
        <p className="schedule-scope-note">
          Für diesen Test sind nur die Kapitel 3.1–3.3 freigeschaltet.
        </p>
      )}
      <ul className="curriculum-list">
        {curriculum.map((chapter) => {
          const isExpanded = expanded === chapter.number;
          const hasSections = chapter.sections.length > 0;
          const chapterLocked = isChapterLocked(chapter);
          return (
            <li key={chapter.number}>
              <button
                type="button"
                className={
                  "curriculum-chapter" +
                  (studyMode.chapter_number === chapter.number ? " selected" : "") +
                  (chapterLocked ? " is-locked" : "")
                }
                disabled={busy || chapterLocked}
                aria-expanded={hasSections && !chapterLocked ? isExpanded : undefined}
                title={chapterLocked ? "Für dieses Konto nicht freigeschaltet" : undefined}
                onClick={() => handleChapterClick(chapter)}
              >
                <span className="chapter-title">
                  {chapter.number}. {chapter.title}
                </span>
                {chapterLocked ? (
                  <LockIcon className="chapter-lock" />
                ) : (
                  hasSections && <Chevron className={"chapter-caret" + (isExpanded ? " open" : "")} />
                )}
              </button>
              {hasSections && !chapterLocked && (
                <div className={"section-collapse" + (isExpanded ? " open" : "")}>
                  <div className="section-collapse-inner">
                    <ul className="curriculum-sections">
                      {chapter.sections.map((section) => {
                        const sectionLocked = isSectionLocked(section.number);
                        return (
                          <li key={section.number}>
                            <button
                              type="button"
                              className={
                                "curriculum-section" +
                                (studyMode.section_number === section.number ? " selected" : "") +
                                (sectionLocked ? " is-locked" : "")
                              }
                              disabled={busy || sectionLocked}
                              title={
                                sectionLocked ? "Für dieses Konto nicht freigeschaltet" : undefined
                              }
                              onClick={() => handleSectionClick(chapter, section.number)}
                            >
                              {section.number} {section.title}
                              {sectionLocked && <LockIcon className="section-lock" />}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}
