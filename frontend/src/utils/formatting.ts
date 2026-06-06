function parseDateValue(value: string | Date): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
  }

  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }

  const trimmed = value.trim();
  const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (dateOnlyMatch) {
    const year = Number(dateOnlyMatch[1]);
    const month = Number(dateOnlyMatch[2]);
    const day = Number(dateOnlyMatch[3]);
    const parsed = new Date(year, month - 1, day);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  const parsed = new Date(trimmed);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatNumberWithOptions(
  value: number,
  minimumFractionDigits: number,
  maximumFractionDigits: number,
): string {
  if (!Number.isFinite(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

export function formatUsd(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatSignedUsd(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }

  return value > 0 ? `+${formatUsd(value)}` : formatUsd(value);
}

export function formatNumber(value: number, digits = 2): string {
  return formatNumberWithOptions(value, digits, digits);
}

export function formatSignedNumber(value: number, digits = 2): string {
  if (!Number.isFinite(value)) {
    return "—";
  }

  const formatted = formatNumber(value, digits);
  return value > 0 ? `+${formatted}` : formatted;
}

export function formatPercentFromRate(rate: number, digits = 2): string {
  if (!Number.isFinite(rate)) {
    return "—";
  }

  return formatPercentValue(rate * 100, digits);
}

export function formatPercentValue(value: number, digits = 2): string {
  if (!Number.isFinite(value)) {
    return "—";
  }

  return `${formatNumberWithOptions(value, digits, digits)}%`;
}

export function formatDateLong(value: string | Date): string {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

export function formatMonthDay(value: string | Date): string {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(parsed);
}

export function formatMonthDayNumeric(value: string | Date): string {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "numeric",
    day: "numeric",
  }).format(parsed);
}

export function formatMonthDayNumericPadded(value: string | Date): string {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return String(value);
  }

  return `${String(parsed.getMonth() + 1).padStart(2, "0")}/${String(parsed.getDate()).padStart(2, "0")}`;
}

export function formatDateTime(value: string | Date): string {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

export function formatDateRange(start: string | Date, end: string | Date): string {
  const startDate = parseDateValue(start);
  const endDate = parseDateValue(end);
  if (!startDate || !endDate) {
    return `${String(start)} – ${String(end)}`;
  }

  const sameYear = startDate.getFullYear() === endDate.getFullYear();
  const startText = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  }).format(startDate);
  const endText = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(endDate);

  return `${startText} – ${endText}`;
}
