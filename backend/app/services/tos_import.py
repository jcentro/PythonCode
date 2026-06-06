from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.schemas.import_preview import DetectedTradePreview, DetectedTradePreviewFill

ACCOUNT_TRADE_HISTORY_TITLE = "Account Trade History"
_preview_trade_cache: dict[str, DetectedTradePreview] = {}


@dataclass
class TradeFill:
    exec_datetime: datetime
    side: str
    qty: int
    pos_effect: str
    symbol: str
    exp: str
    strike: float
    option_type: str
    price: float

    @property
    def group_key(self) -> tuple[str, str, float, str, date]:
        return (
            self.symbol,
            self.exp,
            self.strike,
            self.option_type,
            self.exec_datetime.date(),
        )


def _trim_fill(fill: TradeFill) -> dict[str, str | int | float]:
    return {
        "exec_datetime": fill.exec_datetime.isoformat(),
        "side": fill.side,
        "pos_effect": fill.pos_effect,
        "qty": abs(fill.qty),
        "symbol": fill.symbol,
        "exp": fill.exp,
        "strike": fill.strike,
        "option_type": fill.option_type,
        "price": fill.price,
    }


def _fill_preview_row(fill: TradeFill) -> DetectedTradePreviewFill:
    return DetectedTradePreviewFill(
        side=fill.side,
        qty=abs(fill.qty),
        price=fill.price,
        exec_datetime=fill.exec_datetime.isoformat(),
    )


def preview_tos_statement(csv_text: str) -> tuple[list[DetectedTradePreview], list[str]]:
    detected_trades, warnings, _, _, _, _ = preview_tos_statement_with_metrics(csv_text)
    return detected_trades, warnings


def preview_tos_statement_with_metrics(
    csv_text: str,
) -> tuple[
    list[DetectedTradePreview],
    list[str],
    int,
    list[dict[str, str | int | float]],
    list[dict[str, str | int | float]],
    list[dict[str, str | int | float]],
]:
    warnings: list[str] = []
    fills = _extract_trade_fills(csv_text, warnings)
    detected_trades, unmatched_opens, unmatched_closes = _group_scaled_trades(fills, warnings)
    return (
        detected_trades,
        warnings,
        len(fills),
        [_trim_fill(fill) for fill in fills],
        [_trim_fill(fill) for fill in unmatched_opens],
        [_trim_fill(fill) for fill in unmatched_closes],
    )


def cache_detected_trades(detected_trades: list[DetectedTradePreview]) -> None:
    global _preview_trade_cache
    _preview_trade_cache = {trade.temp_id: trade for trade in detected_trades}


def get_cached_detected_trade(temp_id: str) -> DetectedTradePreview | None:
    return _preview_trade_cache.get(temp_id)


def get_detected_trade_from_batch_fills(
    fills_json: str | None, temp_id: str
) -> tuple[DetectedTradePreview | None, list[str]]:
    if not fills_json:
        return None, ["Batch is missing stored fill data."]

    try:
        raw_items = json.loads(fills_json)
    except json.JSONDecodeError:
        return None, ["Batch fill data is invalid JSON."]

    if not isinstance(raw_items, list):
        return None, ["Batch fill data has an invalid format."]

    warnings: list[str] = []
    normalized_fills = _parse_trimmed_fills(raw_items, warnings)
    if not normalized_fills:
        return None, warnings

    detected_trades, _, _ = _group_scaled_trades(normalized_fills, warnings)
    for trade in detected_trades:
        if trade.temp_id == temp_id:
            return trade, warnings

    return None, warnings


def _extract_trade_fills(csv_text: str, warnings: list[str]) -> list[TradeFill]:
    lines = csv_text.splitlines()
    account_header_index = _find_account_trade_history_index(lines)
    if account_header_index is None:
        warnings.append("Could not locate 'Account Trade History' section.")
        return []

    header_index = _find_next_non_empty_line_index(lines, start=account_header_index + 1)
    if header_index is None:
        warnings.append("Missing trade history header row after 'Account Trade History'.")
        return []

    header_row = _read_csv_row(lines[header_index])
    header_map = _build_header_map(header_row)
    required_columns = {
        "exec_time": ["exec_time"],
        "side": ["side"],
        "qty": ["qty"],
        "pos_effect": ["pos_effect"],
        "symbol": ["symbol"],
        "exp": ["exp"],
        "strike": ["strike"],
        "option_type": ["type", "option_type"],
        "price": ["price"],
    }

    missing = [
        column
        for column, aliases in required_columns.items()
        if _get_column_index(header_map, aliases) is None
    ]
    if missing:
        warnings.append(f"Missing required trade history columns: {', '.join(missing)}")
        return []

    fills: list[TradeFill] = []
    for raw_line in lines[header_index + 1 :]:
        if not raw_line.strip():
            break

        row = _read_csv_row(raw_line)
        if _is_next_section_row(row):
            break

        try:
            fill = _parse_fill_row(row, header_map)
        except ValueError as exc:
            warnings.append(str(exc))
            continue

        fills.append(fill)

    return fills


