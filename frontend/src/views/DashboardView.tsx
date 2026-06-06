import { useEffect, useMemo, useState } from "react";

import { getPnlSeries, getStatsInsights, getTrades } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { TradeForm } from "../components/TradeForm";
import { PnlSeriesPointResponse, StatsInsightsResponse } from "../types/summary";
import { TradeResponse } from "../types/trade";
import { GREEN_POS, RED_NEG } from "../utils/colors";
import {
  formatDateLong,
  formatMonthDayNumeric,
  formatPercentFromRate,
  formatPercentValue,
  formatSignedUsd,
  formatUsd,
} from "../utils/formatting";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./DashboardView.css";

interface DashboardViewProps {
  refreshKey: number;
  setupRefreshKey: number;
  emotionRefreshKey: number;
  onTradeCreated: () => void;
  duplicateTrade?: TradeResponse | null;
  onClearDuplicateTrade?: () => void;
  openAddTradeRequest?: number;
  onNavigateToImport?: () => void;
}

type DashboardRangePreset = "wtd" | "mtd" | "ytd";

interface DashboardRange {
  start: string;
  end: string;
}

interface AggregatedRow {
  label: string;
  count: number;
  total_pnl_usd: number;
}

interface MiniEquityPoint {
  label: string;
  cumulative_pnl_usd: number;
  daily_pnl_usd: number;
}

interface MiniBarPoint {
  label: string;
  total_pnl_usd: number;
  trade_count: number;
}

interface DonutDatum {
  name: string;
  value: number;
}

interface PerformanceCallout {
  title: string;
  primary: string;
  secondary: string;
  tone: "positive" | "negative";
}

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getRangeForPreset(preset: DashboardRangePreset): DashboardRange {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const start = new Date(today);
  if (preset === "wtd") {
    const dayOfWeek = start.getDay();
    const mondayOffset = (dayOfWeek + 6) % 7;
    start.setDate(start.getDate() - mondayOffset);
  } else if (preset === "mtd") {
    start.setDate(1);
  } else {
    start.setMonth(0, 1);
  }

  return {
    start: toIsoDate(start),
    end: toIsoDate(today),
  };
}

function normalizeTicker(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toUpperCase();
  return normalized || "UNKNOWN";
}

function sortSeriesByStartDate(series: PnlSeriesPointResponse[]): PnlSeriesPointResponse[] {
  return [...series].sort((left, right) => left.start_date.localeCompare(right.start_date));
}

function aggregateTopSetups(trades: TradeResponse[]): AggregatedRow[] {
  return aggregateSetupRows(trades).slice(0, 5);
}

function aggregateSetupRows(trades: TradeResponse[]): AggregatedRow[] {
  const bySetup = new Map<string, AggregatedRow>();

  for (const trade of trades) {
    const isUnclassified = !trade.setup_id || !trade.setup_name?.trim();
    const key = isUnclassified ? "unclassified" : `setup:${trade.setup_id}`;
    const label = isUnclassified ? "UNCLASSIFIED" : trade.setup_name;
    const existing = bySetup.get(key);
    if (existing) {
      existing.count += 1;
      existing.total_pnl_usd += trade.total_pnl_usd;
      continue;
    }
    bySetup.set(key, { label, count: 1, total_pnl_usd: trade.total_pnl_usd });
  }

  return [...bySetup.values()]
    .sort(
      (left, right) =>
        right.total_pnl_usd - left.total_pnl_usd ||
        right.count - left.count ||
        left.label.localeCompare(right.label)
    );
}

function aggregateTopTickers(trades: TradeResponse[]): AggregatedRow[] {
  return aggregateTickerRows(trades).slice(0, 5);
}

function aggregateTickerRows(trades: TradeResponse[]): AggregatedRow[] {
  const byTicker = new Map<string, AggregatedRow>();

  for (const trade of trades) {
    const ticker = normalizeTicker(trade.ticker);
    const existing = byTicker.get(ticker);
    if (existing) {
      existing.count += 1;
      existing.total_pnl_usd += trade.total_pnl_usd;
      continue;
    }
    byTicker.set(ticker, { label: ticker, count: 1, total_pnl_usd: trade.total_pnl_usd });
  }

  return [...byTicker.values()]
    .sort(
      (left, right) =>
        right.total_pnl_usd - left.total_pnl_usd ||
        right.count - left.count ||
        left.label.localeCompare(right.label)
    );
}

