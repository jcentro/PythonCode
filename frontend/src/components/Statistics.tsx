import {
  FormEvent,
  MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getHoldTimeStats,
  getPnlSeries,
  getStatsInsights,
  getStatsSummary,
  getTrades,
  getTimeOfDayStats,
} from "../api/client";
import {
  HoldTimeResponse,
  PnlSeriesPointResponse,
  StatsInsightItem,
  StatsInsightsResponse,
  StatsPatternItem,
  StatsSummaryResponse,
  TimeOfDayResponse,
} from "../types/summary";
import { TradeListFilters, TradeResponse } from "../types/trade";
import {
  formatDateLong,
  formatDateRange,
  formatMonthDay,
  formatPercentFromRate,
  formatPercentValue,
  formatSignedUsd,
  formatUsd,
} from "../utils/formatting";
import {
  buildDailyRecentSeries,
  buildDailyYtdSeries,
  buildWeeklyRecentSeries,
  buildWeeklyYtdSeries,
} from "../utils/timeSeries";
import { EmptyState } from "./EmptyState";
import { EquityCurveDailyChart } from "./EquityCurveDailyChart";
import { SetupDistributionChart, SetupDistributionChartRow } from "./SetupDistributionChart";
import { SetupPerformanceChart, SetupPerformanceChartRow } from "./SetupPerformanceChart";
import { TickerPerformanceChart, TickerPerformanceChartRow } from "./TickerPerformanceChart";
import { WeeklyPnLChart } from "./WeeklyPnLChart";
import "./Statistics.css";

interface StatisticsProps {
  hideTitle?: boolean;
  onViewTradesFromInsight?: (filters: TradeListFilters) => void;
}

type RangePreset = "custom" | "wtd" | "ytd";
type ComparePreset = "week" | "month" | "ytd";

const WEEKLY_RECENT_LIMIT = 13;
const DAILY_RECENT_LIMIT = 30;
type WeeklyChartMode = "recent_13w" | "ytd_all";
type DailyChartMode = "recent_30d" | "ytd_all";

interface CompareWindow {
  label: string;
  start: string;
  end: string;
}

interface CompareRanges {
  primary: CompareWindow;
  comparison: CompareWindow;
}

interface DataQualityRow {
  key: string;
  label: string;
  description: string;
  count: number;
}

interface ModalPosition {
  x: number;
  y: number;
}

const WEEKLY_MODAL_POSITION_STORAGE_KEY = "weeklyPnlModalPosition";
const EQUITY_MODAL_POSITION_STORAGE_KEY = "equityCurveModalPosition";
const SETUP_MODAL_POSITION_STORAGE_KEY = "setupChartModalPosition";
const MODAL_VIEWPORT_PADDING = 8;
const MODAL_SNAP_THRESHOLD = 40;

function clampModalPosition(x: number, y: number, width: number, height: number): ModalPosition {
  const maxX = Math.max(MODAL_VIEWPORT_PADDING, window.innerWidth - width - MODAL_VIEWPORT_PADDING);
  const maxY = Math.max(
    MODAL_VIEWPORT_PADDING,
    window.innerHeight - height - MODAL_VIEWPORT_PADDING,
  );

  return {
    x: Math.min(Math.max(x, MODAL_VIEWPORT_PADDING), maxX),
    y: Math.min(Math.max(y, MODAL_VIEWPORT_PADDING), maxY),
  };
}

function getCenteredModalPosition(width: number, height: number): ModalPosition {
  return clampModalPosition(
    (window.innerWidth - width) / 2,
    (window.innerHeight - height) / 2,
    width,
    height,
  );
}

function getSnappedModalPosition(
  position: ModalPosition,
  width: number,
  height: number,
): ModalPosition {
  const clamped = clampModalPosition(position.x, position.y, width, height);
  const rightAnchor = Math.max(
    MODAL_VIEWPORT_PADDING,
    window.innerWidth - width - MODAL_VIEWPORT_PADDING,
  );

  let nextX = clamped.x;
  let nextY = clamped.y;
  let didHorizontalSnap = false;

  if (Math.abs(clamped.x - MODAL_VIEWPORT_PADDING) <= MODAL_SNAP_THRESHOLD) {
    nextX = MODAL_VIEWPORT_PADDING;
    didHorizontalSnap = true;
  } else if (Math.abs(clamped.x - rightAnchor) <= MODAL_SNAP_THRESHOLD) {
    nextX = rightAnchor;
    didHorizontalSnap = true;
  }

  if (!didHorizontalSnap && Math.abs(clamped.y - MODAL_VIEWPORT_PADDING) <= MODAL_SNAP_THRESHOLD) {
    nextY = MODAL_VIEWPORT_PADDING;
  }

  return clampModalPosition(nextX, nextY, width, height);
}

function loadSavedModalPosition(storageKey: string): ModalPosition | null {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<ModalPosition>;
    if (typeof parsed.x !== "number" || typeof parsed.y !== "number") {
      return null;
    }
    return { x: parsed.x, y: parsed.y };
  } catch {
    return null;
  }
}

function saveModalPosition(storageKey: string, position: ModalPosition) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(position));
  } catch {
    // Ignore localStorage failures.
  }
}

function clearSavedModalPosition(storageKey: string) {
  try {
    window.localStorage.removeItem(storageKey);
  } catch {
    // Ignore localStorage failures.
  }
}

function useDraggableModal(isOpen: boolean, storageKey: string) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  const dragOffsetRef = useRef({ dx: 0, dy: 0 });
  const [position, setPosition] = useState<ModalPosition | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let animationFrameId = 0;
    animationFrameId = window.requestAnimationFrame(() => {
      const modalElement = modalRef.current;
      if (!modalElement) {
        return;
      }

      const rect = modalElement.getBoundingClientRect();
      const savedPosition = loadSavedModalPosition(storageKey);
      const nextPosition = savedPosition
        ? clampModalPosition(savedPosition.x, savedPosition.y, rect.width, rect.height)
        : getCenteredModalPosition(rect.width, rect.height);
      setPosition(nextPosition);
      modalElement.focus();
    });

    return () => window.cancelAnimationFrame(animationFrameId);
  }, [isOpen, storageKey]);

  useEffect(() => {
    if (!isOpen || !isDragging) {
      return;
    }

    const previousUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = "none";

    const handleMouseMove = (event: MouseEvent) => {
      const modalElement = modalRef.current;
      if (!modalElement) {
        return;
      }

      const rect = modalElement.getBoundingClientRect();
      const nextX = event.clientX - dragOffsetRef.current.dx;
      const nextY = event.clientY - dragOffsetRef.current.dy;
      setPosition(clampModalPosition(nextX, nextY, rect.width, rect.height));
    };

    const handleMouseUp = () => {
      const modalElement = modalRef.current;
      setIsDragging(false);
      document.body.style.userSelect = previousUserSelect;

      if (!modalElement) {
        return;
      }

      const rect = modalElement.getBoundingClientRect();
      setPosition((previous) => {
        if (!previous) {
          return previous;
        }
        const snapped = getSnappedModalPosition(previous, rect.width, rect.height);
        saveModalPosition(storageKey, snapped);
        return snapped;
      });
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, isOpen, storageKey]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleResize = () => {
      const modalElement = modalRef.current;
      if (!modalElement) {
        return;
      }

      const rect = modalElement.getBoundingClientRect();
      setPosition((previous) => {
        if (!previous) {
          return previous;
        }
        return clampModalPosition(previous.x, previous.y, rect.width, rect.height);
      });
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [isOpen]);

  const handleHeaderMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!isOpen || event.button !== 0) {
        return;
      }

      const modalElement = modalRef.current;
      if (!modalElement) {
        return;
      }

      const rect = modalElement.getBoundingClientRect();
      const currentPosition = position ?? { x: rect.left, y: rect.top };
      const clampedPosition = clampModalPosition(
        currentPosition.x,
        currentPosition.y,
        rect.width,
        rect.height,
      );

      setPosition(clampedPosition);
      dragOffsetRef.current = {
        dx: event.clientX - clampedPosition.x,
        dy: event.clientY - clampedPosition.y,
      };
      setIsDragging(true);
      event.preventDefault();
    },
    [isOpen, position],
  );

  const handleHeaderDoubleClick = useCallback(() => {
    if (!isOpen) {
      return;
    }

    const modalElement = modalRef.current;
    if (!modalElement) {
      return;
    }

    const rect = modalElement.getBoundingClientRect();
    setIsDragging(false);
    setPosition(getCenteredModalPosition(rect.width, rect.height));
    clearSavedModalPosition(storageKey);
  }, [isOpen, storageKey]);

  const resetModalState = useCallback(() => {
    setIsDragging(false);
    setPosition(null);
  }, []);

  const modalStyle = position
    ? ({ left: position.x, top: position.y } as const)
    : ({ left: "50%", top: "50%", transform: "translate(-50%, -50%)" } as const);

  return {
    modalRef,
    modalStyle,
    isDragging,
    handleHeaderMouseDown,
    handleHeaderDoubleClick,
    resetModalState,
  };
}

