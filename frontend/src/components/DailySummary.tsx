import { useEffect, useState } from "react";

import { getDailySummary } from "../api/client";
import { DailySummaryResponse } from "../types/summary";
import { formatDateLong, formatPercentValue, formatUsd } from "../utils/formatting";
import "./DailySummary.css";

interface DailySummaryProps {
  date: string;
  refreshKey?: number;
  hideTitle?: boolean;
}

function getInterpretation(score: number): string {
  if (score >= 20) {
    return "Strong discipline day";
  }
  if (score >= 0) {
    return "Decent\u2014room to tighten up";
  }
  return "Protect capital\u2014review rule breaks";
}

export function DailySummary({
  date,
  refreshKey = 0,
  hideTitle = false,
}: DailySummaryProps) {
  const [summary, setSummary] = useState<DailySummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadSummary() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const response = await getDailySummary(date);
        setSummary(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load summary.";
        setErrorMessage(message);
        setSummary(null);
      } finally {
        setIsLoading(false);
      }
    }

    void loadSummary();
  }, [date, refreshKey]);

  if (isLoading) {
    return (
      <section className="daily-summary-panel">
        {!hideTitle ? <h2>Daily Summary</h2> : null}
        <p className="summary-status">Loading summary...</p>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section className="daily-summary-panel">
        {!hideTitle ? <h2>Daily Summary</h2> : null}
        <p className="summary-status error">{errorMessage}</p>
      </section>
    );
  }

  if (!summary) {
    return (
      <section className="daily-summary-panel">
        {!hideTitle ? <h2>Daily Summary</h2> : null}
        <p className="summary-status">No summary available.</p>
      </section>
    );
  }

  return (
    <section className="daily-summary-panel">
      {!hideTitle ? <h2>Daily Summary</h2> : null}
      <p className="summary-date">{formatDateLong(date)}</p>
      {summary.total_trades === 0 ? <p className="summary-status">No trades for this date yet.</p> : null}
      <div className="summary-grid">
        <article>
          <h3>Total Trades</h3>
          <p>{summary.total_trades}</p>
        </article>
        <article>
          <h3>Rule Followed</h3>
          <p>{formatPercentValue(summary.pct_rule_followed)}</p>
        </article>
        <article>
          <h3>Discipline Score</h3>
          <p>{summary.discipline_score}</p>
        </article>
        <article>
          <h3>Total PnL (USD)</h3>
          <p>{formatUsd(summary.total_pnl)}</p>
        </article>
      </div>
      <p className="summary-interpretation">{getInterpretation(summary.discipline_score)}</p>
    </section>
  );
}
