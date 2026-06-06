import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PnlSeriesPointResponse } from "../types/summary";
import { GREEN_POS, RED_NEG } from "../utils/colors";
import { formatDateLong, formatMonthDay, formatMonthDayNumericPadded } from "../utils/formatting";

interface EquityCurveDailyChartProps {
  dailySeries: PnlSeriesPointResponse[];
  rangeStart?: string;
  rangeEnd?: string;
  formatUsd: (value: number) => string;
  chartHeight?: number;
  onDayClick?: (point: PnlSeriesPointResponse) => void;
}

interface EquityCurveChartPoint {
  date: string;
  daily_pnl_usd: number;
  cumulative_pnl_usd: number;
  trade_count: number;
  source: PnlSeriesPointResponse;
}

interface EquityTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: EquityCurveChartPoint;
  }>;
  formatUsd: (value: number) => string;
}

interface EquityChartMouseState {
  isTooltipActive?: boolean;
  activeTooltipIndex?: number | string;
}

function buildChartData(dailySeries: PnlSeriesPointResponse[]): EquityCurveChartPoint[] {
  const sortedSeries = [...dailySeries].sort((left, right) =>
    left.start_date.localeCompare(right.start_date)
  );

  let runningTotal = 0;
  return sortedSeries.map((point) => {
    runningTotal += point.total_pnl_usd;

    return {
      date: point.start_date,
      daily_pnl_usd: point.total_pnl_usd,
      cumulative_pnl_usd: Number(runningTotal.toFixed(2)),
      trade_count: point.trade_count,
      source: point,
    };
  });
}

function EquityTooltip({ active, payload, formatUsd }: EquityTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  if (!point) {
    return null;
  }

  return (
    <div className="weekly-pnl-tooltip">
      <strong>{formatMonthDay(point.date)}</strong>
      <span>Daily PnL: {formatUsd(point.daily_pnl_usd)}</span>
      <span>Cumulative PnL: {formatUsd(point.cumulative_pnl_usd)}</span>
      <span>Trades: {point.trade_count}</span>
    </div>
  );
}

function getPaddedDomain(values: number[]): [number, number] {
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);

  if (minValue === maxValue) {
    const padding = Math.max(Math.abs(minValue) * 0.1, 50);
    return [minValue - padding, maxValue + padding];
  }

  const range = maxValue - minValue;
  const padding = Math.max(range * 0.1, 50);
  return [minValue - padding, maxValue + padding];
}