function compareRecentTrades(left: TradeResponse, right: TradeResponse): number {
  const byDate = right.date.localeCompare(left.date);
  if (byDate !== 0) {
    return byDate;
  }

  const leftTime = left.entry_time ?? "";
  const rightTime = right.entry_time ?? "";
  const byTime = rightTime.localeCompare(leftTime);
  if (byTime !== 0) {
    return byTime;
  }

  return right.id - left.id;
}

function formatDonutPercent(percent?: number): string {
  if (!percent || percent <= 0) {
    return "";
  }
  return formatPercentValue(percent * 100, 0);
}

export function DashboardView({
  refreshKey,
  setupRefreshKey,
  emotionRefreshKey,
  onTradeCreated,
  duplicateTrade,
  onClearDuplicateTrade,
  openAddTradeRequest = 0,
  onNavigateToImport,
}: DashboardViewProps) {
  const [rangePreset, setRangePreset] = useState<DashboardRangePreset>("wtd");
  const [rangeOverall, setRangeOverall] = useState<StatsInsightsResponse["overall"] | null>(null);
  const [rangeTrades, setRangeTrades] = useState<TradeResponse[]>([]);
  const [rangeDailySeries, setRangeDailySeries] = useState<PnlSeriesPointResponse[]>([]);
  const [rangeWeeklySeries, setRangeWeeklySeries] = useState<PnlSeriesPointResponse[]>([]);
  const [isLoadingRangeData, setIsLoadingRangeData] = useState(false);
  const [rangeDataError, setRangeDataError] = useState<string | null>(null);
  const [isAddTradeModalOpen, setIsAddTradeModalOpen] = useState(false);
  const [focusTickerSignal, setFocusTickerSignal] = useState(0);
  const range = useMemo(() => getRangeForPreset(rangePreset), [rangePreset]);

  useEffect(() => {
    async function loadDashboardRangeData() {
      setIsLoadingRangeData(true);
      setRangeDataError(null);
      try {
        const [insightsResponse, tradesResponse, dailySeriesResponse, weeklySeriesResponse] =
          await Promise.all([
            getStatsInsights(range.start, range.end),
            getTrades({ start: range.start, end: range.end }),
            getPnlSeries("daily", range.start, range.end),
            getPnlSeries("weekly", range.start, range.end),
          ]);

        setRangeOverall(insightsResponse.overall);
        setRangeTrades(tradesResponse);
        setRangeDailySeries(dailySeriesResponse.series);
        setRangeWeeklySeries(weeklySeriesResponse.series);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load dashboard KPIs.";
        setRangeDataError(message);
        setRangeOverall(null);
        setRangeTrades([]);
        setRangeDailySeries([]);
        setRangeWeeklySeries([]);
      } finally {
        setIsLoadingRangeData(false);
      }
    }

    void loadDashboardRangeData();
  }, [range.start, range.end, refreshKey]);

  useEffect(() => {
    if (isAddTradeModalOpen) {
      setFocusTickerSignal((previous) => previous + 1);
    }
  }, [isAddTradeModalOpen]);

  useEffect(() => {
    if (!duplicateTrade) {
      return;
    }
    setIsAddTradeModalOpen(true);
  }, [duplicateTrade]);

  useEffect(() => {
    if (openAddTradeRequest <= 0) {
      return;
    }
    setIsAddTradeModalOpen(true);
  }, [openAddTradeRequest]);

  useEffect(() => {
    if (!isAddTradeModalOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsAddTradeModalOpen(false);
        if (duplicateTrade) {
          onClearDuplicateTrade?.();
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isAddTradeModalOpen, duplicateTrade, onClearDuplicateTrade]);

  const sortedDailySeries = useMemo(
    () => sortSeriesByStartDate(rangeDailySeries),
    [rangeDailySeries]
  );
  const sortedWeeklySeries = useMemo(
    () => sortSeriesByStartDate(rangeWeeklySeries),
    [rangeWeeklySeries]
  );
  const miniEquitySeries = useMemo<MiniEquityPoint[]>(() => {
    let cumulative = 0;
    return sortedDailySeries.map((point) => {
      cumulative += point.total_pnl_usd;
      return {
        label: formatMonthDayNumeric(point.start_date),
        cumulative_pnl_usd: cumulative,
        daily_pnl_usd: point.total_pnl_usd,
      };
    });
  }, [sortedDailySeries]);
  const secondaryMiniBarSeries = useMemo<MiniBarPoint[]>(() => {
    if (rangePreset === "wtd") {
      return sortedDailySeries.map((point) => ({
        label: formatMonthDayNumeric(point.start_date),
        total_pnl_usd: point.total_pnl_usd,
        trade_count: point.trade_count,
      }));
    }

    return sortedWeeklySeries.map((point) => ({
      label: formatMonthDayNumeric(point.start_date),
      total_pnl_usd: point.total_pnl_usd,
      trade_count: point.trade_count,
    }));
  }, [rangePreset, sortedDailySeries, sortedWeeklySeries]);
  const allSetupRows = useMemo(() => aggregateSetupRows(rangeTrades), [rangeTrades]);
  const allTickerRows = useMemo(() => aggregateTickerRows(rangeTrades), [rangeTrades]);
  const topSetups = useMemo(() => aggregateTopSetups(rangeTrades), [rangeTrades]);
  const topTickers = useMemo(() => aggregateTopTickers(rangeTrades), [rangeTrades]);
  const recentTrades = useMemo(
    () => [...rangeTrades].sort(compareRecentTrades).slice(0, 10),
    [rangeTrades]
  );
  const tradeWinLossCounts = useMemo(() => {
    let winners = 0;
    let losers = 0;

    for (const trade of rangeTrades) {
      if (trade.total_pnl_usd > 0) {
        winners += 1;
      } else if (trade.total_pnl_usd < 0) {
        losers += 1;
      }
    }

    return { winners, losers, total: winners + losers };
  }, [rangeTrades]);
  const dayWinLossCounts = useMemo(() => {
    const dailyTotals = new Map<string, number>();

    for (const trade of rangeTrades) {
      dailyTotals.set(trade.date, (dailyTotals.get(trade.date) ?? 0) + trade.total_pnl_usd);
    }

    let winningDays = 0;
    let losingDays = 0;
    for (const totalPnl of dailyTotals.values()) {
      if (totalPnl > 0) {
        winningDays += 1;
      } else if (totalPnl < 0) {
        losingDays += 1;
      }
    }

    return { winningDays, losingDays, total: winningDays + losingDays };
  }, [rangeTrades]);
  const tradeWinLossData = useMemo<DonutDatum[]>(
    () => [
      { name: "Winners", value: tradeWinLossCounts.winners },
      { name: "Losers", value: tradeWinLossCounts.losers },
    ],
    [tradeWinLossCounts.losers, tradeWinLossCounts.winners]
  );
  const dayWinLossData = useMemo<DonutDatum[]>(
    () => [
      { name: "Total Winning Days", value: dayWinLossCounts.winningDays },
      { name: "Total Losing Days", value: dayWinLossCounts.losingDays },
    ],
    [dayWinLossCounts.losingDays, dayWinLossCounts.winningDays]
  );
  const hasDonutData = tradeWinLossCounts.total > 0 || dayWinLossCounts.total > 0;
  const performanceCallouts = useMemo<PerformanceCallout[]>(() => {
    const bestSetup = allSetupRows[0] ?? null;
    const worstSetup = [...allSetupRows]
      .sort(
        (left, right) =>
          left.total_pnl_usd - right.total_pnl_usd ||
          right.count - left.count ||
          left.label.localeCompare(right.label)
      )[0] ?? null;
    const bestTicker = allTickerRows[0] ?? null;
    const worstTicker = [...allTickerRows]
      .sort(
        (left, right) =>
          left.total_pnl_usd - right.total_pnl_usd ||
          right.count - left.count ||
          left.label.localeCompare(right.label)
      )[0] ?? null;
    const largestWin =
      [...rangeTrades]
        .filter((trade) => trade.total_pnl_usd > 0)
        .sort((left, right) => right.total_pnl_usd - left.total_pnl_usd)[0] ?? null;
    const largestLoss =
      [...rangeTrades]
        .filter((trade) => trade.total_pnl_usd < 0)
        .sort((left, right) => left.total_pnl_usd - right.total_pnl_usd)[0] ?? null;

    return [
      {
        title: "Best Setup",
        primary: bestSetup?.label ?? "No data",
        secondary: bestSetup ? formatSignedUsd(bestSetup.total_pnl_usd) : "No data",
        tone: "positive",
      },
      {
        title: "Worst Setup",
        primary: worstSetup?.label ?? "No data",
        secondary: worstSetup ? formatSignedUsd(worstSetup.total_pnl_usd) : "No data",
        tone: "negative",
      },
      {
        title: "Best Ticker",
        primary: bestTicker?.label ?? "No data",
        secondary: bestTicker ? formatSignedUsd(bestTicker.total_pnl_usd) : "No data",
        tone: "positive",
      },
      {
        title: "Worst Ticker",
        primary: worstTicker?.label ?? "No data",
        secondary: worstTicker ? formatSignedUsd(worstTicker.total_pnl_usd) : "No data",
        tone: "negative",
      },
      {
        title: "Largest Win",
        primary: largestWin ? normalizeTicker(largestWin.ticker) : "No data",
        secondary: largestWin ? formatSignedUsd(largestWin.total_pnl_usd) : "No data",
        tone: "positive",
      },
      {
        title: "Largest Loss",
        primary: largestLoss ? normalizeTicker(largestLoss.ticker) : "No data",
        secondary: largestLoss ? formatSignedUsd(largestLoss.total_pnl_usd) : "No data",
        tone: "negative",
      },
    ];
  }, [allSetupRows, allTickerRows, rangeTrades]);

  const kpiCards = [
    {
      label: "Total PnL (USD)",
      value: formatUsd(rangeOverall?.total_pnl_usd ?? 0),
    },
    {
      label: "Total Trades",
      value: String(rangeOverall?.total_trades ?? 0),
    },
    {
      label: "Win Rate",
      value: formatPercentFromRate(rangeOverall?.win_rate ?? 0),
    },
    {
      label: "Avg Win (USD)",
      value: formatUsd(rangeOverall?.avg_win_usd ?? 0),
    },
    {
      label: "Avg Loss (USD)",
      value: formatUsd(rangeOverall?.avg_loss_usd ?? 0),
    },
    {
      label: "Expectancy (USD/trade)",
      value: formatUsd(rangeOverall?.expectancy_usd_per_trade ?? 0),
    },
  ];
  const isWelcomeStateVisible = !isLoadingRangeData && !rangeDataError && rangeTrades.length === 0;

  function openAddTradeModal() {
    setIsAddTradeModalOpen(true);
  }

  function closeAddTradeModal() {
    setIsAddTradeModalOpen(false);
    if (duplicateTrade) {
      onClearDuplicateTrade?.();
    }
  }

  function handleTradeCreatedInModal() {
    onTradeCreated();
    setIsAddTradeModalOpen(false);
  }

  return (
    <section className="dashboard-daily-layout">
      <div className="dashboard-daily-overview">
        <section className="dashboard-range-panel">
          <div className="dashboard-range-header">
            <div className="dashboard-range-controls" role="tablist" aria-label="Dashboard range">
              <button
                type="button"
                className={`dashboard-range-button${rangePreset === "wtd" ? " active" : ""}`}
                onClick={() => setRangePreset("wtd")}
              >
                WTD
              </button>
              <button
                type="button"
                className={`dashboard-range-button${rangePreset === "mtd" ? " active" : ""}`}
                onClick={() => setRangePreset("mtd")}
              >
                MTD
              </button>
              <button
                type="button"
                className={`dashboard-range-button${rangePreset === "ytd" ? " active" : ""}`}
                onClick={() => setRangePreset("ytd")}
              >
                YTD
              </button>
            </div>
            {!isWelcomeStateVisible ? (
              <button
                type="button"
                className="dashboard-add-trade-quick-button"
                onClick={openAddTradeModal}
              >
                + Add Trade
              </button>
            ) : null}
          </div>
          <p className="dashboard-range-label">
            Range: {formatDateLong(range.start)} to {formatDateLong(range.end)}
          </p>
          {isLoadingRangeData ? (
            <p className="dashboard-range-status">Loading dashboard data...</p>
          ) : rangeDataError ? (
            <p className="dashboard-range-status error">{rangeDataError}</p>
          ) : null}
          {isWelcomeStateVisible ? (
            <EmptyState
              title="Welcome to your trading journal"
              description="Start by adding your first trade or importing a ThinkorSwim CSV."
              actions={[
                { label: "Add Trade", onClick: openAddTradeModal },
                ...(onNavigateToImport
                  ? [
                      {
                        label: "Import CSV",
                        onClick: onNavigateToImport,
                        variant: "secondary" as const,
                      },
                    ]
                  : []),
              ]}
            />
          ) : null}
          <div className="dashboard-kpi-strip">
            {kpiCards.map((card) => (
              <article key={card.label} className="dashboard-kpi-card">
                <h3>{card.label}</h3>
                <p>{card.value}</p>
              </article>
            ))}
          </div>

          <section className="dashboard-callouts-section" aria-labelledby="dashboard-callouts-title">
            <div className="dashboard-mini-header">
              <h3 id="dashboard-callouts-title">Performance Callouts</h3>
            </div>
            {rangeTrades.length === 0 ? (
              <p className="dashboard-mini-empty">No performance callouts for this range.</p>
            ) : (
              <div className="dashboard-callouts-grid">
                {performanceCallouts.map((callout) => (
                  <article
                    key={callout.title}
                    className={`dashboard-callout-card dashboard-callout-card--${callout.tone}`}
                  >
                    <h4>{callout.title}</h4>
                    <p className="dashboard-callout-primary">{callout.primary}</p>
                    <p className="dashboard-callout-secondary">{callout.secondary}</p>
                  </article>
                ))}
              </div>
            )}
          </section>

          <div className="dashboard-mini-grid">
            <article className="dashboard-mini-card">
              <div className="dashboard-mini-header">
                <h3>Mini Equity Curve</h3>
              </div>
              {miniEquitySeries.length === 0 ? (
                <p className="dashboard-mini-empty">No data for this range.</p>
              ) : (
                <div className="dashboard-mini-chart-shell">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={miniEquitySeries} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" minTickGap={18} tick={{ fontSize: 11 }} />
                      <YAxis hide />
                      <Tooltip
                        formatter={(value, _name, item) => {
                          const numericValue =
                            typeof value === "number" ? value : Number(value ?? 0);
                          if (item?.dataKey === "daily_pnl_usd") {
                            return [formatUsd(numericValue), "Daily PnL"];
                          }
                          return [formatUsd(numericValue), "Cumulative PnL"];
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="cumulative_pnl_usd"
                        stroke="#1d4ed8"
                        strokeWidth={2}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </article>

            <article className="dashboard-mini-card">
              <div className="dashboard-mini-header">
                <h3>{rangePreset === "wtd" ? "Daily PnL" : "Weekly PnL"}</h3>
              </div>
              {secondaryMiniBarSeries.length === 0 ? (
                <p className="dashboard-mini-empty">No data for this range.</p>
              ) : (
                <div className="dashboard-mini-chart-shell">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={secondaryMiniBarSeries}
                      margin={{ top: 8, right: 8, bottom: 4, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" minTickGap={18} tick={{ fontSize: 11 }} />
                      <YAxis hide />
                      <Tooltip
                        formatter={(value, name, context) => {
                          if (name === "total_pnl_usd") {
                            const numericValue =
                              typeof value === "number" ? value : Number(value ?? 0);
                            return [formatUsd(numericValue), "Total PnL"];
                          }
                          return [String(context?.payload?.trade_count ?? 0), "Trades"];
                        }}
                        labelFormatter={(value) => `Period: ${String(value ?? "")}`}
                      />
                      <Bar
                        dataKey="total_pnl_usd"
                        radius={[3, 3, 0, 0]}
                        isAnimationActive={false}
                      >
                        {secondaryMiniBarSeries.map((point, index) => (
                          <Cell
                            key={`${point.label}-${index}`}
                            fill={point.total_pnl_usd >= 0 ? GREEN_POS : RED_NEG}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </article>
          </div>

          <div className="dashboard-top-grid">
            <article className="dashboard-top-card">
              <h3>Top Setups (by PnL)</h3>
              {topSetups.length === 0 ? (
                <p className="dashboard-mini-empty">No setup data for this range.</p>
              ) : (
                <table className="dashboard-compact-table">
                  <thead>
                    <tr>
                      <th>Setup</th>
                      <th>Trades</th>
                      <th>Total PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topSetups.map((row) => (
                      <tr key={row.label}>
                        <td>{row.label}</td>
                        <td>{row.count}</td>
                        <td>{formatUsd(row.total_pnl_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </article>

            <article className="dashboard-top-card">
              <h3>Top Tickers (by PnL)</h3>
              {topTickers.length === 0 ? (
                <p className="dashboard-mini-empty">No ticker data for this range.</p>
              ) : (
                <table className="dashboard-compact-table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Trades</th>
                      <th>Total PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topTickers.map((row) => (
                      <tr key={row.label}>
                        <td>{row.label}</td>
                        <td>{row.count}</td>
                        <td>{formatUsd(row.total_pnl_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </article>
          </div>

          <article className="dashboard-recent-card">
            <h3>Recent Trades</h3>
            {recentTrades.length === 0 ? (
              <p className="dashboard-mini-empty">No recent trades in this range.</p>
            ) : (
              <div className="dashboard-recent-layout">
                <div className="dashboard-recent-left">
                  <div className="dashboard-recent-wrap">
                    <table className="dashboard-compact-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Ticker</th>
                          <th>PnL</th>
                          <th>Setup</th>
                          <th>Emotion</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentTrades.map((trade) => (
                          <tr key={trade.id}>
                            <td>{formatDateLong(trade.date)}</td>
                            <td>{trade.ticker}</td>
                            <td>{formatUsd(trade.total_pnl_usd)}</td>
                            <td>{trade.setup_name || "UNCLASSIFIED"}</td>
                            <td>{trade.emotion_name || "UNCLASSIFIED"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <aside className="dashboard-recent-empty-side">
                  {!hasDonutData ? (
                    <p className="dashboard-mini-empty">
                      Not enough data for charts in this range.
                    </p>
                  ) : (
                    <article className="dashboard-win-rates-card">
                      <h4>Win Rates</h4>
                      <p className="dashboard-win-rates-subtitle">By Trades vs By Days</p>
                      <div className="dashboard-donut-grid">
                        <div className="dashboard-donut-pane">
                          <h5>Winning % By Trades</h5>
                          {tradeWinLossCounts.total === 0 ? (
                            <p className="dashboard-mini-empty">Not enough data for this chart.</p>
                          ) : (
                            <div className="dashboard-donut-shell">
                              <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                  <Pie
                                    data={tradeWinLossData}
                                    dataKey="value"
                                    nameKey="name"
                                    innerRadius={38}
                                    outerRadius={66}
                                    paddingAngle={2}
                                    label={({ percent }) => formatDonutPercent(percent)}
                                    labelLine={false}
                                    isAnimationActive={false}
                                  >
                                    {tradeWinLossData.map((entry) => (
                                      <Cell
                                        key={entry.name}
                                        fill={entry.name === "Winners" ? GREEN_POS : RED_NEG}
                                      />
                                    ))}
                                  </Pie>
                                  <Legend
                                    verticalAlign="bottom"
                                    align="center"
                                    layout="horizontal"
                                    iconType="circle"
                                    wrapperStyle={{ fontSize: 11 }}
                                  />
                                </PieChart>
                              </ResponsiveContainer>
                            </div>
                          )}
                        </div>

                        <div className="dashboard-donut-pane">
                          <h5>Winning % By Days</h5>
                          {dayWinLossCounts.total === 0 ? (
                            <p className="dashboard-mini-empty">Not enough data for this chart.</p>
                          ) : (
                            <div className="dashboard-donut-shell">
                              <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                  <Pie
                                    data={dayWinLossData}
                                    dataKey="value"
                                    nameKey="name"
                                    innerRadius={38}
                                    outerRadius={66}
                                    paddingAngle={2}
                                    label={({ percent }) => formatDonutPercent(percent)}
                                    labelLine={false}
                                    isAnimationActive={false}
                                  >
                                    {dayWinLossData.map((entry) => (
                                      <Cell
                                        key={entry.name}
                                        fill={entry.name === "Total Winning Days" ? GREEN_POS : RED_NEG}
                                      />
                                    ))}
                                  </Pie>
                                  <Legend
                                    verticalAlign="bottom"
                                    align="center"
                                    layout="horizontal"
                                    iconType="circle"
                                    wrapperStyle={{ fontSize: 11 }}
                                  />
                                </PieChart>
                              </ResponsiveContainer>
                            </div>
                          )}
                        </div>
                      </div>
                    </article>
                  )}
                </aside>
              </div>
            )}
          </article>
        </section>
      </div>

      {isAddTradeModalOpen ? (
        <div
          className="dashboard-add-trade-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeAddTradeModal();
            }
          }}
        >
          <section
            className="dashboard-add-trade-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dashboard-add-trade-modal-title"
          >
            <div className="dashboard-add-trade-modal-header">
              <h2 id="dashboard-add-trade-modal-title">Add Trade</h2>
              <button
                type="button"
                className="dashboard-add-trade-modal-close"
                onClick={closeAddTradeModal}
                aria-label="Close add trade modal"
              >
                ✕
              </button>
            </div>
            <TradeForm
              onTradeCreated={handleTradeCreatedInModal}
              hideTitle
              setupRefreshKey={setupRefreshKey}
              emotionRefreshKey={emotionRefreshKey}
              duplicateTrade={duplicateTrade}
              onClearDuplicateTrade={onClearDuplicateTrade}
              focusTickerSignal={focusTickerSignal}
            />
          </section>
        </div>
      ) : null}
    </section>
  );
}
