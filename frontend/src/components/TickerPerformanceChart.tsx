import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { GREEN_POS, RED_NEG } from "../utils/colors";

export interface TickerPerformanceChartRow {
  ticker: string;
  tradeCount: number;
  totalPnlUsd: number;
}

interface TickerPerformanceChartProps {
  rows: TickerPerformanceChartRow[];
  formatUsd: (value: number) => string;
  chartHeight?: number;
  enableDrilldown?: boolean;
  onBarClick?: (row: TickerPerformanceChartRow) => void;
}

interface TickerPerformanceTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: TickerPerformanceChartRow;
  }>;
  formatUsd: (value: number) => string;
}

const TICKER_MAX_LENGTH = 14;

function truncateTicker(ticker: string): string {
  if (ticker.length <= TICKER_MAX_LENGTH) {
    return ticker;
  }
  return `${ticker.slice(0, TICKER_MAX_LENGTH - 1)}…`;
}

function TickerPerformanceTooltip({ active, payload, formatUsd }: TickerPerformanceTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  if (!point) {
    return null;
  }

  return (
    <div className="weekly-pnl-tooltip">
      <strong>{point.ticker}</strong>
      <span>Total PnL: {formatUsd(point.totalPnlUsd)}</span>
      <span>Trades: {point.tradeCount}</span>
    </div>
  );
}

export function TickerPerformanceChart({
  rows,
  formatUsd,
  chartHeight,
  enableDrilldown = false,
  onBarClick,
}: TickerPerformanceChartProps) {
  const values = rows.map((row) => row.totalPnlUsd);
  const minValue = values.length > 0 ? Math.min(...values) : 0;
  const maxValue = values.length > 0 ? Math.max(...values) : 0;
  const maxAbs = Math.max(Math.abs(minValue), Math.abs(maxValue));
  const padding = Math.max(50, maxAbs * 0.1);
  const xDomain: [number, number] =
    maxAbs === 0 ? [-100, 100] : [-(maxAbs + padding), maxAbs + padding];

  function handleBarClick(_data: unknown, index: number) {
    if (!enableDrilldown || !onBarClick) {
      return;
    }
    const row = rows[index];
    if (!row || row.tradeCount <= 0) {
      return;
    }
    onBarClick(row);
  }

  return (
    <div className="chart-card setup-distribution-chart-card">
      <div
        className="chart-body chart-wrapper"
        style={
          typeof chartHeight === "number"
            ? { height: chartHeight, minHeight: chartHeight }
            : undefined
        }
      >
        <div className="chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 16, right: 20, bottom: 16, left: 20 }}
              barCategoryGap="22%"
            >
              <CartesianGrid stroke="#d0d5dd" strokeDasharray="4 4" horizontal={false} />
              <XAxis
                type="number"
                domain={xDomain}
                tickFormatter={formatUsd}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={{ stroke: "#98a2b3" }}
                tickLine={{ stroke: "#98a2b3" }}
              />
              <YAxis
                dataKey="ticker"
                type="category"
                width={120}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={truncateTicker}
              />
              <Tooltip
                cursor={{ fill: "rgba(11, 116, 222, 0.08)" }}
                content={<TickerPerformanceTooltip formatUsd={formatUsd} />}
              />
              <ReferenceLine x={0} stroke="#98a2b3" strokeDasharray="4 4" />
              <Bar
                dataKey="totalPnlUsd"
                name="Total PnL (USD)"
                radius={[0, 4, 4, 0]}
                cursor={enableDrilldown ? "pointer" : "default"}
                onClick={handleBarClick}
              >
                {rows.map((row) => (
                  <Cell
                    key={`ticker-performance-${row.ticker}`}
                    fill={row.totalPnlUsd >= 0 ? GREEN_POS : RED_NEG}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
