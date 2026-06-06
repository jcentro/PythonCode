import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  createEmotion,
  createSetup,
  createTrade,
  getEmotions,
  getSetups,
  getTickers,
  rememberTicker,
} from "../api/client";
import { EmotionOptionResponse } from "../types/emotion";
import { SetupOptionResponse } from "../types/setup";
import { TradeDirection, TradeResponse } from "../types/trade";
import { getTodayDate } from "../utils/date";
import { FillDraftRow, createEmptyFillRow } from "../utils/fills";
import {
  clearLastUsedEmotionId,
  clearLastUsedSetupId,
  getLastUsedEmotionId,
  getLastUsedRuleFollowed,
  getLastUsedSetupId,
  setLastUsedEmotionId,
  setLastUsedRuleFollowed,
  setLastUsedSetupId,
} from "../utils/lastUsedClassification";
import { validateTradeDraft } from "../utils/tradeValidation";
import { FillsEditor } from "./FillsEditor";
import "./TradeForm.css";

interface TradeFormState {
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

function createInitialState(): TradeFormState {
  const lastUsedRuleFollowed = getLastUsedRuleFollowed();
  return {
    date: getTodayDate(),
    ticker: "",
    direction: "CALL",
    entryPrice: "",
    exitPrice: "",
    quantity: "1",
    setupId: "",
    emotionId: "",
    ruleFollowed: lastUsedRuleFollowed === "false" ? false : true,
    notes: "",
  };
}

const directionOptions: TradeDirection[] = ["CALL", "PUT"];

function sortSetupOptions(options: SetupOptionResponse[]): SetupOptionResponse[] {
  return [...options].sort((left, right) => {
    const leftOrder = left.sort_order ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = right.sort_order ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.name.localeCompare(right.name);
  });
}

function sortEmotionOptions(options: EmotionOptionResponse[]): EmotionOptionResponse[] {
  return [...options].sort((left, right) => {
    const leftOrder = left.sort_order ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = right.sort_order ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.name.localeCompare(right.name);
  });
}

interface TradeFormProps {
  onTradeCreated?: (trade: TradeResponse) => void;
  hideTitle?: boolean;
  setupRefreshKey?: number;
  emotionRefreshKey?: number;
  duplicateTrade?: TradeResponse | null;
  onClearDuplicateTrade?: () => void;
  focusTickerSignal?: number;
}

export function TradeForm({
  onTradeCreated,
  hideTitle = false,
  setupRefreshKey = 0,
  emotionRefreshKey = 0,
  duplicateTrade = null,
  onClearDuplicateTrade,
  focusTickerSignal = 0,
}: TradeFormProps) {
  const [form, setForm] = useState<TradeFormState>(createInitialState);
  const [setupOptions, setSetupOptions] = useState<SetupOptionResponse[]>([]);
  const [emotionOptions, setEmotionOptions] = useState<EmotionOptionResponse[]>([]);
  const [isLoadingSetups, setIsLoadingSetups] = useState(false);
  const [isLoadingEmotions, setIsLoadingEmotions] = useState(false);
  const [isLoadingTickers, setIsLoadingTickers] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showNewSetupForm, setShowNewSetupForm] = useState(false);
  const [showNewEmotionForm, setShowNewEmotionForm] = useState(false);
  const [newSetupName, setNewSetupName] = useState("");
  const [newEmotionName, setNewEmotionName] = useState("");
  const [isCreatingSetup, setIsCreatingSetup] = useState(false);
  const [isCreatingEmotion, setIsCreatingEmotion] = useState(false);
  const [newSetupError, setNewSetupError] = useState<string | null>(null);
  const [newEmotionError, setNewEmotionError] = useState<string | null>(null);
  const [hasLoadedTickers, setHasLoadedTickers] = useState(false);
  const [recentTickers, setRecentTickers] = useState<string[]>([]);
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const [useFills, setUseFills] = useState(false);
  const [fillRows, setFillRows] = useState<FillDraftRow[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showValidationErrors, setShowValidationErrors] = useState(false);
  const tickerInputRef = useRef<HTMLInputElement | null>(null);
  const newSetupInputRef = useRef<HTMLInputElement | null>(null);
  const newEmotionInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (focusTickerSignal <= 0) {
      return;
    }
    tickerInputRef.current?.focus();
  }, [focusTickerSignal]);

  useEffect(() => {
    async function loadSetups() {
      setIsLoadingSetups(true);
      setErrorMessage(null);
      try {
        const response = await getSetups(false);
        const lastUsedSetupId = getLastUsedSetupId();
        setSetupOptions(sortSetupOptions(response));
        setForm((previous) => {
          if (response.length === 0) {
            if (lastUsedSetupId) {
              clearLastUsedSetupId();
            }
            return { ...previous, setupId: "" };
          }

          const hasSelectedSetup = response.some(
            (option) => String(option.id) === previous.setupId,
          );
          if (!hasSelectedSetup) {
            const hasLastUsedSetup = response.some(
              (option) => String(option.id) === lastUsedSetupId,
            );
            if (hasLastUsedSetup) {
              return { ...previous, setupId: lastUsedSetupId };
            }
            if (lastUsedSetupId) {
              clearLastUsedSetupId();
            }
            return { ...previous, setupId: String(response[0].id) };
          }

          return previous;
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load setup options.";
        setErrorMessage(message);
      } finally {
        setIsLoadingSetups(false);
      }
    }

    void loadSetups();
  }, [setupRefreshKey]);

  useEffect(() => {
    async function loadEmotions() {
      setIsLoadingEmotions(true);
      setErrorMessage(null);
      try {
        const response = await getEmotions(false);
        const lastUsedEmotionId = getLastUsedEmotionId();
        setEmotionOptions(sortEmotionOptions(response));
        setForm((previous) => {
          if (response.length === 0) {
            if (lastUsedEmotionId) {
              clearLastUsedEmotionId();
            }
            return { ...previous, emotionId: "" };
          }

          const hasSelectedEmotion = response.some(
            (option) => String(option.id) === previous.emotionId,
          );
          if (!hasSelectedEmotion) {
            const hasLastUsedEmotion = response.some(
              (option) => String(option.id) === lastUsedEmotionId,
            );
            if (hasLastUsedEmotion) {
              return { ...previous, emotionId: lastUsedEmotionId };
            }
            if (lastUsedEmotionId) {
              clearLastUsedEmotionId();
            }
            return { ...previous, emotionId: String(response[0].id) };
          }

          return previous;
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load emotion options.";
        setErrorMessage(message);
      } finally {
        setIsLoadingEmotions(false);
      }
    }

    void loadEmotions();
  }, [emotionRefreshKey]);

  useEffect(() => {
    if (!duplicateTrade) {
      return;
    }

    setErrorMessage(null);
    setSuccessMessage(null);
    setUseFills(false);
    setFillRows([]);
    setShowTickerSuggestions(false);
    setForm((previous) => ({
      ...previous,
      ticker: duplicateTrade.ticker ?? previous.ticker,
      direction: duplicateTrade.direction ?? previous.direction,
      entryPrice: Number.isFinite(duplicateTrade.entry_price)
        ? String(duplicateTrade.entry_price)
        : previous.entryPrice,
      exitPrice: Number.isFinite(duplicateTrade.exit_price)
        ? String(duplicateTrade.exit_price)
        : previous.exitPrice,
      quantity:
        Number.isFinite(duplicateTrade.quantity) && duplicateTrade.quantity > 0
          ? String(duplicateTrade.quantity)
          : previous.quantity,
      setupId:
        typeof duplicateTrade.setup_id === "number" &&
        Number.isInteger(duplicateTrade.setup_id) &&
        duplicateTrade.setup_id > 0
          ? String(duplicateTrade.setup_id)
          : previous.setupId,
      emotionId:
        typeof duplicateTrade.emotion_id === "number" &&
        Number.isInteger(duplicateTrade.emotion_id) &&
        duplicateTrade.emotion_id > 0
          ? String(duplicateTrade.emotion_id)
          : previous.emotionId,
      ruleFollowed:
        typeof duplicateTrade.rule_followed === "boolean"
          ? duplicateTrade.rule_followed
          : previous.ruleFollowed,
      notes: duplicateTrade.notes ?? "",
    }));
  }, [duplicateTrade]);

  useEffect(() => {
    if (showNewSetupForm) {
      newSetupInputRef.current?.focus();
    }
  }, [showNewSetupForm]);

  useEffect(() => {
    if (showNewEmotionForm) {
      newEmotionInputRef.current?.focus();
    }
  }, [showNewEmotionForm]);

  const filteredTickerSuggestions = useMemo(() => {
    const query = form.ticker.trim().toUpperCase();
    if (!query) {
      return recentTickers.slice(0, 8);
    }

    return recentTickers.filter((ticker) => ticker.includes(query)).slice(0, 8);
  }, [form.ticker, recentTickers]);

  const validationResult = useMemo(
    () =>
      validateTradeDraft({
        date: form.date,
        ticker: form.ticker,
        direction: form.direction,
        entryPrice: form.entryPrice,
        exitPrice: form.exitPrice,
        quantity: form.quantity,
        setupId: form.setupId,
        emotionId: form.emotionId,
        ruleFollowed: form.ruleFollowed,
        notes: form.notes,
        useFills,
        fillRows,
      }),
    [fillRows, form, useFills],
  );
  const validationErrors = validationResult.errors;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    setShowValidationErrors(true);

    if (validationErrors.length > 0 || validationResult.payload === null) {
      return;
    }

    setIsSubmitting(true);
    try {
      const createdTrade: TradeResponse = await createTrade(validationResult.payload);

      setRecentTickers((previous) => [
        createdTrade.ticker,
        ...previous.filter((ticker) => ticker !== createdTrade.ticker),
      ]);
      rememberTicker(createdTrade.ticker);
      setHasLoadedTickers(true);
      setShowTickerSuggestions(false);

      const preservedDate = form.date;
      const preservedSetupId =
        setupOptions.some((option) => String(option.id) === form.setupId) && form.setupId
          ? form.setupId
          : "";
      const preservedEmotionId =
        emotionOptions.some((option) => String(option.id) === form.emotionId) && form.emotionId
          ? form.emotionId
          : "";
      if (preservedSetupId) {
        setLastUsedSetupId(preservedSetupId);
      } else {
        clearLastUsedSetupId();
      }
      if (preservedEmotionId) {
        setLastUsedEmotionId(preservedEmotionId);
      } else {
        clearLastUsedEmotionId();
      }
      setLastUsedRuleFollowed(form.ruleFollowed ? "true" : "false");

      setForm({
        ...createInitialState(),
        date: preservedDate,
        setupId: preservedSetupId,
        emotionId: preservedEmotionId,
      });
      if (useFills) {
        setFillRows([createEmptyFillRow("BUY"), createEmptyFillRow("SELL")]);
      }
      setShowValidationErrors(false);
      setSuccessMessage(`Trade #${createdTrade.id} saved.`);
      onClearDuplicateTrade?.();
      onTradeCreated?.(createdTrade);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save trade.";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  const submitDisabled =
    isSubmitting || isLoadingSetups || isLoadingEmotions;

  async function loadRecentTickers() {
    if (hasLoadedTickers || isLoadingTickers) {
      return;
    }

    setIsLoadingTickers(true);
    try {
      const tickers = await getTickers(100);
      setRecentTickers(tickers);
      setHasLoadedTickers(true);
    } catch {
      // Autocomplete should not block form usage.
    } finally {
      setIsLoadingTickers(false);
    }
  }

  function openNewSetupForm() {
    setShowNewSetupForm(true);
    setNewSetupError(null);
  }

  function cancelNewSetupForm() {
    setShowNewSetupForm(false);
    setNewSetupName("");
    setNewSetupError(null);
  }

  async function handleCreateSetupInline() {
    const normalizedName = newSetupName.trim();
    setNewSetupError(null);

    if (!normalizedName) {
      setNewSetupError("Setup name is required.");
      return;
    }

    setIsCreatingSetup(true);
    try {
      const created = await createSetup({ name: normalizedName });
      setSetupOptions((previous) => sortSetupOptions([...previous, created]));
      setForm((previous) => ({ ...previous, setupId: String(created.id) }));
      setLastUsedSetupId(String(created.id));
      setNewSetupName("");
      setShowNewSetupForm(false);
    } catch (error) {
      setNewSetupError(
        error instanceof Error ? error.message : "This name already exists.",
      );
    } finally {
      setIsCreatingSetup(false);
    }
  }

  function openNewEmotionForm() {
    setShowNewEmotionForm(true);
    setNewEmotionError(null);
  }

  function cancelNewEmotionForm() {
    setShowNewEmotionForm(false);
    setNewEmotionName("");
    setNewEmotionError(null);
  }

  async function handleCreateEmotionInline() {
    const normalizedName = newEmotionName.trim();
    setNewEmotionError(null);

    if (!normalizedName) {
      setNewEmotionError("Emotion name is required.");
      return;
    }

    setIsCreatingEmotion(true);
    try {
      const created = await createEmotion({ name: normalizedName });
      setEmotionOptions((previous) => sortEmotionOptions([...previous, created]));
      setForm((previous) => ({ ...previous, emotionId: String(created.id) }));
      setLastUsedEmotionId(String(created.id));
      setNewEmotionName("");
      setShowNewEmotionForm(false);
    } catch (error) {
      setNewEmotionError(
        error instanceof Error ? error.message : "This name already exists.",
      );
    } finally {
      setIsCreatingEmotion(false);
    }
  }

  return (
    <section className="trade-form-panel">
      {!hideTitle ? <h2>New Trade</h2> : null}
      <form className="trade-form" onSubmit={handleSubmit}>
        {duplicateTrade ? (
          <div className="duplicate-trade-banner" role="status">
            <span>
              Duplicating trade from {duplicateTrade.date} ({duplicateTrade.ticker})
            </span>
            <button type="button" onClick={onClearDuplicateTrade}>
              Clear
            </button>
          </div>
        ) : null}
        {showValidationErrors && validationErrors.length > 0 ? (
          <ul className="status-list error" role="alert">
            {validationErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        <label>
          Date
          <input
            type="date"
            value={form.date}
            onChange={(event) => setForm((previous) => ({ ...previous, date: event.target.value }))}
            required
          />
        </label>

        <label>
          Ticker
          <div className="ticker-input-wrap">
            <input
              ref={tickerInputRef}
              type="text"
              placeholder="SPY"
              value={form.ticker}
              onFocus={() => {
                setShowTickerSuggestions(true);
                void loadRecentTickers();
              }}
              onBlur={() => {
                window.setTimeout(() => setShowTickerSuggestions(false), 120);
              }}
              onChange={(event) => {
                const ticker = event.target.value.toUpperCase();
                setForm((previous) => ({ ...previous, ticker }));
                setShowTickerSuggestions(true);
                if (!hasLoadedTickers) {
                  void loadRecentTickers();
                }
              }}
              required
            />
            {showTickerSuggestions && filteredTickerSuggestions.length > 0 ? (
              <ul className="ticker-suggestions" role="listbox">
                {filteredTickerSuggestions.map((ticker) => (
                  <li key={ticker}>
                    <button
                      type="button"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        setForm((previous) => ({ ...previous, ticker }));
                        setShowTickerSuggestions(false);
                      }}
                    >
                      {ticker}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </label>

        <label>
          Direction
          <select
            value={form.direction}
            onChange={(event) =>
              setForm((previous) => ({
                ...previous,
                direction: event.target.value as TradeDirection,
              }))
            }
          >
            {directionOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={useFills}
            onChange={(event) => {
              const nextValue = event.target.checked;
              setUseFills(nextValue);
              if (nextValue && fillRows.length === 0) {
                setFillRows([createEmptyFillRow("BUY"), createEmptyFillRow("SELL")]);
              }
            }}
          />
          Use fills (scaling)
        </label>

        {!useFills ? (
          <>
            <label>
              Entry Price
              <input
                type="number"
                step="0.01"
                value={form.entryPrice}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, entryPrice: event.target.value }))
                }
                required
              />
            </label>

            <label>
              Exit Price
              <input
                type="number"
                step="0.01"
                value={form.exitPrice}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, exitPrice: event.target.value }))
                }
                required
              />
            </label>

            <label>
              Quantity
              <input
                type="number"
                step="1"
                min="1"
                value={form.quantity}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, quantity: event.target.value }))
                }
                required
              />
            </label>
          </>
        ) : (
          <label className="fills-editor-label">
            Fills
            <FillsEditor rows={fillRows} onChange={setFillRows} disabled={isSubmitting} />
          </label>
        )}

        <label>
          Setup
          <select
            value={form.setupId}
            onChange={(event) => {
              const setupId = event.target.value;
              setForm((previous) => ({ ...previous, setupId }));
            }}
            disabled={isLoadingSetups}
          >
            <option value="" disabled={setupOptions.length === 0}>
              {isLoadingSetups
                ? "Loading setups..."
                : setupOptions.length === 0
                  ? "No setups yet"
                  : "No setup"}
            </option>
            {setupOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          {setupOptions.length === 0 && !isLoadingSetups ? (
            <span className="trade-form-helper">
              You can create setups later in Settings.
            </span>
          ) : null}
          <div className="trade-form-inline-actions">
            {!showNewSetupForm ? (
              <button
                type="button"
                className="trade-form-inline-link"
                onClick={openNewSetupForm}
                disabled={isSubmitting || isCreatingSetup}
              >
                + New Setup
              </button>
            ) : (
              <div className="trade-form-inline-create">
                <input
                  ref={newSetupInputRef}
                  type="text"
                  value={newSetupName}
                  placeholder="Setup name"
                  onChange={(event) => setNewSetupName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleCreateSetupInline();
                    }
                    if (event.key === "Escape") {
                      event.preventDefault();
                      cancelNewSetupForm();
                    }
                  }}
                  disabled={isCreatingSetup}
                />
                <div className="trade-form-inline-create-actions">
                  <button
                    type="button"
                    className="trade-form-inline-save"
                    onClick={() => void handleCreateSetupInline()}
                    disabled={isCreatingSetup}
                  >
                    {isCreatingSetup ? "Saving..." : "Save"}
                  </button>
                  <button
                    type="button"
                    className="trade-form-inline-cancel"
                    onClick={cancelNewSetupForm}
                    disabled={isCreatingSetup}
                  >
                    Cancel
                  </button>
                </div>
                {newSetupError ? (
                  <span className="trade-form-inline-error">{newSetupError}</span>
                ) : null}
              </div>
            )}
          </div>
        </label>

        <label>
          Emotion
          <select
            value={form.emotionId}
            onChange={(event) => {
              const emotionId = event.target.value;
              setForm((previous) => ({ ...previous, emotionId }));
            }}
            disabled={isLoadingEmotions}
          >
            <option value="" disabled={emotionOptions.length === 0}>
              {isLoadingEmotions
                ? "Loading emotions..."
                : emotionOptions.length === 0
                  ? "No emotions yet"
                  : "No emotion"}
            </option>
            {emotionOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          {emotionOptions.length === 0 && !isLoadingEmotions ? (
            <span className="trade-form-helper">
              You can create emotions later in Settings.
            </span>
          ) : null}
          <div className="trade-form-inline-actions">
            {!showNewEmotionForm ? (
              <button
                type="button"
                className="trade-form-inline-link"
                onClick={openNewEmotionForm}
                disabled={isSubmitting || isCreatingEmotion}
              >
                + New Emotion
              </button>
            ) : (
              <div className="trade-form-inline-create">
                <input
                  ref={newEmotionInputRef}
                  type="text"
                  value={newEmotionName}
                  placeholder="Emotion name"
                  onChange={(event) => setNewEmotionName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleCreateEmotionInline();
                    }
                    if (event.key === "Escape") {
                      event.preventDefault();
                      cancelNewEmotionForm();
                    }
                  }}
                  disabled={isCreatingEmotion}
                />
                <div className="trade-form-inline-create-actions">
                  <button
                    type="button"
                    className="trade-form-inline-save"
                    onClick={() => void handleCreateEmotionInline()}
                    disabled={isCreatingEmotion}
                  >
                    {isCreatingEmotion ? "Saving..." : "Save"}
                  </button>
                  <button
                    type="button"
                    className="trade-form-inline-cancel"
                    onClick={cancelNewEmotionForm}
                    disabled={isCreatingEmotion}
                  >
                    Cancel
                  </button>
                </div>
                {newEmotionError ? (
                  <span className="trade-form-inline-error">{newEmotionError}</span>
                ) : null}
              </div>
            )}
          </div>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.ruleFollowed}
            onChange={(event) =>
              setForm((previous) => ({ ...previous, ruleFollowed: event.target.checked }))
            }
          />
          Rule Followed
        </label>

        <label>
          Notes
          <textarea
            rows={4}
            value={form.notes}
            onChange={(event) =>
              setForm((previous) => ({ ...previous, notes: event.target.value }))
            }
          />
        </label>

        <button type="submit" disabled={submitDisabled}>
          {isSubmitting ? "Saving..." : "Save Trade"}
        </button>

        {errorMessage ? <p className="status error">{errorMessage}</p> : null}
        {successMessage ? <p className="status success">{successMessage}</p> : null}
      </form>
    </section>
  );
}
