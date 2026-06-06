import { ChangeEvent, FormEvent, Fragment, useEffect, useMemo, useState } from "react";

import { commitToSImport, getEmotions, getSetups, previewToSImport } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { EmotionOptionResponse } from "../types/emotion";
import {
  ImportedTradeFillPreview,
  ImportedTradePreview,
  ToSImportCommitItem,
  ToSImportCommitResponse,
  ToSImportPreviewResponse,
} from "../types/import";
import { SetupOptionResponse } from "../types/setup";
import { formatDateLong, formatNumber, formatUsd } from "../utils/formatting";
import "./ImportView.css";

interface ImportViewProps {
  onImportCommitted?: () => void;
}

interface ImportRowState {
  selected: boolean;
  setupId: string;
  emotionId: string;
  ruleFollowed: boolean;
  notes: string;
}

function getDuplicateStatusLabel(
  status: ImportedTradePreview["duplicate_status"],
): "New" | "Duplicate" | "Possible Duplicate" {
  if (status === "duplicate") {
    return "Duplicate";
  }
  if (status === "possible_duplicate") {
    return "Possible Duplicate";
  }
  return "New";
}

function formatDuration(durationSeconds: number | null | undefined): string {
  if (!durationSeconds || durationSeconds <= 0) {
    return "-";
  }

  const hours = Math.floor(durationSeconds / 3600);
  const minutes = Math.floor((durationSeconds % 3600) / 60);
  const seconds = durationSeconds % 60;
  const parts: string[] = [];

  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (minutes > 0) {
    parts.push(`${minutes}m`);
  }
  if (seconds > 0 || parts.length === 0) {
    parts.push(`${seconds}s`);
  }

  return parts.join(" ");
}

function formatFillTime(fill: ImportedTradeFillPreview): string {
  const raw = fill.exec_datetime;
  if (!raw) {
    return "-";
  }
  const splitOnT = raw.split("T");
  if (splitOnT.length < 2) {
    return raw;
  }
  const timePart = splitOnT[1];
  return timePart.split(".")[0];
}

function getTradeSymbol(trade: ImportedTradePreview): string {
  return trade.symbol || trade.ticker;
}

function getTradeType(trade: ImportedTradePreview): string {
  return trade.option_type || trade.direction;
}

