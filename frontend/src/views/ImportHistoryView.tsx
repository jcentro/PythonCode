import { useEffect, useState } from "react";

import { getImportBatchDetail, getImportBatches } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ImportBatchDetail, ImportBatchFill, ImportBatchListItem } from "../types/import";
import { TradeListFilters } from "../types/trade";
import { formatDateTime, formatNumber, formatUsd } from "../utils/formatting";
import "./ImportHistoryView.css";

interface ImportHistoryViewProps {
  onViewImportedTrades?: (filters: TradeListFilters) => void;
  onOpenImport?: () => void;
}

function formatStatus(status: ImportBatchListItem["status"]): string {
  if (status === "previewed") {
    return "Previewed";
  }
  if (status === "committed") {
    return "Committed";
  }
  return "Failed";
}

function renderFillTable(rows: ImportBatchFill[]) {
  if (rows.length === 0) {
    return <p className="import-history-status">None</p>;
  }

  return (
    <div className="import-unmatched-table-wrap">
      <table className="import-unmatched-table">
        <thead>
          <tr>
            <th>Exec time</th>
            <th>Symbol</th>
            <th>Exp</th>
            <th>Strike</th>
            <th>Type</th>
            <th>Qty</th>
            <th>Side</th>
            <th>Price</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((fill, index) => (
            <tr key={`${fill.exec_datetime}-${fill.symbol}-${index}`}>
              <td>{formatDateTime(fill.exec_datetime)}</td>
              <td>{fill.symbol}</td>
              <td>{fill.exp}</td>
              <td>{fill.strike}</td>
              <td>{fill.option_type}</td>
              <td>{fill.qty}</td>
              <td>{fill.side}</td>
              <td>{formatNumber(fill.price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function csvEscape(value: string | number): string {
  const raw = String(value);
  const escaped = raw.replace(/"/g, '""');
  return `"${escaped}"`;
}

export function ImportHistoryView({ onViewImportedTrades, onOpenImport }: ImportHistoryViewProps) {
  const [batches, setBatches] = useState<ImportBatchListItem[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [selectedBatch, setSelectedBatch] = useState<ImportBatchDetail | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadBatches() {
      setIsLoadingList(true);
      setErrorMessage(null);
      try {
        const response = await getImportBatches("tos_csv");
        setBatches(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load import history.";
        setErrorMessage(message);
        setBatches([]);
      } finally {
        setIsLoadingList(false);
      }
    }

    void loadBatches();
  }, []);

  useEffect(() => {
    if (selectedBatchId === null) {
      return;
    }
    const batchId = selectedBatchId;

    async function loadBatchDetail() {
      setIsLoadingDetail(true);
      setErrorMessage(null);
      try {
        const response = await getImportBatchDetail(batchId);
        setSelectedBatch(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load batch detail.";
        setErrorMessage(message);
        setSelectedBatch(null);
      } finally {
        setIsLoadingDetail(false);
      }
    }

    void loadBatchDetail();
  }, [selectedBatchId]);

  function openBatchDetail(batchId: number) {
    setSelectedBatchId(batchId);
    setSelectedBatch(null);
  }

  function handleBackToList() {
    setSelectedBatchId(null);
    setSelectedBatch(null);
    setErrorMessage(null);
  }

  function handleViewImportedTrades() {
    if (!selectedBatch || !onViewImportedTrades) {
      return;
    }
    onViewImportedTrades({
      import_batch_id: selectedBatch.id,
    });
  }

  function handleExportUnmatchedCsv() {
    if (!selectedBatch) {
      return;
    }

    const unmatchedRows = [
      ...selectedBatch.unmatched_opens.map((fill) => ({ unmatched_type: "open" as const, fill })),
      ...selectedBatch.unmatched_closes.map((fill) => ({ unmatched_type: "close" as const, fill })),
    ];
    if (unmatchedRows.length === 0) {
      return;
    }

    const header = [
      "unmatched_type",
      "exec_datetime",
      "symbol",
      "exp",
      "strike",
      "option_type",
      "qty",
      "side",
      "price",
      "pos_effect",
    ];

    const lines = [header.join(",")];
    for (const row of unmatchedRows) {
      lines.push(
        [
          csvEscape(row.unmatched_type),
          csvEscape(row.fill.exec_datetime),
          csvEscape(row.fill.symbol),
          csvEscape(row.fill.exp),
          csvEscape(row.fill.strike),
          csvEscape(row.fill.option_type),
          csvEscape(row.fill.qty),
          csvEscape(row.fill.side),
          csvEscape(row.fill.price),
          csvEscape(row.fill.pos_effect),
        ].join(",")
      );
    }

    const csvContent = lines.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `import-batch-${selectedBatch.id}-unmatched-fills.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  if (selectedBatchId !== null) {
    const unmatchedCount =
      (selectedBatch?.unmatched_opens.length ?? 0) + (selectedBatch?.unmatched_closes.length ?? 0);

    return (
      <section className="single-view-grid">
        <section className="import-history-panel">
          <div className="import-history-header">
            <button type="button" className="import-history-back" onClick={handleBackToList}>
              Back to Import History
            </button>
            <h2>Batch Detail</h2>
          </div>

          {errorMessage ? <p className="import-history-status error">{errorMessage}</p> : null}
          {isLoadingDetail ? <p className="import-history-status">Loading batch detail...</p> : null}

          {!isLoadingDetail && selectedBatch ? (
            <div className="import-batch-detail">
              <section className="import-detail-section">
                <h3>Summary</h3>
                <dl className="import-detail-grid">
                  <div>
                    <dt>Filename</dt>
                    <dd>{selectedBatch.original_filename ?? "-"}</dd>
                  </div>
                  <div>
                    <dt>Date/Time</dt>
                    <dd>{formatDateTime(selectedBatch.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{formatStatus(selectedBatch.status)}</dd>
                  </div>
                </dl>
                {onViewImportedTrades ? (
                  <button
                    type="button"
                    className="import-history-button"
                    onClick={handleViewImportedTrades}
                  >
                    View imported trades
                  </button>
                ) : null}
              </section>

              <section className="import-detail-section">
                <h3>Preview Metrics</h3>
                <dl className="import-detail-grid">
                  <div>
                    <dt>Parsed rows</dt>
                    <dd>{selectedBatch.parsed_rows_count}</dd>
                  </div>
                  <div>
                    <dt>Fills parsed</dt>
                    <dd>{selectedBatch.fills_parsed_count}</dd>
                  </div>
                  <div>
                    <dt>Detected trades</dt>
                    <dd>{selectedBatch.detected_trades_count}</dd>
                  </div>
                  <div>
                    <dt>Excluded</dt>
                    <dd>{selectedBatch.excluded_count}</dd>
                  </div>
                </dl>
              </section>

              <section className="import-detail-section">
                <h3>Commit Metrics</h3>
                <dl className="import-detail-grid">
                  <div>
                    <dt>Imported</dt>
                    <dd>{selectedBatch.committed_count}</dd>
                  </div>
                  <div>
                    <dt>Duplicates skipped</dt>
                    <dd>{selectedBatch.skipped_duplicates_count}</dd>
                  </div>
                  <div>
                    <dt>Total committed PnL (USD)</dt>
                    <dd>{formatUsd(selectedBatch.pnl_total_committed_usd)}</dd>
                  </div>
                  <div>
                    <dt>Errors</dt>
                    <dd>{selectedBatch.errors.length}</dd>
                  </div>
                </dl>
                {selectedBatch.errors.length > 0 ? (
                  <ul className="import-detail-list">
                    {selectedBatch.errors.map((error, index) => (
                      <li key={`${error}-${index}`}>{error}</li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <details className="import-detail-warnings" open={selectedBatch.warnings.length > 0}>
                <summary>Warnings ({selectedBatch.warnings.length})</summary>
                {selectedBatch.warnings.length > 0 ? (
                  <ul className="import-detail-list">
                    {selectedBatch.warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="import-history-status">No warnings for this batch.</p>
                )}
              </details>

              <section className="import-detail-section">
                <h3>Unmatched Fills</h3>
                <div className="import-unmatched-actions">
                  <button
                    type="button"
                    className="import-history-button"
                    onClick={handleExportUnmatchedCsv}
                    disabled={!selectedBatch || unmatchedCount === 0}
                  >
                    Export Unmatched CSV
                  </button>
                </div>
                {selectedBatch.unmatched_opens.length === 0 &&
                selectedBatch.unmatched_closes.length === 0 ? (
                  <p className="import-history-status">
                    No unmatched fills detected in this batch.
                  </p>
                ) : (
                  <div className="import-unmatched-panels">
                    <details
                      className="import-unmatched-panel"
                      open={selectedBatch.unmatched_opens.length > 0}
                    >
                      <summary>Unmatched Opens ({selectedBatch.unmatched_opens.length})</summary>
                      {renderFillTable(selectedBatch.unmatched_opens)}
                    </details>
                    <details
                      className="import-unmatched-panel"
                      open={selectedBatch.unmatched_closes.length > 0}
                    >
                      <summary>Unmatched Closes ({selectedBatch.unmatched_closes.length})</summary>
                      {renderFillTable(selectedBatch.unmatched_closes)}
                    </details>
                  </div>
                )}
              </section>
            </div>
          ) : null}
        </section>
      </section>
    );
  }

  return (
    <section className="single-view-grid">
      <section className="import-history-panel">
        <div className="import-history-header">
          <h2>Import History</h2>
        </div>

        {errorMessage ? <p className="import-history-status error">{errorMessage}</p> : null}
        {isLoadingList ? <p className="import-history-status">Loading import history...</p> : null}

        {!isLoadingList && batches.length === 0 ? (
          <EmptyState
            title="No imports yet."
            description="Imported CSV batches will appear here."
            actions={onOpenImport ? [{ label: "Import CSV", onClick: onOpenImport }] : []}
            compact
          />
        ) : null}

        {!isLoadingList && batches.length > 0 ? (
          <div className="import-history-table-wrap">
            <table className="import-history-table">
              <thead>
                <tr>
                  <th>Date/Time</th>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Detected Trades</th>
                  <th>Imported</th>
                  <th>Duplicates Skipped</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <tr
                    key={batch.id}
                    className="import-history-row"
                    onClick={() => openBatchDetail(batch.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openBatchDetail(batch.id);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>{formatDateTime(batch.created_at)}</td>
                    <td>{batch.original_filename ?? "-"}</td>
                    <td>{formatStatus(batch.status)}</td>
                    <td>{batch.detected_trades_count}</td>
                    <td>{batch.committed_count}</td>
                    <td>{batch.skipped_duplicates_count}</td>
                    <td>{batch.warnings_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </section>
  );
}
