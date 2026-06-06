export interface ImportedTradeFillPreview {
  side: "BUY" | "SELL";
  qty: number;
  price: number;
  exec_datetime: string;
}

export interface ImportedTradePreview {
  temp_id: string;
  date: string;
  symbol: string;
  exp: string;
  strike: number;
  option_type: "CALL" | "PUT";
  entry_fills_count: number;
  exit_fills_count: number;
  total_entry_qty: number;
  total_exit_qty: number;
  matched_qty: number;
  avg_entry_price: number;
  avg_exit_price: number;
  total_pnl_usd: number;
  duration_seconds: number | null;
  is_partial: boolean;
  fills: ImportedTradeFillPreview[];

  // Backward-compatible fields currently still returned by backend.
  ticker: string;
  direction: "CALL" | "PUT";
  quantity: number;
  entry_time: string | null;
  exit_time: string | null;
  entry_price: number;
  exit_price: number;
  duplicate_status: "new" | "duplicate" | "possible_duplicate";
  duplicate_reason?: string | null;
  existing_trade_id?: number | null;
}

export interface ToSImportPreviewResponse {
  batch_id: number;
  detected_trades: ImportedTradePreview[];
  warnings: string[];
}

export interface ToSImportCommitItem {
  temp_id: string;
  setup_id?: number;
  emotion_id?: number;
  rule_followed?: boolean;
  notes?: string;
}

export interface ToSImportCommitRequest {
  batch_id: number;
  items: ToSImportCommitItem[];
}

export interface ToSImportCommitResponse {
  imported: number;
  skipped_duplicates: number;
  errors: string[];
}

export type ImportBatchStatus = "previewed" | "committed" | "failed";

export interface ImportBatchFill {
  exec_datetime: string;
  side: "BUY" | "SELL";
  pos_effect: "TO OPEN" | "TO CLOSE" | string;
  qty: number;
  symbol: string;
  exp: string;
  strike: number;
  option_type: "CALL" | "PUT";
  price: number;
}

export interface ImportBatchListItem {
  id: number;
  created_at: string;
  source: string;
  original_filename: string | null;
  status: ImportBatchStatus;
  detected_trades_count: number;
  matched_pairs_count: number;
  unmatched_opens_count: number;
  unmatched_closes_count: number;
  committed_count: number;
  skipped_duplicates_count: number;
  warnings_count: number;
}

export interface ImportBatchDetail {
  id: number;
  created_at: string;
  source: string;
  original_filename: string | null;
  file_hash: string | null;
  status: ImportBatchStatus;
  parsed_rows_count: number;
  fills_parsed_count: number;
  detected_trades_count: number;
  matched_pairs_count: number;
  unmatched_opens_count: number;
  unmatched_closes_count: number;
  excluded_count: number;
  warnings: string[];
  fills_count: number;
  fills: ImportBatchFill[];
  unmatched_opens: ImportBatchFill[];
  unmatched_closes: ImportBatchFill[];
  committed_count: number;
  skipped_duplicates_count: number;
  errors: string[];
  pnl_total_committed_usd: number;
}

export interface BackupImportResponse {
  status: string;
  imported: {
    trades: number;
    fills: number;
    setups: number;
    emotions: number;
  };
}
