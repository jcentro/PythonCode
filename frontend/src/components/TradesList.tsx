import {
  Fragment,
  KeyboardEvent as ReactKeyboardEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  deleteTrade,
  getEmotions,
  getSetups,
  getTrades,
  patchTrade,
  updateTradesBulk,
  updateTrade,
} from "../api/client";
import { EmotionOptionResponse } from "../types/emotion";
import { SetupOptionResponse } from "../types/setup";
import { TradeDirection, TradeListFilters, TradeResponse } from "../types/trade";
import { FillDraftRow, toFillDraftRow } from "../utils/fills";
import {
  formatDateLong,
  formatDateTime,
  formatNumber,
  formatSignedNumber,
  formatUsd,
} from "../utils/formatting";
import {
  setLastUsedEmotionId,
  setLastUsedRuleFollowed,
  setLastUsedSetupId,
} from "../utils/lastUsedClassification";
import { validateTradeDraft } from "../utils/tradeValidation";
import { FillsEditor } from "./FillsEditor";
import "./TradesList.css";

interface TradesListProps {
  selectedDate?: string;
  filters?: TradeListFilters;
  onDateChange?: (date: string) => void;
  hideHeader?: boolean;
  emptyMessage?: string;
  emptyState?: ReactNode;
  refreshKey?: number;
  setupRefreshKey?: number;
  emotionRefreshKey?: number;
  onTradeDeleted?: () => void;
  onTradesLoaded?: (count: number) => void;
  enableBulkEdit?: boolean;
  onDuplicateTrade?: (trade: TradeResponse) => void;
}

interface EditTradeFormState {
  date: string;
  ticker: string;
  direction: TradeDirection;
  entryPrice: string;
  exitPrice: string;
  quantity: string;
  setupId: string;
  emotionId: string;
  ruleFollowed: boolean;
  notes: string;
}

type InlineEditableField = "setup" | "emotion" | "rule_followed";

interface InlineEditingCell {
  tradeId: number;
  field: InlineEditableField;
}

const directionOptions: TradeDirection[] = ["CALL", "PUT"];