function toLocalDateString(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getWeekToDateRange(): { start: string; end: string } {
  const today = new Date();
  const monday = new Date(today);
  const day = today.getDay();
  const daysFromMonday = (day + 6) % 7;
  monday.setDate(today.getDate() - daysFromMonday);

  return {
    start: toLocalDateString(monday),
    end: toLocalDateString(today),
  };
}

function getYearToDateRange(): { start: string; end: string } {
  const today = new Date();
  const start = new Date(today.getFullYear(), 0, 1);

  return {
    start: toLocalDateString(start),
    end: toLocalDateString(today),
  };
}

function getDaysInMonth(year: number, monthIndex: number): number {
  return new Date(year, monthIndex + 1, 0).getDate();
}

function createClampedDate(year: number, monthIndex: number, day: number): Date {
  return new Date(year, monthIndex, Math.min(day, getDaysInMonth(year, monthIndex)));
}

function getCompareRanges(preset: ComparePreset): CompareRanges {
  const today = new Date();

  if (preset === "week") {
    const currentWeekStart = new Date(today);
    const currentDay = today.getDay();
    const daysFromMonday = (currentDay + 6) % 7;
    currentWeekStart.setDate(today.getDate() - daysFromMonday);

    const previousWeekStart = new Date(currentWeekStart);
    previousWeekStart.setDate(currentWeekStart.getDate() - 7);

    const elapsedDays = Math.max(
      0,
      Math.floor((today.getTime() - currentWeekStart.getTime()) / (1000 * 60 * 60 * 24)),
    );
    const previousWeekEnd = new Date(previousWeekStart);
    previousWeekEnd.setDate(previousWeekStart.getDate() + elapsedDays);

    return {
      primary: {
        label: "This week",
        start: toLocalDateString(currentWeekStart),
        end: toLocalDateString(today),
      },
      comparison: {
        label: "Last week",
        start: toLocalDateString(previousWeekStart),
        end: toLocalDateString(previousWeekEnd),
      },
    };
  }

  if (preset === "month") {
    const currentMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);
    const previousMonthYear =
      today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();
    const previousMonthIndex = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
    const previousMonthStart = new Date(previousMonthYear, previousMonthIndex, 1);
    const previousMonthEnd = createClampedDate(
      previousMonthYear,
      previousMonthIndex,
      today.getDate(),
    );

    return {
      primary: {
        label: "This month",
        start: toLocalDateString(currentMonthStart),
        end: toLocalDateString(today),
      },
      comparison: {
        label: "Last month",
        start: toLocalDateString(previousMonthStart),
        end: toLocalDateString(previousMonthEnd),
      },
    };
  }

  const previousYear = today.getFullYear() - 1;
  const previousYtdEnd = createClampedDate(previousYear, today.getMonth(), today.getDate());
  return {
    primary: {
      label: "YTD",
      start: toLocalDateString(new Date(today.getFullYear(), 0, 1)),
      end: toLocalDateString(today),
    },
    comparison: {
      label: "Last YTD",
      start: toLocalDateString(new Date(previousYear, 0, 1)),
      end: toLocalDateString(previousYtdEnd),
    },
  };
}