export function ImportView({ onImportCommitted }: ImportViewProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ToSImportPreviewResponse | null>(null);
  const [setupOptions, setSetupOptions] = useState<SetupOptionResponse[]>([]);
  const [emotionOptions, setEmotionOptions] = useState<EmotionOptionResponse[]>([]);
  const [rowStateByTempId, setRowStateByTempId] = useState<Record<string, ImportRowState>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [commitResult, setCommitResult] = useState<ToSImportCommitResponse | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadClassifications() {
      try {
        const [setupsResponse, emotionsResponse] = await Promise.all([
          getSetups(false),
          getEmotions(false),
        ]);
        setSetupOptions(setupsResponse);
        setEmotionOptions(emotionsResponse);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to load setup/emotion options.";
        setErrorMessage(message);
      }
    }

    void loadClassifications();
  }, []);

  const selectedCount = useMemo(() => {
    if (!preview) {
      return 0;
    }
    return preview.detected_trades.filter((trade) => rowStateByTempId[trade.temp_id]?.selected)
      .length;
  }, [preview, rowStateByTempId]);

  const allSelected = useMemo(() => {
    if (!preview || preview.detected_trades.length === 0) {
      return false;
    }
    return preview.detected_trades.every((trade) => rowStateByTempId[trade.temp_id]?.selected);
  }, [preview, rowStateByTempId]);

  const duplicateCount = useMemo(() => {
    if (!preview) {
      return 0;
    }
    return preview.detected_trades.filter((trade) => trade.duplicate_status !== "new").length;
  }, [preview]);

  function buildDefaultRowState(trades: ImportedTradePreview[]): Record<string, ImportRowState> {
    const nextState: Record<string, ImportRowState> = {};
    for (const trade of trades) {
      nextState[trade.temp_id] = {
        selected: trade.duplicate_status === "new",
        setupId: "",
        emotionId: "",
        ruleFollowed: true,
        notes: "",
      };
    }
    return nextState;
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
  }

  async function handlePreviewImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setCommitResult(null);

    if (!selectedFile) {
      setErrorMessage("Select a CSV file to preview.");
      return;
    }

    setIsLoadingPreview(true);
    try {
      const response = await previewToSImport(selectedFile);
      setPreview(response);
      setRowStateByTempId(buildDefaultRowState(response.detected_trades));
      setExpandedRows({});
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to preview import.";
      setErrorMessage(message);
      setPreview(null);
      setRowStateByTempId({});
      setExpandedRows({});
    } finally {
      setIsLoadingPreview(false);
    }
  }

  function updateRowState(tempId: string, patch: Partial<ImportRowState>) {
    setRowStateByTempId((previous) => {
      const current = previous[tempId];
      if (!current) {
        return previous;
      }
      return { ...previous, [tempId]: { ...current, ...patch } };
    });
  }

  function handleToggleSelectAll(checked: boolean) {
    setRowStateByTempId((previous) => {
      const nextState: Record<string, ImportRowState> = {};
      for (const [tempId, value] of Object.entries(previous)) {
        nextState[tempId] = { ...value, selected: checked };
      }
      return nextState;
    });
  }

  function toggleExpanded(tempId: string) {
    setExpandedRows((previous) => ({ ...previous, [tempId]: !previous[tempId] }));
  }

  async function handleCommitImport() {
    setErrorMessage(null);
    setCommitResult(null);

    if (!preview) {
      setErrorMessage("Preview trades first.");
      return;
    }

    const selectedTrades = preview.detected_trades.filter(
      (trade) => rowStateByTempId[trade.temp_id]?.selected,
    );
    if (selectedTrades.length === 0) {
      setErrorMessage("Select at least one trade to import.");
      return;
    }

    const items: ToSImportCommitItem[] = selectedTrades.map((trade) => {
      const rowState = rowStateByTempId[trade.temp_id];
      return {
        temp_id: trade.temp_id,
        setup_id: rowState.setupId ? Number(rowState.setupId) : undefined,
        emotion_id: rowState.emotionId ? Number(rowState.emotionId) : undefined,
        rule_followed: rowState.ruleFollowed,
        notes: rowState.notes.trim() ? rowState.notes.trim() : undefined,
      };
    });

    setIsCommitting(true);
    try {
      const response = await commitToSImport({ batch_id: preview.batch_id, items });
      setCommitResult(response);
      onImportCommitted?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to import selected trades.";
      setErrorMessage(message);
    } finally {
      setIsCommitting(false);
    }
  }

  return (
    <section className="single-view-grid">
      <section className="import-panel">
        <h2>ThinkorSwim Import</h2>
        <form className="import-upload-form" onSubmit={handlePreviewImport}>
          <label>
            CSV File
            <input type="file" accept=".csv,text/csv" onChange={handleFileChange} />
          </label>
          <button type="submit" disabled={isLoadingPreview}>
            {isLoadingPreview ? "Previewing..." : "Preview Import"}
          </button>
        </form>

        {!preview ? (
          <EmptyState
            title="Upload a ThinkorSwim CSV statement to preview trades before importing."
            description="Duplicates are detected automatically, and the import preview lets you confirm trades before saving."
            compact
          />
        ) : null}

        {errorMessage ? <p className="import-status error">{errorMessage}</p> : null}

        {commitResult ? (
          <div className="import-result">
            <p>
              Imported: <strong>{commitResult.imported}</strong> | Skipped duplicates:{" "}
              <strong>{commitResult.skipped_duplicates}</strong>
            </p>
            {commitResult.errors.length > 0 ? (
              <ul>
                {commitResult.errors.map((error, index) => (
                  <li key={`${error}-${index}`}>{error}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {preview?.warnings.length ? (
          <details className="import-warnings">
            <summary>Warnings ({preview.warnings.length})</summary>
            <ul>
              {preview.warnings.map((warning, index) => (
                <li key={`${warning}-${index}`}>{warning}</li>
              ))}
            </ul>
          </details>
        ) : null}

        {preview ? (
          <div className="import-preview">
            <div className="import-preview-header">
              <h3>Detected Trades ({preview.detected_trades.length})</h3>
              <label className="import-select-all">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) => handleToggleSelectAll(event.target.checked)}
                />
                Select All
              </label>
            </div>
            {duplicateCount > 0 ? (
              <div className="import-duplicate-summary" role="status">
                {duplicateCount} duplicate{duplicateCount === 1 ? "" : "s"} detected. They will be
                skipped by default.
              </div>
            ) : null}
            <div className="import-table-wrap">
              <table className="import-table">
                <thead>
                  <tr>
                    <th />
                    <th>Select</th>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Exp</th>
                    <th>Strike</th>
                    <th>Type</th>
                    <th>Entry Fills</th>
                    <th>Exit Fills</th>
                    <th>Qty In</th>
                    <th>Qty Out</th>
                    <th>Matched</th>
                    <th>Avg Entry</th>
                    <th>Avg Exit</th>
                    <th>Total PnL (USD)</th>
                    <th>Duration</th>
                    <th>Status</th>
                    <th>Setup</th>
                    <th>Emotion</th>
                    <th>Rule</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.detected_trades.map((trade) => {
                    const rowState = rowStateByTempId[trade.temp_id];
                    if (!rowState) {
                      return null;
                    }
                    const isExpanded = Boolean(expandedRows[trade.temp_id]);

                    return (
                      <Fragment key={trade.temp_id}>
                        <tr>
                          <td>
                            <button
                              type="button"
                              className="import-expand-button"
                              onClick={() => toggleExpanded(trade.temp_id)}
                              aria-label={isExpanded ? "Hide fills" : "Show fills"}
                            >
                              {isExpanded ? "▾" : "▸"}
                            </button>
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              checked={rowState.selected}
                              onChange={(event) =>
                                updateRowState(trade.temp_id, { selected: event.target.checked })
                              }
                            />
                          </td>
                          <td>{formatDateLong(trade.date)}</td>
                          <td>{getTradeSymbol(trade)}</td>
                          <td>{trade.exp}</td>
                          <td>{trade.strike}</td>
                          <td>{getTradeType(trade)}</td>
                          <td>{trade.entry_fills_count}</td>
                          <td>{trade.exit_fills_count}</td>
                          <td>{trade.total_entry_qty}</td>
                          <td>{trade.total_exit_qty}</td>
                          <td>{trade.matched_qty}</td>
                          <td>{formatNumber(trade.avg_entry_price)}</td>
                          <td>{formatNumber(trade.avg_exit_price)}</td>
                          <td>{formatUsd(trade.total_pnl_usd)}</td>
                          <td>{formatDuration(trade.duration_seconds)}</td>
                          <td>
                            <div className="import-status-cell">
                              <span
                                className={`import-status-badge import-status-${trade.duplicate_status}`}
                                title={trade.duplicate_reason ?? undefined}
                              >
                                {getDuplicateStatusLabel(trade.duplicate_status)}
                              </span>
                              {trade.is_partial ? (
                                <span className="import-partial-badge">Partial</span>
                              ) : null}
                              {trade.existing_trade_id ? (
                                <span className="import-duplicate-meta">
                                  Existing #{trade.existing_trade_id}
                                </span>
                              ) : null}
                            </div>
                          </td>
                          <td>
                            <select
                              value={rowState.setupId}
                              onChange={(event) =>
                                updateRowState(trade.temp_id, { setupId: event.target.value })
                              }
                              disabled={!rowState.selected}
                            >
                              <option value="">Unassigned</option>
                              {setupOptions.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {option.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <select
                              value={rowState.emotionId}
                              onChange={(event) =>
                                updateRowState(trade.temp_id, { emotionId: event.target.value })
                              }
                              disabled={!rowState.selected}
                            >
                              <option value="">Unassigned</option>
                              {emotionOptions.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {option.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              checked={rowState.ruleFollowed}
                              onChange={(event) =>
                                updateRowState(trade.temp_id, {
                                  ruleFollowed: event.target.checked,
                                })
                              }
                              disabled={!rowState.selected}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              value={rowState.notes}
                              onChange={(event) =>
                                updateRowState(trade.temp_id, { notes: event.target.value })
                              }
                              disabled={!rowState.selected}
                              placeholder="Optional"
                            />
                          </td>
                        </tr>
                        {isExpanded ? (
                          <tr className="import-fill-detail-row">
                            <td colSpan={21}>
                              {trade.fills.length > 0 ? (
                                <div className="import-fills-wrap">
                                  <table className="import-fills-table">
                                    <thead>
                                      <tr>
                                        <th>Time</th>
                                        <th>Side</th>
                                        <th>Qty</th>
                                        <th>Price</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {trade.fills.map((fill, fillIndex) => (
                                        <tr
                                          key={`${trade.temp_id}-${fill.exec_datetime}-${fillIndex}`}
                                        >
                                          <td>{formatFillTime(fill)}</td>
                                          <td>{fill.side}</td>
                                          <td>{fill.qty}</td>
                                          <td>{formatNumber(fill.price)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <span className="import-fills-empty">No fills available.</span>
                              )}
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="import-actions">
              <span>{selectedCount} selected</span>
              <button
                type="button"
                onClick={() => void handleCommitImport()}
                disabled={isCommitting}
              >
                {isCommitting ? "Importing..." : "Import Selected"}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </section>
  );
}
