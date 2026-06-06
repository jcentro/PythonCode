import { useCallback, useEffect, useState } from "react";

import { getUnclassifiedTradesCount } from "./api/client";
import { TradeListFilters } from "./types/trade";
import { TradeResponse } from "./types/trade";
import { getTodayDate } from "./utils/date";
import { DashboardView } from "./views/DashboardView";
import { InboxView } from "./views/InboxView";
import { ImportHistoryView } from "./views/ImportHistoryView";
import { ImportView } from "./views/ImportView";
import { SettingsView } from "./views/SettingsView";
import { StatisticsView } from "./views/StatisticsView";
import { TradeHistoryView } from "./views/TradeHistoryView";
import "./App.css";

const ACTIVE_VIEW_STORAGE_KEY = "discipline-tracker:active-view";
const SIDEBAR_OPEN_STORAGE_KEY = "discipline-tracker:sidebar-open";
const SIDEBAR_COLLAPSED_STORAGE_KEY = "sidebarCollapsed";
const APP_VERSION = "v1.0.0-rc1";
const APP_VERSION_COMPACT = APP_VERSION.replace(/\.0-rc\d+$/, "");
type AppView =
  | "dashboard"
  | "inbox"
  | "statistics"
  | "trade-history"
  | "settings"
  | "import"
  | "import-history";

interface NavItem {
  id: AppView;
  label: string;
  iconLabel: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", iconLabel: "DB" },
      { id: "inbox", label: "Inbox", iconLabel: "IN" },
      { id: "statistics", label: "Statistics", iconLabel: "ST" },
    ],
  },
  {
    label: "Trades",
    items: [
      { id: "trade-history", label: "Trade History", iconLabel: "TH" },
      { id: "import", label: "Import", iconLabel: "UP" },
      { id: "import-history", label: "Import History", iconLabel: "IH" },
    ],
  },
  {
    label: "System",
    items: [{ id: "settings", label: "Settings", iconLabel: "SE" }],
  },
];

const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);