export function Statistics({ hideTitle = false, onViewTradesFromInsight }: StatisticsProps) {
  const CHART_HEIGHT = 320;
  const [rangePreset, setRangePreset] = useState<RangePreset>("custom");
  const [isCompareMode, setIsCompareMode] = useState(false);
  const [comparePreset, setComparePreset] = useState<ComparePreset>("week");
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [appliedStart, setAppliedStart] = useState<string | undefined>(undefined);
  const [appliedEnd, setAppliedEnd] = useState<string | undefined>(undefined);
  const [summary, setSummary] = useState<StatsSummaryResponse | null>(null);
  const [insights, setInsights] = useState<StatsInsightsResponse | null>(null);
  const [comparePrimaryInsights, setComparePrimaryInsights] =
    useState<StatsInsightsResponse | null>(null);
  const [compareComparisonInsights, setCompareComparisonInsights] =
    useState<StatsInsightsResponse | null>(null);
  const [dailyPnlSeries, setDailyPnlSeries] = useState<PnlSeriesPointResponse[]>([]);
  const [weeklyPnlSeries, setWeeklyPnlSeries] = useState<PnlSeriesPointResponse[]>([]);
  const [statsRangeTrades, setStatsRangeTrades] = useState<TradeResponse[]>([]);
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDayResponse | null>(null);
  const [holdTime, setHoldTime] = useState<HoldTimeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCompareLoading, setIsCompareLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [compareErrorMessage, setCompareErrorMessage] = useState<string | null>(null);
  const [weeklyChartMode, setWeeklyChartMode] = useState<WeeklyChartMode>("recent_13w");
  const [dailyChartMode, setDailyChartMode] = useState<DailyChartMode>("recent_30d");
  const [selectedWeek, setSelectedWeek] = useState<PnlSeriesPointResponse | null>(null);
  const [selectedWeekTrades, setSelectedWeekTrades] = useState<TradeResponse[]>([]);
  const [isSelectedWeekTradesLoading, setIsSelectedWeekTradesLoading] = useState(false);
  const [selectedWeekTradesError, setSelectedWeekTradesError] = useState<string | null>(null);
  const [selectedEquityDay, setSelectedEquityDay] = useState<PnlSeriesPointResponse | null>(null);
  const [selectedEquityTrades, setSelectedEquityTrades] = useState<TradeResponse[]>([]);
  const [isSelectedEquityTradesLoading, setIsSelectedEquityTradesLoading] = useState(false);
  const [selectedEquityTradesError, setSelectedEquityTradesError] = useState<string | null>(null);
  const [selectedSetupRow, setSelectedSetupRow] = useState<{
    setupId: number | null;
    setupName: string;
  } | null>(null);
  const [selectedTickerRow, setSelectedTickerRow] = useState<{
    ticker: string;
  } | null>(null);
  const selectedWeekRequestIdRef = useRef(0);
  const selectedEquityRequestIdRef = useRef(0);

  const weeklyModal = useDraggableModal(Boolean(selectedWeek), WEEKLY_MODAL_POSITION_STORAGE_KEY);
  const equityModal = useDraggableModal(
    Boolean(selectedEquityDay),
    EQUITY_MODAL_POSITION_STORAGE_KEY,
  );
  const setupModal = useDraggableModal(
    Boolean(selectedSetupRow || selectedTickerRow),
    SETUP_MODAL_POSITION_STORAGE_KEY,
  );

  useEffect(() => {
    async function loadStats() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const [
          summaryResponse,
          dailySeriesResponse,
          weeklySeriesResponse,
          insightsResponse,
          timeOfDayResponse,
          holdTimeResponse,
        ] = await Promise.all([
          getStatsSummary(appliedStart, appliedEnd),
          getPnlSeries("daily", appliedStart, appliedEnd),
          getPnlSeries("weekly", appliedStart, appliedEnd),
          getStatsInsights(appliedStart, appliedEnd),
          getTimeOfDayStats(appliedStart, appliedEnd),
          getHoldTimeStats(appliedStart, appliedEnd),
        ]);
        setSummary(summaryResponse);
        setDailyPnlSeries(dailySeriesResponse.series);
        setWeeklyPnlSeries(weeklySeriesResponse.series);
        setInsights(insightsResponse);
        setTimeOfDay(timeOfDayResponse);
        setHoldTime(holdTimeResponse);
        try {
          const rangeTrades = await getTrades({
            start: insightsResponse.range.start,
            end: insightsResponse.range.end,
            include_fills: true,
          });
          setStatsRangeTrades(rangeTrades);
        } catch {
          setStatsRangeTrades([]);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load statistics.";
        setErrorMessage(message);
        setSummary(null);
        setInsights(null);
        setDailyPnlSeries([]);
        setWeeklyPnlSeries([]);
        setStatsRangeTrades([]);
        setTimeOfDay(null);
        setHoldTime(null);
      } finally {
        setIsLoading(false);
      }
    }

    void loadStats();
  }, [appliedStart, appliedEnd]);

  const compareRanges = useMemo(
    () => (isCompareMode ? getCompareRanges(comparePreset) : null),
    [comparePreset, isCompareMode],
  );

  useEffect(() => {
    async function loadCompareStats() {
      if (!isCompareMode || !compareRanges) {
        setComparePrimaryInsights(null);
        setCompareComparisonInsights(null);
        setCompareErrorMessage(null);
        return;
      }

      setIsCompareLoading(true);
      setCompareErrorMessage(null);
      try {
        const [primaryResponse, comparisonResponse] = await Promise.all([
          getStatsInsights(compareRanges.primary.start, compareRanges.primary.end),
          getStatsInsights(compareRanges.comparison.start, compareRanges.comparison.end),
        ]);
        setComparePrimaryInsights(primaryResponse);
        setCompareComparisonInsights(comparisonResponse);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load comparison data.";
        setComparePrimaryInsights(null);
        setCompareComparisonInsights(null);
        setCompareErrorMessage(message);
      } finally {
        setIsCompareLoading(false);
      }
    }

    void loadCompareStats();
  }, [compareRanges, isCompareMode]);

  useEffect(() => {
    if (!selectedWeek && !selectedEquityDay && !selectedSetupRow && !selectedTickerRow) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      if (selectedTickerRow) {
        setupModal.resetModalState();
        setSelectedTickerRow(null);
        return;
      }
      if (selectedSetupRow) {
        setupModal.resetModalState();
        setSelectedSetupRow(null);
        return;
      }
      if (selectedEquityDay) {
        selectedEquityRequestIdRef.current += 1;
        equityModal.resetModalState();
        setSelectedEquityDay(null);
        setSelectedEquityTrades([]);
        setSelectedEquityTradesError(null);
        setIsSelectedEquityTradesLoading(false);
        return;
      }
      if (selectedWeek) {
        selectedWeekRequestIdRef.current += 1;
        weeklyModal.resetModalState();
        setSelectedWeek(null);
        setSelectedWeekTrades([]);
        setSelectedWeekTradesError(null);
        setIsSelectedWeekTradesLoading(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    equityModal,
    selectedEquityDay,
    selectedSetupRow,
    selectedTickerRow,
    selectedWeek,
    setupModal,
    weeklyModal,
  ]);

  function handleApply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedStart(draftStart || undefined);
    setAppliedEnd(draftEnd || undefined);
  }

  function handleRangePresetChange(nextPreset: RangePreset) {
    setRangePreset(nextPreset);

    if (nextPreset === "wtd") {
      const range = getWeekToDateRange();
      setDraftStart(range.start);
      setDraftEnd(range.end);
      setAppliedStart(range.start);
      setAppliedEnd(range.end);
      return;
    }

    if (nextPreset === "ytd") {
      const range = getYearToDateRange();
      setDraftStart(range.start);
      setDraftEnd(range.end);
      setAppliedStart(range.start);
      setAppliedEnd(range.end);
      return;
    }
  }

  function closeSelectedWeekModal() {
    selectedWeekRequestIdRef.current += 1;
    weeklyModal.resetModalState();
    setSelectedWeek(null);
    setSelectedWeekTrades([]);
    setSelectedWeekTradesError(null);
    setIsSelectedWeekTradesLoading(false);
  }

  function closeSelectedEquityModal() {
    selectedEquityRequestIdRef.current += 1;
    equityModal.resetModalState();
    setSelectedEquityDay(null);
    setSelectedEquityTrades([]);
    setSelectedEquityTradesError(null);
    setIsSelectedEquityTradesLoading(false);
  }

  function closeSelectedSetupModal() {
    setupModal.resetModalState();
    setSelectedSetupRow(null);
  }

  function closeSelectedTickerModal() {
    setupModal.resetModalState();
    setSelectedTickerRow(null);
  }

  function closeSelectedSetupDrilldownModal() {
    setupModal.resetModalState();
    setSelectedSetupRow(null);
    setSelectedTickerRow(null);
  }

  async function handleWeeklyBarClick(point: PnlSeriesPointResponse) {
    if (point.trade_count <= 0) {
      return;
    }
    closeSelectedEquityModal();
    setSelectedWeek(point);
    setSelectedWeekTrades([]);
    setSelectedWeekTradesError(null);
    setIsSelectedWeekTradesLoading(true);

    const requestId = selectedWeekRequestIdRef.current + 1;
    selectedWeekRequestIdRef.current = requestId;
    const filterStart =
      appliedStart && appliedStart > point.start_date ? appliedStart : point.start_date;
    const filterEnd = appliedEnd && appliedEnd < point.end_date ? appliedEnd : point.end_date;

    try {
      const trades = await getTrades({
        start: filterStart,
        end: filterEnd,
      });

      if (selectedWeekRequestIdRef.current !== requestId) {
        return;
      }
      setSelectedWeekTrades(trades);
    } catch (error) {
      if (selectedWeekRequestIdRef.current !== requestId) {
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load trades for selected week.";
      setSelectedWeekTradesError(message);
      setSelectedWeekTrades([]);
    } finally {
      if (selectedWeekRequestIdRef.current === requestId) {
        setIsSelectedWeekTradesLoading(false);
      }
    }
  }

  async function handleEquityDayClick(point: PnlSeriesPointResponse) {
    if (point.trade_count <= 0) {
      return;
    }
    closeSelectedWeekModal();
    setSelectedEquityDay(point);
    setSelectedEquityTrades([]);
    setSelectedEquityTradesError(null);
    setIsSelectedEquityTradesLoading(true);

    const requestId = selectedEquityRequestIdRef.current + 1;
    selectedEquityRequestIdRef.current = requestId;
    const filterStart =
      appliedStart && appliedStart > point.start_date ? appliedStart : point.start_date;
    const filterEnd = appliedEnd && appliedEnd < point.end_date ? appliedEnd : point.end_date;

    try {
      const trades = await getTrades({
        start: filterStart,
        end: filterEnd,
      });

      if (selectedEquityRequestIdRef.current !== requestId) {
        return;
      }
      setSelectedEquityTrades(trades);
    } catch (error) {
      if (selectedEquityRequestIdRef.current !== requestId) {
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load trades for selected date.";
      setSelectedEquityTradesError(message);
      setSelectedEquityTrades([]);
    } finally {
      if (selectedEquityRequestIdRef.current === requestId) {
        setIsSelectedEquityTradesLoading(false);
      }
    }
  }

  const emotionRows = useMemo(() => {
    if (!insights) {
      return [];
    }

    return [...insights.by_emotion].sort(
      (left, right) =>
        right.count - left.count ||
        Math.abs(right.total_pnl_usd) - Math.abs(left.total_pnl_usd) ||
        left.emotion_name.localeCompare(right.emotion_name),
    );
  }, [insights]);

  const worstEmotion = useMemo(() => {
    if (!insights || insights.by_emotion.length === 0) {
      return null;
    }

    return insights.by_emotion.reduce((worst, current) =>
      current.total_pnl_usd < worst.total_pnl_usd ? current : worst,
    );
  }, [insights]);

  const topInsights = useMemo(() => {
    if (!insights) {
      return [];
    }
    return insights.insights.slice(0, 6);
  }, [insights]);

  const topPatterns = useMemo(() => {
    if (!insights) {
      return [];
    }
    return insights.patterns.slice(0, 4);
  }, [insights]);

  const weeklyRecentSeries = useMemo(
    () => buildWeeklyRecentSeries(weeklyPnlSeries, WEEKLY_RECENT_LIMIT),
    [weeklyPnlSeries],
  );
  const weeklyYtdSeries = useMemo(() => buildWeeklyYtdSeries(weeklyPnlSeries), [weeklyPnlSeries]);
  const displayedWeeklySeries =
    weeklyChartMode === "recent_13w" ? weeklyRecentSeries : weeklyYtdSeries;

  const dailyRecentSeries = useMemo(
    () => buildDailyRecentSeries(dailyPnlSeries, DAILY_RECENT_LIMIT),
    [dailyPnlSeries],
  );
  const dailyYtdSeries = useMemo(() => buildDailyYtdSeries(dailyPnlSeries), [dailyPnlSeries]);
  const displayedDailySeries = dailyChartMode === "recent_30d" ? dailyRecentSeries : dailyYtdSeries;

  const displayedDailyRangeStart = displayedDailySeries[0]?.start_date;
  const displayedDailyRangeEnd = displayedDailySeries[displayedDailySeries.length - 1]?.end_date;
  const isChartDrilldownEnabled =
    weeklyChartMode === "recent_13w" && dailyChartMode === "recent_30d";
  const setupDistributionRows = useMemo(() => {
    if (!summary) {
      return [];
    }

    const bySetupRows: SetupDistributionChartRow[] = summary.by_setup
      .filter((row) => row.count > 0)
      .map((row) => ({
        setupId: row.setup_id ?? null,
        setupName: row.setup_name || "UNCLASSIFIED",
        tradeCount: row.count,
      }));
    const classifiedCount = bySetupRows.reduce((sum, row) => sum + row.tradeCount, 0);
    const unclassifiedCount = Math.max(0, summary.total_trades - classifiedCount);
    if (unclassifiedCount > 0) {
      bySetupRows.push({
        setupId: null,
        setupName: "UNCLASSIFIED",
        tradeCount: unclassifiedCount,
      });
    }

    return bySetupRows.sort(
      (left, right) =>
        right.tradeCount - left.tradeCount || left.setupName.localeCompare(right.setupName),
    );
  }, [summary]);
  const setupPerformanceRows = useMemo(() => {
    if (!summary) {
      return [];
    }

    const bySetupRows: SetupPerformanceChartRow[] = summary.by_setup
      .filter((row) => row.count > 0)
      .map((row) => ({
        setupId: row.setup_id ?? null,
        setupName: row.setup_name || "UNCLASSIFIED",
        tradeCount: row.count,
        totalPnlUsd: row.total_pnl_usd,
      }));

    const classifiedCount = bySetupRows.reduce((sum, row) => sum + row.tradeCount, 0);
    const classifiedPnl = bySetupRows.reduce((sum, row) => sum + row.totalPnlUsd, 0);
    const unclassifiedCount = Math.max(0, summary.total_trades - classifiedCount);
    const unclassifiedPnl = summary.total_pnl_usd - classifiedPnl;

    if (unclassifiedCount > 0) {
      bySetupRows.push({
        setupId: null,
        setupName: "UNCLASSIFIED",
        tradeCount: unclassifiedCount,
        totalPnlUsd: unclassifiedPnl,
      });
    }

    return bySetupRows.sort(
      (left, right) =>
        right.totalPnlUsd - left.totalPnlUsd || left.setupName.localeCompare(right.setupName),
    );
  }, [summary]);
  const tickerPerformanceRows = useMemo(() => {
    if (statsRangeTrades.length === 0) {
      return [];
    }

    const groupedByTicker = new Map<string, TickerPerformanceChartRow>();

    for (const trade of statsRangeTrades) {
      const normalizedTicker = trade.ticker?.trim().toUpperCase() || "UNKNOWN";
      const current = groupedByTicker.get(normalizedTicker);
      if (current) {
        current.tradeCount += 1;
        current.totalPnlUsd += trade.total_pnl_usd;
      } else {
        groupedByTicker.set(normalizedTicker, {
          ticker: normalizedTicker,
          tradeCount: 1,
          totalPnlUsd: trade.total_pnl_usd,
        });
      }
    }

    return [...groupedByTicker.values()].sort(
      (left, right) =>
        right.totalPnlUsd - left.totalPnlUsd || left.ticker.localeCompare(right.ticker),
    );
  }, [statsRangeTrades]);
  const selectedTickerTrades = useMemo(() => {
    if (!selectedTickerRow) {
      return [];
    }

    return statsRangeTrades.filter((trade) => {
      const normalizedTicker = trade.ticker?.trim().toUpperCase() || "UNKNOWN";
      return normalizedTicker === selectedTickerRow.ticker;
    });
  }, [selectedTickerRow, statsRangeTrades]);
  const selectedSetupTrades = useMemo(() => {
    if (!selectedSetupRow) {
      return [];
    }

    return statsRangeTrades.filter((trade) => {
      const tradeSetupId =
        typeof trade.setup_id === "number"
          ? trade.setup_id
          : trade.setup_id === null || trade.setup_id === undefined
            ? null
            : null;

      if (selectedSetupRow.setupId === null) {
        return tradeSetupId === null;
      }

      return tradeSetupId === selectedSetupRow.setupId;
    });
  }, [selectedSetupRow, statsRangeTrades]);
  const selectedSetupTotalPnl = useMemo(
    () => selectedSetupTrades.reduce((sum, trade) => sum + trade.total_pnl_usd, 0),
    [selectedSetupTrades],
  );
  const selectedTickerTotalPnl = useMemo(
    () => selectedTickerTrades.reduce((sum, trade) => sum + trade.total_pnl_usd, 0),
    [selectedTickerTrades],
  );
  const selectedSetupRangeText = useMemo(() => {
    if (insights) {
      return formatDateRange(insights.range.start, insights.range.end);
    }
    return "Selected range";
  }, [insights]);
  const selectedSetupModalTrades = selectedSetupRow ? selectedSetupTrades : selectedTickerTrades;
  const selectedSetupModalTotalPnl = selectedSetupRow
    ? selectedSetupTotalPnl
    : selectedTickerTotalPnl;
  const selectedSetupModalTitle = selectedSetupRow
    ? `Trades for Setup: ${selectedSetupRow.setupName}`
    : selectedTickerRow
      ? `Trades for Ticker: ${selectedTickerRow.ticker}`
      : "";
  const selectedSetupModalEmptyMessage = selectedSetupRow
    ? "No trades for this setup."
    : "No trades for this ticker.";
  const dataQualityRows = useMemo<DataQualityRow[]>(() => {
    if (statsRangeTrades.length === 0) {
      return [];
    }

    return [
      {
        key: "missing_setup",
        label: "Trades missing setup",
        description: "These trades may weaken setup-based analytics.",
        count: statsRangeTrades.filter(
          (trade) => trade.setup_id === null || trade.setup_id === undefined,
        ).length,
      },
      {
        key: "missing_emotion",
        label: "Trades missing emotion",
        description: "These trades may weaken emotion-based analytics.",
        count: statsRangeTrades.filter(
          (trade) => trade.emotion_id === null || trade.emotion_id === undefined,
        ).length,
      },
      {
        key: "unknown_rule",
        label: "Trades with unknown rule status",
        description: "These trades are excluded from rule-followed analysis.",
        count: statsRangeTrades.filter(
          (trade) => trade.rule_followed === null || trade.rule_followed === undefined,
        ).length,
      },
      {
        key: "zero_pnl",
        label: "Zero-PnL trades",
        description: "Review whether these are true breakeven trades.",
        count: statsRangeTrades.filter((trade) => trade.total_pnl_usd === 0).length,
      },
      {
        key: "scaled_missing_fills",
        label: "Scaled trades missing fills",
        description: "Scaled trades should include fill rows.",
        count: statsRangeTrades.filter(
          (trade) =>
            (trade.use_fills === true || trade.source === "tos_csv") &&
            (trade.fills?.length ?? 0) === 0,
        ).length,
      },
    ];
  }, [statsRangeTrades]);
  const hasDataQualityIssues = useMemo(
    () => dataQualityRows.some((row) => row.count > 0),
    [dataQualityRows],
  );

  const timeOfDayRows = useMemo(() => {
    if (!timeOfDay) {
      return [];
    }
    return [...timeOfDay.buckets].sort((left, right) => left.start_minute - right.start_minute);
  }, [timeOfDay]);

  const holdTimeRows = useMemo(() => {
    if (!holdTime) {
      return [];
    }
    return [...holdTime.buckets].sort(
      (left, right) =>
        left.min_seconds - right.min_seconds ||
        (left.max_seconds ?? Number.MAX_SAFE_INTEGER) -
          (right.max_seconds ?? Number.MAX_SAFE_INTEGER),
    );
  }, [holdTime]);

  function formatRateAsPercent(rate: number): string {
    return formatPercentFromRate(rate);
  }

  function formatRateDelta(rate: number): string {
    const percentPoints = rate * 100;
    return `${percentPoints >= 0 ? "+" : "-"}${Math.abs(percentPoints).toFixed(2)} pp`;
  }

  function formatSummaryPercent(percentValue: number): string {
    return formatPercentValue(percentValue);
  }

  function formatCountDelta(value: number): string {
    return `${value >= 0 ? "+" : ""}${value}`;
  }

  function formatRuleFollowedValue(value: boolean | null): string {
    if (value === true) {
      return "Yes";
    }
    if (value === false) {
      return "No";
    }
    return "—";
  }

  function formatDateWithYear(value: string): string {
    return formatDateLong(value);
  }

  function formatRangeLabel(label: string): string {
    return label.replace("-", "–");
  }

  function formatCurrentStreak(): string {
    if (!insights || insights.streaks.current_streak_type === "none") {
      return "None";
    }
    const label = insights.streaks.current_streak_type === "win" ? "Win" : "Loss";
    return `${label} x${insights.streaks.current_streak_length}`;
  }

  function formatDrawdownRange(): string {
    if (!insights) {
      return "-";
    }
    const start = insights.risk.max_drawdown_start;
    const end = insights.risk.max_drawdown_end;
    if (!start && !end) {
      return "-";
    }
    if (start && end) {
      return `${start} to ${end}`;
    }
    return start ?? end ?? "-";
  }

  function handleSetupBarClick(row: SetupDistributionChartRow | SetupPerformanceChartRow) {
    if (!isChartDrilldownEnabled || row.tradeCount <= 0) {
      return;
    }
    closeSelectedWeekModal();
    closeSelectedEquityModal();
    closeSelectedTickerModal();
    setSelectedSetupRow({
      setupId: row.setupId ?? null,
      setupName: row.setupName,
    });
  }

  function handleTickerBarClick(row: TickerPerformanceChartRow) {
    if (!isChartDrilldownEnabled || row.tradeCount <= 0) {
      return;
    }
    closeSelectedWeekModal();
    closeSelectedEquityModal();
    closeSelectedSetupModal();
    setSelectedTickerRow({
      ticker: row.ticker,
    });
  }

  function renderInsightMessage(message: string) {
    const parts = message.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, index) =>
      index % 2 === 1 ? <strong key={`insight-bold-${index}`}>{part}</strong> : part,
    );
  }

  function getInsightTradeFilters(item: StatsInsightItem): TradeListFilters | null {
    const baseFilters: TradeListFilters = {
      start: appliedStart,
      end: appliedEnd,
    };

    if (item.type === "rule_adherence" && item.severity === "warning") {
      return { ...baseFilters, rule_followed: "false" };
    }

    if (item.type === "emotion") {
      const emotionId = item.data?.emotion_id;
      if (typeof emotionId === "number") {
        return { ...baseFilters, emotion_id: emotionId };
      }
    }

    if (item.type === "expectancy" && item.severity === "warning") {
      return { ...baseFilters, outcome: "loss" };
    }

    return null;
  }

  function getPatternTradeFilters(item: StatsPatternItem): TradeListFilters {
    const baseFilters: TradeListFilters = {
      start: appliedStart,
      end: appliedEnd,
    };
    const nextFilters: TradeListFilters = { ...baseFilters };

    if (typeof item.filters.entry_time_start_minute === "number") {
      nextFilters.entry_time_start_minute = item.filters.entry_time_start_minute;
    }
    if (typeof item.filters.entry_time_end_minute === "number") {
      nextFilters.entry_time_end_minute = item.filters.entry_time_end_minute;
    }
    if (typeof item.filters.hold_time_min_seconds === "number") {
      nextFilters.hold_time_min_seconds = item.filters.hold_time_min_seconds;
    }
    if (typeof item.filters.hold_time_max_seconds === "number") {
      nextFilters.hold_time_max_seconds = item.filters.hold_time_max_seconds;
    }
    if (item.filters.pattern === "after_2_losses_next_trade") {
      nextFilters.pattern = "after_2_losses_next_trade";
    }
    if (item.filters.pattern === "trade_index_after_3") {
      nextFilters.trade_index_bucket = "after_3";
    }

    return nextFilters;
  }

  function renderCompareMetricCard(
    title: string,
    primaryValue: string,
    comparisonValue: string,
    deltaValue: string,
    deltaNumber: number,
  ) {
    return (
      <article className="statistics-compare-card">
        <h4>{title}</h4>
        <div className="statistics-compare-values">
          <div>
            <span>Primary</span>
            <strong>{primaryValue}</strong>
          </div>
          <div>
            <span>Comparison</span>
            <strong>{comparisonValue}</strong>
          </div>
        </div>
        <p
          className={`statistics-compare-delta ${
            deltaNumber > 0 ? "positive" : deltaNumber < 0 ? "negative" : "neutral"
          }`}
        >
          Delta: {deltaValue}
        </p>
      </article>
    );
  }

  return (
    <section className="statistics-panel">
      {!hideTitle ? <h2>Statistics</h2> : null}
      <form className="statistics-filters" onSubmit={handleApply}>
        <label>
          Range
          <select
            value={rangePreset}
            onChange={(event) => handleRangePresetChange(event.target.value as RangePreset)}
          >
            <option value="custom">Custom</option>
            <option value="wtd">WTD</option>
            <option value="ytd">YTD</option>
          </select>
        </label>
        <label>
          Start
          <input
            type="date"
            value={draftStart}
            onChange={(event) => setDraftStart(event.target.value)}
            disabled={rangePreset !== "custom"}
          />
        </label>
        <label>
          End
          <input
            type="date"
            value={draftEnd}
            onChange={(event) => setDraftEnd(event.target.value)}
            disabled={rangePreset !== "custom"}
          />
        </label>
        <button type="submit" disabled={isLoading || rangePreset !== "custom"}>
          {isLoading ? "Loading..." : "Apply"}
        </button>
        <label className="statistics-compare-toggle">
          <input
            type="checkbox"
            checked={isCompareMode}
            onChange={(event) => setIsCompareMode(event.target.checked)}
          />
          Compare
        </label>
        {isCompareMode ? (
          <label>
            Compare Range
            <select
              value={comparePreset}
              onChange={(event) => setComparePreset(event.target.value as ComparePreset)}
            >
              <option value="week">This week vs last week</option>
              <option value="month">This month vs last month</option>
              <option value="ytd">YTD vs last YTD</option>
            </select>
          </label>
        ) : null}
      </form>

      {errorMessage ? <p className="statistics-status error">{errorMessage}</p> : null}

      {isLoading ? <p className="statistics-status">Loading statistics...</p> : null}

      {!isLoading && !errorMessage && summary === null ? (
        <p className="statistics-status">No statistics available.</p>
      ) : null}

      {!isLoading && !errorMessage && summary ? (
        <>
          {isCompareMode ? (
            <section className="statistics-compare-panel">
              <div className="statistics-compare-header">
                <h3>Compare Mode</h3>
                {compareRanges ? (
                  <div className="statistics-compare-ranges">
                    <p>
                      <strong>{compareRanges.primary.label}</strong>: {compareRanges.primary.start}{" "}
                      to {compareRanges.primary.end}
                    </p>
                    <p>
                      <strong>{compareRanges.comparison.label}</strong>:{" "}
                      {compareRanges.comparison.start} to {compareRanges.comparison.end}
                    </p>
                  </div>
                ) : null}
              </div>
              <p className="statistics-helper">
                Compare mode affects KPI cards only. Charts below still use the selected range.
              </p>
              {isCompareLoading ? (
                <p className="statistics-status">Loading comparison...</p>
              ) : compareErrorMessage ? (
                <p className="statistics-status error">{compareErrorMessage}</p>
              ) : comparePrimaryInsights && compareComparisonInsights ? (
                <div className="statistics-compare-grid">
                  {renderCompareMetricCard(
                    "PnL",
                    formatUsd(comparePrimaryInsights.overall.total_pnl_usd),
                    formatUsd(compareComparisonInsights.overall.total_pnl_usd),
                    formatSignedUsd(
                      comparePrimaryInsights.overall.total_pnl_usd -
                        compareComparisonInsights.overall.total_pnl_usd,
                    ),
                    comparePrimaryInsights.overall.total_pnl_usd -
                      compareComparisonInsights.overall.total_pnl_usd,
                  )}
                  {renderCompareMetricCard(
                    "Win Rate",
                    formatRateAsPercent(comparePrimaryInsights.overall.win_rate),
                    formatRateAsPercent(compareComparisonInsights.overall.win_rate),
                    formatRateDelta(
                      comparePrimaryInsights.overall.win_rate -
                        compareComparisonInsights.overall.win_rate,
                    ),
                    comparePrimaryInsights.overall.win_rate -
                      compareComparisonInsights.overall.win_rate,
                  )}
                  {renderCompareMetricCard(
                    "Expectancy",
                    formatUsd(comparePrimaryInsights.overall.expectancy_usd_per_trade),
                    formatUsd(compareComparisonInsights.overall.expectancy_usd_per_trade),
                    formatSignedUsd(
                      comparePrimaryInsights.overall.expectancy_usd_per_trade -
                        compareComparisonInsights.overall.expectancy_usd_per_trade,
                    ),
                    comparePrimaryInsights.overall.expectancy_usd_per_trade -
                      compareComparisonInsights.overall.expectancy_usd_per_trade,
                  )}
                  {renderCompareMetricCard(
                    "Trades",
                    String(comparePrimaryInsights.overall.total_trades),
                    String(compareComparisonInsights.overall.total_trades),
                    formatCountDelta(
                      comparePrimaryInsights.overall.total_trades -
                        compareComparisonInsights.overall.total_trades,
                    ),
                    comparePrimaryInsights.overall.total_trades -
                      compareComparisonInsights.overall.total_trades,
                  )}
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="statistics-executive-summary">
            {!isLoading && (summary?.total_trades ?? 0) === 0 ? (
              <EmptyState
                title="No trades found for this range."
                description="Charts and analytics will appear once trades exist."
                compact
              />
            ) : null}
            <div className="statistics-executive-header">
              <h3>Executive Summary</h3>
              <p className="statistics-helper">
                Range:{" "}
                {insights
                  ? `${insights.range.start} to ${insights.range.end}`
                  : appliedStart && appliedEnd
                    ? `${appliedStart} to ${appliedEnd}`
                    : "All time"}
              </p>
            </div>

            <div className="statistics-tiles statistics-executive-kpis">
              <article>
                <h3>Total PnL (USD)</h3>
                <p className="statistics-metric">
                  {formatUsd(insights ? insights.overall.total_pnl_usd : summary.total_pnl_usd)}
                </p>
              </article>
              <article>
                <h3>Win Rate</h3>
                <p className="statistics-metric">
                  {insights
                    ? formatRateAsPercent(insights.overall.win_rate)
                    : formatSummaryPercent(summary.win_rate_overall)}
                </p>
              </article>
              <article>
                <h3>Expectancy (USD/trade)</h3>
                <p className="statistics-metric">
                  {insights ? formatUsd(insights.overall.expectancy_usd_per_trade) : "-"}
                </p>
              </article>
              <article>
                <h3>Trades</h3>
                <p className="statistics-metric">
                  {insights ? insights.overall.total_trades : summary.total_trades}
                </p>
              </article>
              {insights ? (
                <article>
                  <h3>Max Drawdown (USD)</h3>
                  <p className="statistics-metric">{formatUsd(insights.risk.max_drawdown_usd)}</p>
                </article>
              ) : null}
            </div>

            <div className="statistics-executive-discipline">
              <article className="statistics-executive-card">
                <h4>Rule Adherence</h4>
                {insights ? (
                  <div className="statistics-executive-card-body">
                    <div className="statistics-executive-row">
                      <span>Followed ({insights.by_rule_followed.followed.count})</span>
                      <span>{formatUsd(insights.by_rule_followed.followed.total_pnl_usd)}</span>
                      <span>
                        {formatRateAsPercent(insights.by_rule_followed.followed.win_rate)}
                      </span>
                    </div>
                    <div className="statistics-executive-row">
                      <span>Broken ({insights.by_rule_followed.broken.count})</span>
                      <span>{formatUsd(insights.by_rule_followed.broken.total_pnl_usd)}</span>
                      <span>{formatRateAsPercent(insights.by_rule_followed.broken.win_rate)}</span>
                    </div>
                  </div>
                ) : (
                  <p className="statistics-helper">No rule adherence data for selected range.</p>
                )}
              </article>

              <article className="statistics-executive-card">
                <h4>Worst Emotion</h4>
                {worstEmotion ? (
                  <div className="statistics-executive-card-body">
                    <div className="statistics-executive-emotion-name">
                      {worstEmotion.emotion_name}
                    </div>
                    <div className="statistics-executive-row">
                      <span>Total PnL</span>
                      <span>{formatUsd(worstEmotion.total_pnl_usd)}</span>
                    </div>
                    <div className="statistics-executive-row">
                      <span>Win Rate</span>
                      <span>{formatRateAsPercent(worstEmotion.win_rate)}</span>
                    </div>
                  </div>
                ) : (
                  <p className="statistics-helper">No emotion data for selected range.</p>
                )}
              </article>
            </div>
          </section>

          <section className="statistics-data-quality">
            <div className="statistics-data-quality-header">
              <div>
                <h3>Data Quality</h3>
                <p className="statistics-helper">Issues that may affect analytics accuracy</p>
              </div>
            </div>
            {statsRangeTrades.length === 0 ? (
              <p className="statistics-data-quality-healthy">No trades to inspect yet.</p>
            ) : !hasDataQualityIssues ? (
              <p className="statistics-data-quality-healthy">No data quality issues detected.</p>
            ) : (
              <div className="statistics-data-quality-grid">
                {dataQualityRows.map((row) => (
                  <article
                    key={row.key}
                    className={`statistics-data-quality-card ${
                      row.count > 0 ? "has-issues" : "is-healthy"
                    }`}
                  >
                    <span>{row.label}</span>
                    <strong>{row.count}</strong>
                    <p>{row.description}</p>
                  </article>
                ))}
              </div>
            )}
          </section>

          <div className="statistics-table-wrap statistics-insights-wrap">
            <h3>Insights</h3>
            {topInsights.length === 0 ? (
              <p className="statistics-status">Not enough data to generate insights yet.</p>
            ) : (
              <div className="statistics-insights-list">
                {topInsights.map((item, index) => {
                  const tradeFilters = getInsightTradeFilters(item);
                  return (
                    <article
                      key={`${item.type}-${index}`}
                      className={`statistics-insight-card statistics-insight-${item.severity}`}
                    >
                      <p>{renderInsightMessage(item.message)}</p>
                      {onViewTradesFromInsight && tradeFilters ? (
                        <button
                          type="button"
                          className="statistics-insight-link"
                          onClick={() => onViewTradesFromInsight(tradeFilters)}
                        >
                          View trades
                        </button>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
            <h4 className="statistics-subheading">Patterns Detected</h4>
            {topPatterns.length === 0 ? (
              <p className="statistics-status">No patterns detected yet.</p>
            ) : (
              <div className="statistics-insights-list">
                {topPatterns.map((item) => (
                  <article
                    key={item.id}
                    className={`statistics-insight-card statistics-insight-${item.severity}`}
                  >
                    <p className="statistics-pattern-title">{item.title}</p>
                    <p>{renderInsightMessage(item.message)}</p>
                    <div className="statistics-pattern-footer">
                      <span className="statistics-pattern-sample">n={item.sample_size}</span>
                      {onViewTradesFromInsight ? (
                        <button
                          type="button"
                          className="statistics-insight-link"
                          onClick={() => onViewTradesFromInsight(getPatternTradeFilters(item))}
                        >
                          View trades
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="statistics-tiles">
            <article>
              <h3>Total Trades</h3>
              <p className="statistics-metric">{summary.total_trades}</p>
            </article>
            <article>
              <h3>Total PnL (USD)</h3>
              <p className="statistics-metric">{formatUsd(summary.total_pnl_usd)}</p>
            </article>
            <article>
              <h3>Win Rate (Overall)</h3>
              <p className="statistics-metric">{formatPercentValue(summary.win_rate_overall)}</p>
            </article>
          </div>

          <div className="statistics-table-wrap">
            <h3>Performance</h3>
            {insights ? (
              <>
                <div className="statistics-tiles">
                  <article>
                    <h3>Total PnL (USD)</h3>
                    <p className="statistics-metric">{formatUsd(insights.overall.total_pnl_usd)}</p>
                  </article>
                  <article>
                    <h3>Win Rate</h3>
                    <p className="statistics-metric">
                      {formatRateAsPercent(insights.overall.win_rate)}
                    </p>
                  </article>
                  <article>
                    <h3>Avg Win</h3>
                    <p className="statistics-metric">{formatUsd(insights.overall.avg_win_usd)}</p>
                  </article>
                  <article>
                    <h3>Avg Loss</h3>
                    <p className="statistics-metric">{formatUsd(insights.overall.avg_loss_usd)}</p>
                  </article>
                  <article>
                    <h3>Expectancy (USD/trade)</h3>
                    <p className="statistics-metric">
                      {formatUsd(insights.overall.expectancy_usd_per_trade)}
                    </p>
                  </article>
                </div>

                <p className="statistics-helper">
                  {insights.definitions.win_rule}. {insights.definitions.breakeven_handling}
                </p>

                <div className="risk-streaks-card">
                  <h4 className="statistics-subheading">Risk &amp; Streaks</h4>
                  <div className="risk-streaks-grid">
                    <article>
                      <h5>Max Drawdown</h5>
                      <p>{formatUsd(insights.risk.max_drawdown_usd)}</p>
                      <span>{formatDrawdownRange()}</span>
                    </article>
                    <article>
                      <h5>Max Win Streak</h5>
                      <p>{insights.streaks.max_win_streak}</p>
                    </article>
                    <article>
                      <h5>Max Loss Streak</h5>
                      <p>{insights.streaks.max_loss_streak}</p>
                    </article>
                    <article>
                      <h5>Current Streak</h5>
                      <p>{formatCurrentStreak()}</p>
                    </article>
                  </div>
                </div>

                <h4 className="statistics-subheading">Rule Followed vs Broken</h4>
                <table className="statistics-table">
                  <thead>
                    <tr>
                      <th>Bucket</th>
                      <th>Count</th>
                      <th>Total PnL (USD)</th>
                      <th>Win Rate</th>
                      <th>Avg PnL (USD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Followed</td>
                      <td>{insights.by_rule_followed.followed.count}</td>
                      <td>{formatUsd(insights.by_rule_followed.followed.total_pnl_usd)}</td>
                      <td>{formatRateAsPercent(insights.by_rule_followed.followed.win_rate)}</td>
                      <td>{formatUsd(insights.by_rule_followed.followed.avg_pnl_usd)}</td>
                    </tr>
                    <tr>
                      <td>Broken</td>
                      <td>{insights.by_rule_followed.broken.count}</td>
                      <td>{formatUsd(insights.by_rule_followed.broken.total_pnl_usd)}</td>
                      <td>{formatRateAsPercent(insights.by_rule_followed.broken.win_rate)}</td>
                      <td>{formatUsd(insights.by_rule_followed.broken.avg_pnl_usd)}</td>
                    </tr>
                  </tbody>
                </table>

                <h4 className="statistics-subheading">Emotion Breakdown</h4>
                {emotionRows.length === 0 ? (
                  <p className="statistics-status">No emotion data for selected range.</p>
                ) : (
                  <table className="statistics-table">
                    <thead>
                      <tr>
                        <th>Emotion</th>
                        <th>Count</th>
                        <th>Total PnL (USD)</th>
                        <th>Win Rate</th>
                        <th>Avg PnL (USD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {emotionRows.map((row) => (
                        <tr key={row.emotion_id}>
                          <td>{row.emotion_name}</td>
                          <td>{row.count}</td>
                          <td>{formatUsd(row.total_pnl_usd)}</td>
                          <td>{formatRateAsPercent(row.win_rate)}</td>
                          <td>{formatUsd(row.avg_pnl_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <p className="statistics-status">No insights available.</p>
            )}
          </div>

          <div className="statistics-table-wrap">
            <div className="chart-centered">
              <h3>PnL Charts</h3>
              {isLoading ? <p className="statistics-status">Loading charts...</p> : null}
              {!isLoading && dailyPnlSeries.length === 0 && weeklyPnlSeries.length === 0 ? (
                <p className="statistics-status">No trades in this range.</p>
              ) : null}
              {!isLoading && (dailyPnlSeries.length > 0 || weeklyPnlSeries.length > 0) ? (
                <div className="statistics-chart-grid">
                  <section>
                    <div className="statistics-subheading-row">
                      <h4 className="statistics-subheading">Weekly PnL</h4>
                      <div
                        className="statistics-mode-toggle"
                        role="group"
                        aria-label="Weekly chart mode"
                      >
                        <button
                          type="button"
                          className={`statistics-mode-button ${
                            weeklyChartMode === "recent_13w" ? "is-active" : ""
                          }`}
                          onClick={() => setWeeklyChartMode("recent_13w")}
                        >
                          Recent ({WEEKLY_RECENT_LIMIT}W)
                        </button>
                        <button
                          type="button"
                          className={`statistics-mode-button ${
                            weeklyChartMode === "ytd_all" ? "is-active" : ""
                          }`}
                          onClick={() => setWeeklyChartMode("ytd_all")}
                        >
                          View All (YTD)
                        </button>
                      </div>
                    </div>
                    {displayedWeeklySeries.length > 0 ? (
                      <WeeklyPnLChart
                        weeklySeries={displayedWeeklySeries}
                        formatUsd={formatUsd}
                        chartHeight={CHART_HEIGHT}
                        onBarClick={
                          weeklyChartMode === "recent_13w" ? handleWeeklyBarClick : undefined
                        }
                      />
                    ) : (
                      <p className="statistics-status">No weekly data for selected range.</p>
                    )}
                  </section>
                  <section>
                    <div className="statistics-subheading-row">
                      <h4 className="statistics-subheading">Equity Curve (Daily)</h4>
                      <div
                        className="statistics-mode-toggle"
                        role="group"
                        aria-label="Daily chart mode"
                      >
                        <button
                          type="button"
                          className={`statistics-mode-button ${
                            dailyChartMode === "recent_30d" ? "is-active" : ""
                          }`}
                          onClick={() => setDailyChartMode("recent_30d")}
                        >
                          Recent ({DAILY_RECENT_LIMIT}D)
                        </button>
                        <button
                          type="button"
                          className={`statistics-mode-button ${
                            dailyChartMode === "ytd_all" ? "is-active" : ""
                          }`}
                          onClick={() => setDailyChartMode("ytd_all")}
                        >
                          View All (YTD)
                        </button>
                      </div>
                    </div>
                    {displayedDailySeries.length > 0 ? (
                      <EquityCurveDailyChart
                        dailySeries={displayedDailySeries}
                        rangeStart={displayedDailyRangeStart}
                        rangeEnd={displayedDailyRangeEnd}
                        formatUsd={formatUsd}
                        chartHeight={CHART_HEIGHT}
                        onDayClick={
                          dailyChartMode === "recent_30d" ? handleEquityDayClick : undefined
                        }
                      />
                    ) : (
                      <p className="statistics-status">No daily data for selected range.</p>
                    )}
                  </section>
                </div>
              ) : null}
            </div>
          </div>

          <div className="statistics-table-wrap">
            <div className="chart-centered">
              <h3>Setup Charts</h3>
              <h4 className="statistics-subheading">Trade Distribution by Setup</h4>
              {isLoading ? <p className="statistics-status">Loading setup chart...</p> : null}
              {!isLoading && setupDistributionRows.length === 0 ? (
                <p className="statistics-status">No setup distribution data for selected range.</p>
              ) : null}
              {!isLoading && setupDistributionRows.length > 0 ? (
                <SetupDistributionChart
                  rows={setupDistributionRows}
                  chartHeight={CHART_HEIGHT}
                  enableDrilldown={isChartDrilldownEnabled}
                  onBarClick={handleSetupBarClick}
                />
              ) : null}
              <h4 className="statistics-subheading">Performance by Setup</h4>
              {isLoading ? (
                <p className="statistics-status">Loading setup performance chart...</p>
              ) : null}
              {!isLoading && setupPerformanceRows.length === 0 ? (
                <p className="statistics-status">No setup performance data for selected range.</p>
              ) : null}
              {!isLoading && setupPerformanceRows.length > 0 ? (
                <SetupPerformanceChart
                  rows={setupPerformanceRows}
                  formatUsd={formatUsd}
                  chartHeight={CHART_HEIGHT}
                  enableDrilldown={isChartDrilldownEnabled}
                  onBarClick={handleSetupBarClick}
                />
              ) : null}
            </div>
          </div>

          <div className="statistics-table-wrap">
            <div className="chart-centered">
              <h3>Ticker Charts</h3>
              <h4 className="statistics-subheading">Performance by Ticker</h4>
              {isLoading ? (
                <p className="statistics-status">Loading ticker performance chart...</p>
              ) : null}
              {!isLoading && tickerPerformanceRows.length === 0 ? (
                <p className="statistics-status">No ticker performance data for selected range.</p>
              ) : null}
              {!isLoading && tickerPerformanceRows.length > 0 ? (
                <TickerPerformanceChart
                  rows={tickerPerformanceRows}
                  formatUsd={formatUsd}
                  chartHeight={CHART_HEIGHT}
                  enableDrilldown={isChartDrilldownEnabled}
                  onBarClick={handleTickerBarClick}
                />
              ) : null}
            </div>
          </div>

          <div className="statistics-table-wrap">
            <h3>Time-based Analytics</h3>
            <h4 className="statistics-subheading">Performance by Time of Day</h4>
            {timeOfDay ? (
              <>
                {timeOfDay.excluded_missing_time > 0 ? (
                  <p className="statistics-helper">
                    {timeOfDay.excluded_missing_time} trades excluded (missing entry time).
                  </p>
                ) : null}
                {timeOfDayRows.length === 0 ? (
                  <p className="statistics-status">No time-of-day data for selected range.</p>
                ) : (
                  <table className="statistics-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Trades</th>
                        <th>Total PnL (USD)</th>
                        <th>Win Rate</th>
                        <th>Avg PnL (USD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeOfDayRows.map((row) => (
                        <tr key={row.start_minute}>
                          <td>{row.label}</td>
                          <td>{row.count}</td>
                          <td>{formatUsd(row.total_pnl_usd)}</td>
                          <td>{formatRateAsPercent(row.win_rate)}</td>
                          <td>{formatUsd(row.avg_pnl_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <p className="statistics-status">No time-of-day data for selected range.</p>
            )}

            <h4 className="statistics-subheading">Performance by Hold Time</h4>
            {holdTime ? (
              <>
                {holdTime.excluded_missing_duration > 0 ? (
                  <p className="statistics-helper">
                    {holdTime.excluded_missing_duration} trades excluded (missing duration).
                  </p>
                ) : null}
                {holdTimeRows.length === 0 ? (
                  <p className="statistics-status">No hold-time data for selected range.</p>
                ) : (
                  <table className="statistics-table">
                    <thead>
                      <tr>
                        <th>Duration</th>
                        <th>Trades</th>
                        <th>Total PnL (USD)</th>
                        <th>Win Rate</th>
                        <th>Avg PnL (USD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holdTimeRows.map((row) => (
                        <tr key={`${row.min_seconds}-${row.max_seconds ?? "plus"}`}>
                          <td>{formatRangeLabel(row.label)}</td>
                          <td>{row.count}</td>
                          <td>{formatUsd(row.total_pnl_usd)}</td>
                          <td>{formatRateAsPercent(row.win_rate)}</td>
                          <td>{formatUsd(row.avg_pnl_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <p className="statistics-status">No hold-time data for selected range.</p>
            )}
          </div>

          <div className="statistics-table-wrap">
            <h3>By Setup</h3>
            {summary.by_setup.length === 0 ? (
              <p className="statistics-status">No setup stats for selected range.</p>
            ) : (
              <table className="statistics-table">
                <thead>
                  <tr>
                    <th>Setup</th>
                    <th>Count</th>
                    <th>Total PnL (USD)</th>
                    <th>Win Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_setup.map((row) => (
                    <tr key={row.setup_id}>
                      <td>{row.setup_name}</td>
                      <td>{row.count}</td>
                      <td>{formatUsd(row.total_pnl_usd)}</td>
                      <td>{formatPercentValue(row.win_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      ) : null}

      {selectedWeek ? (
        <div
          className="weekly-trades-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeSelectedWeekModal();
            }
          }}
        >
          <section
            className={`weekly-trades-modal ${weeklyModal.isDragging ? "is-dragging" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="weekly-trades-modal-title"
            ref={weeklyModal.modalRef}
            tabIndex={-1}
            style={weeklyModal.modalStyle}
          >
            <div
              className="weekly-trades-modal-header"
              onMouseDown={weeklyModal.handleHeaderMouseDown}
              onDoubleClick={weeklyModal.handleHeaderDoubleClick}
            >
              <div className="weekly-trades-modal-title-wrap">
                <span className="weekly-trades-modal-grip" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <div>
                  <h3 id="weekly-trades-modal-title">
                    Trades for {formatMonthDay(selectedWeek.start_date)}
                  </h3>
                  <p className="statistics-helper">
                    {formatDateRange(selectedWeek.start_date, selectedWeek.end_date)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="weekly-trades-modal-close"
                onMouseDown={(event) => event.stopPropagation()}
                onClick={closeSelectedWeekModal}
                aria-label="Close weekly trades modal"
              >
                Close
              </button>
            </div>
            <div className="weekly-trades-modal-summary">
              <span>Total PnL: {formatUsd(selectedWeek.total_pnl_usd)}</span>
              <span>Trades: {selectedWeek.trade_count}</span>
            </div>

            {isSelectedWeekTradesLoading ? (
              <p className="statistics-status">Loading trades...</p>
            ) : selectedWeekTradesError ? (
              <p className="statistics-status error">{selectedWeekTradesError}</p>
            ) : selectedWeekTrades.length === 0 ? (
              <p className="statistics-status">No trades for this week.</p>
            ) : (
              <div className="weekly-trades-modal-table-wrap">
                <table className="statistics-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Ticker</th>
                      <th>Direction</th>
                      <th>Total PnL (USD)</th>
                      <th>Setup</th>
                      <th>Emotion</th>
                      <th>Rule Followed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedWeekTrades.map((trade) => (
                      <tr key={trade.id}>
                        <td>{trade.entry_time ?? "-"}</td>
                        <td>{trade.ticker}</td>
                        <td>{trade.direction}</td>
                        <td>{formatUsd(trade.total_pnl_usd)}</td>
                        <td>{trade.setup_name || "—"}</td>
                        <td>{trade.emotion_name || "—"}</td>
                        <td>{formatRuleFollowedValue(trade.rule_followed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {selectedEquityDay ? (
        <div
          className="weekly-trades-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeSelectedEquityModal();
            }
          }}
        >
          <section
            className={`weekly-trades-modal ${equityModal.isDragging ? "is-dragging" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="equity-trades-modal-title"
            ref={equityModal.modalRef}
            tabIndex={-1}
            style={equityModal.modalStyle}
          >
            <div
              className="weekly-trades-modal-header"
              onMouseDown={equityModal.handleHeaderMouseDown}
              onDoubleClick={equityModal.handleHeaderDoubleClick}
            >
              <div className="weekly-trades-modal-title-wrap">
                <span className="weekly-trades-modal-grip" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <div>
                  <h3 id="equity-trades-modal-title">
                    Trades for date {formatMonthDay(selectedEquityDay.start_date)}
                  </h3>
                  <p className="statistics-helper">
                    {formatDateWithYear(selectedEquityDay.start_date)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="weekly-trades-modal-close"
                onMouseDown={(event) => event.stopPropagation()}
                onClick={closeSelectedEquityModal}
                aria-label="Close equity trades modal"
              >
                Close
              </button>
            </div>
            <div className="weekly-trades-modal-summary">
              <span>Total PnL: {formatUsd(selectedEquityDay.total_pnl_usd)}</span>
              <span>Trades: {selectedEquityDay.trade_count}</span>
            </div>

            {isSelectedEquityTradesLoading ? (
              <p className="statistics-status">Loading trades...</p>
            ) : selectedEquityTradesError ? (
              <p className="statistics-status error">{selectedEquityTradesError}</p>
            ) : selectedEquityTrades.length === 0 ? (
              <p className="statistics-status">No trades for this date.</p>
            ) : (
              <div className="weekly-trades-modal-table-wrap">
                <table className="statistics-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Ticker</th>
                      <th>Direction</th>
                      <th>Total PnL (USD)</th>
                      <th>Setup</th>
                      <th>Emotion</th>
                      <th>Rule Followed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedEquityTrades.map((trade) => (
                      <tr key={trade.id}>
                        <td>{trade.entry_time ?? "-"}</td>
                        <td>{trade.ticker}</td>
                        <td>{trade.direction}</td>
                        <td>{formatUsd(trade.total_pnl_usd)}</td>
                        <td>{trade.setup_name || "—"}</td>
                        <td>{trade.emotion_name || "—"}</td>
                        <td>{formatRuleFollowedValue(trade.rule_followed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {selectedSetupRow || selectedTickerRow ? (
        <div
          className="weekly-trades-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeSelectedSetupDrilldownModal();
            }
          }}
        >
          <section
            className={`weekly-trades-modal ${setupModal.isDragging ? "is-dragging" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="setup-trades-modal-title"
            ref={setupModal.modalRef}
            tabIndex={-1}
            style={setupModal.modalStyle}
          >
            <div
              className="weekly-trades-modal-header"
              onMouseDown={setupModal.handleHeaderMouseDown}
              onDoubleClick={setupModal.handleHeaderDoubleClick}
            >
              <div className="weekly-trades-modal-title-wrap">
                <span className="weekly-trades-modal-grip" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <div>
                  <h3 id="setup-trades-modal-title">{selectedSetupModalTitle}</h3>
                  <p className="statistics-helper">{selectedSetupRangeText}</p>
                </div>
              </div>
              <button
                type="button"
                className="weekly-trades-modal-close"
                onMouseDown={(event) => event.stopPropagation()}
                onClick={closeSelectedSetupDrilldownModal}
                aria-label="Close setup trades modal"
              >
                Close
              </button>
            </div>
            <div className="weekly-trades-modal-summary">
              <span>Total PnL: {formatUsd(selectedSetupModalTotalPnl)}</span>
              <span>Trades: {selectedSetupModalTrades.length}</span>
            </div>

            {selectedSetupModalTrades.length === 0 ? (
              <p className="statistics-status">{selectedSetupModalEmptyMessage}</p>
            ) : (
              <div className="weekly-trades-modal-table-wrap">
                <table className="statistics-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Time</th>
                      <th>Ticker</th>
                      <th>Direction</th>
                      <th>Total PnL (USD)</th>
                      <th>Setup</th>
                      <th>Emotion</th>
                      <th>Rule Followed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedSetupModalTrades.map((trade) => (
                      <tr key={trade.id}>
                        <td>{formatDateLong(trade.date)}</td>
                        <td>{trade.entry_time ?? "-"}</td>
                        <td>{trade.ticker}</td>
                        <td>{trade.direction}</td>
                        <td>{formatUsd(trade.total_pnl_usd)}</td>
                        <td>{trade.setup_name || "—"}</td>
                        <td>{trade.emotion_name || "—"}</td>
                        <td>{formatRuleFollowedValue(trade.rule_followed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
