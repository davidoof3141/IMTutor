import { useEffect, useRef, useState } from "react";
import type { Theme } from "../theme";

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
  username: string;
  roleLabel: string;
  isAdmin: boolean;
  onOpenSettings: () => void;
  onLogout: () => void;
}

export function ProfileMenu({
  theme,
  onToggleTheme,
  username,
  roleLabel,
  isAdmin,
  onOpenSettings,
  onLogout,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handlePointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div className="profile-menu" ref={rootRef}>
      <button
        type="button"
        className="avatar"
        aria-label="Profil und Einstellungen"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="8" r="4" fill="currentColor" />
          <path
            d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </button>

      {open && (
        <div className="profile-popover" role="menu">
          <div className="profile-id">
            <div className="profile-id-name">{username}</div>
            <div className="profile-id-role">{roleLabel}</div>
          </div>

          <button
            type="button"
            className="profile-popover-item"
            role="menuitemcheckbox"
            aria-checked={theme === "dark"}
            onClick={onToggleTheme}
          >
            <span>Dunkelmodus</span>
            <span className={"switch" + (theme === "dark" ? " on" : "")} aria-hidden="true">
              <span className="switch-knob" />
            </span>
          </button>

          {isAdmin && (
            <button
              type="button"
              className="profile-popover-item"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onOpenSettings();
              }}
            >
              Admin-Einstellungen
            </button>
          )}

          <button
            type="button"
            className="profile-popover-item is-danger"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            Abmelden
          </button>
        </div>
      )}
    </div>
  );
}
