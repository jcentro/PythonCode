import { useEffect, useState } from "react";

import { getTrades } from "../api/client";
import { CollapsibleSection } from "../components/CollapsibleSection";
import { EmptyState } from "../components/EmptyState";
import { TradeFilters, TradeFiltersValue } from "../components/TradeFilters";
import { TradesList } from "../components/TradesList";
import { TradeListFilters, TradeResponse } from "../types/trade";
import "./TradeHistoryView.css";

interface TradeHistoryViewProps {
  selectedDate: string;
  refreshKey: number;
  setupRefreshKey: number;
  emotionRefreshKey: number;
  filters: TradeListFilters;
  onFiltersChange: (filters: TradeListFilters) => void;
  onTradeDeleted: () => void;
  onDuplicateTrade?: (trade: TradeResponse) => void;
  onAddTrade?: () => void;
  onImportCsv?: () => void;
}

function buildDraftFilters(sourceFilters: TradeListFilters, defaultDate: string): TradeFiltersValue {
  const patternValue =
    sourceFilters.pattern === "after_2_losses_next_trade"
      ? "after_2_losses_next_trade"
      : sourceFilters.trade_index_bucket === "after_3"
        ? "trade_index_after_3"
        : "";

  return {
    start: sourceFilters.start ?? defaultDate,
    end: sourceFilters.end ?? defaultDate,
    ticker: sourceFilters.ticker ?? "",
    setupId: sourceFilters.setup_id ? String(sourceFilters.setup_id) : "",
    emotionId: sourceFilters.emotion_id ? String(sourceFilters.emotion_id) : "",
    ruleFollowed: sourceFilters.rule_followed ?? "",
    outcome: sourceFilters.outcome ?? "",
    source: sourceFilters.source ?? "",
    classification: sourceFilters.classification ?? "all",
    pattern: patternValue,
  };
}

function formatRuleFollowed(ruleFollowed: boolean | null): string {
  if (ruleFollowed === true) {
    return "Followed";
  }
  if (ruleFollowed === false) {
    return "Broken";
  }
  return "Unknown";
}

