import { useCallback, useEffect, useState } from "react";

export interface ChatModelOption {
  id: string;
  name: string;
  blurb: string;
}

export interface ChatModelGroup {
  provider: string;
  models: ChatModelOption[];
}

/**
 * A curated shortlist of the OpenRouter models that make sense for tutoring,
 * grouped by provider. `id` is the exact OpenRouter slug passed to the backend.
 * The full catalogue lives at https://openrouter.ai/models.
 */
export const CHAT_MODEL_GROUPS: ChatModelGroup[] = [
  {
    provider: "Anthropic",
    models: [
      {
        id: "anthropic/claude-sonnet-5",
        name: "Claude Sonnet 5 — ausgewogen",
        blurb: "Empfohlen. Starke Balance aus Qualität, Tempo und Kosten für die meisten Sitzungen.",
      },
      {
        id: "anthropic/claude-opus-5",
        name: "Claude Opus 5 — höchste Denkleistung",
        blurb: "Für dichtes Fachmaterial und lange Herleitungen. Langsamer und teurer.",
      },
      {
        id: "anthropic/claude-haiku-4.5",
        name: "Claude Haiku 4.5 — schnell & günstig",
        blurb: "Niedrige Latenz und Kosten; gut für kurze Rückfragen.",
      },
    ],
  },
  {
    provider: "OpenAI",
    models: [
      {
        id: "openai/gpt-5.1",
        name: "GPT-5.1 — Spitzenmodell",
        blurb: "Gründliche Erklärungen mit starker Schlussfolgerung. Höhere Kosten.",
      },
      {
        id: "openai/gpt-5-mini",
        name: "GPT-5 mini — günstig & schnell",
        blurb: "Kompakte OpenAI-Option für den Alltag.",
      },
    ],
  },
  {
    provider: "Google",
    models: [
      {
        id: "google/gemini-3.1-pro-preview",
        name: "Gemini 3.1 Pro — großer Kontext",
        blurb: "Sehr großer Kontext, gut für ganze Kapitel am Stück.",
      },
      {
        id: "google/gemini-2.5-flash",
        name: "Gemini 2.5 Flash — schnell & günstig",
        blurb: "Zügige Antworten bei großem Kontextfenster.",
      },
    ],
  },
  {
    provider: "Weitere Anbieter",
    models: [
      {
        id: "deepseek/deepseek-v3.2",
        name: "DeepSeek V3.2 — sehr günstig",
        blurb: "Offenes Modell, solide für Standarderklärungen zu geringen Kosten.",
      },
      {
        id: "x-ai/grok-4.3",
        name: "Grok 4.3 — großer Kontext",
        blurb: "xAI-Modell mit sehr großem Kontextfenster.",
      },
      {
        id: "mistralai/mistral-large-2512",
        name: "Mistral Large 3 — ausgewogen",
        blurb: "Europäisches Modell, gutes Preis-Leistungs-Verhältnis.",
      },
    ],
  },
];

export const CHAT_MODELS: ChatModelOption[] = CHAT_MODEL_GROUPS.flatMap((g) => g.models);

const STORAGE_KEY = "itm-chat-model";
export const DEFAULT_CHAT_MODEL = "anthropic/claude-sonnet-5";

function isKnown(id: string): boolean {
  return CHAT_MODELS.some((m) => m.id === id);
}

/** Selected chat model, persisted per browser. */
export function useChatModel() {
  const [model, setModelState] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored && isKnown(stored) ? stored : DEFAULT_CHAT_MODEL;
    } catch {
      return DEFAULT_CHAT_MODEL;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, model);
    } catch {
      // ignore — private mode or blocked storage
    }
  }, [model]);

  const setModel = useCallback((id: string) => setModelState(id), []);

  return { model, setModel };
}
