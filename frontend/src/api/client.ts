import {
  BulkUpdateTradesRequest,
  BulkUpdateTradesResponse,
  CreateTradeRequest,
  TradePatchRequest,
  TradeFillWriteRequest,
  TradeListFilters,
  TradeResponse,
} from "../types/trade";
import {
  DailySummaryResponse,
  HoldTimeResponse,
  PnlSeriesResponse,
  StatsInsightsResponse,
  StatsSummaryResponse,
  TimeOfDayResponse,
} from "../types/summary";
import {
  CreateSetupOptionRequest,
  SetupOptionResponse,
  UpdateSetupOptionRequest,
} from "../types/setup";
import {
  CreateEmotionOptionRequest,
  EmotionOptionResponse,
  UpdateEmotionOptionRequest,
} from "../types/emotion";
import {
  BackupImportResponse,
  ImportBatchDetail,
  ImportBatchListItem,
  ToSImportCommitRequest,
  ToSImportCommitResponse,
  ToSImportPreviewResponse,
} from "../types/import";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
let recentTickersCache: string[] | null = null;

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

async function apiRequest<TResponse, TRequest = undefined>(
  path: string,
  options: {
    method?: "GET" | "POST" | "DELETE" | "PUT" | "PATCH";
    body?: TRequest;
  } = {}
): Promise<TResponse> {
  const response = await fetch(buildUrl(path), {
    method: options.method ?? "GET",
    headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

function normalizeTicker(ticker: string): string {
  return ticker.trim().toUpperCase();
}

function addTickerToCache(ticker: string): void {
  const normalizedTicker = normalizeTicker(ticker);
  if (!normalizedTicker) {
    return;
  }

  recentTickersCache = [
    normalizedTicker,
    ...(recentTickersCache ?? []).filter((existingTicker) => existingTicker !== normalizedTicker),
  ];
}

export function createTrade(payload: CreateTradeRequest): Promise<TradeResponse> {
  return apiRequest<TradeResponse, CreateTradeRequest>("/api/trades", {
    method: "POST",
    body: payload,
  }).then((trade) => {
    addTickerToCache(trade.ticker);
    return trade;
  });
}

export function getTrades(filters?: TradeListFilters): Promise<TradeResponse[]> {
  const params = new URLSearchParams();
  if (filters?.date) params.set("date", filters.date);
  if (filters?.start) params.set("start", filters.start);
  if (filters?.end) params.set("end", filters.end);
  if (filters?.import_batch_id !== undefined) {
    params.set("import_batch_id", String(filters.import_batch_id));
  }
  if (filters?.ticker) params.set("ticker", filters.ticker);
  if (filters?.setup_id !== undefined) params.set("setup_id", String(filters.setup_id));
  if (filters?.emotion_id !== undefined) params.set("emotion_id", String(filters.emotion_id));
  if (filters?.rule_followed) params.set("rule_followed", filters.rule_followed);
  if (filters?.outcome) params.set("outcome", filters.outcome);
  if (filters?.source) params.set("source", filters.source);
  if (filters?.classification) params.set("classification", filters.classification);
  if (filters?.entry_time_start_minute !== undefined) {
    params.set("entry_time_start_minute", String(filters.entry_time_start_minute));
  }
  if (filters?.entry_time_end_minute !== undefined) {
    params.set("entry_time_end_minute", String(filters.entry_time_end_minute));
  }
  if (filters?.hold_time_min_seconds !== undefined) {
    params.set("hold_time_min_seconds", String(filters.hold_time_min_seconds));
  }
  if (filters?.hold_time_max_seconds !== undefined) {
    params.set("hold_time_max_seconds", String(filters.hold_time_max_seconds));
  }
  if (filters?.trade_index_bucket) params.set("trade_index_bucket", filters.trade_index_bucket);
  if (filters?.pattern) params.set("pattern", filters.pattern);
  if (filters?.include_fills) params.set("include_fills", "true");

  const queryString = params.toString();
  const path = queryString ? `/api/trades?${queryString}` : "/api/trades";
  return apiRequest<TradeResponse[]>(path);
}

export function deleteTrade(tradeId: number): Promise<TradeResponse> {
  return apiRequest<TradeResponse>(`/api/trades/${tradeId}`, {
    method: "DELETE",
  });
}

export function updateTrade(tradeId: number, payload: CreateTradeRequest): Promise<TradeResponse> {
  return apiRequest<TradeResponse, CreateTradeRequest>(`/api/trades/${tradeId}`, {
    method: "PUT",
    body: payload,
  }).then((trade) => {
    addTickerToCache(trade.ticker);
    return trade;
  });
}

export function patchTrade(tradeId: number, payload: TradePatchRequest): Promise<TradeResponse> {
  return apiRequest<TradeResponse, TradePatchRequest>(`/api/trades/${tradeId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function getUnclassifiedTradesCount(): Promise<number> {
  const response = await apiRequest<{ count: number }>("/api/trades/unclassified-count");
  return response.count;
}

export function updateTradesBulk(
  payload: BulkUpdateTradesRequest
): Promise<BulkUpdateTradesResponse> {
  return apiRequest<BulkUpdateTradesResponse, BulkUpdateTradesRequest>("/api/trades/bulk", {
    method: "PATCH",
    body: payload,
  });
}

export function createTradeFill(
  tradeId: number,
  payload: TradeFillWriteRequest
): Promise<TradeResponse> {
  return apiRequest<TradeResponse, TradeFillWriteRequest>(`/api/trades/${tradeId}/fills`, {
    method: "POST",
    body: payload,
  });
}

export function updateTradeFill(
  tradeId: number,
  fillId: number,
  payload: TradeFillWriteRequest
): Promise<TradeResponse> {
  return apiRequest<TradeResponse, TradeFillWriteRequest>(
    `/api/trades/${tradeId}/fills/${fillId}`,
    {
      method: "PUT",
      body: payload,
    }
  );
}

export function deleteTradeFill(tradeId: number, fillId: number): Promise<TradeResponse> {
  return apiRequest<TradeResponse>(`/api/trades/${tradeId}/fills/${fillId}`, {
    method: "DELETE",
  });
}

export function getSetups(includeInactive = false): Promise<SetupOptionResponse[]> {
  const params = new URLSearchParams();
  if (includeInactive) {
    params.set("include_inactive", "true");
  }

  const queryString = params.toString();
  const path = queryString ? `/api/setups?${queryString}` : "/api/setups";
  return apiRequest<SetupOptionResponse[]>(path);
}

export function createSetup(payload: CreateSetupOptionRequest): Promise<SetupOptionResponse> {
  return apiRequest<SetupOptionResponse, CreateSetupOptionRequest>("/api/setups", {
    method: "POST",
    body: payload,
  });
}

export function updateSetup(
  setupId: number,
  payload: UpdateSetupOptionRequest
): Promise<SetupOptionResponse> {
  return apiRequest<SetupOptionResponse, UpdateSetupOptionRequest>(`/api/setups/${setupId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function getDailySummary(date: string): Promise<DailySummaryResponse> {
  const params = new URLSearchParams({ date });
  return apiRequest<DailySummaryResponse>(`/api/summary/daily?${params.toString()}`);
}

export function getStatsSummary(start?: string, end?: string): Promise<StatsSummaryResponse> {
  const params = new URLSearchParams();
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }

  const queryString = params.toString();
  const path = queryString ? `/api/stats/summary?${queryString}` : "/api/stats/summary";
  return apiRequest<StatsSummaryResponse>(path);
}

export function getPnlSeries(
  groupBy: "daily" | "weekly",
  start?: string,
  end?: string
): Promise<PnlSeriesResponse> {
  const params = new URLSearchParams();
  params.set("group_by", groupBy);
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }

  const queryString = params.toString();
  return apiRequest<PnlSeriesResponse>(`/api/stats/pnl-series?${queryString}`);
}

export function getStatsInsights(start?: string, end?: string): Promise<StatsInsightsResponse> {
  const params = new URLSearchParams();
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }

  const queryString = params.toString();
  const path = queryString ? `/api/stats/insights?${queryString}` : "/api/stats/insights";
  return apiRequest<StatsInsightsResponse>(path);
}

export function getTimeOfDayStats(start?: string, end?: string): Promise<TimeOfDayResponse> {
  const params = new URLSearchParams({ bucket: "hour" });
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }

  return apiRequest<TimeOfDayResponse>(`/api/stats/time-of-day?${params.toString()}`);
}

export function getHoldTimeStats(start?: string, end?: string): Promise<HoldTimeResponse> {
  const params = new URLSearchParams();
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }

  const queryString = params.toString();
  const path = queryString ? `/api/stats/hold-time?${queryString}` : "/api/stats/hold-time";
  return apiRequest<HoldTimeResponse>(path);
}

export function getEmotions(includeInactive = false): Promise<EmotionOptionResponse[]> {
  const params = new URLSearchParams();
  if (includeInactive) {
    params.set("include_inactive", "true");
  }

  const queryString = params.toString();
  const path = queryString ? `/api/emotions?${queryString}` : "/api/emotions";
  return apiRequest<EmotionOptionResponse[]>(path);
}

export function createEmotion(payload: CreateEmotionOptionRequest): Promise<EmotionOptionResponse> {
  return apiRequest<EmotionOptionResponse, CreateEmotionOptionRequest>("/api/emotions", {
    method: "POST",
    body: payload,
  });
}

export function updateEmotion(
  emotionId: number,
  payload: UpdateEmotionOptionRequest
): Promise<EmotionOptionResponse> {
  return apiRequest<EmotionOptionResponse, UpdateEmotionOptionRequest>(`/api/emotions/${emotionId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function getTickers(limit = 20): Promise<string[]> {
  if (recentTickersCache !== null) {
    return recentTickersCache.slice(0, limit);
  }

  const params = new URLSearchParams({ limit: String(limit) });
  const tickers = await apiRequest<string[]>(`/api/tickers?${params.toString()}`);
  recentTickersCache = tickers.map(normalizeTicker).filter(Boolean);
  return recentTickersCache.slice(0, limit);
}

export function rememberTicker(ticker: string): void {
  addTickerToCache(ticker);
}

export async function previewToSImport(file: File): Promise<ToSImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(buildUrl("/api/import/tos/preview"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as ToSImportPreviewResponse;
}

export function commitToSImport(
  payload: ToSImportCommitRequest
): Promise<ToSImportCommitResponse> {
  return apiRequest<ToSImportCommitResponse, ToSImportCommitRequest>("/api/import/tos/commit", {
    method: "POST",
    body: payload,
  });
}

export function getImportBatches(source = "tos_csv", limit = 50): Promise<ImportBatchListItem[]> {
  const params = new URLSearchParams({
    source,
    limit: String(limit),
  });
  return apiRequest<ImportBatchListItem[]>(`/api/import/batches?${params.toString()}`);
}

export function getImportBatchDetail(batchId: number): Promise<ImportBatchDetail> {
  return apiRequest<ImportBatchDetail>(`/api/import/batches/${batchId}`);
}

export function importBackup(payload: unknown): Promise<BackupImportResponse> {
  return fetch(buildUrl("/api/backup/import"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (response) => {
    if (!response.ok) {
      const rawText = await response.text();
      try {
        const parsed = JSON.parse(rawText) as { detail?: string };
        if (typeof parsed.detail === "string") {
          return Promise.reject(new Error(parsed.detail));
        }
      } catch {
        return Promise.reject(new Error(rawText || `Request failed with status ${response.status}`));
      }
      return Promise.reject(new Error(rawText || `Request failed with status ${response.status}`));
    }

    return (await response.json()) as BackupImportResponse;
  });
}

export function wipeAllData(): Promise<{ status: string }> {
  return apiRequest<{ status: string }>("/api/admin/wipe", {
    method: "POST",
  });
}
