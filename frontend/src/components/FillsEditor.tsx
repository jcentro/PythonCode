import { useMemo } from "react";

import { TradeFillSide } from "../types/trade";
import { FillDraftRow, computeFillSummary, createEmptyFillRow } from "../utils/fills";
import { formatNumber, formatUsd } from "../utils/formatting";
import "./FillsEditor.css";

interface FillsEditorProps {
  rows: FillDraftRow[];
  onChange: (rows: FillDraftRow[]) => void;
  disabled?: boolean;
}

const sideOptions: TradeFillSide[] = ["BUY", "SELL"];

function formatSummaryPrice(value: number | null): string {
  return value === null ? "-" : formatNumber(value);
}

export function FillsEditor({ rows, onChange, disabled = false }: FillsEditorProps) {
  const summary = useMemo(() => computeFillSummary(rows), [rows]);

  function updateRow(index: number, patch: Partial<FillDraftRow>) {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function addRow(side: TradeFillSide) {
    onChange([...rows, createEmptyFillRow(side)]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, rowIndex) => rowIndex !== index));
  }

  return (
    <div className="fills-editor">
      <div className="fills-table-wrap">
        <table className="fills-table">
          <thead>
            <tr>
              <th>Side</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Time (optional)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.id ?? `new-${index}`}>
                <td>
                  <select
                    value={row.side}
                    onChange={(event) =>
                      updateRow(index, { side: event.target.value as TradeFillSide })
                    }
                    disabled={disabled}
                  >
                    {sideOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={row.quantity}
                    onChange={(event) => updateRow(index, { quantity: event.target.value })}
                    disabled={disabled}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={row.price}
                    onChange={(event) => updateRow(index, { price: event.target.value })}
                    disabled={disabled}
                  />
                </td>
                <td>
                  <input
                    type="datetime-local"
                    value={row.filledAt}
                    onChange={(event) => updateRow(index, { filledAt: event.target.value })}
                    disabled={disabled}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="fills-remove-button"
                    onClick={() => removeRow(index)}
                    disabled={disabled}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="fills-empty">
                  No fills yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="fills-editor-actions">
        <button
          type="button"
          className="fills-add-button"
          onClick={() => addRow("BUY")}
          disabled={disabled}
        >
          Add Buy Fill
        </button>
        <button
          type="button"
          className="fills-add-button"
          onClick={() => addRow("SELL")}
          disabled={disabled}
        >
          Add Sell Fill
        </button>
      </div>

      <div className="fills-summary-grid">
        <div>
          <span>Total Quantity</span>
          <strong>{summary.totalEntryQty}</strong>
        </div>
        <div>
          <span>Avg Entry</span>
          <strong>{formatSummaryPrice(summary.avgEntryPrice)}</strong>
        </div>
        <div>
          <span>Avg Exit</span>
          <strong>{formatSummaryPrice(summary.avgExitPrice)}</strong>
        </div>
        <div>
          <span>Total PnL (USD)</span>
          <strong>{formatUsd(summary.realizedPnlUsd)}</strong>
        </div>
        <div>
          <span>BUY Qty</span>
          <strong>{summary.totalEntryQty}</strong>
        </div>
        <div>
          <span>SELL Qty</span>
          <strong>{summary.totalExitQty}</strong>
        </div>
      </div>
    </div>
  );
}