function escapeCsvField(value: string | number): string {
  const normalized = String(value).replace(/"/g, '""');
  if (/[",\r\n]/.test(normalized)) {
    return `"${normalized}"`;
  }
  return normalized;
}

function buildTradesCsv(trades: TradeResponse[]): string {
  const headers = [
    "date",
    "ticker",
    "direction",
    "quantity",
    "entry_price",
    "exit_price",
    "total_pnl_usd",
    "setup",
    "emotion",
    "rule_followed",
    "notes",
    "source",
  ];

  const rows = trades.map((trade) => {
    const sourceValue =
      (
        trade as TradeResponse & {
          source?: string | null;
        }
      ).source === "tos_csv"
        ? "tos_csv"
        : "manual";

    return [
      trade.date,
      trade.ticker ?? "",
      trade.direction ?? "",
      trade.quantity,
      trade.entry_price,
      trade.exit_price,
      trade.total_pnl_usd,
      trade.setup_name ?? "",
      trade.emotion_name ?? "",
      formatRuleFollowed(trade.rule_followed),
      trade.notes ?? "",
      sourceValue,
    ];
  });

  return [headers, ...rows]
    .map((row) => row.map((value) => escapeCsvField(value)).join(","))
    .join("\r\n");
}

function getExportFileName(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `trades_export_${year}-${month}-${day}.csv`;
}

function triggerCsvDownload(csvContent: string): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = getExportFileName();
  link.click();
  URL.revokeObjectURL(url);
}

export function TradeHistoryView({
  selectedDate,
  refreshKey,
  setupRefreshKey,
  emotionRefreshKey,
  filters,
  onFiltersChange,
  onTradeDeleted,
  onDuplicateTrade,
  onAddTrade,
  onImportCsv,
}: TradeHistoryViewProps) {
  const [shownTradesCount, setShownTradesCount] = useState(0);
  const [draftFilters, setDraftFilters] = useState<TradeFiltersValue>(buildDraftFilters(filters, selectedDate));
  const [isExportingFiltered, setIsExportingFiltered] = useState(false);
  const [isExportingAll, setIsExportingAll] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    setDraftFilters(buildDraftFilters(filters, selectedDate));
  }, [filters, selectedDate]);

  function buildAppliedFilters(filters: TradeFiltersValue): TradeListFilters {
    return {
      start: filters.start || undefined,
      end: filters.end || undefined,
      ticker: filters.ticker.trim() || undefined,
      setup_id: filters.setupId ? Number(filters.setupId) : undefined,
      emotion_id: filters.emotionId ? Number(filters.emotionId) : undefined,
      rule_followed: filters.ruleFollowed || undefined,
      outcome: filters.outcome || undefined,
      source: filters.source || undefined,
      classification: filters.classification === "all" ? undefined : filters.classification,
      pattern: filters.pattern === "after_2_losses_next_trade" ? "after_2_losses_next_trade" : undefined,
      trade_index_bucket: filters.pattern === "trade_index_after_3" ? "after_3" : undefined,
    };
  }

  function handleApplyFilters() {
    onFiltersChange({
      ...buildAppliedFilters(draftFilters),
      import_batch_id: filters.import_batch_id,
    });
  }

  function handleClearFilters() {
    const cleared: TradeFiltersValue = {
      start: selectedDate,
      end: selectedDate,
      ticker: "",
      setupId: "",
      emotionId: "",
      ruleFollowed: "",
      outcome: "",
      source: "",
      classification: "all",
      pattern: "",
    };
    setDraftFilters(cleared);
    onFiltersChange(buildAppliedFilters(cleared));
  }

  async function handleExportFiltered() {
    setIsExportingFiltered(true);
    setExportError(null);
    try {
      const trades = await getTrades(filters);
      triggerCsvDownload(buildTradesCsv(trades));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to export filtered trades.";
      setExportError(message);
    } finally {
      setIsExportingFiltered(false);
    }
  }

  async function handleExportAll() {
    setIsExportingAll(true);
    setExportError(null);
    try {
      const trades = await getTrades();
      triggerCsvDownload(buildTradesCsv(trades));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to export all trades.";
      setExportError(message);
    } finally {
      setIsExportingAll(false);
    }
  }

  const isDefaultView =
    draftFilters.start === selectedDate &&
    draftFilters.end === selectedDate &&
    draftFilters.ticker === "" &&
    draftFilters.setupId === "" &&
    draftFilters.emotionId === "" &&
    draftFilters.ruleFollowed === "" &&
    draftFilters.outcome === "" &&
    draftFilters.source === "" &&
    draftFilters.classification === "all" &&
    draftFilters.pattern === "";

  return (
    <section className="single-view-grid">
      <CollapsibleSection id="trade-history" title="Trade History">
        <TradeFilters
          value={draftFilters}
          onChange={setDraftFilters}
          onApply={handleApplyFilters}
          onClear={handleClearFilters}
          setupRefreshKey={setupRefreshKey}
          emotionRefreshKey={emotionRefreshKey}
        />
        <div className="trade-history-toolbar">
          <p className="trade-history-count">Showing {shownTradesCount} trades</p>
          <div className="trade-history-export-actions">
            <button
              type="button"
              onClick={() => void handleExportFiltered()}
              disabled={isExportingFiltered || isExportingAll}
            >
              {isExportingFiltered ? "Exporting..." : "Export Filtered"}
            </button>
            <button
              type="button"
              onClick={() => void handleExportAll()}
              disabled={isExportingFiltered || isExportingAll}
            >
              {isExportingAll ? "Exporting..." : "Export All"}
            </button>
          </div>
        </div>
        {exportError ? <p className="trade-history-export-error">{exportError}</p> : null}
        <TradesList
          filters={filters}
          hideHeader
          refreshKey={refreshKey}
          setupRefreshKey={setupRefreshKey}
          emotionRefreshKey={emotionRefreshKey}
          onTradeDeleted={onTradeDeleted}
          onTradesLoaded={setShownTradesCount}
          enableBulkEdit
          onDuplicateTrade={onDuplicateTrade}
          emptyState={
            isDefaultView ? (
              <EmptyState
                title="No trades logged yet."
                description="Add a trade manually or import from CSV to get started."
                actions={[
                  ...(onAddTrade ? [{ label: "Add Trade", onClick: onAddTrade }] : []),
                  ...(onImportCsv
                    ? [{ label: "Import CSV", onClick: onImportCsv, variant: "secondary" as const }]
                    : []),
                ]}
              />
            ) : undefined
          }
        />
      </CollapsibleSection>
    </section>
  );
}
