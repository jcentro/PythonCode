import { ReactNode } from "react";

import "./DashboardLayout.css";

interface DashboardLayoutProps {
  summary: ReactNode;
  statistics: ReactNode;
  addTrade: ReactNode;
  trades: ReactNode;
  manageSetups: ReactNode;
  manageEmotions: ReactNode;
}

export function DashboardLayout({
  summary,
  statistics,
  addTrade,
  trades,
  manageSetups,
  manageEmotions,
}: DashboardLayoutProps) {
  return (
    <section className="dashboard-layout">
      <div className="dashboard-area dashboard-summary">{summary}</div>
      <div className="dashboard-area dashboard-statistics">{statistics}</div>
      <div className="dashboard-area dashboard-add-trade">{addTrade}</div>
      <div className="dashboard-area dashboard-trades">{trades}</div>
      <div className="dashboard-area dashboard-manage-setups">{manageSetups}</div>
      <div className="dashboard-area dashboard-manage-emotions">{manageEmotions}</div>
    </section>
  );
}
