export interface DailySummaryResponse {
  date: string;
  total_trades: number;
  pct_rule_followed: number;
  discipline_score: number;
  total_pnl: number;
  counts_by_setup?: Record<string, number>;
  counts_by_emotion?: Record<string, number>;
}

export interface StatsBySetupRow {
  setup_id: number | null;
  setup_name: string;
  count: number;
  total_pnl_usd: number;
  win_rate: number;
}

export interface StatsSummaryResponse {
  total_trades: number;
  total_pnl_usd: number;
  win_rate_overall: number;
  by_setup: StatsBySetupRow[];
}

export interface EquityPointResponse {
  date: string;
  daily_pnl_usd: number;
  cumulative_pnl_usd: number;
}

export interface EquityCurveResponse {
  points: EquityPointResponse[];
}

export interface PnlSeriesPointResponse {
  label: string;
  start_date: string;
  end_date: string;
  trade_count: number;
  total_pnl_usd: number;
}

export interface PnlSeriesResponse {
  range: StatsInsightsRange;
  group_by: "daily" | "weekly";
  series: PnlSeriesPointResponse[];
}

export interface TimeOfDayBucketResponse {
  label: string;
  start_minute: number;
  end_minute: number;
  count: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_pnl_usd: number;
}

export interface TimeOfDayResponse {
  range: StatsInsightsRange;
  bucket: "hour";
  excluded_missing_time: number;
  buckets: TimeOfDayBucketResponse[];
}

export interface HoldTimeBucketResponse {
  label: string;
  min_seconds: number;
  max_seconds: number | null;
  count: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_pnl_usd: number;
}

export interface HoldTimeResponse {
  range: StatsInsightsRange;
  excluded_missing_duration: number;
  buckets: HoldTimeBucketResponse[];
}

export interface StatsInsightsRange {
  start: string;
  end: string;
}

export interface StatsInsightsDefinitions {
  win_rule: string;
  breakeven_handling: string;
}

export interface StatsInsightsOverall {
  total_trades: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  expectancy_usd_per_trade: number;
}

export interface StatsInsightsRisk {
  max_drawdown_usd: number;
  max_drawdown_start: string | null;
  max_drawdown_end: string | null;
}

export interface StatsInsightsStreaks {
  max_win_streak: number;
  max_loss_streak: number;
  current_streak_type: "win" | "loss" | "none";
  current_streak_length: number;
}

export interface StatsInsightsRuleBucket {
  count: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_pnl_usd: number;
}

export interface StatsInsightsByRuleFollowed {
  followed: StatsInsightsRuleBucket;
  broken: StatsInsightsRuleBucket;
}

export interface StatsInsightsEmotionRow {
  emotion_id: number | null;
  emotion_name: string;
  count: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_pnl_usd: number;
}

export interface StatsInsightsSetupRow {
  setup_id: number | null;
  setup_name: string;
  count: number;
  total_pnl_usd: number;
  win_rate: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  expectancy: number;
}

export type StatsInsightType = "rule_adherence" | "emotion" | "expectancy" | "behavior";
export type StatsInsightSeverity = "info" | "warning" | "positive";

export interface StatsInsightItem {
  type: StatsInsightType;
  severity: StatsInsightSeverity;
  priority_score?: number;
  message: string;
  data: Record<string, string | number | boolean | null> | null;
}

export interface StatsPatternItem {
  id: string;
  title: string;
  severity: StatsInsightSeverity;
  message: string;
  sample_size: number;
  data: Record<string, string | number | boolean | null>;
  filters: Record<string, string | number | boolean | null>;
}

export interface StatsInsightsResponse {
  range: StatsInsightsRange;
  definitions: StatsInsightsDefinitions;
  overall: StatsInsightsOverall;
  risk: StatsInsightsRisk;
  streaks: StatsInsightsStreaks;
  by_rule_followed: StatsInsightsByRuleFollowed;
  by_emotion: StatsInsightsEmotionRow[];
  by_setup_optional: StatsInsightsSetupRow[];
  insights: StatsInsightItem[];
  patterns: StatsPatternItem[];
}
