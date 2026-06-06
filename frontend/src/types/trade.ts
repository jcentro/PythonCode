export type TradeDirection = "CALL" | "PUT";
export type TradeRuleFollowedFilter = "true" | "false" | "unknown";
export type TradeOutcomeFilter = "win" | "loss" | "breakeven";
export type TradeSourceFilter = "tos_csv" | "manual";
export type TradeClassificationFilter = "all" | "unclassified" | "classified";
export type TradeIndexBucketFilter = "first_3" | "after_3";
export type TradePatternFilter = "after_2_losses_next_trade";
export type TradeFillSide = "BUY" | "SELL";

export interface TradeListFilters {
  date?: string;
  start?: string;
  end?: string;
  import_batch_id?: number;
  ticker?: string;
  setup_id?: number;
  emotion_id?: number;
  rule_followed?: TradeRuleFollowedFilter;
  outcome?: TradeOutcomeFilter;
  source?: TradeSourceFilter;
  classification?: TradeClassificationFilter;
  entry_time_start_minute?: number;
  entry_time_end_minute?: number;
  hold_time_min_seconds?: number;
  hold_time_max_seconds?: number;
  trade_index_bucket?: TradeIndexBucketFilter;
  pattern?: TradePatternFilter;
  include_fills?: boolean;
}

export interface CreateTradeRequest {
  date: string;
  ticker: string;
  direction: TradeDirection;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl?: number;
  setup_id?: number | null;
  emotion_id?: number | null;
  rule_followed: boolean;
  notes?: string | null;
  use_fills?: boolean;
  fills?: TradeFillWriteRequest[];
}

export interface BulkUpdateTradesRequest {
  trade_ids: number[];
  setup_id?: number | null;
  emotion_id?: number | null;
  rule_followed?: boolean | null;
}

export interface BulkUpdateTradesResponse {
  updated_count: number;
  errors: string[];
}

export interface TradePatchRequest {
  setup_id?: number | null;
  emotion_id?: number | null;
  rule_followed?: boolean | null;
}

export interface TradeResponse {
  id: number;
  date: string;
  ticker: string;
  direction: TradeDirection;
  entry_price: number;
  exit_price: number;
  pnl: number;
  quantity: number;
  contract_multiplier: number;
  total_pnl_usd: number;
  setup_id: number | null;
  setup_name: string;
  emotion_id: number | null;
  emotion_name: string;
  rule_followed: boolean | null;
  notes: string | null;
  source?: string | null;
  source_id?: string | null;
  entry_time?: string | null;
  exit_time?: string | null;
  duration_seconds?: number | null;
  total_entry_qty?: number | null;
  total_exit_qty?: number | null;
  avg_entry_price?: number | null;
  avg_exit_price?: number | null;
  realized_pnl_usd?: number | null;
  is_partial?: boolean;
  use_fills?: boolean;
  fills?: TradeFillResponse[] | null;
}

export interface TradeFillResponse {
  id: number;
  trade_id: number;
  filled_at: string | null;
  side: TradeFillSide;
  quantity: number;
  price: number;
  source: string | null;
  source_id: string | null;
}

export interface TradeFillWriteRequest {
  side: TradeFillSide;
  quantity: number;
  price: number;
  filled_at?: string | null;
}
