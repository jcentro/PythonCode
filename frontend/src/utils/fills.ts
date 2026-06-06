import { TradeFillResponse, TradeFillSide, TradeFillWriteRequest } from "../types/trade";

export interface FillDraftRow {
  id?: number;
  side: TradeFillSide;
  quantity: string;
  price: string;
  filledAt: string;
}

export interface FillSummary {
  totalEntryQty: number;
  totalExitQty: number;
  matchedQty: number;
  avgEntryPrice: number | null;
  avgExitPrice: number | null;
  realizedPnlUsd: number;
  isPartial: boolean;
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

function normalizeFilledAt(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return trimmed.length === 16 ? `${trimmed}:00` : trimmed;
}

export function createEmptyFillRow(side: TradeFillSide = "BUY"): FillDraftRow {
  return {
    side,
    quantity: "1",
    price: "",
    filledAt: "",
  };
}

export function toFillDraftRow(fill: TradeFillResponse): FillDraftRow {
  return {
    id: fill.id,
    side: fill.side,
    quantity: String(fill.quantity),
    price: String(fill.price),
    filledAt: fill.filled_at ? fill.filled_at.slice(0, 16) : "",
  };
}

export function getFillValidationErrors(rows: FillDraftRow[]): string[] {
  if (rows.length === 0) {
    return ["Add at least one BUY fill and one SELL fill."];
  }

  let totalBuyQty = 0;
  let totalSellQty = 0;

  for (const [index, row] of rows.entries()) {
    const label = `Fill ${index + 1}`;
    const quantity = parsePositiveInteger(row.quantity);
    if (quantity === null) {
      return [`${label}: quantity must be a whole number greater than zero.`];
    }

    const price = parsePositiveFloat(row.price);
    if (price === null) {
      return [`${label}: price must be greater than zero.`];
    }

    if (row.side === "BUY") {
      totalBuyQty += quantity;
    } else {
      totalSellQty += quantity;
    }
  }

  if (totalBuyQty === 0 || totalSellQty === 0) {
    return ["Add at least one BUY fill and one SELL fill."];
  }

  if (totalBuyQty !== totalSellQty) {
    return [
      "Open positions are not supported yet. Total BUY quantity must equal total SELL quantity.",
    ];
  }

  return [];
}

export function validateFillRows(rows: FillDraftRow[]): string | null {
  return getFillValidationErrors(rows)[0] ?? null;
}

export function buildFillWritePayload(row: FillDraftRow): TradeFillWriteRequest {
  const quantity = parsePositiveInteger(row.quantity);
  const price = parsePositiveFloat(row.price);
  if (quantity === null || price === null) {
    throw new Error("Invalid fill row");
  }

  return {
    side: row.side,
    quantity,
    price,
    filled_at: normalizeFilledAt(row.filledAt) ?? null,
  };
}

export function computeFillSummary(rows: FillDraftRow[]): FillSummary {
  let totalEntryQty = 0;
  let totalExitQty = 0;
  let entryNotional = 0;
  let exitNotional = 0;

  for (const row of rows) {
    const quantity = parsePositiveInteger(row.quantity);
    const price = parsePositiveFloat(row.price);
    if (quantity === null || price === null) {
      continue;
    }

    if (row.side === "BUY") {
      totalEntryQty += quantity;
      entryNotional += quantity * price;
    } else {
      totalExitQty += quantity;
      exitNotional += quantity * price;
    }
  }

  const avgEntryPrice = totalEntryQty > 0 ? entryNotional / totalEntryQty : null;
  const avgExitPrice = totalExitQty > 0 ? exitNotional / totalExitQty : null;
  const matchedQty = Math.min(totalEntryQty, totalExitQty);
  const realizedPnlUsd =
    matchedQty > 0 && avgEntryPrice !== null && avgExitPrice !== null
      ? Number(((avgExitPrice - avgEntryPrice) * matchedQty * 100).toFixed(2))
      : 0;

  return {
    totalEntryQty,
    totalExitQty,
    matchedQty,
    avgEntryPrice,
    avgExitPrice,
    realizedPnlUsd,
    isPartial: totalEntryQty !== totalExitQty,
  };
}