export function TradesList({
  selectedDate,
  filters,
  onDateChange,
  hideHeader = false,
  emptyMessage = "No trades match the current filters.",
  emptyState,
  refreshKey = 0,
  setupRefreshKey = 0,
  emotionRefreshKey = 0,
  onTradeDeleted,
  onTradesLoaded,
  enableBulkEdit = false,
  onDuplicateTrade,
}: TradesListProps) {
  const [trades, setTrades] = useState<TradeResponse[]>([]);
  const [setupOptions, setSetupOptions] = useState<SetupOptionResponse[]>([]);
  const [emotionOptions, setEmotionOptions] = useState<EmotionOptionResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeletingId, setIsDeletingId] = useState<number | null>(null);
  const [editingTradeId, setEditingTradeId] = useState<number | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editForm, setEditForm] = useState<EditTradeFormState | null>(null);
  const [isEditFillsMode, setIsEditFillsMode] = useState(false);
  const [editFillRows, setEditFillRows] = useState<FillDraftRow[]>([]);
  const [expandedTradeIds, setExpandedTradeIds] = useState<Record<number, boolean>>({});
  const [selectedFillsTrade, setSelectedFillsTrade] = useState<TradeResponse | null>(null);
  const [inlineEditingCell, setInlineEditingCell] = useState<InlineEditingCell | null>(null);
  const [inlineSavingCell, setInlineSavingCell] = useState<string | null>(null);
  const [inlineErrorByTrade, setInlineErrorByTrade] = useState<Record<number, string>>({});
  const [selectedTradeIds, setSelectedTradeIds] = useState<number[]>([]);
  const [bulkSetupId, setBulkSetupId] = useState("");
  const [bulkEmotionId, setBulkEmotionId] = useState("");
  const [bulkRuleFollowed, setBulkRuleFollowed] = useState<"" | "true" | "false" | "unknown">("");
  const [bulkSuccessMessage, setBulkSuccessMessage] = useState<string | null>(null);
  const [bulkErrorMessage, setBulkErrorMessage] = useState<string | null>(null);
  const [bulkErrors, setBulkErrors] = useState<string[]>([]);
  const [isApplyingBulk, setIsApplyingBulk] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [editSubmitAttempted, setEditSubmitAttempted] = useState(false);

  const loadTrades = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const baseFilters = filters ?? (selectedDate ? { date: selectedDate } : undefined);
      const response = await getTrades({
        ...(baseFilters ?? {}),
        include_fills: true,
      });
      setTrades(response);
      setExpandedTradeIds({});
      setInlineEditingCell(null);
      onTradesLoaded?.(response.length);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to fetch trades.";
      setErrorMessage(message);
      setTrades([]);
      onTradesLoaded?.(0);
    } finally {
      setIsLoading(false);
    }
  }, [filters, onTradesLoaded, selectedDate]);

  useEffect(() => {
    void loadTrades();
  }, [loadTrades, refreshKey]);

  useEffect(() => {
    async function loadSetups() {
      try {
        const response = await getSetups(true);
        setSetupOptions(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to fetch setups.";
        setErrorMessage(message);
        setSetupOptions([]);
      }
    }

    void loadSetups();
  }, [setupRefreshKey]);

  useEffect(() => {
    setSelectedTradeIds((previous) =>
      previous.filter((tradeId) => trades.some((trade) => trade.id === tradeId)),
    );
  }, [trades]);

  useEffect(() => {
    async function loadEmotions() {
      try {
        const response = await getEmotions(true);
        setEmotionOptions(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to fetch emotions.";
        setErrorMessage(message);
        setEmotionOptions([]);
      }
    }

    void loadEmotions();
  }, [emotionRefreshKey]);

  useEffect(() => {
    if (!selectedFillsTrade) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedFillsTrade(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedFillsTrade]);

  function getInlineCellKey(tradeId: number, field: InlineEditableField): string {
    return `${tradeId}:${field}`;
  }

  function isInlineEditing(tradeId: number, field: InlineEditableField): boolean {
    return inlineEditingCell?.tradeId === tradeId && inlineEditingCell.field === field;
  }

  function isInlineSaving(tradeId: number, field: InlineEditableField): boolean {
    return inlineSavingCell === getInlineCellKey(tradeId, field);
  }

  function openInlineEditor(tradeId: number, field: InlineEditableField) {
    setInlineEditingCell({ tradeId, field });
    setInlineErrorByTrade((previous) => {
      if (!previous[tradeId]) {
        return previous;
      }
      const next = { ...previous };
      delete next[tradeId];
      return next;
    });
  }

  function closeInlineEditor() {
    setInlineEditingCell(null);
  }

  async function applyInlineUpdate(
    trade: TradeResponse,
    field: InlineEditableField,
    value: string,
  ) {
    const cellKey = getInlineCellKey(trade.id, field);
    const payload: { setup_id?: number; emotion_id?: number; rule_followed?: boolean | null } = {};

    if (field === "setup") {
      if (!value) {
        return;
      }
      payload.setup_id = Number(value);
    } else if (field === "emotion") {
      if (!value) {
        return;
      }
      payload.emotion_id = Number(value);
    } else {
      payload.rule_followed = value === "true" ? true : value === "false" ? false : null;
    }

    setInlineSavingCell(cellKey);
    setInlineErrorByTrade((previous) => {
      if (!previous[trade.id]) {
        return previous;
      }
      const next = { ...previous };
      delete next[trade.id];
      return next;
    });

    try {
      const updatedTrade = await patchTrade(trade.id, payload);
      setTrades((previous) =>
        previous.map((existingTrade) =>
          existingTrade.id === updatedTrade.id ? updatedTrade : existingTrade,
        ),
      );
      closeInlineEditor();
      onTradeDeleted?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save change.";
      setInlineErrorByTrade((previous) => ({ ...previous, [trade.id]: message }));
    } finally {
      setInlineSavingCell(null);
    }
  }

  function handleInlineEditorKeyDown(event: ReactKeyboardEvent<HTMLSelectElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeInlineEditor();
    }
  }

  function renderRuleDisplayValue(ruleFollowed: boolean | null): string {
    if (ruleFollowed === true) {
      return "Yes";
    }
    if (ruleFollowed === false) {
      return "No";
    }
    return "—";
  }

  function handleToggleTradeSelection(tradeId: number, checked: boolean) {
    setSelectedTradeIds((previous) => {
      if (checked) {
        if (previous.includes(tradeId)) {
          return previous;
        }
        return [...previous, tradeId];
      }
      return previous.filter((id) => id !== tradeId);
    });
  }

  function handleToggleSelectAll(checked: boolean) {
    if (checked) {
      setSelectedTradeIds(trades.map((trade) => trade.id));
      return;
    }
    setSelectedTradeIds([]);
  }

  function clearSelection() {
    setSelectedTradeIds([]);
  }

  async function handleApplyBulkUpdate() {
    if (selectedTradeIds.length === 0) {
      return;
    }

    const payload: { setup_id?: number; emotion_id?: number; rule_followed?: boolean | null } = {};
    if (bulkSetupId) {
      payload.setup_id = Number(bulkSetupId);
    }
    if (bulkEmotionId) {
      payload.emotion_id = Number(bulkEmotionId);
    }
    if (bulkRuleFollowed) {
      payload.rule_followed =
        bulkRuleFollowed === "true" ? true : bulkRuleFollowed === "false" ? false : null;
    }

    if (!Object.keys(payload).length) {
      return;
    }

    setBulkSuccessMessage(null);
    setBulkErrorMessage(null);
    setBulkErrors([]);
    setIsApplyingBulk(true);
    try {
      const response = await updateTradesBulk({
        trade_ids: selectedTradeIds,
        ...payload,
      });

      await loadTrades();
      onTradeDeleted?.();

      if (response.errors.length > 0) {
        setBulkErrorMessage(
          `Updated ${response.updated_count} trades with ${response.errors.length} issue(s).`,
        );
        setBulkErrors(response.errors);
        return;
      }

      setBulkSuccessMessage(`Updated ${response.updated_count} trades`);
      setSelectedTradeIds([]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to apply bulk update.";
      setBulkErrorMessage(message);
    } finally {
      setIsApplyingBulk(false);
    }
  }

  async function handleDelete(tradeId: number) {
    setIsDeletingId(tradeId);
    setErrorMessage(null);
    try {
      await deleteTrade(tradeId);
      setTrades((previous) => {
        const next = previous.filter((trade) => trade.id !== tradeId);
        onTradesLoaded?.(next.length);
        return next;
      });
      onTradeDeleted?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete trade.";
      setErrorMessage(message);
    } finally {
      setIsDeletingId(null);
    }
  }

  function handleEditStart(trade: TradeResponse) {
    setErrorMessage(null);
    setEditSubmitAttempted(false);
    setEditingTradeId(trade.id);
    setEditForm({
      date: trade.date,
      ticker: trade.ticker,
      direction: trade.direction,
      entryPrice: String(trade.entry_price),
      exitPrice: String(trade.exit_price),
      quantity: String(trade.quantity),
      setupId: String(trade.setup_id),
      emotionId: String(trade.emotion_id),
      ruleFollowed: trade.rule_followed ?? false,
      notes: trade.notes ?? "",
    });

    const fillRows = (trade.fills ?? []).map(toFillDraftRow);
    setEditFillRows(fillRows);
    setIsEditFillsMode(fillRows.length > 0);
  }

  function toggleTradeExpanded(tradeId: number) {
    setExpandedTradeIds((previous) => ({ ...previous, [tradeId]: !previous[tradeId] }));
  }

  function getSortedFills(trade: TradeResponse) {
    return [...(trade.fills ?? [])].sort((left, right) => {
      const leftTime = left.filled_at ? Date.parse(left.filled_at) : Number.MAX_SAFE_INTEGER;
      const rightTime = right.filled_at ? Date.parse(right.filled_at) : Number.MAX_SAFE_INTEGER;
      return leftTime - rightTime || left.id - right.id;
    });
  }

  function formatFillTime(value: string | null | undefined): string {
    if (!value) {
      return "-";
    }
    return formatDateTime(value);
  }

  function openFillsModal(trade: TradeResponse) {
    setSelectedFillsTrade(trade);
  }

  function closeFillsModal() {
    setSelectedFillsTrade(null);
  }

  function handleEditCancel() {
    setEditingTradeId(null);
    setEditForm(null);
    setEditFillRows([]);
    setIsEditFillsMode(false);
    setEditSubmitAttempted(false);
    setErrorMessage(null);
  }

  function convertToFills() {
    if (editForm === null) {
      return;
    }

    const quantityValue = Number(editForm.quantity);
    const safeQuantity = Number.isInteger(quantityValue) && quantityValue > 0 ? quantityValue : 1;
    setEditFillRows([
      {
        side: "BUY",
        quantity: String(safeQuantity),
        price: editForm.entryPrice || "",
        filledAt: "",
      },
      {
        side: "SELL",
        quantity: String(safeQuantity),
        price: editForm.exitPrice || "",
        filledAt: "",
      },
    ]);
    setIsEditFillsMode(true);
  }

  const editValidationResult = useMemo(() => {
    if (editForm === null) {
      return null;
    }

    return validateTradeDraft({
      date: editForm.date,
      ticker: editForm.ticker,
      direction: editForm.direction,
      entryPrice: editForm.entryPrice,
      exitPrice: editForm.exitPrice,
      quantity: editForm.quantity,
      setupId: editForm.setupId,
      emotionId: editForm.emotionId,
      ruleFollowed: editForm.ruleFollowed,
      notes: editForm.notes,
      useFills: isEditFillsMode,
      fillRows: editFillRows,
    });
  }, [editFillRows, editForm, isEditFillsMode]);

  function getComputedEditPnl(form: EditTradeFormState): string {
    const entryPrice = Number(form.entryPrice);
    const exitPrice = Number(form.exitPrice);

    if (!Number.isFinite(entryPrice) || !Number.isFinite(exitPrice)) {
      return "-";
    }

    return (exitPrice - entryPrice).toFixed(2);
  }

  function getComputedEditTotalPnlUsd(form: EditTradeFormState): string {
    const quantity = Number(form.quantity);
    const basePnl = Number(form.exitPrice) - Number(form.entryPrice);

    if (!Number.isFinite(basePnl) || !Number.isFinite(quantity)) {
      return "-";
    }

    return (basePnl * quantity * 100).toFixed(2);
  }

  async function handleEditSave() {
    if (editingTradeId === null || editForm === null) {
      return;
    }
    const originalTrade = trades.find((trade) => trade.id === editingTradeId) ?? null;
    setEditSubmitAttempted(true);

    if (editValidationResult === null) {
      return;
    }
    if (editValidationResult.errors.length > 0 || editValidationResult.payload === null) {
      return;
    }

    setErrorMessage(null);
    setIsSavingEdit(true);
    try {
      await updateTrade(editingTradeId, editValidationResult.payload);

      if (originalTrade) {
        const nextSetupId = Number(editForm.setupId);
        if (
          Number.isInteger(nextSetupId) &&
          nextSetupId > 0 &&
          originalTrade.setup_id !== nextSetupId
        ) {
          setLastUsedSetupId(String(nextSetupId));
        }

        const nextEmotionId = Number(editForm.emotionId);
        if (
          Number.isInteger(nextEmotionId) &&
          nextEmotionId > 0 &&
          originalTrade.emotion_id !== nextEmotionId
        ) {
          setLastUsedEmotionId(String(nextEmotionId));
        }

        const previousRule =
          typeof originalTrade.rule_followed === "boolean"
            ? originalTrade.rule_followed
              ? "true"
              : "false"
            : "unknown";
        const nextRule = editForm.ruleFollowed ? "true" : "false";
        if (previousRule !== nextRule) {
          setLastUsedRuleFollowed(nextRule);
        }
      }

      await loadTrades();
      setEditingTradeId(null);
      setEditForm(null);
      setEditFillRows([]);
      setIsEditFillsMode(false);
      setEditSubmitAttempted(false);
      onTradeDeleted?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update trade.";
      setErrorMessage(message);
    } finally {
      setIsSavingEdit(false);
    }
  }

  return (
    <section className="trades-list-panel">
      {!hideHeader ? (
        <div className="trades-list-header">
          <h2>Trades</h2>
          {onDateChange ? (
            <label>
              Date
              <input
                type="date"
                value={selectedDate ?? ""}
                onChange={(event) => onDateChange(event.target.value)}
              />
            </label>
          ) : null}
        </div>
      ) : null}

      {errorMessage ? <p className="list-status error">{errorMessage}</p> : null}
      {bulkSuccessMessage ? <p className="list-status success">{bulkSuccessMessage}</p> : null}
      {bulkErrorMessage ? <p className="list-status error">{bulkErrorMessage}</p> : null}
      {bulkErrors.length > 0 ? (
        <details className="bulk-errors">
          <summary>Some updates were not applied ({bulkErrors.length})</summary>
          <ul>
            {bulkErrors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {isLoading ? <p className="list-status">Loading trades...</p> : null}

      {!isLoading && trades.length === 0
        ? emptyState ?? <p className="list-status">{emptyMessage}</p>
        : null}

      {!isLoading && trades.length > 0 ? (
        <div className="table-wrap">
          {enableBulkEdit && selectedTradeIds.length > 0 ? (
            <div className="bulk-actions-bar">
              <span className="bulk-actions-count">Selected: {selectedTradeIds.length}</span>
              <select
                value={bulkSetupId}
                onChange={(event) => setBulkSetupId(event.target.value)}
                disabled={isApplyingBulk}
              >
                <option value="">Setup (no change)</option>
                {setupOptions
                  .filter((option) => option.is_active)
                  .map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
              </select>
              <select
                value={bulkEmotionId}
                onChange={(event) => setBulkEmotionId(event.target.value)}
                disabled={isApplyingBulk}
              >
                <option value="">Emotion (no change)</option>
                {emotionOptions
                  .filter((option) => option.is_active)
                  .map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
              </select>
              <select
                value={bulkRuleFollowed}
                onChange={(event) =>
                  setBulkRuleFollowed(event.target.value as "" | "true" | "false" | "unknown")
                }
                disabled={isApplyingBulk}
              >
                <option value="">Rule Followed (no change)</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
                <option value="unknown">Unknown</option>
              </select>
              <button
                type="button"
                className="bulk-apply-button"
                onClick={() => void handleApplyBulkUpdate()}
                disabled={
                  isApplyingBulk ||
                  (!bulkSetupId && !bulkEmotionId && !bulkRuleFollowed) ||
                  selectedTradeIds.length === 0
                }
              >
                {isApplyingBulk ? "Applying..." : "Apply to selected"}
              </button>
              <button
                type="button"
                className="bulk-clear-button"
                onClick={clearSelection}
                disabled={isApplyingBulk}
              >
                Clear selection
              </button>
            </div>
          ) : null}
          <table>
            <thead>
              <tr>
                {enableBulkEdit ? (
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all on page"
                      checked={trades.length > 0 && selectedTradeIds.length === trades.length}
                      onChange={(event) => handleToggleSelectAll(event.target.checked)}
                    />
                  </th>
                ) : null}
                <th />
                <th>Time</th>
                <th>Ticker</th>
                <th>Direction</th>
                <th>Total PnL (USD)</th>
                <th>Rule Followed</th>
                <th>Emotion</th>
                <th>Setup</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const hasFills = (trade.fills?.length ?? 0) > 0;
                const isExpanded = Boolean(expandedTradeIds[trade.id]) && hasFills;
                const sortedFills = hasFills ? getSortedFills(trade) : [];
                const setupValue = typeof trade.setup_id === "number" ? String(trade.setup_id) : "";
                const emotionValue =
                  typeof trade.emotion_id === "number" ? String(trade.emotion_id) : "";
                const setupOptionExists = setupOptions.some(
                  (option) => String(option.id) === setupValue,
                );
                const emotionOptionExists = emotionOptions.some(
                  (option) => String(option.id) === emotionValue,
                );
                const ruleValue =
                  trade.rule_followed === true
                    ? "true"
                    : trade.rule_followed === false
                      ? "false"
                      : "unknown";
                const ruleCellEditing = isInlineEditing(trade.id, "rule_followed");
                const setupCellEditing = isInlineEditing(trade.id, "setup");
                const emotionCellEditing = isInlineEditing(trade.id, "emotion");

                return (
                  <Fragment key={trade.id}>
                    <tr>
                      {enableBulkEdit ? (
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Select trade ${trade.id}`}
                            checked={selectedTradeIds.includes(trade.id)}
                            onChange={(event) =>
                              handleToggleTradeSelection(trade.id, event.target.checked)
                            }
                          />
                        </td>
                      ) : null}
                      <td>
                        {hasFills ? (
                          <button
                            type="button"
                            className="expand-button"
                            onClick={() => toggleTradeExpanded(trade.id)}
                            aria-label={isExpanded ? "Hide fills" : "Show fills"}
                          >
                            {isExpanded ? "▾" : "▸"}
                          </button>
                        ) : null}
                      </td>
                      <td>{trade.entry_time ?? "-"}</td>
                      <td>{trade.ticker}</td>
                      <td>{trade.direction}</td>
                      <td>
                        <div className="pnl-primary">{formatUsd(trade.total_pnl_usd)}</div>
                        <div className="pnl-secondary">
                          <span>Premium: {formatSignedNumber(trade.pnl)}</span>
                          {hasFills ? <span className="scaled-badge">Scaled</span> : null}
                        </div>
                      </td>
                      <td>
                        {ruleCellEditing ? (
                          <select
                            autoFocus
                            value={ruleValue}
                            onChange={(event) =>
                              void applyInlineUpdate(trade, "rule_followed", event.target.value)
                            }
                            onBlur={closeInlineEditor}
                            onKeyDown={handleInlineEditorKeyDown}
                            disabled={isInlineSaving(trade.id, "rule_followed")}
                          >
                            <option value="true">Followed</option>
                            <option value="false">Broken</option>
                            <option value="unknown">Unknown</option>
                          </select>
                        ) : (
                          <button
                            type="button"
                            className="inline-edit-trigger"
                            onClick={() => openInlineEditor(trade.id, "rule_followed")}
                            title="Edit rule followed"
                          >
                            {renderRuleDisplayValue(trade.rule_followed)}
                          </button>
                        )}
                        {isInlineSaving(trade.id, "rule_followed") ? (
                          <span className="inline-saving">Saving...</span>
                        ) : null}
                      </td>
                      <td>
                        {emotionCellEditing ? (
                          <select
                            autoFocus
                            value={emotionValue}
                            onChange={(event) =>
                              void applyInlineUpdate(trade, "emotion", event.target.value)
                            }
                            onBlur={closeInlineEditor}
                            onKeyDown={handleInlineEditorKeyDown}
                            disabled={isInlineSaving(trade.id, "emotion")}
                          >
                            <option value="" disabled>
                              Select emotion
                            </option>
                            {emotionValue && !emotionOptionExists ? (
                              <option value={emotionValue}>{trade.emotion_name || "—"}</option>
                            ) : null}
                            {emotionOptions.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                                {!option.is_active ? " (inactive)" : ""}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <button
                            type="button"
                            className="inline-edit-trigger"
                            onClick={() => openInlineEditor(trade.id, "emotion")}
                            title="Edit emotion"
                          >
                            {trade.emotion_name || "—"}
                          </button>
                        )}
                        {isInlineSaving(trade.id, "emotion") ? (
                          <span className="inline-saving">Saving...</span>
                        ) : null}
                      </td>
                      <td>
                        {setupCellEditing ? (
                          <select
                            autoFocus
                            value={setupValue}
                            onChange={(event) =>
                              void applyInlineUpdate(trade, "setup", event.target.value)
                            }
                            onBlur={closeInlineEditor}
                            onKeyDown={handleInlineEditorKeyDown}
                            disabled={isInlineSaving(trade.id, "setup")}
                          >
                            <option value="" disabled>
                              Select setup
                            </option>
                            {setupValue && !setupOptionExists ? (
                              <option value={setupValue}>{trade.setup_name || "—"}</option>
                            ) : null}
                            {setupOptions.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                                {!option.is_active ? " (inactive)" : ""}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <button
                            type="button"
                            className="inline-edit-trigger"
                            onClick={() => openInlineEditor(trade.id, "setup")}
                            title="Edit setup"
                          >
                            {trade.setup_name || "—"}
                          </button>
                        )}
                        {isInlineSaving(trade.id, "setup") ? (
                          <span className="inline-saving">Saving...</span>
                        ) : null}
                      </td>
                      <td>
                        {onDuplicateTrade ? (
                          <button
                            type="button"
                            className="duplicate-button"
                            disabled={isDeletingId === trade.id || isSavingEdit}
                            onClick={() => onDuplicateTrade(trade)}
                          >
                            Duplicate
                          </button>
                        ) : null}
                        {hasFills ? (
                          <button
                            type="button"
                            className="view-fills-button"
                            disabled={isDeletingId === trade.id || isSavingEdit}
                            onClick={() => openFillsModal(trade)}
                          >
                            View Fills
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="edit-button"
                          disabled={isDeletingId === trade.id || isSavingEdit}
                          onClick={() => handleEditStart(trade)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="delete-button"
                          disabled={isDeletingId === trade.id || isSavingEdit}
                          onClick={() => void handleDelete(trade.id)}
                        >
                          {isDeletingId === trade.id ? "Deleting..." : "Delete"}
                        </button>
                        {inlineErrorByTrade[trade.id] ? (
                          <p className="inline-edit-error">{inlineErrorByTrade[trade.id]}</p>
                        ) : null}
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr className="fills-detail-row">
                        <td colSpan={enableBulkEdit ? 10 : 9}>
                          <div className="fills-detail-wrap">
                            <table className="fills-detail-table">
                              <thead>
                                <tr>
                                  <th>Time</th>
                                  <th>Side</th>
                                  <th>Qty</th>
                                  <th>Price</th>
                                </tr>
                              </thead>
                              <tbody>
                                {sortedFills.map((fill) => (
                                  <tr key={fill.id}>
                                    <td>{formatFillTime(fill.filled_at)}</td>
                                    <td>{fill.side}</td>
                                    <td>{fill.quantity}</td>
                                    <td>{formatNumber(fill.price)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {editingTradeId !== null && editForm !== null ? (
        <section className="edit-panel">
          <h3>Edit Trade #{editingTradeId}</h3>
          {editSubmitAttempted && (editValidationResult?.errors.length ?? 0) > 0 ? (
            <ul className="edit-validation-errors" role="alert">
              {editValidationResult?.errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : null}
          <div className="edit-grid">
            <label>
              Date
              <input
                type="date"
                value={editForm.date}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, date: event.target.value } : previous,
                  )
                }
              />
            </label>
            <label>
              Ticker
              <input
                type="text"
                value={editForm.ticker}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, ticker: event.target.value } : previous,
                  )
                }
              />
            </label>
            <label>
              Direction
              <select
                value={editForm.direction}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous
                      ? { ...previous, direction: event.target.value as TradeDirection }
                      : previous,
                  )
                }
              >
                {directionOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            {!isEditFillsMode ? (
              <>
                <label>
                  Entry Price
                  <input
                    type="number"
                    step="0.01"
                    value={editForm.entryPrice}
                    onChange={(event) =>
                      setEditForm((previous) =>
                        previous ? { ...previous, entryPrice: event.target.value } : previous,
                      )
                    }
                  />
                </label>
                <label>
                  Exit Price
                  <input
                    type="number"
                    step="0.01"
                    value={editForm.exitPrice}
                    onChange={(event) =>
                      setEditForm((previous) =>
                        previous ? { ...previous, exitPrice: event.target.value } : previous,
                      )
                    }
                  />
                </label>
                <label>
                  Quantity
                  <input
                    type="number"
                    step="1"
                    min="1"
                    value={editForm.quantity}
                    onChange={(event) =>
                      setEditForm((previous) =>
                        previous ? { ...previous, quantity: event.target.value } : previous,
                      )
                    }
                  />
                </label>
                <label>
                  PnL Premium (computed)
                  <input type="text" value={getComputedEditPnl(editForm)} readOnly />
                </label>
                <label>
                  Total PnL USD (computed)
                  <input type="text" value={getComputedEditTotalPnlUsd(editForm)} readOnly />
                </label>
              </>
            ) : null}

            <label>
              Setup
              <select
                value={editForm.setupId}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, setupId: event.target.value } : previous,
                  )
                }
              >
                {setupOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                    {!option.is_active ? " (inactive)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Emotion
              <select
                value={editForm.emotionId}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, emotionId: event.target.value } : previous,
                  )
                }
              >
                {emotionOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                    {!option.is_active ? " (inactive)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="edit-checkbox">
              <input
                type="checkbox"
                checked={editForm.ruleFollowed}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, ruleFollowed: event.target.checked } : previous,
                  )
                }
              />
              Rule Followed
            </label>
            <label className="edit-notes">
              Notes
              <textarea
                rows={3}
                value={editForm.notes}
                onChange={(event) =>
                  setEditForm((previous) =>
                    previous ? { ...previous, notes: event.target.value } : previous,
                  )
                }
              />
            </label>
          </div>

          {isEditFillsMode ? (
            <div className="edit-fills-wrap">
              <h4>Fills (scaling)</h4>
              <FillsEditor rows={editFillRows} onChange={setEditFillRows} disabled={isSavingEdit} />
            </div>
          ) : (
            <div className="edit-mode-actions">
              <button
                type="button"
                className="convert-fills-button"
                onClick={convertToFills}
                disabled={isSavingEdit}
              >
                Convert to fills
              </button>
            </div>
          )}

          <div className="edit-actions">
            <button
              type="button"
              className="save-button"
              onClick={() => void handleEditSave()}
              disabled={isSavingEdit}
            >
              {isSavingEdit ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              className="cancel-button"
              onClick={handleEditCancel}
              disabled={isSavingEdit}
            >
              Cancel
            </button>
          </div>
        </section>
      ) : null}

      {selectedFillsTrade ? (
        <div
          className="trade-fills-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeFillsModal();
            }
          }}
        >
          <section
            className="trade-fills-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trade-fills-modal-title"
          >
            <div className="trade-fills-modal-header">
              <div>
                <h3 id="trade-fills-modal-title">Fills for {selectedFillsTrade.ticker}</h3>
                <p className="trade-fills-modal-subtitle">
                  {formatDateLong(selectedFillsTrade.date)} · {selectedFillsTrade.direction}
                </p>
              </div>
              <button
                type="button"
                className="trade-fills-modal-close"
                onClick={closeFillsModal}
                aria-label="Close fills modal"
              >
                Close
              </button>
            </div>

            <div className="trade-fills-modal-summary">
              <span>Total PnL: {formatUsd(selectedFillsTrade.total_pnl_usd)}</span>
              <span>
                Avg Entry:{" "}
                {formatNumber(
                  selectedFillsTrade.avg_entry_price ?? selectedFillsTrade.entry_price,
                )}
              </span>
              <span>
                Avg Exit:{" "}
                {formatNumber(
                  selectedFillsTrade.avg_exit_price ?? selectedFillsTrade.exit_price,
                )}
              </span>
              <span>
                Total Quantity: {selectedFillsTrade.total_entry_qty ?? selectedFillsTrade.quantity}
              </span>
            </div>

            {(selectedFillsTrade.fills?.length ?? 0) === 0 ? (
              <p className="list-status">No fills found for this trade.</p>
            ) : (
              <div className="trade-fills-modal-table-wrap">
                <table className="fills-detail-table">
                  <thead>
                    <tr>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Quantity</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {getSortedFills(selectedFillsTrade).map((fill) => (
                      <tr key={fill.id}>
                        <td>{fill.side}</td>
                        <td>{formatNumber(fill.price)}</td>
                        <td>{fill.quantity}</td>
                        <td>{formatFillTime(fill.filled_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