export function EquityCurveDailyChart({
  dailySeries,
  rangeStart,
  rangeEnd,
  formatUsd,
  chartHeight,
  onDayClick,
}: EquityCurveDailyChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [isTooltipActive, setIsTooltipActive] = useState(false);
  const chartData = buildChartData(dailySeries);
  const firstDate = chartData[0]?.date ?? "";
  const lastDate = chartData[chartData.length - 1]?.date ?? "";
  const latestValue = chartData[chartData.length - 1]?.cumulative_pnl_usd ?? 0;
  const displayRangeStart = rangeStart ?? firstDate;
  const displayRangeEnd = rangeEnd ?? lastDate;
  const cumulativeDomain = getPaddedDomain(chartData.map((point) => point.cumulative_pnl_usd));
  const dailyDomain = getPaddedDomain(chartData.map((point) => point.daily_pnl_usd));
  const desiredTickCount = 7;
  const visibleDateTicks = useMemo(() => {
    if (chartData.length <= desiredTickCount) {
      return chartData.map((point) => point.date);
    }

    const lastIndex = chartData.length - 1;
    const step = lastIndex / (desiredTickCount - 1);
    const tickIndices = new Set<number>([0, lastIndex]);

    for (let index = 1; index < desiredTickCount - 1; index += 1) {
      tickIndices.add(Math.round(index * step));
    }

    return [...tickIndices]
      .sort((left, right) => left - right)
      .map((index) => chartData[index]?.date)
      .filter((value): value is string => Boolean(value));
  }, [chartData]);

  function getEventIndex(state: EquityChartMouseState | undefined): number | null {
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
    const chartState = state as EquityChartMouseState | undefined;
    const nextTooltipActive = chartState?.isTooltipActive === true;
    const nextIndex = nextTooltipActive ? getEventIndex(chartState) : null;
    setIsTooltipActive(nextTooltipActive);
    setActiveIndex(nextIndex);
  }

  function handleChartClick(state: unknown) {
    if (!onDayClick) {
      return;
    }

    const chartState = state as EquityChartMouseState | undefined;
    const directIndex = getEventIndex(chartState);
    const resolvedIndex = directIndex !== null ? directIndex : isTooltipActive ? activeIndex : null;
    if (resolvedIndex === null) {
      return;
    }

    const point = chartData[resolvedIndex];
    if (point?.source) {
      onDayClick(point.source);
    }
  }

  return (
    <div className="chart-card equity-daily-chart-card">
      <div className="chart-header">
        <div className="equity-curve-meta">
          <span>Cumulative PnL (USD): {formatUsd(latestValue)}</span>
          <span>
            Range:{" "}
            {displayRangeStart ? formatDateLong(displayRangeStart) : "-"}
            {displayRangeEnd ? ` - ${formatDateLong(displayRangeEnd)}` : ""}
          </span>
        </div>
        <div className="equity-axis-captions" aria-hidden="true">
          <span>Daily PnL (USD)</span>
          <span>Cumulative PnL (USD)</span>
        </div>
      </div>
      <div
        className="chart-body chart-wrapper equity-daily-chart-shell"
        style={
          typeof chartHeight === "number"
            ? { height: chartHeight, minHeight: chartHeight }
            : undefined
        }
      >
        <div className="chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ top: 12, right: 16, bottom: 8, left: 8 }}
              onMouseMove={handleChartMouseMove}
              onMouseLeave={() => {
                setIsTooltipActive(false);
                setActiveIndex(null);
              }}
              onClick={handleChartClick}
            >
              <CartesianGrid stroke="#d0d5dd" strokeDasharray="4 4" vertical={false} />
              <Legend verticalAlign="bottom" align="center" wrapperStyle={{ fontSize: "12px" }} />
              <XAxis
                dataKey="date"
                tickFormatter={formatMonthDayNumericPadded}
                ticks={visibleDateTicks}
                interval={0}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={{ stroke: "#98a2b3" }}
                tickLine={{ stroke: "#98a2b3" }}
                minTickGap={22}
              />
              <YAxis
                yAxisId="daily"
                type="number"
                domain={dailyDomain}
                tickFormatter={formatUsd}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={72}
                tickMargin={8}
              />
              <YAxis
                yAxisId="cumulative"
                type="number"
                orientation="right"
                domain={cumulativeDomain}
                tickFormatter={formatUsd}
                tick={{ fill: "#667085", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={68}
                tickMargin={8}
              />
              <Tooltip
                cursor={{ stroke: "#98a2b3", strokeDasharray: "4 4" }}
                content={<EquityTooltip formatUsd={formatUsd} />}
              />
              <ReferenceLine yAxisId="daily" y={0} stroke="#98a2b3" strokeDasharray="4 4" />
              <Bar
                yAxisId="daily"
                dataKey="daily_pnl_usd"
                name="Daily PnL"
                maxBarSize={24}
                isAnimationActive={false}
              >
                {chartData.map((point) => (
                  <Cell
                    key={`daily-bar-${point.date}`}
                    fill={point.daily_pnl_usd >= 0 ? GREEN_POS : RED_NEG}
                  />
                ))}
              </Bar>
              <Line
                yAxisId="cumulative"
                type="monotone"
                dataKey="cumulative_pnl_usd"
                name="Cumulative PnL"
                stroke="#344054"
                strokeWidth={2}
                dot={{ r: 3, fill: "#344054" }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