def _parse_trimmed_fills(items: list[Any], warnings: list[str]) -> list[TradeFill]:
    fills: list[TradeFill] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"Skipped stored fill at index {index}: expected object.")
            continue

        try:
            exec_datetime_raw = str(item["exec_datetime"])
            exec_datetime = datetime.fromisoformat(exec_datetime_raw)
            side = _normalize_side(str(item["side"]))
            qty = int(float(item["qty"]))
            pos_effect = _normalize_pos_effect(str(item.get("pos_effect", "")))
            symbol = str(item["symbol"]).upper().strip()
            exp = str(item["exp"]).strip()
            strike = float(item["strike"])
            option_type = _normalize_option_type(str(item["option_type"]))
            price = float(item["price"])
        except (KeyError, TypeError, ValueError) as exc:
            warnings.append(f"Skipped stored fill at index {index}: {exc!s}")
            continue

        if qty <= 0:
            warnings.append(f"Skipped stored fill at index {index}: quantity must be positive.")
            continue

        fills.append(
            TradeFill(
                exec_datetime=exec_datetime,
                side=side,
                qty=qty,
                pos_effect=pos_effect,
                symbol=symbol,
                exp=exp,
                strike=strike,
                option_type=option_type,
                price=price,
            )
        )

    return fills


def _find_account_trade_history_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if ACCOUNT_TRADE_HISTORY_TITLE in line:
            return index
    return None


