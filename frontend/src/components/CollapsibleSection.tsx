import { ReactNode, useEffect, useMemo, useState } from "react";

import "./CollapsibleSection.css";

interface CollapsibleSectionProps {
  id: string;
  title: string;
  headerRight?: ReactNode;
  defaultCollapsed?: boolean;
  isCollapsed?: boolean;
  onCollapsedChange?: (isCollapsed: boolean) => void;
  keepMountedWhenCollapsed?: boolean;
  children: ReactNode;
}

function getStorageKey(id: string): string {
  return `discipline-tracker:section:${id}`;
}

export function CollapsibleSection({
  id,
  title,
  headerRight,
  defaultCollapsed = false,
  isCollapsed,
  onCollapsedChange,
  keepMountedWhenCollapsed = false,
  children,
}: CollapsibleSectionProps) {
  const storageKey = useMemo(() => getStorageKey(id), [id]);
  const [internalCollapsed, setInternalCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return defaultCollapsed;
    }

    const saved = window.sessionStorage.getItem(storageKey);
    if (saved === "true") {
      return true;
    }
    if (saved === "false") {
      return false;
    }
    return defaultCollapsed;
  });
  const resolvedIsCollapsed = isCollapsed ?? internalCollapsed;

  function handleToggle() {
    const nextValue = !resolvedIsCollapsed;
    if (isCollapsed === undefined) {
      setInternalCollapsed(nextValue);
    }
    onCollapsedChange?.(nextValue);
  }

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(storageKey, String(resolvedIsCollapsed));
    }
  }, [resolvedIsCollapsed, storageKey]);

  return (
    <section className="collapsible-section">
      <div className="collapsible-header">
        <button
          type="button"
          className="collapsible-toggle"
          onClick={handleToggle}
          aria-expanded={!resolvedIsCollapsed}
        >
          <div className="collapsible-title-wrap">
            <span className="collapsible-chevron">{resolvedIsCollapsed ? "▸" : "▾"}</span>
            <span className="collapsible-title">{title}</span>
          </div>
        </button>
        {headerRight ? <div className="collapsible-right">{headerRight}</div> : null}
      </div>
      {keepMountedWhenCollapsed ? (
        <div
          className={`collapsible-content${resolvedIsCollapsed ? " is-hidden" : ""}`}
          aria-hidden={resolvedIsCollapsed}
        >
          {children}
        </div>
      ) : !resolvedIsCollapsed ? (
        <div className="collapsible-content">{children}</div>
      ) : null}
    </section>
  );
}
