import { PnlSeriesPointResponse } from "../types/summary";
import { getTodayDate } from "./date";

function parseIsoDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return new Date(NaN);
  }
  return new Date(year, month - 1, day);
}

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function startOfWeekMonday(value: Date): Date {
  const start = new Date(value);
  const day = start.getDay();
  const offset = (day + 6) % 7;
  start.setDate(start.getDate() - offset);
  return start;
}

function getIsoWeekLabel(weekStart: Date): string {
  const date = new Date(weekStart);
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7));
  const isoYear = date.getFullYear();
  const week1 = new Date(isoYear, 0, 4);
  week1.setDate(week1.getDate() + 3 - ((week1.getDay() + 6) % 7));
  const weekNo = 1 + Math.round((date.getTime() - week1.getTime()) / (7 * 24 * 60 * 60 * 1000));
  return `${isoYear}-W${String(weekNo).padStart(2, "0")}`;
}

function sortByStartDate(series: PnlSeriesPointResponse[]): PnlSeriesPointResponse[] {
  return [...series].sort((left, right) => left.start_date.localeCompare(right.start_date));
}

function getFirstPopulatedStartDate(
  series: PnlSeriesPointResponse[]
): string | null {
  return sortByStartDate(series)[0]?.start_date ?? null;
}

function buildWeeklyBuckets(startDateIso: string, endDateIso: string): PnlSeriesPointResponse[] {
  const startDate = parseIsoDate(startDateIso);
  const endDate = parseIsoDate(endDateIso);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || startDate > endDate) {
    return [];
  }

  const buckets: PnlSeriesPointResponse[] = [];
  for (let cursor = new Date(startDate); cursor <= endDate; cursor = addDays(cursor, 7)) {
    const startDateKey = toIsoDate(cursor);
    buckets.push({
      label: getIsoWeekLabel(cursor),
      start_date: startDateKey,
      end_date: toIsoDate(addDays(cursor, 6)),
      trade_count: 0,
      total_pnl_usd: 0,
    });
  }

  return buckets;
}

function buildDailyBuckets(startDateIso: string, endDateIso: string): PnlSeriesPointResponse[] {
  const startDate = parseIsoDate(startDateIso);
  const endDate = parseIsoDate(endDateIso);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || startDate > endDate) {
    return [];
  }

  const buckets: PnlSeriesPointResponse[] = [];
  for (let cursor = new Date(startDate); cursor <= endDate; cursor = addDays(cursor, 1)) {
    const dayIso = toIsoDate(cursor);
    buckets.push({
      label: dayIso,
      start_date: dayIso,
      end_date: dayIso,
      trade_count: 0,
      total_pnl_usd: 0,
    });
  }

  return buckets;
}

function mergeByStartDate(
  buckets: PnlSeriesPointResponse[],
  realSeries: PnlSeriesPointResponse[]
): PnlSeriesPointResponse[] {
  const realByStartDate = new Map(
    sortByStartDate(realSeries).map((point) => [point.start_date, point])
  );

  return buckets.map((bucket) => realByStartDate.get(bucket.start_date) ?? bucket);
}

function buildRecentWeeklyBuckets(
  weeklySeries: PnlSeriesPointResponse[],
  count: number
): PnlSeriesPointResponse[] {
  const firstPopulatedStartDate = getFirstPopulatedStartDate(weeklySeries);
  if (weeklySeries.length === 0 || weeklySeries.length >= count || !firstPopulatedStartDate) {
    const today = parseIsoDate(getTodayDate());
    const currentWeekStart = startOfWeekMonday(today);
    const startWeek = addDays(currentWeekStart, -7 * (count - 1));
    return buildWeeklyBuckets(toIsoDate(startWeek), toIsoDate(currentWeekStart));
  }

  const firstWeekStart = parseIsoDate(firstPopulatedStartDate);
  const lastWeekStart = addDays(firstWeekStart, 7 * (count - 1));
  return buildWeeklyBuckets(toIsoDate(firstWeekStart), toIsoDate(lastWeekStart));
}

function buildRecentDailyBuckets(
  dailySeries: PnlSeriesPointResponse[],
  count: number
): PnlSeriesPointResponse[] {
  const firstPopulatedStartDate = getFirstPopulatedStartDate(dailySeries);
  if (dailySeries.length === 0 || dailySeries.length >= count || !firstPopulatedStartDate) {
    const today = parseIsoDate(getTodayDate());
    const startDate = addDays(today, -(count - 1));
    return buildDailyBuckets(toIsoDate(startDate), toIsoDate(today));
  }

  const firstDate = parseIsoDate(firstPopulatedStartDate);
  const lastDate = addDays(firstDate, count - 1);
  return buildDailyBuckets(toIsoDate(firstDate), toIsoDate(lastDate));
}

export function buildWeeklyRecentSeries(
  weeklySeries: PnlSeriesPointResponse[],
  count: number
): PnlSeriesPointResponse[] {
  if (count <= 0) {
    return [];
  }

  const buckets = buildRecentWeeklyBuckets(weeklySeries, count);
  return mergeByStartDate(buckets, weeklySeries);
}

export function buildWeeklyYtdSeries(weeklySeries: PnlSeriesPointResponse[]): PnlSeriesPointResponse[] {
  const today = parseIsoDate(getTodayDate());
  const currentWeekStart = startOfWeekMonday(today);
  const yearStart = new Date(today.getFullYear(), 0, 1);
  const yearStartWeek = startOfWeekMonday(yearStart);
  const buckets = buildWeeklyBuckets(toIsoDate(yearStartWeek), toIsoDate(currentWeekStart));
  return mergeByStartDate(buckets, weeklySeries);
}

export function buildDailyRecentSeries(
  dailySeries: PnlSeriesPointResponse[],
  count: number
): PnlSeriesPointResponse[] {
  if (count <= 0) {
    return [];
  }

  const buckets = buildRecentDailyBuckets(dailySeries, count);
  return mergeByStartDate(buckets, dailySeries);
}

export function buildDailyYtdSeries(dailySeries: PnlSeriesPointResponse[]): PnlSeriesPointResponse[] {
  const today = parseIsoDate(getTodayDate());
  const yearStart = new Date(today.getFullYear(), 0, 1);
  const buckets = buildDailyBuckets(toIsoDate(yearStart), toIsoDate(today));
  return mergeByStartDate(buckets, dailySeries);
}