export default function App() {
  const [selectedDate] = useState(getTodayDate);
  const [tradeHistoryFilters, setTradeHistoryFilters] = useState<TradeListFilters>({
    start: selectedDate,
    end: selectedDate,
  });
  const [duplicateTrade, setDuplicateTrade] = useState<TradeResponse | null>(null);
  const [openAddTradeRequest, setOpenAddTradeRequest] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [setupRefreshKey, setSetupRefreshKey] = useState(0);
  const [emotionRefreshKey, setEmotionRefreshKey] = useState(0);
  const [activeView, setActiveView] = useState<AppView>(() => {
    if (typeof window === "undefined") {
      return "dashboard";
    }
    try {
      const stored = window.localStorage.getItem(ACTIVE_VIEW_STORAGE_KEY);
      if (
        stored === "dashboard" ||
        stored === "inbox" ||
        stored === "statistics" ||
        stored === "trade-history" ||
        stored === "settings" ||
        stored === "import" ||
        stored === "import-history"
      ) {
        return stored;
      }
      return "dashboard";
    } catch {
      return "dashboard";
    }
  });
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    try {
      return window.localStorage.getItem(SIDEBAR_OPEN_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    try {
      return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [unclassifiedCount, setUnclassifiedCount] = useState(0);

  const refreshUnclassifiedCount = useCallback(async () => {
    try {
      const count = await getUnclassifiedTradesCount();
      setUnclassifiedCount(count);
    } catch {
      // Badge should fail silently when count endpoint is temporarily unavailable.
    }
  }, []);

  const triggerDataRefresh = useCallback(() => {
    setRefreshKey((previous) => previous + 1);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_VIEW_STORAGE_KEY, activeView);
    }
  }, [activeView]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SIDEBAR_OPEN_STORAGE_KEY, String(isSidebarOpen));
    }
  }, [isSidebarOpen]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        SIDEBAR_COLLAPSED_STORAGE_KEY,
        String(isSidebarCollapsed)
      );
    }
  }, [isSidebarCollapsed]);

  useEffect(() => {
    setTradeHistoryFilters((previous) => ({
      ...previous,
      start: selectedDate,
      end: selectedDate,
    }));
  }, [selectedDate]);

  useEffect(() => {
    void refreshUnclassifiedCount();
  }, [refreshKey, refreshUnclassifiedCount]);

  useEffect(() => {
    if (activeView === "inbox") {
      void refreshUnclassifiedCount();
    }
  }, [activeView, refreshUnclassifiedCount]);

  function navigateToView(nextView: AppView) {
    setActiveView(nextView);
    setIsSidebarOpen(false);
  }

  function navigateToDashboardForAddTrade() {
    setDuplicateTrade(null);
    setOpenAddTradeRequest((previous) => previous + 1);
    setActiveView("dashboard");
    setIsSidebarOpen(false);
  }

  function navigateToTradeHistoryWithFilters(filters: TradeListFilters) {
    setTradeHistoryFilters(filters);
    setActiveView("trade-history");
    setIsSidebarOpen(false);
  }

  function navigateToDashboardWithDuplicate(trade: TradeResponse) {
    setDuplicateTrade(trade);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("discipline-tracker:section:add-trade", "false");
    }
    setActiveView("dashboard");
    setIsSidebarOpen(false);
  }

  function renderActiveView() {
    if (activeView === "statistics") {
      return <StatisticsView onViewTradesFromInsight={navigateToTradeHistoryWithFilters} />;
    }

    if (activeView === "inbox") {
      return (
        <InboxView
          refreshKey={refreshKey}
          setupRefreshKey={setupRefreshKey}
          emotionRefreshKey={emotionRefreshKey}
          onTradeDeleted={triggerDataRefresh}
        />
      );
    }

    if (activeView === "trade-history") {
      return (
        <TradeHistoryView
          selectedDate={selectedDate}
          refreshKey={refreshKey}
          setupRefreshKey={setupRefreshKey}
          emotionRefreshKey={emotionRefreshKey}
          filters={tradeHistoryFilters}
          onFiltersChange={setTradeHistoryFilters}
          onTradeDeleted={triggerDataRefresh}
          onDuplicateTrade={navigateToDashboardWithDuplicate}
          onAddTrade={navigateToDashboardForAddTrade}
          onImportCsv={() => navigateToView("import")}
        />
      );
    }

    if (activeView === "settings") {
      return (
        <SettingsView
          setupRefreshKey={setupRefreshKey}
          emotionRefreshKey={emotionRefreshKey}
          onSetupCreated={() => setSetupRefreshKey((previous) => previous + 1)}
          onEmotionCreated={() => setEmotionRefreshKey((previous) => previous + 1)}
        />
      );
    }

    if (activeView === "import") {
      return <ImportView onImportCommitted={triggerDataRefresh} />;
    }

    if (activeView === "import-history") {
      return (
        <ImportHistoryView
          onViewImportedTrades={navigateToTradeHistoryWithFilters}
          onOpenImport={() => navigateToView("import")}
        />
      );
    }

    return (
      <DashboardView
        refreshKey={refreshKey}
        setupRefreshKey={setupRefreshKey}
        emotionRefreshKey={emotionRefreshKey}
        onTradeCreated={triggerDataRefresh}
        duplicateTrade={duplicateTrade}
        onClearDuplicateTrade={() => setDuplicateTrade(null)}
        openAddTradeRequest={openAddTradeRequest}
        onNavigateToImport={() => navigateToView("import")}
      />
    );
  }

  const activeNavLabel = NAV_ITEMS.find((item) => item.id === activeView)?.label ?? "Dashboard";

  return (
    <div
      className={`app-shell${isSidebarCollapsed ? " sidebar-collapsed" : ""}`}
    >
      <aside
        className={`app-sidebar${isSidebarOpen ? " open" : ""}${
          isSidebarCollapsed ? " collapsed" : ""
        }`}
      >
        <div className="sidebar-brand">
          <div className="sidebar-brand-header">
            <div className="sidebar-brand-main">
              <span className="sidebar-brand-mark" aria-hidden="true">
                DT
              </span>
              {!isSidebarCollapsed ? (
                <div className="sidebar-brand-copy">
                  <h2>Discipline Tracker</h2>
                  <p>Trading Journal</p>
                </div>
              ) : null}
            </div>
            <button
              type="button"
              className="sidebar-collapse-button"
              onClick={() => setIsSidebarCollapsed((previous) => !previous)}
              aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {isSidebarCollapsed ? "»" : "«"}
            </button>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="sidebar-nav-group">
              {!isSidebarCollapsed ? (
                <p className="sidebar-group-label">{group.label}</p>
              ) : null}
              <div className="sidebar-group-items">
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`sidebar-item${activeView === item.id ? " active" : ""}`}
                    onClick={() => navigateToView(item.id)}
                    aria-current={activeView === item.id ? "page" : undefined}
                    aria-label={item.label}
                    title={isSidebarCollapsed ? item.label : undefined}
                  >
                    <span className="sidebar-item-main">
                      <span className="sidebar-item-icon" aria-hidden="true">
                        {item.iconLabel}
                      </span>
                      {!isSidebarCollapsed ? <span>{item.label}</span> : null}
                    </span>
                    {item.id === "inbox" && unclassifiedCount > 0 ? (
                      <span className="sidebar-count-badge">{unclassifiedCount}</span>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div
          className="sidebar-version"
          title={APP_VERSION}
          aria-label={`Application version ${APP_VERSION}`}
        >
          {isSidebarCollapsed ? APP_VERSION_COMPACT : APP_VERSION}
        </div>
      </aside>

      {isSidebarOpen ? (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setIsSidebarOpen(false)}
        />
      ) : null}

      <div className="app-main">
        <header className="app-topbar">
          <div className="app-topbar-left">
            <button
              type="button"
              className="sidebar-toggle"
              aria-label="Toggle navigation"
              onClick={() => setIsSidebarOpen((previous) => !previous)}
            >
              ☰
            </button>
            <div className="app-topbar-title-wrap">
              <h1>Discipline Tracker</h1>
              <p>{activeNavLabel}</p>
            </div>
          </div>
        </header>

        <main className="app-view">{renderActiveView()}</main>
      </div>
    </div>
  );
}
