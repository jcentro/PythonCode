import { FormEvent, useEffect, useState } from "react";

import { getEmotions, getSetups } from "../api/client";
import { EmotionOptionResponse } from "../types/emotion";
import { SetupOptionResponse } from "../types/setup";
import {
  TradeClassificationFilter,
  TradeOutcomeFilter,
  TradeRuleFollowedFilter,
  TradeSourceFilter,
} from "../types/trade";
import "./TradeFilters.css";

export interface TradeFiltersValue {
  start: string;
  end: string;
  ticker: string;
  setupId: string;
  emotionId: string;
  ruleFollowed: "" | TradeRuleFollowedFilter;
  outcome: "" | TradeOutcomeFilter;
  source: "" | TradeSourceFilter;
  classification: TradeClassificationFilter;
  pattern:
    | ""
    | "after_2_losses_next_trade"
    | "trade_index_after_3"
    | "worst_time_window"
    | "worst_hold_time";
}

interface TradeFiltersProps {
  value: TradeFiltersValue;
  setupRefreshKey?: number;
  emotionRefreshKey?: number;
  onChange: (nextValue: TradeFiltersValue) => void;
  onApply: () => void;
  onClear: () => void;
}

export function TradeFilters({
  value,
  setupRefreshKey = 0,
  emotionRefreshKey = 0,
  onChange,
  onApply,
  onClear,
}: TradeFiltersProps) {
  const [setupOptions, setSetupOptions] = useState<SetupOptionResponse[]>([]);
  const [emotionOptions, setEmotionOptions] = useState<EmotionOptionResponse[]>([]);

  useEffect(() => {
    async function loadSetups() {
      try {
        const response = await getSetups();
        setSetupOptions(response);
      } catch {
        setSetupOptions([]);
      }
    }

    void loadSetups();
  }, [setupRefreshKey]);

  useEffect(() => {
    async function loadEmotions() {
      try {
        const response = await getEmotions();
        setEmotionOptions(response);
      } catch {
        setEmotionOptions([]);
      }
    }

    void loadEmotions();
  }, [emotionRefreshKey]);

  function updateField<Key extends keyof TradeFiltersValue>(field: Key, fieldValue: TradeFiltersValue[Key]) {
    onChange({ ...value, [field]: fieldValue });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply();
  }

  return (
    <form className="trade-filters-form" onSubmit={handleSubmit}>
      <label>
        Start
        <input
          type="date"
          value={value.start}
          onChange={(event) => updateField("start", event.target.value)}
        />
      </label>
      <label>
        End
        <input type="date" value={value.end} onChange={(event) => updateField("end", event.target.value)} />
      </label>
      <label>
        Ticker
        <input
          type="text"
          placeholder="e.g. SPY"
          value={value.ticker}
          onChange={(event) => updateField("ticker", event.target.value)}
        />
      </label>
      <label>
        Setup
        <select value={value.setupId} onChange={(event) => updateField("setupId", event.target.value)}>
          <option value="">All</option>
          {setupOptions.map((option) => (
            <option key={option.id} value={String(option.id)}>
              {option.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Emotion
        <select value={value.emotionId} onChange={(event) => updateField("emotionId", event.target.value)}>
          <option value="">All</option>
          {emotionOptions.map((option) => (
            <option key={option.id} value={String(option.id)}>
              {option.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Rule
        <select
          value={value.ruleFollowed}
          onChange={(event) =>
            updateField("ruleFollowed", event.target.value as TradeFiltersValue["ruleFollowed"])
          }
        >
          <option value="">All</option>
          <option value="true">Followed</option>
          <option value="false">Broken</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>
      <label>
        Outcome
        <select
          value={value.outcome}
          onChange={(event) => updateField("outcome", event.target.value as TradeFiltersValue["outcome"])}
        >
          <option value="">All</option>
          <option value="win">Win</option>
          <option value="loss">Loss</option>
          <option value="breakeven">Breakeven</option>
        </select>
      </label>
      <label>
        Source
        <select
          value={value.source}
          onChange={(event) => updateField("source", event.target.value as TradeFiltersValue["source"])}
        >
          <option value="">All</option>
          <option value="tos_csv">Imported (TOS)</option>
          <option value="manual">Manual</option>
        </select>
      </label>
      <label>
        Classification
        <select
          value={value.classification}
          onChange={(event) =>
            updateField("classification", event.target.value as TradeFiltersValue["classification"])
          }
        >
          <option value="all">All</option>
          <option value="unclassified">Unclassified</option>
          <option value="classified">Classified</option>
        </select>
      </label>
      <label>
        Pattern
        <select
          value={value.pattern}
          onChange={(event) => updateField("pattern", event.target.value as TradeFiltersValue["pattern"])}
        >
          <option value="">None</option>
          <option value="after_2_losses_next_trade">After 2 losses (next trade)</option>
          <option value="trade_index_after_3">Trades 4+</option>
          <option value="worst_time_window" disabled>
            Worst time window (from Statistics)
          </option>
          <option value="worst_hold_time" disabled>
            Worst hold-time (from Statistics)
          </option>
        </select>
      </label>
      <div className="trade-filters-actions">
        <button type="submit">Apply</button>
        <button type="button" className="trade-filters-clear" onClick={onClear}>
          Clear
        </button>
      </div>
    </form>
  );
}
