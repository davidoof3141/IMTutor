import type { StudyModeName } from "../types";

interface Props {
  mode: StudyModeName;
  onChange: (mode: StudyModeName) => void;
  disabled?: boolean;
}

const MODES: { value: StudyModeName; label: string }[] = [
  { value: "exploration", label: "Erkundung" },
  { value: "training", label: "Lernplan" },
];

export function ModeToggle({ mode, onChange, disabled }: Props) {
  return (
    <div className="segmented" role="tablist" aria-label="Lernmodus">
      {MODES.map((m) => (
        <button
          key={m.value}
          type="button"
          role="tab"
          aria-selected={mode === m.value}
          className={"segmented-option" + (mode === m.value ? " active" : "")}
          disabled={disabled}
          onClick={() => onChange(m.value)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
