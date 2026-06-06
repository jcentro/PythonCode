import { ReactNode } from "react";

import "./EmptyState.css";

interface EmptyStateAction {
  label: string;
  onClick?: () => void;
  href?: string;
  variant?: "primary" | "secondary";
}

interface EmptyStateProps {
  title: string;
  description: string;
  actions?: EmptyStateAction[];
  tone?: "default" | "positive";
  compact?: boolean;
  children?: ReactNode;
}

export function EmptyState({
  title,
  description,
  actions = [],
  tone = "default",
  compact = false,
  children,
}: EmptyStateProps) {
  return (
    <section
      className={`app-empty-state${tone === "positive" ? " is-positive" : ""}${
        compact ? " is-compact" : ""
      }`}
    >
      <span className="app-empty-state-icon" aria-hidden="true">
        {tone === "positive" ? "✓" : "○"}
      </span>
      <div className="app-empty-state-copy">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {actions.length > 0 ? (
        <div className="app-empty-state-actions">
          {actions.map((action) =>
            action.href ? (
              <a
                key={action.label}
                className={`app-empty-state-button${action.variant === "secondary" ? " secondary" : ""}`}
                href={action.href}
              >
                {action.label}
              </a>
            ) : (
              <button
                key={action.label}
                type="button"
                className={`app-empty-state-button${action.variant === "secondary" ? " secondary" : ""}`}
                onClick={action.onClick}
              >
                {action.label}
              </button>
            ),
          )}
        </div>
      ) : null}
      {children}
    </section>
  );
}