def _find_next_non_empty_line_index(lines: list[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if lines[index].strip():
            return index
    return None


def _read_csv_row(line: str) -> list[str]:
    return next(csv.reader([line]))


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace(" ", "_")
    return normalized


def _build_header_map(header_row: list[str]) -> dict[str, int]:
    header_map: dict[str, int] = {}
    for index, cell in enumerate(header_row):
        normalized = _normalize_header(cell)
        if normalized:
            header_map[normalized] = index
    return header_map


def _get_column_index(header_map: dict[str, int], aliases: list[str]) -> int | None:
    for alias in aliases:
        normalized_alias = _normalize_header(alias)
        if normalized_alias in header_map:
            return header_map[normalized_alias]
    return None


def _get_cell_value(row: list[str], column_index: int) -> str:
    if column_index >= len(row):
        return ""
    return row[column_index].strip()


def _is_next_section_row(row: list[str]) -> bool:
    non_empty = [cell.strip() for cell in row if cell.strip()]
    if len(non_empty) != 1:
        return False

    section_name = non_empty[0]
    return section_name != ACCOUNT_TRADE_HISTORY_TITLE


def _parse_fill_row(row: list[str], header_map: dict[str, int]) -> TradeFill:
    exec_time_index = _require_column_index(header_map, "exec_time")
    side_index = _require_column_index(header_map, "side")
    qty_index = _require_column_index(header_map, "qty")
    pos_effect_index = _require_column_index(header_map, "pos_effect")
    symbol_index = _require_column_index(header_map, "symbol")
    exp_index = _require_column_index(header_map, "exp")
    strike_index = _require_column_index(header_map, "strike")
    option_type_index = _require_column_index_any(header_map, ["type", "option_type"])
    price_index = _require_column_index(header_map, "price")

    exec_datetime = _parse_exec_datetime(_get_cell_value(row, exec_time_index))
    side = _normalize_side(_get_cell_value(row, side_index))
    qty = _parse_int(_get_cell_value(row, qty_index))
    pos_effect = _normalize_pos_effect(_get_cell_value(row, pos_effect_index))
    symbol = _get_cell_value(row, symbol_index).upper()
    exp = _get_cell_value(row, exp_index)
    strike = _parse_float(_get_cell_value(row, strike_index))
    option_type = _normalize_option_type(_get_cell_value(row, option_type_index))
    price = _parse_float(_get_cell_value(row, price_index))

    if not symbol:
        raise ValueError("Skipped a trade history row with an empty symbol.")

    return TradeFill(
        exec_datetime=exec_datetime,
        side=side,
        qty=qty,
        pos_effect=pos_effect,
        symbol=symbol,
        exp=exp,
        strike=strike,
        option_type=option_type,
        price=price,
    )


def _require_column_index(header_map: dict[str, int], alias: str) -> int:
    index = _get_column_index(header_map, [alias])
    if index is None:
        raise ValueError(f"Missing required column: {alias}")
    return index


def _require_column_index_any(header_map: dict[str, int], aliases: list[str]) -> int:
    index = _get_column_index(header_map, aliases)
    if index is None:
        raise ValueError(f"Missing required column: {', '.join(aliases)}")
    return index


def _parse_exec_datetime(value: str) -> datetime:
    candidates = [
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse Exec Time value: {value!r}")


def _parse_float(value: str) -> float:
    normalized = value.replace("$", "").replace(",", "").strip()
    if not normalized:
        raise ValueError("Expected a numeric value but found blank text.")
    return float(normalized)


def _parse_int(value: str) -> int:
    normalized = value.replace(",", "").strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("Expected an integer quantity but found blank text.")
    return int(float(normalized))


def _normalize_side(value: str) -> str:
    upper = value.strip().upper()
    if upper not in {"BUY", "SELL"}:
        raise ValueError(f"Unsupported Side value: {value!r}")
    return upper


def _normalize_pos_effect(value: str) -> str:
    upper = value.strip().upper()
    if upper in {"TO OPEN", "OPENING"}:
        return "TO OPEN"
    if upper in {"TO CLOSE", "CLOSING"}:
        return "TO CLOSE"
    return upper


def _normalize_option_type(value: str) -> str:
    upper = value.strip().upper()
    if upper in {"CALL", "C"}:
        return "CALL"
    if upper in {"PUT", "P"}:
        return "PUT"
    raise ValueError(f"Unsupported option type value: {value!r}")


def _group_scaled_trades(
    fills: list[TradeFill], warnings: list[str]
) -> tuple[list[DetectedTradePreview], list[TradeFill], list[TradeFill]]:
    grouped_fills: dict[tuple[str, str, float, str, date], list[TradeFill]] = defaultdict(list)
    sorted_fills = sorted(
        fills,
        key=lambda entry: (
            entry.exec_datetime,
            entry.symbol,
            entry.exp,
            entry.strike,
            entry.option_type,
            entry.side,
        ),
    )
    for fill in sorted_fills:
        grouped_fills[fill.group_key].append(fill)

    detected_trades: list[DetectedTradePreview] = []
    unmatched_opens: list[TradeFill] = []
    unmatched_closes: list[TradeFill] = []

    sorted_group_keys = sorted(
        grouped_fills.keys(),
        key=lambda key: (key[4], key[0], key[1], key[2], key[3]),
    )
    for group_key in sorted_group_keys:
        group_detected_trade, group_unmatched_opens, group_unmatched_closes = (
            _build_grouped_trade_preview(group_key, grouped_fills[group_key], warnings)
        )
        if group_detected_trade is not None:
            detected_trades.append(group_detected_trade)
        unmatched_opens.extend(group_unmatched_opens)
        unmatched_closes.extend(group_unmatched_closes)

    return detected_trades, unmatched_opens, unmatched_closes


def _build_grouped_trade_preview(
    group_key: tuple[str, str, float, str, date],
    group_fills: list[TradeFill],
    warnings: list[str],
) -> tuple[DetectedTradePreview | None, list[TradeFill], list[TradeFill]]:
    symbol, exp, strike, option_type, trade_date = group_key
    entry_fills_count = 0
    exit_fills_count = 0
    total_entry_qty = 0
    total_exit_qty = 0
    total_entry_notional = 0.0
    matched_entry_notional = 0.0
    matched_exit_notional = 0.0
    matched_qty = 0
    realized_pnl_usd = 0.0

    unmatched_opens: list[TradeFill] = []
    unmatched_closes: list[TradeFill] = []
    open_lots: deque[tuple[TradeFill, int]] = deque()

    for fill in group_fills:
        fill_qty = abs(fill.qty)
        if fill_qty <= 0:
            warnings.append(
                "Skipped fill with non-positive quantity: "
                f"{fill.symbol} {fill.exp} {fill.strike} {fill.option_type} at {fill.exec_datetime}"
            )
            continue

        if fill_qty > 1:
            warnings.append(
                "Detected multi-contract quantity for "
                f"{fill.symbol} {fill.exp} {fill.strike} {fill.option_type}; using qty={fill_qty}."
            )

        if fill.side == "BUY":
            entry_fills_count += 1
            total_entry_qty += fill_qty
            total_entry_notional += fill.price * fill_qty
            open_lots.append((fill, fill_qty))
            continue

        exit_fills_count += 1
        total_exit_qty += fill_qty
        remaining_close_qty = fill_qty

        while remaining_close_qty > 0 and open_lots:
            open_fill, open_remaining_qty = open_lots[0]
            lot_matched_qty = min(open_remaining_qty, remaining_close_qty)
            matched_qty += lot_matched_qty
            matched_entry_notional += open_fill.price * lot_matched_qty
            matched_exit_notional += fill.price * lot_matched_qty
            realized_pnl_usd += (fill.price - open_fill.price) * lot_matched_qty * 100

            open_remaining_qty -= lot_matched_qty
            remaining_close_qty -= lot_matched_qty

            if open_remaining_qty <= 0:
                open_lots.popleft()
            else:
                open_lots[0] = (open_fill, open_remaining_qty)

        if remaining_close_qty > 0:
            unmatched_close_fill = _copy_fill_with_qty(fill, remaining_close_qty)
            unmatched_closes.append(unmatched_close_fill)
            warnings.append(
                "Close fill without matching open: "
                f"{symbol} {exp} {strike} {option_type} at {fill.exec_datetime}"
            )

    for remaining_open_fill, remaining_open_qty in open_lots:
        unmatched_open_fill = _copy_fill_with_qty(remaining_open_fill, remaining_open_qty)
        unmatched_opens.append(unmatched_open_fill)
        warnings.append(
            "Unmatched open fill: "
            f"{symbol} {exp} {strike} {option_type} at {remaining_open_fill.exec_datetime}"
        )

    has_entries = total_entry_qty > 0
    has_exits = total_exit_qty > 0
    if not has_entries or not has_exits or matched_qty <= 0:
        return None, unmatched_opens, unmatched_closes

    avg_entry_price = round(total_entry_notional / total_entry_qty, 4)
    avg_exit_price = round(matched_exit_notional / matched_qty, 4)
    matched_entry_price = round(matched_entry_notional / matched_qty, 4)
    realized_pnl_usd = round(realized_pnl_usd, 2)
    is_partial = total_entry_qty != total_exit_qty
    if is_partial:
        warnings.append(
            "Partial grouped trade detected for "
            f"{symbol} {exp} {strike} {option_type} on {trade_date.isoformat()}: "
            f"entry_qty={total_entry_qty}, exit_qty={total_exit_qty}."
        )

    first_fill_time = group_fills[0].exec_datetime
    last_fill_time = group_fills[-1].exec_datetime
    duration_seconds = max(0, int((last_fill_time - first_fill_time).total_seconds()))

    grouped_trade = DetectedTradePreview(
        temp_id=_build_group_temp_id(group_key, group_fills),
        date=trade_date.isoformat(),
        symbol=symbol,
        exp=exp,
        strike=strike,
        option_type=option_type,
        entry_fills_count=entry_fills_count,
        exit_fills_count=exit_fills_count,
        total_entry_qty=total_entry_qty,
        total_exit_qty=total_exit_qty,
        matched_qty=matched_qty,
        avg_entry_price=avg_entry_price,
        avg_exit_price=avg_exit_price,
        total_pnl_usd=realized_pnl_usd,
        duration_seconds=duration_seconds,
        is_partial=is_partial,
        fills=[_fill_preview_row(fill) for fill in group_fills],
        ticker=symbol,
        direction=option_type,
        quantity=matched_qty,
        entry_time=first_fill_time.strftime("%H:%M:%S"),
        exit_time=last_fill_time.strftime("%H:%M:%S"),
        entry_price=matched_entry_price,
        exit_price=avg_exit_price,
    )
    return grouped_trade, unmatched_opens, unmatched_closes


def _copy_fill_with_qty(fill: TradeFill, qty: int) -> TradeFill:
    return TradeFill(
        exec_datetime=fill.exec_datetime,
        side=fill.side,
        qty=qty,
        pos_effect=fill.pos_effect,
        symbol=fill.symbol,
        exp=fill.exp,
        strike=fill.strike,
        option_type=fill.option_type,
        price=fill.price,
    )


def _build_group_temp_id(
    group_key: tuple[str, str, float, str, date], group_fills: list[TradeFill]
) -> str:
    symbol, exp, strike, option_type, trade_date = group_key
    parts = [
        symbol,
        exp,
        str(strike),
        option_type,
        trade_date.isoformat(),
    ]
    for fill in group_fills:
        parts.extend(
            [
                fill.exec_datetime.isoformat(),
                fill.side,
                str(abs(fill.qty)),
                fill.pos_effect,
                str(fill.price),
            ]
        )
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
