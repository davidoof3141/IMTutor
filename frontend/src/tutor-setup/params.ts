import type { ControlVector } from "../types";

export type ParamKey = keyof ControlVector;

export interface ParamMeta {
  key: ParamKey;
  name: string;
  blurb: string;
  options: (string | number)[];
  /** Verständliches Wort je Option, in derselben Reihenfolge wie `options`. */
  labels: string[];
}

export const PARAMS: ParamMeta[] = [
  {
    key: "explanation_depth",
    name: "Detailtiefe",
    blurb: "Wie ausführlich der Tutor jeden Gedanken erklärt.",
    options: [1, 2, 3, 4, 5],
    labels: ["Nur das Wichtigste", "Knapp", "Ausgewogen", "Ausführlich", "Sehr ausführlich"],
  },
  {
    key: "example_density",
    name: "Beispiele",
    blurb: "Wie oft der Tutor eine Aussage mit einem Beispiel untermauert.",
    options: [1, 2, 3, 4, 5],
    labels: ["Selten", "Gelegentlich", "Ausgewogen", "Oft", "Sehr oft"],
  },
  {
    key: "concreteness",
    name: "Konkret oder abstrakt",
    blurb: "Ob der Tutor von realen Situationen oder von allgemeinen Prinzipien ausgeht.",
    options: [1, 2, 3, 4, 5],
    labels: ["Sehr abstrakt", "Abstrakt", "Ausgewogen", "Konkret", "Sehr konkret"],
  },
  {
    key: "example_domain",
    name: "Branche der Beispiele",
    blurb: "Aus welcher Branche der Tutor seine Beispiele wählt.",
    options: [
      "manufacturing",
      "finance",
      "public_sector",
      "healthcare",
      "retail",
      "it_software",
      "logistics",
      "energy",
      "consulting",
      "neutral",
    ],
    labels: [
      "Fertigung & Industrie",
      "Banken & Versicherungen",
      "Öffentliche Verwaltung",
      "Gesundheitswesen",
      "Handel & E-Commerce",
      "IT & Software",
      "Logistik & Transport",
      "Energie & Versorgung",
      "Beratung & Dienstleistung",
      "Branchenneutral",
    ],
  },
  {
    key: "register",
    name: "Ton",
    blurb: "Wie förmlich die Sprache des Tutors ist.",
    options: ["formal", "neutral", "informal"],
    labels: ["Förmlich", "Neutral", "Locker"],
  },
  {
    key: "assessment_frequency",
    name: "Zwischenfragen",
    blurb: "Wie oft der Tutor prüft, was du verstanden hast.",
    options: ["every_topic", "every_second_topic", "on_request"],
    labels: ["Nach jedem Thema", "Nach jedem zweiten Thema", "Nur auf Nachfrage"],
  },
];
