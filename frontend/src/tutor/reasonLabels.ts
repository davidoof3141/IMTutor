import type { ReasonTag } from "../types";

export const REASON_LABELS: Record<ReasonTag, string> = {
  detail: "Passende Detailtiefe",
  tone: "Passender Ton",
  clarity: "Klarere Erklärung",
  examples: "Bessere Beispiele",
  difficulty: "Richtige Schwierigkeit",
  other: "Sonstiges",
};

export const REASON_ORDER: ReasonTag[] = [
  "detail",
  "tone",
  "clarity",
  "examples",
  "difficulty",
  "other",
];
