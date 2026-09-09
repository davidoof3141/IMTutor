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
}

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

export function CurriculumPanel({
  learnerId,
  curriculum,
  studyMode,
  onStudyModeChange,
  collapsed,
  onToggleCollapsed,
}: Props) {
  const [expanded, setExpanded] = useState<string | null>(studyMode.chapter_number);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setExpanded(expanded === chapter.number ? null : chapter.number);
    if (studyMode.chapter_number !== chapter.number) {
      void apply(chapter.number, null);
    }
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
            return (
              <li key={chapter.number}>
                <button
                  type="button"
                  className={"collapsed-chapter" + (isSelected ? " selected" : "")}
                  disabled={busy}
                  aria-current={isSelected ? "true" : undefined}
                  aria-label={`${chapter.number}. ${chapter.title}`}
                  title={`${chapter.number}. ${chapter.title}`}
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
      <ul className="curriculum-list">
        {curriculum.map((chapter) => {
          const isExpanded = expanded === chapter.number;
          const hasSections = chapter.sections.length > 0;
          return (
            <li key={chapter.number}>
              <button
                type="button"
                className={
                  "curriculum-chapter" +
                  (studyMode.chapter_number === chapter.number ? " selected" : "")
                }
                disabled={busy}
                aria-expanded={hasSections ? isExpanded : undefined}
                onClick={() => handleChapterClick(chapter)}
              >
                <span className="chapter-title">
                  {chapter.number}. {chapter.title}
                </span>
                {hasSections && (
                  <Chevron className={"chapter-caret" + (isExpanded ? " open" : "")} />
                )}
              </button>
              {hasSections && (
                <div className={"section-collapse" + (isExpanded ? " open" : "")}>
                  <div className="section-collapse-inner">
                    <ul className="curriculum-sections">
                      {chapter.sections.map((section) => (
                        <li key={section.number}>
                          <button
                            type="button"
                            className={
                              "curriculum-section" +
                              (studyMode.section_number === section.number ? " selected" : "")
                            }
                            disabled={busy}
                            onClick={() => void apply(chapter.number, section.number)}
                          >
                            {section.number} {section.title}
                          </button>
                        </li>
                      ))}
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
