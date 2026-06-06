import { CreateTradeRequest, TradeDirection } from "../types/trade";
import {
  FillDraftRow,
  FillSummary,
  buildFillWritePayload,
  computeFillSummary,
  getFillValidationErrors,
} from "./fills";

export interface TradeDraftInput {
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
  useFills: boolean;
  fillRows: FillDraftRow[];
}

export interface TradeDraftValidationResult {
  errors: string[];
  payload: CreateTradeRequest | null;
  fillSummary: FillSummary | null;
}

const VALID_DIRECTIONS: TradeDirection[] = ["CALL", "PUT"];
const CONTRACT_MULTIPLIER = 100;

function isValidDateString(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }

  const date = new Date(`${value}T00:00:00`);
  return Number.isFinite(date.getTime());
}

function parsePositiveInteger(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parsePositiveFloat(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

export function validateTradeDraft(input: TradeDraftInput): TradeDraftValidationResult {
  const errors: string[] = [];
  const normalizedTicker = input.ticker.trim().toUpperCase();

  if (!input.date) {
    errors.push("Date is required.");
  } else if (!isValidDateString(input.date)) {
    errors.push("Date must be valid.");
  }

  if (!normalizedTicker) {
    errors.push("Ticker is required.");
  }

  if (!VALID_DIRECTIONS.includes(input.direction)) {
    errors.push("Direction is required.");
  }

  const parsedSetupId = input.setupId ? Number(input.setupId) : null;
  const setupId =
    parsedSetupId !== null && Number.isInteger(parsedSetupId) && parsedSetupId > 0
      ? parsedSetupId
      : null;
  if (input.setupId && setupId === null) {
    errors.push("Setup must be valid when provided.");
  }

  const parsedEmotionId = input.emotionId ? Number(input.emotionId) : null;
  const emotionId =
    parsedEmotionId !== null && Number.isInteger(parsedEmotionId) && parsedEmotionId > 0
      ? parsedEmotionId
      : null;
  if (input.emotionId && emotionId === null) {
    errors.push("Emotion must be valid when provided.");
  }

  if (input.useFills) {
    const fillErrors = getFillValidationErrors(input.fillRows);
    if (fillErrors.length > 0) {
      return { errors: [...errors, ...fillErrors], payload: null, fillSummary: null };
    }

    const fillSummary = computeFillSummary(input.fillRows);
    if (
      fillSummary.avgEntryPrice === null ||
      !Number.isFinite(fillSummary.avgEntryPrice) ||
      fillSummary.avgEntryPrice <= 0
    ) {
      errors.push("Avg Entry must be a finite value greater than zero.");
    }
    if (
      fillSummary.avgExitPrice === null ||
      !Number.isFinite(fillSummary.avgExitPrice) ||
      fillSummary.avgExitPrice <= 0
    ) {
      errors.push("Avg Exit must be a finite value greater than zero.");
    }
    if (!Number.isInteger(fillSummary.matchedQty) || fillSummary.matchedQty <= 0) {
      errors.push("Total Quantity must be a whole number greater than zero.");
    }
    if (!Number.isFinite(fillSummary.realizedPnlUsd)) {
      errors.push("Total PnL must be finite.");
    }

    if (errors.length > 0) {
      return { errors, payload: null, fillSummary };
    }

    return {
      errors: [],
      fillSummary,
      payload: {
        date: input.date,
        ticker: normalizedTicker,
        direction: input.direction,
        entry_price: fillSummary.avgEntryPrice as number,
        exit_price: fillSummary.avgExitPrice as number,
        quantity: fillSummary.matchedQty,
        setup_id: setupId,
        emotion_id: emotionId,
        rule_followed: input.ruleFollowed,
        notes: input.notes.trim() ? input.notes.trim() : null,
        use_fills: true,
        fills: input.fillRows.map(buildFillWritePayload),
      },
    };
  }

  const entryPrice = parsePositiveFloat(input.entryPrice);
  if (entryPrice === null) {
    errors.push("Entry price must be greater than zero.");
  }

  const exitPrice = parsePositiveFloat(input.exitPrice);
  if (exitPrice === null) {
    errors.push("Exit price must be greater than zero.");
  }

  const quantity = parsePositiveInteger(input.quantity);
  if (quantity === null) {
    errors.push("Quantity must be a whole number greater than zero.");
  }

  const computedPnl =
    entryPrice !== null && exitPrice !== null ? Number((exitPrice - entryPrice).toFixed(4)) : null;
  if (computedPnl === null || !Number.isFinite(computedPnl)) {
    errors.push("Computed PnL must be finite.");
  }

  const totalPnlUsd =
    computedPnl !== null && quantity !== null ? computedPnl * quantity * CONTRACT_MULTIPLIER : null;
  if (totalPnlUsd === null || !Number.isFinite(totalPnlUsd)) {
    errors.push("Total PnL must be finite.");
  }

  if (errors.length > 0) {
    return { errors, payload: null, fillSummary: null };
  }

  return {
    errors: [],
    fillSummary: null,
    payload: {
      date: input.date,
      ticker: normalizedTicker,
      direction: input.direction,
      entry_price: entryPrice as number,
      exit_price: exitPrice as number,
      quantity: quantity as number,
      setup_id: setupId,
      emotion_id: emotionId,
      rule_followed: input.ruleFollowed,
      notes: input.notes.trim() ? input.notes.trim() : null,
    },
  };
}
