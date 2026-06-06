import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface SetupDistributionChartRow {
  setupId: number | null;
  setupName: string;
  tradeCount: number;
}

interface SetupDistributionChartProps {
  rows: SetupDistributionChartRow[];
  chartHeight?: number;
  enableDrilldown?: boolean;
  onBarClick?: (row: SetupDistributionChartRow) => void;
}

interface SetupDistributionTooltipProps {
  active?: boolean;
  payload?: Array<{
    value: number;
    payload: SetupDistributionChartRow;
  }>;
}

const SETUP_NAME_MAX_LENGTH = 20;

function truncateSetupName(name: string): string {
  if (name.length <= SETUP_NAME_MAX_LENGTH) {
    return name;
  }
  return `${name.slice(0, SETUP_NAME_MAX_LENGTH - 1)}…`;
}

function SetupDistributionTooltip({ active, payload }: SetupDistributionTooltipProps) {
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
      <span>Trades: {point.tradeCount}</span>
    </div>
  );
}

export function SetupDistributionChart({
  rows,
  chartHeight,
  enableDrilldown = false,
  onBarClick,
}: SetupDistributionChartProps) {
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
                allowDecimals={false}
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
                content={<SetupDistributionTooltip />}
              />
              <Bar
                dataKey="tradeCount"
                name="Trades"
                fill="#175cd3"
                radius={[0, 4, 4, 0]}
                cursor={enableDrilldown ? "pointer" : "default"}
                onClick={handleBarClick}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
