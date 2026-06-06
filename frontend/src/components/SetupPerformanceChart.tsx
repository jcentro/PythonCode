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

export interface SetupPerformanceChartRow {
  setupId: number | null;
  setupName: string;
  tradeCount: number;
  totalPnlUsd: number;
}

interface SetupPerformanceChartProps {
  rows: SetupPerformanceChartRow[];
  formatUsd: (value: number) => string;
  chartHeight?: number;
  enableDrilldown?: boolean;
  onBarClick?: (row: SetupPerformanceChartRow) => void;
}

interface SetupPerformanceTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: SetupPerformanceChartRow;
  }>;
  formatUsd: (value: number) => string;
}

const SETUP_NAME_MAX_LENGTH = 20;

function truncateSetupName(name: string): string {
  if (name.length <= SETUP_NAME_MAX_LENGTH) {
    return name;
  }
  return `${name.slice(0, SETUP_NAME_MAX_LENGTH - 1)}…`;
}

function SetupPerformanceTooltip({ active, payload, formatUsd }: SetupPerformanceTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  if (!point) {
    return null;
  }

  return (
    <div className="weekly-pnl-tooltip">
      <strong>{point.setupName}</strong>
      <span>Total PnL: {formatUsd(point.totalPnlUsd)}</span>
      <span>Trades: {point.tradeCount}</span>
    </div>
  );
}

export function SetupPerformanceChart({
  rows,
  formatUsd,
  chartHeight,
  enableDrilldown = false,
  onBarClick,
}: SetupPerformanceChartProps) {
  const values = rows.map((row) => row.totalPnlUsd);
  const minValue = values.length > 0 ? Math.min(...values) : 0;
  const maxValue = values.length > 0 ? Math.max(...values) : 0;
  const maxAbs = Math.max(Math.abs(minValue), Math.abs(maxValue));
  const padding = Math.max(50, maxAbs * 0.1);
  const xDomain: [number, number] = maxAbs === 0 ? [-100, 100] : [-(maxAbs + padding), maxAbs + padding];

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
                dataKey="setupName"
                type="category"
                width={170}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={truncateSetupName}
              />
              <Tooltip
                cursor={{ fill: "rgba(11, 116, 222, 0.08)" }}
                content={<SetupPerformanceTooltip formatUsd={formatUsd} />}
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
                    key={`setup-performance-${row.setupName}`}
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
