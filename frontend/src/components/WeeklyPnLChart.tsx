import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PnlSeriesPointResponse } from "../types/summary";
import { GREEN_POS, RED_NEG } from "../utils/colors";
import { formatDateRange, formatMonthDay } from "../utils/formatting";

interface WeeklyPnLChartProps {
  weeklySeries: PnlSeriesPointResponse[];
  formatUsd: (value: number) => string;
  chartHeight?: number;
  onBarClick?: (point: PnlSeriesPointResponse) => void;
}

interface WeeklyTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: PnlSeriesPointResponse;
  }>;
  formatUsd: (value: number) => string;
}

interface WeeklyChartMouseState {
  isTooltipActive?: boolean;
  activeTooltipIndex?: number | string;
}

function WeeklyTooltip({ active, payload, formatUsd }: WeeklyTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  if (!point) {
    return null;
  }

  return (
    <div className="weekly-pnl-tooltip">
      <strong>{formatMonthDay(point.start_date)}</strong>
      <span>{formatDateRange(point.start_date, point.end_date)}</span>
      <span>Total PnL: {formatUsd(point.total_pnl_usd)}</span>
      <span>Trades: {point.trade_count}</span>
    </div>
  );
}

export function WeeklyPnLChart({
  weeklySeries,
  formatUsd,
  chartHeight,
  onBarClick,
}: WeeklyPnLChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [isTooltipActive, setIsTooltipActive] = useState(false);
  const barCategoryGap = weeklySeries.length <= 2 ? "40%" : "15%";
  const values = weeklySeries.map((point) => point.total_pnl_usd);
  const minValue = values.length > 0 ? Math.min(...values) : 0;
  const maxValue = values.length > 0 ? Math.max(...values) : 0;
  const maxAbs = Math.max(Math.abs(minValue), Math.abs(maxValue));
  const padding = Math.max(25, maxAbs * 0.1);
  const yDomain: [number, number] =
    maxAbs === 0 ? [-100, 100] : [-(maxAbs + padding), maxAbs + padding];
  const avgWeeklyPnl =
    weeklySeries.length > 0
      ? weeklySeries.reduce((sum, point) => sum + point.total_pnl_usd, 0) / weeklySeries.length
      : null;

  function getPointByIndex(index: number): PnlSeriesPointResponse | null {
    if (!Number.isInteger(index) || index < 0 || index >= weeklySeries.length) {
      return null;
    }
    return weeklySeries[index] ?? null;
  }

  function getEventIndex(state: WeeklyChartMouseState | undefined): number | null {
    const rawIndex = state?.activeTooltipIndex;
    const parsedIndex =
      typeof rawIndex === "number"
        ? rawIndex
        : typeof rawIndex === "string"
          ? Number(rawIndex)
          : null;

    if (parsedIndex === null || Number.isNaN(parsedIndex) || !Number.isInteger(parsedIndex)) {
      return null;
    }
    return parsedIndex;
  }

  function handleChartMouseMove(state: unknown) {
    const chartState = state as WeeklyChartMouseState | undefined;
    const nextTooltipActive = chartState?.isTooltipActive === true;
    const nextIndex = nextTooltipActive ? getEventIndex(chartState) : null;

    setIsTooltipActive(nextTooltipActive);
    setActiveIndex(nextIndex);
  }

  function handleChartClick(state: unknown) {
    if (!onBarClick) {
      return;
    }

    const chartState = state as WeeklyChartMouseState | undefined;
    const directIndex = getEventIndex(chartState);
    const resolvedIndex =
      directIndex !== null ? directIndex : isTooltipActive ? activeIndex : null;

    if (resolvedIndex === null) {
      return;
    }

    const point = getPointByIndex(resolvedIndex);
    if (point) {
      onBarClick(point);
    }
  }

  return (
    <div className="chart-card weekly-pnl-chart-card">
      <div className="chart-header">
        <div className="equity-curve-meta">
          <span>Weekly PnL (USD)</span>
          <span>{weeklySeries.length} weeks</span>
        </div>
      </div>
      <div className="equity-axis-captions" aria-hidden="true">
        <span>Weekly PnL (USD)</span>
        <span>{avgWeeklyPnl === null ? "--" : `Avg/Week: ${formatUsd(avgWeeklyPnl)}`}</span>
      </div>
      <div
        className="chart-body chart-wrapper weekly-pnl-chart-shell"
        style={
          typeof chartHeight === "number"
            ? { height: chartHeight, minHeight: chartHeight }
            : undefined
        }
      >
        <div className="chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={weeklySeries}
              margin={{ top: 20, right: 30, bottom: 20, left: 30 }}
              barCategoryGap={barCategoryGap}
              onMouseMove={handleChartMouseMove}
              onMouseLeave={() => {
                setIsTooltipActive(false);
                setActiveIndex(null);
              }}
              onClick={handleChartClick}
            >
              <CartesianGrid stroke="#d0d5dd" strokeDasharray="4 4" vertical={false} />
              <Legend
                verticalAlign="bottom"
                align="center"
                iconType="square"
                wrapperStyle={{ fontSize: "12px", color: "#667085" }}
              />
              <XAxis
                dataKey="start_date"
                tickFormatter={formatMonthDay}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={{ stroke: "#98a2b3" }}
                tickLine={{ stroke: "#98a2b3" }}
                minTickGap={16}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={yDomain}
                tickFormatter={formatUsd}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={80}
                tickMargin={8}
                tickCount={5}
              />
              <Tooltip
                cursor={{ fill: "rgba(11, 116, 222, 0.08)" }}
                content={<WeeklyTooltip formatUsd={formatUsd} />}
              />
              <ReferenceLine y={0} stroke="#98a2b3" strokeDasharray="4 4" />
              <Bar
                dataKey="total_pnl_usd"
                name="Weekly PnL"
                radius={[4, 4, 0, 0]}
                maxBarSize={80}
                isAnimationActive={false}
              >
                {weeklySeries.map((point) => (
                  <Cell
                    key={`${point.label}-${point.start_date}`}
                    fill={point.total_pnl_usd >= 0 ? GREEN_POS : RED_NEG}
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
