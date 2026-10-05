import { useEffect, useLayoutEffect, useMemo, useState } from "react";

interface TourStep {
  /** Matches a `data-tour="..."` attribute on the element to spotlight. */
  target: string;
  title: string;
  body: string;
}

function buildSteps(dualMode: boolean): TourStep[] {
  return [
    {
      target: "mode-toggle",
      title: "Erkundung oder Lernplan",
      body: dualMode
        ? "Du startest direkt im Lernplan. Hier kannst du zwischen den für diesen Test freigeschalteten Kapiteln 3.1–3.3 wechseln."
        : "Wechsle hier zwischen freier Erkundung und einem strukturierten Lernplan mit Kapiteln, Fahrplan und nächsten Schritten.",
    },
    {
      target: "scrutability",
      title: "So ist dein Tutor eingestellt",
      body: "Hier siehst du, warum der Tutor gerade so antwortet, und kannst Detailtiefe, Beispiele, Ton und mehr selbst anpassen.",
    },
    {
      target: "history",
      title: "Verlauf",
      body: "Frühere Unterhaltungen findest du hier -- du kannst jederzeit dorthin zurückkehren.",
    },
  ];
}

function storageKey(learnerId: string): string {
  return `itm-tour-seen:${learnerId}`;
}

function hasSeenTour(learnerId: string): boolean {
  try {
    return localStorage.getItem(storageKey(learnerId)) === "1";
  } catch {
    return true; // fail closed -- don't nag if storage is unavailable
  }
}

function markTourSeen(learnerId: string): void {
  try {
    localStorage.setItem(storageKey(learnerId), "1");
  } catch {
    // ignore
  }
}

interface Props {
  learnerId: string;
  /** Link-invited accounts get different copy on the mode-toggle step,
   * pointing out the specific chapters unlocked for them. */
  dualMode: boolean;
}

/** A one-time, per-learner spotlight tour pointing at a few features that
 * aren't obvious from the main view alone (the mode toggle that reveals the
 * lesson schedule, the scrutability panel, conversation history). Steps
 * target elements tagged `data-tour="..."` elsewhere in the app; a step
 * whose element isn't in the DOM (a layout variant that omits it) is
 * skipped rather than spotlighting nothing. */
export function OnboardingTour({ learnerId, dualMode }: Props) {
  const [active, setActive] = useState(() => !hasSeenTour(learnerId));
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // Stable across renders while dualMode doesn't change -- otherwise `step`
  // is a new object every render, the layout effect below (which depends on
  // it) re-fires on every commit, and its setRect call loops forever.
  const steps = useMemo(() => buildSteps(dualMode), [dualMode]);
  const step = steps[stepIndex];

  function close() {
    setActive(false);
    markTourSeen(learnerId);
  }

  function next() {
    if (stepIndex < steps.length - 1) setStepIndex((i) => i + 1);
    else close();
  }

  useLayoutEffect(() => {
    if (!active || !step) return;

    function locate() {
      const el = document.querySelector(`[data-tour="${step.target}"]`);
      if (!el) {
        if (stepIndex < steps.length - 1) setStepIndex((i) => i + 1);
        else close();
        return;
      }
      setRect(el.getBoundingClientRect());
    }

    locate();
    window.addEventListener("resize", locate);
    window.addEventListener("scroll", locate, true);
    return () => {
      window.removeEventListener("resize", locate);
      window.removeEventListener("scroll", locate, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, step, stepIndex]);

  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  if (!active || !step || !rect) return null;

  const cardWidth = 300;
  const margin = 12;
  const spotlightPad = 6;

  const placeBelow = window.innerHeight - rect.bottom > 160 || rect.top < 160;
  const left = Math.min(Math.max(rect.left, margin), window.innerWidth - cardWidth - margin);

  return (
    <div className="tour-root">
      <div
        className="tour-spotlight"
        style={{
          top: `${rect.top - spotlightPad}px`,
          left: `${rect.left - spotlightPad}px`,
          width: `${rect.width + spotlightPad * 2}px`,
          height: `${rect.height + spotlightPad * 2}px`,
        }}
      />
      <div
        className="tour-card"
        style={{
          left: `${left}px`,
          width: `${cardWidth}px`,
          ...(placeBelow
            ? { top: `${rect.bottom + margin}px` }
            : { bottom: `${window.innerHeight - rect.top + margin}px` }),
        }}
      >
        <span className="tour-step-count">
          Schritt {stepIndex + 1} von {steps.length}
        </span>
        <h3>{step.title}</h3>
        <p>{step.body}</p>
        <div className="tour-actions">
          <button type="button" className="link-btn" onClick={close}>
            Tour überspringen
          </button>
          <button type="button" className="invite-btn" onClick={next}>
            {stepIndex < steps.length - 1 ? "Weiter" : "Fertig"}
          </button>
        </div>
      </div>
    </div>
  );
}
