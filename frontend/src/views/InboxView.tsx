import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createEmotion,
  createSetup,
  getEmotions,
  getSetups,
  getTrades,
  patchTrade,
  updateTradesBulk,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { EmotionOptionResponse } from "../types/emotion";
import { SetupOptionResponse } from "../types/setup";
import { TradeResponse } from "../types/trade";
import { formatDateLong, formatUsd } from "../utils/formatting";
import {
  clearLastUsedEmotionId,
  clearLastUsedSetupId,
  clearLastUsedTaggingDefaults,
  getLastUsedEmotionId,
  getLastUsedRuleFollowed,
  getLastUsedSetupId,
  setLastUsedEmotionId,
  setLastUsedRuleFollowed,
  setLastUsedSetupId,
} from "../utils/lastUsedClassification";
import "./InboxView.css";

interface InboxViewProps {
  refreshKey: number;
  setupRefreshKey: number;
  emotionRefreshKey: number;
  onTradeDeleted: () => void;
}

type RuleBulkSelection = "" | "true" | "false" | "unknown";
type RowRuleSelection = "true" | "false" | "unknown";

interface InboxRowDraft {
  setupId: string;
  emotionId: string;
  ruleValue: RowRuleSelection;
  isSaving: boolean;
  error: string | null;
  showNewSetup: boolean;
  newSetupName: string;
  newSetupError: string | null;
  isCreatingSetup: boolean;
  showNewEmotion: boolean;
  newEmotionName: string;
  newEmotionError: string | null;
  isCreatingEmotion: boolean;
}

const INBOX_AUTO_ADVANCE_STORAGE_KEY = "inbox_auto_advance";

function sortSetupOptions(options: SetupOptionResponse[]): SetupOptionResponse[] {
  return [...options].sort((left, right) => {
    const leftOrder = left.sort_order ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = right.sort_order ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.name.localeCompare(right.name);
  });
}

function sortEmotionOptions(options: EmotionOptionResponse[]): EmotionOptionResponse[] {
  return [...options].sort((left, right) => {
    const leftOrder = left.sort_order ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = right.sort_order ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.name.localeCompare(right.name);
  });
}

function getRuleSelectionFromTrade(trade: TradeResponse): RowRuleSelection {
  if (trade.rule_followed === true) {
    return "true";
  }
  if (trade.rule_followed === false) {
    return "false";
  }
  return "unknown";
}

function createRowDraft(trade: TradeResponse): InboxRowDraft {
  return {
    setupId:
      trade.setup_id !== null && trade.setup_id !== undefined ? String(trade.setup_id) : "",
    emotionId:
      trade.emotion_id !== null && trade.emotion_id !== undefined ? String(trade.emotion_id) : "",
    ruleValue: getRuleSelectionFromTrade(trade),
    isSaving: false,
    error: null,
    showNewSetup: false,
    newSetupName: "",
    newSetupError: null,
    isCreatingSetup: false,
    showNewEmotion: false,
    newEmotionName: "",
    newEmotionError: null,
    isCreatingEmotion: false,
  };
}

export function InboxView({
  refreshKey,
  setupRefreshKey,
  emotionRefreshKey,
  onTradeDeleted,
}: InboxViewProps) {
  const [trades, setTrades] = useState<TradeResponse[]>([]);
  const [setupOptions, setSetupOptions] = useState<SetupOptionResponse[]>([]);
  const [emotionOptions, setEmotionOptions] = useState<EmotionOptionResponse[]>([]);
  const [selectedById, setSelectedById] = useState<Record<number, boolean>>({});
  const [bulkSetupId, setBulkSetupId] = useState(() => getLastUsedSetupId());
  const [bulkEmotionId, setBulkEmotionId] = useState(() => getLastUsedEmotionId());
  const [bulkRuleFollowed, setBulkRuleFollowed] = useState<RuleBulkSelection>(
    () => getLastUsedRuleFollowed() || ""
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [bulkErrors, setBulkErrors] = useState<string[]>([]);
  const [activeRowIndex, setActiveRowIndex] = useState(-1);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [rowDraftsById, setRowDraftsById] = useState<Record<number, InboxRowDraft>>({});
  const [isAutoAdvanceEnabled, setIsAutoAdvanceEnabled] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return true;
    }
    try {
      const saved = window.localStorage.getItem(INBOX_AUTO_ADVANCE_STORAGE_KEY);
      return saved === null ? true : saved === "true";
    } catch {
      return true;
    }
  });
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});
  const setupSelectRef = useRef<HTMLSelectElement | null>(null);
  const emotionSelectRef = useRef<HTMLSelectElement | null>(null);
  const selectAllCheckboxRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        INBOX_AUTO_ADVANCE_STORAGE_KEY,
        isAutoAdvanceEnabled ? "true" : "false"
      );
    }
  }, [isAutoAdvanceEnabled]);

  useEffect(() => {
    async function loadClassifications() {
      try {
        const [setupsResponse, emotionsResponse] = await Promise.all([
          getSetups(false),
          getEmotions(false),
        ]);
        setSetupOptions(sortSetupOptions(setupsResponse));
        setEmotionOptions(sortEmotionOptions(emotionsResponse));
        const storedSetupId = getLastUsedSetupId();
        const storedEmotionId = getLastUsedEmotionId();
        const hasStoredSetup =
          storedSetupId && setupsResponse.some((option) => String(option.id) === storedSetupId);
        const hasStoredEmotion =
          storedEmotionId &&
          emotionsResponse.some((option) => String(option.id) === storedEmotionId);

        if (storedSetupId && !hasStoredSetup) {
          clearLastUsedSetupId();
        }
        if (storedEmotionId && !hasStoredEmotion) {
          clearLastUsedEmotionId();
        }

        setBulkSetupId((previous) => {
          if (previous && setupsResponse.some((option) => String(option.id) === previous)) {
            return previous;
          }
          if (hasStoredSetup) {
            return storedSetupId;
          }
          return "";
        });
        setBulkEmotionId((previous) => {
          if (previous && emotionsResponse.some((option) => String(option.id) === previous)) {
            return previous;
          }
          if (hasStoredEmotion) {
            return storedEmotionId;
          }
          return "";
        });
        setBulkRuleFollowed((previous) => {
          if (previous) {
            return previous;
          }
          return getLastUsedRuleFollowed() || "";
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to load setup/emotion options.";
        setErrorMessage(message);
      }
    }

    void loadClassifications();
  }, [setupRefreshKey, emotionRefreshKey]);

  const loadTrades = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await getTrades({
        classification: "unclassified",
        include_fills: true,
      });
      setTrades(response);
      setSelectedById({});
      setActiveRowIndex(response.length > 0 ? 0 : -1);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load unclassified trades.";
      setErrorMessage(message);
      setTrades([]);
      setSelectedById({});
      setActiveRowIndex(-1);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTrades();
  }, [loadTrades, refreshKey]);

  useEffect(() => {
    setRowDraftsById(
      Object.fromEntries(trades.map((trade) => [trade.id, createRowDraft(trade)]))
    );
  }, [trades]);

  const selectedTradeIds = useMemo(
    () => trades.filter((trade) => selectedById[trade.id]).map((trade) => trade.id),
    [selectedById, trades]
  );

  const selectedCount = selectedTradeIds.length;
  const allSelected = trades.length > 0 && selectedCount === trades.length;
  const someSelected = selectedCount > 0 && !allSelected;
  const hasBulkChanges = Boolean(bulkSetupId || bulkEmotionId || bulkRuleFollowed);
  const canApplyBulk = selectedCount > 0 && hasBulkChanges && !isApplying;
  const hasTrades = trades.length > 0;

  const activeTrade = activeRowIndex >= 0 && activeRowIndex < trades.length
    ? trades[activeRowIndex]
    : null;

  function updateRowDraft(
    tradeId: number,
    updater: (draft: InboxRowDraft) => InboxRowDraft
  ): void {
    setRowDraftsById((previous) => {
      const currentDraft = previous[tradeId];
      if (!currentDraft) {
        return previous;
      }
      return {
        ...previous,
        [tradeId]: updater(currentDraft),
      };
    });
  }

  function getTradeById(tradeId: number): TradeResponse | undefined {
    return trades.find((trade) => trade.id === tradeId);
  }

  function isRowDirty(trade: TradeResponse, draft: InboxRowDraft): boolean {
    const currentSetupId =
      trade.setup_id !== null && trade.setup_id !== undefined ? String(trade.setup_id) : "";
    const currentEmotionId =
      trade.emotion_id !== null && trade.emotion_id !== undefined ? String(trade.emotion_id) : "";
    const currentRule = getRuleSelectionFromTrade(trade);

    return (
      draft.setupId !== currentSetupId ||
      draft.emotionId !== currentEmotionId ||
      draft.ruleValue !== currentRule
    );
  }

  function isTradeClassified(trade: TradeResponse): boolean {
    return (
      trade.setup_id !== null &&
      trade.setup_id !== undefined &&
      trade.emotion_id !== null &&
      trade.emotion_id !== undefined &&
      trade.rule_followed !== null &&
      trade.rule_followed !== undefined
    );
  }

  function getClampedIndex(index: number, listLength: number): number {
    if (listLength <= 0) {
      return -1;
    }
    if (index < 0) {
      return 0;
    }
    if (index >= listLength) {
      return listLength - 1;
    }
    return index;
  }

  const applyTradeUpdateToList = useCallback(
    (updatedTrade: TradeResponse, tradeId: number, options: { shouldAdvance: boolean }) => {
      const currentIndex = trades.findIndex((trade) => trade.id === tradeId);
      if (currentIndex === -1) {
        return;
      }

      const shouldRemove = isTradeClassified(updatedTrade);
      const nextTrades = shouldRemove
        ? trades.filter((trade) => trade.id !== tradeId)
        : trades.map((trade) => (trade.id === tradeId ? updatedTrade : trade));
      setTrades(nextTrades);
      setSelectedById((previous) => {
        if (!previous[tradeId]) {
          return previous;
        }
        const next = { ...previous };
        delete next[tradeId];
        return next;
      });

      if (nextTrades.length === 0) {
        setActiveRowIndex(-1);
        return;
      }

      if (options.shouldAdvance) {
        const advanceTarget = shouldRemove ? currentIndex : currentIndex + 1;
        setActiveRowIndex(getClampedIndex(advanceTarget, nextTrades.length));
        return;
      }

      if (shouldRemove) {
        setActiveRowIndex(getClampedIndex(currentIndex, nextTrades.length));
      }
    },
    [trades]
  );

  async function handleSaveRow(tradeId: number): Promise<void> {
    const trade = getTradeById(tradeId);
    const draft = rowDraftsById[tradeId];
    if (!trade || !draft || draft.isSaving || !isRowDirty(trade, draft)) {
      return;
    }

    const payload: { setup_id?: number | null; emotion_id?: number | null; rule_followed?: boolean | null } = {};
    const currentSetupId =
      trade.setup_id !== null && trade.setup_id !== undefined ? String(trade.setup_id) : "";
    const currentEmotionId =
      trade.emotion_id !== null && trade.emotion_id !== undefined ? String(trade.emotion_id) : "";
    const currentRule = getRuleSelectionFromTrade(trade);

    if (draft.setupId !== currentSetupId) {
      payload.setup_id = draft.setupId ? Number(draft.setupId) : null;
    }
    if (draft.emotionId !== currentEmotionId) {
      payload.emotion_id = draft.emotionId ? Number(draft.emotionId) : null;
    }
    if (draft.ruleValue !== currentRule) {
      payload.rule_followed =
        draft.ruleValue === "true" ? true : draft.ruleValue === "false" ? false : null;
    }

    updateRowDraft(tradeId, (currentDraft) => ({
      ...currentDraft,
      isSaving: true,
      error: null,
    }));

    try {
      const updatedTrade = await patchTrade(tradeId, payload);
      if (draft.setupId) {
        setLastUsedSetupId(draft.setupId);
      } else {
        clearLastUsedSetupId();
      }
      if (draft.emotionId) {
        setLastUsedEmotionId(draft.emotionId);
      } else {
        clearLastUsedEmotionId();
      }
      setLastUsedRuleFollowed(draft.ruleValue);
      setStatusMessage(`Trade #${tradeId} updated.`);
      setErrorMessage(null);
      applyTradeUpdateToList(updatedTrade, tradeId, {
        shouldAdvance: isAutoAdvanceEnabled && activeTrade?.id === tradeId,
      });
      onTradeDeleted();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update trade.";
      updateRowDraft(tradeId, (currentDraft) => ({
        ...currentDraft,
        isSaving: false,
        error: message,
      }));
      return;
    }
  }

  function handleRevertRow(tradeId: number): void {
    const trade = getTradeById(tradeId);
    if (!trade) {
      return;
    }
    setRowDraftsById((previous) => ({
      ...previous,
      [tradeId]: createRowDraft(trade),
    }));
  }

  function openInlineSetupCreate(tradeId: number): void {
    updateRowDraft(tradeId, (draft) => ({
      ...draft,
      showNewSetup: true,
      newSetupError: null,
    }));
  }

  function cancelInlineSetupCreate(tradeId: number): void {
    updateRowDraft(tradeId, (draft) => ({
      ...draft,
      showNewSetup: false,
      newSetupName: "",
      newSetupError: null,
      isCreatingSetup: false,
    }));
  }

  async function handleCreateSetupInline(tradeId: number): Promise<void> {
    const draft = rowDraftsById[tradeId];
    if (!draft || draft.isCreatingSetup) {
      return;
    }

    const normalizedName = draft.newSetupName.trim();
    if (!normalizedName) {
      updateRowDraft(tradeId, (currentDraft) => ({
        ...currentDraft,
        newSetupError: "Setup name is required.",
      }));
      return;
    }

    updateRowDraft(tradeId, (currentDraft) => ({
      ...currentDraft,
      isCreatingSetup: true,
      newSetupError: null,
    }));

    try {
      const created = await createSetup({ name: normalizedName });
      setSetupOptions((previous) => sortSetupOptions([...previous, created]));
      setRowDraftsById((previous) => {
        const nextDrafts = { ...previous };
        for (const [id, currentDraft] of Object.entries(previous)) {
          nextDrafts[Number(id)] = {
            ...currentDraft,
            setupId: Number(id) === tradeId ? String(created.id) : currentDraft.setupId,
            showNewSetup: Number(id) === tradeId ? false : currentDraft.showNewSetup,
            newSetupName: Number(id) === tradeId ? "" : currentDraft.newSetupName,
            newSetupError: Number(id) === tradeId ? null : currentDraft.newSetupError,
            isCreatingSetup: false,
          };
        }
        return nextDrafts;
      });
    } catch (error) {
      updateRowDraft(tradeId, (currentDraft) => ({
        ...currentDraft,
        isCreatingSetup: false,
        newSetupError: error instanceof Error ? error.message : "This name already exists.",
      }));
    }
  }

  function openInlineEmotionCreate(tradeId: number): void {
    updateRowDraft(tradeId, (draft) => ({
      ...draft,
      showNewEmotion: true,
      newEmotionError: null,
    }));
  }

  function cancelInlineEmotionCreate(tradeId: number): void {
    updateRowDraft(tradeId, (draft) => ({
      ...draft,
      showNewEmotion: false,
      newEmotionName: "",
      newEmotionError: null,
      isCreatingEmotion: false,
    }));
  }

  async function handleCreateEmotionInline(tradeId: number): Promise<void> {
    const draft = rowDraftsById[tradeId];
    if (!draft || draft.isCreatingEmotion) {
      return;
    }

    const normalizedName = draft.newEmotionName.trim();
    if (!normalizedName) {
      updateRowDraft(tradeId, (currentDraft) => ({
        ...currentDraft,
        newEmotionError: "Emotion name is required.",
      }));
      return;
    }

    updateRowDraft(tradeId, (currentDraft) => ({
      ...currentDraft,
      isCreatingEmotion: true,
      newEmotionError: null,
    }));

    try {
      const created = await createEmotion({ name: normalizedName });
      setEmotionOptions((previous) => sortEmotionOptions([...previous, created]));
      setRowDraftsById((previous) => {
        const nextDrafts = { ...previous };
        for (const [id, currentDraft] of Object.entries(previous)) {
          nextDrafts[Number(id)] = {
            ...currentDraft,
            emotionId: Number(id) === tradeId ? String(created.id) : currentDraft.emotionId,
            showNewEmotion: Number(id) === tradeId ? false : currentDraft.showNewEmotion,
            newEmotionName: Number(id) === tradeId ? "" : currentDraft.newEmotionName,
            newEmotionError: Number(id) === tradeId ? null : currentDraft.newEmotionError,
            isCreatingEmotion: false,
          };
        }
        return nextDrafts;
      });
    } catch (error) {
      updateRowDraft(tradeId, (currentDraft) => ({
        ...currentDraft,
        isCreatingEmotion: false,
        newEmotionError: error instanceof Error ? error.message : "This name already exists.",
      }));
    }
  }

  const handleApplyBulk = useCallback(async () => {
    if (!canApplyBulk || selectedCount === 0) {
      return;
    }

    setIsApplying(true);
    setErrorMessage(null);
    setStatusMessage(null);
    setBulkErrors([]);

    try {
      const payload: {
        trade_ids: number[];
        setup_id?: number;
        emotion_id?: number;
        rule_followed?: boolean | null;
      } = {
        trade_ids: selectedTradeIds,
      };

      if (bulkSetupId) {
        payload.setup_id = Number(bulkSetupId);
      }
      if (bulkEmotionId) {
        payload.emotion_id = Number(bulkEmotionId);
      }
      if (bulkRuleFollowed === "true") {
        payload.rule_followed = true;
      } else if (bulkRuleFollowed === "false") {
        payload.rule_followed = false;
      } else if (bulkRuleFollowed === "unknown") {
        payload.rule_followed = null;
      }

      const response = await updateTradesBulk(payload);
      setStatusMessage(
        `Updated ${response.updated_count} trade${response.updated_count === 1 ? "" : "s"}.`
      );
      setBulkErrors(response.errors);
      if (response.updated_count > 0) {
        if (bulkSetupId) {
          setLastUsedSetupId(bulkSetupId);
        }
        if (bulkEmotionId) {
          setLastUsedEmotionId(bulkEmotionId);
        }
        if (bulkRuleFollowed) {
          setLastUsedRuleFollowed(bulkRuleFollowed);
        }
      }

      const isSingleSelection = selectedTradeIds.length === 1;
      if (response.updated_count > 0 && isSingleSelection) {
        const selectedTradeId = selectedTradeIds[0];
        const currentTrade = trades.find((trade) => trade.id === selectedTradeId);

        if (currentTrade) {
          const updatedTrade: TradeResponse = {
            ...currentTrade,
            setup_id: bulkSetupId ? Number(bulkSetupId) : currentTrade.setup_id,
            emotion_id: bulkEmotionId ? Number(bulkEmotionId) : currentTrade.emotion_id,
            rule_followed:
              bulkRuleFollowed === "true"
                ? true
                : bulkRuleFollowed === "false"
                  ? false
                  : bulkRuleFollowed === "unknown"
                    ? null
                    : currentTrade.rule_followed,
          };

          applyTradeUpdateToList(updatedTrade, selectedTradeId, {
            shouldAdvance: isAutoAdvanceEnabled,
          });
        } else {
          await loadTrades();
        }

        setSelectedById({});
      } else {
        setSelectedById({});
        await loadTrades();
      }

      if (response.updated_count > 0) {
        onTradeDeleted();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to apply bulk update.";
      setErrorMessage(message);
    } finally {
      setIsApplying(false);
    }
  }, [
    applyTradeUpdateToList,
    bulkEmotionId,
    bulkRuleFollowed,
    bulkSetupId,
    canApplyBulk,
    isAutoAdvanceEnabled,
    loadTrades,
    onTradeDeleted,
    selectedCount,
    selectedTradeIds,
    trades,
  ]);

  useEffect(() => {
    if (!activeTrade) {
      return;
    }
    const activeRow = rowRefs.current[activeTrade.id];
    activeRow?.scrollIntoView({ block: "nearest" });
  }, [activeTrade]);

  useEffect(() => {
    if (!selectAllCheckboxRef.current) {
      return;
    }
    selectAllCheckboxRef.current.indeterminate = someSelected;
  }, [someSelected]);

  useEffect(() => {
    function isTypingTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      const tagName = target.tagName.toLowerCase();
      if (tagName === "input" || tagName === "textarea" || tagName === "select" || tagName === "button") {
        return true;
      }
      if (target.isContentEditable) {
        return true;
      }
      return Boolean(
        target.closest(
          "input, textarea, select, button, [contenteditable='true'], .inbox-row-editor, .inbox-row-actions"
        )
      );
    }

    function moveActiveRow(offset: number): void {
      if (!hasTrades) {
        return;
      }
      setActiveRowIndex((previous) => {
        const currentIndex = previous < 0 ? 0 : previous;
        const nextIndex = Math.min(Math.max(currentIndex + offset, 0), trades.length - 1);
        return nextIndex;
      });
    }

    function toggleActiveRowSelection(): void {
      if (!activeTrade) {
        return;
      }
      setSelectedById((previous) => ({
        ...previous,
        [activeTrade.id]: !previous[activeTrade.id],
      }));
    }

    function cycleRuleSelection(): void {
      setBulkRuleFollowed((previous) => {
        if (previous === "" || previous === "unknown") {
          return "true";
        }
        if (previous === "true") {
          return "false";
        }
        return "unknown";
      });
    }

    function onKeyDown(event: KeyboardEvent): void {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }

      if (event.key === "?") {
        event.preventDefault();
        setIsShortcutsOpen((previous) => !previous);
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        if (isShortcutsOpen) {
          setIsShortcutsOpen(false);
          return;
        }
        setSelectedById({});
        return;
      }

      if (event.key === "j") {
        event.preventDefault();
        moveActiveRow(1);
        return;
      }

      if (event.key === "k") {
        event.preventDefault();
        moveActiveRow(-1);
        return;
      }

      if (event.key === "g") {
        event.preventDefault();
        if (hasTrades) {
          setActiveRowIndex(0);
        }
        return;
      }

      if (event.key === "G" || (event.key === "g" && event.shiftKey)) {
        event.preventDefault();
        if (hasTrades) {
          setActiveRowIndex(trades.length - 1);
        }
        return;
      }

      if (event.key === " ") {
        event.preventDefault();
        toggleActiveRowSelection();
        return;
      }

      if (event.key === "a") {
        event.preventDefault();
        setSelectedById(() => {
          if (allSelected) {
            return {};
          }
          const nextState: Record<number, boolean> = {};
          for (const trade of trades) {
            nextState[trade.id] = true;
          }
          return nextState;
        });
        return;
      }

      if (event.key === "r") {
        event.preventDefault();
        cycleRuleSelection();
        return;
      }

      if (event.key === "s") {
        event.preventDefault();
        setupSelectRef.current?.focus();
        return;
      }

      if (event.key === "e") {
        event.preventDefault();
        emotionSelectRef.current?.focus();
        return;
      }

      if (event.key === "Enter") {
        if (!canApplyBulk) {
          return;
        }
        event.preventDefault();
        void handleApplyBulk();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [
    activeTrade,
    allSelected,
    canApplyBulk,
    handleApplyBulk,
    hasTrades,
    isShortcutsOpen,
    trades,
  ]);

  function toggleSelectAll(checked: boolean) {
    const nextState: Record<number, boolean> = {};
    if (checked) {
      for (const trade of trades) {
        nextState[trade.id] = true;
      }
    }
    setSelectedById(nextState);
  }

  function toggleSelectTrade(tradeId: number, checked: boolean) {
    setSelectedById((previous) => ({ ...previous, [tradeId]: checked }));
  }

  function handleBulkSetupChange(setupId: string) {
    setBulkSetupId(setupId);
  }

  function handleBulkEmotionChange(emotionId: string) {
    setBulkEmotionId(emotionId);
  }

  function handleClearSelection() {
    setSelectedById({});
  }

  function handleClearDefaults() {
    clearLastUsedTaggingDefaults();
    setBulkSetupId("");
    setBulkEmotionId("");
    setBulkRuleFollowed("");
  }

  return (
    <section className="single-view-grid">
      <section className="inbox-panel">
        <div className="inbox-header">
          <h2 className="inbox-title">Unclassified Trades ({trades.length})</h2>
          <div className="inbox-header-controls">
            <label
              className="inbox-auto-advance-toggle"
              title="After updating a trade, move to the next one automatically."
            >
              <input
                type="checkbox"
                checked={isAutoAdvanceEnabled}
                onChange={(event) => setIsAutoAdvanceEnabled(event.target.checked)}
              />
              Auto-advance
            </label>
            <button
              type="button"
              className="inbox-shortcuts-button"
              onClick={() => setIsShortcutsOpen((previous) => !previous)}
              aria-expanded={isShortcutsOpen}
            >
              Shortcuts ?
            </button>
          </div>
        </div>

        {isShortcutsOpen ? (
          <section className="inbox-shortcuts-panel" role="dialog" aria-label="Keyboard shortcuts">
            <h3>Keyboard Shortcuts</h3>
            <ul>
              <li>`j` / `k`: move active row down/up</li>
              <li>`g` / `G`: jump to top/bottom</li>
              <li>`Space`: toggle selection for active row</li>
              <li>`a`: select all / clear all</li>
              <li>`r`: cycle rule (Followed, Broken, Unknown)</li>
              <li>`s` / `e`: focus setup/emotion bulk dropdown</li>
              <li>`Enter`: apply bulk changes</li>
              <li>`Esc`: close shortcuts or clear selection</li>
              <li>`?`: toggle this panel</li>
            </ul>
          </section>
        ) : null}

        {errorMessage ? <p className="inbox-status error">{errorMessage}</p> : null}
        {statusMessage ? <p className="inbox-status success">{statusMessage}</p> : null}
        {bulkErrors.length > 0 ? (
          <details className="inbox-errors">
            <summary>Some updates were not applied ({bulkErrors.length})</summary>
            <ul>
              {bulkErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </details>
        ) : null}
        {isLoading ? <p className="inbox-status">Loading unclassified trades...</p> : null}

        {!isLoading && trades.length === 0 ? (
          <EmptyState
            title="Inbox is clear."
            description="All trades are currently classified."
            tone="positive"
            compact
          />
        ) : null}

        {!isLoading && selectedCount > 0 ? (
          <div className="inbox-bulk-bar">
            <span>Selected: {selectedCount}</span>
            <select
              ref={setupSelectRef}
              value={bulkSetupId}
              onChange={(event) => handleBulkSetupChange(event.target.value)}
            >
              <option value="">No setup change</option>
              {setupOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
            <select
              ref={emotionSelectRef}
              value={bulkEmotionId}
              onChange={(event) => handleBulkEmotionChange(event.target.value)}
            >
              <option value="">No emotion change</option>
              {emotionOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
            <select
              value={bulkRuleFollowed}
              onChange={(event) => setBulkRuleFollowed(event.target.value as RuleBulkSelection)}
            >
              <option value="">No rule change</option>
              <option value="true">Followed</option>
              <option value="false">Broken</option>
              <option value="unknown">Unknown</option>
            </select>
            <button
              type="button"
              onClick={() => void handleApplyBulk()}
              disabled={!canApplyBulk || isApplying}
            >
              {isApplying ? "Applying..." : "Apply to Selected"}
            </button>
            <button type="button" className="clear-selection-button" onClick={handleClearSelection}>
              Clear selection
            </button>
            <button type="button" className="clear-defaults-button" onClick={handleClearDefaults}>
              Clear defaults
            </button>
          </div>
        ) : null}

        {!isLoading && trades.length > 0 ? (
          <div className="inbox-table-wrap">
            <table className="inbox-table">
              <thead>
                <tr>
                  <th>
                    <input
                      ref={selectAllCheckboxRef}
                      type="checkbox"
                      checked={allSelected}
                      aria-checked={someSelected ? "mixed" : allSelected}
                      onChange={(event) => toggleSelectAll(event.target.checked)}
                      aria-label="Select all unclassified trades"
                    />
                  </th>
                  <th>Date</th>
                  <th>Ticker</th>
                  <th>Direction</th>
                  <th>Total PnL (USD)</th>
                  <th>Setup</th>
                  <th>Emotion</th>
                  <th>Rule</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade, index) => {
                  const draft = rowDraftsById[trade.id] ?? createRowDraft(trade);
                  const isDirty = isRowDirty(trade, draft);

                  return (
                    <tr
                      key={trade.id}
                      ref={(node) => {
                        rowRefs.current[trade.id] = node;
                      }}
                      className={index === activeRowIndex ? "inbox-active-row" : undefined}
                      onClick={() => setActiveRowIndex(index)}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedById[trade.id])}
                          onChange={(event) => toggleSelectTrade(trade.id, event.target.checked)}
                          aria-label={`Select trade ${trade.id}`}
                        />
                      </td>
                      <td>{formatDateLong(trade.date)}</td>
                      <td>{trade.ticker}</td>
                      <td>{trade.direction}</td>
                      <td>{formatUsd(trade.total_pnl_usd)}</td>
                      <td>
                        <div className="inbox-row-editor">
                          <select
                            value={draft.setupId}
                            onChange={(event) =>
                              updateRowDraft(trade.id, (currentDraft) => ({
                                ...currentDraft,
                                setupId: event.target.value,
                                error: null,
                              }))
                            }
                            disabled={draft.isSaving || draft.isCreatingSetup}
                          >
                            <option value="">
                              {setupOptions.length === 0 ? "No setups yet" : "No setup"}
                            </option>
                            {setupOptions.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="inbox-inline-create-trigger"
                            onClick={() => openInlineSetupCreate(trade.id)}
                            disabled={draft.isSaving || draft.isCreatingSetup}
                          >
                            + New Setup
                          </button>
                          {draft.showNewSetup ? (
                            <div className="inbox-inline-create">
                              <input
                                type="text"
                                value={draft.newSetupName}
                                placeholder="Setup name"
                                autoFocus
                                onChange={(event) =>
                                  updateRowDraft(trade.id, (currentDraft) => ({
                                    ...currentDraft,
                                    newSetupName: event.target.value,
                                    newSetupError: null,
                                  }))
                                }
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    void handleCreateSetupInline(trade.id);
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    cancelInlineSetupCreate(trade.id);
                                  }
                                }}
                              />
                              <div className="inbox-inline-create-actions">
                                <button
                                  type="button"
                                  onClick={() => void handleCreateSetupInline(trade.id)}
                                  disabled={draft.isCreatingSetup}
                                >
                                  {draft.isCreatingSetup ? "Saving..." : "Save"}
                                </button>
                                <button type="button" onClick={() => cancelInlineSetupCreate(trade.id)}>
                                  Cancel
                                </button>
                              </div>
                              {draft.newSetupError ? (
                                <span className="inbox-inline-error">{draft.newSetupError}</span>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="inbox-row-editor">
                          <select
                            value={draft.emotionId}
                            onChange={(event) =>
                              updateRowDraft(trade.id, (currentDraft) => ({
                                ...currentDraft,
                                emotionId: event.target.value,
                                error: null,
                              }))
                            }
                            disabled={draft.isSaving || draft.isCreatingEmotion}
                          >
                            <option value="">
                              {emotionOptions.length === 0 ? "No emotions yet" : "No emotion"}
                            </option>
                            {emotionOptions.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="inbox-inline-create-trigger"
                            onClick={() => openInlineEmotionCreate(trade.id)}
                            disabled={draft.isSaving || draft.isCreatingEmotion}
                          >
                            + New Emotion
                          </button>
                          {draft.showNewEmotion ? (
                            <div className="inbox-inline-create">
                              <input
                                type="text"
                                value={draft.newEmotionName}
                                placeholder="Emotion name"
                                autoFocus
                                onChange={(event) =>
                                  updateRowDraft(trade.id, (currentDraft) => ({
                                    ...currentDraft,
                                    newEmotionName: event.target.value,
                                    newEmotionError: null,
                                  }))
                                }
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    void handleCreateEmotionInline(trade.id);
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    cancelInlineEmotionCreate(trade.id);
                                  }
                                }}
                              />
                              <div className="inbox-inline-create-actions">
                                <button
                                  type="button"
                                  onClick={() => void handleCreateEmotionInline(trade.id)}
                                  disabled={draft.isCreatingEmotion}
                                >
                                  {draft.isCreatingEmotion ? "Saving..." : "Save"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => cancelInlineEmotionCreate(trade.id)}
                                >
                                  Cancel
                                </button>
                              </div>
                              {draft.newEmotionError ? (
                                <span className="inbox-inline-error">{draft.newEmotionError}</span>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="inbox-row-editor">
                          <select
                            value={draft.ruleValue}
                            onChange={(event) =>
                              updateRowDraft(trade.id, (currentDraft) => ({
                                ...currentDraft,
                                ruleValue: event.target.value as RowRuleSelection,
                                error: null,
                              }))
                            }
                            disabled={draft.isSaving}
                          >
                            <option value="true">Followed</option>
                            <option value="false">Broken</option>
                            <option value="unknown">Unknown</option>
                          </select>
                          <div className="inbox-row-actions">
                            <button
                              type="button"
                              onClick={() => void handleSaveRow(trade.id)}
                              disabled={
                                !isDirty ||
                                draft.isSaving ||
                                draft.isCreatingSetup ||
                                draft.isCreatingEmotion ||
                                draft.showNewSetup ||
                                draft.showNewEmotion
                              }
                            >
                              {draft.isSaving ? "Saving..." : "Save"}
                            </button>
                            <button
                              type="button"
                              className="secondary"
                              onClick={() => handleRevertRow(trade.id)}
                              disabled={!isDirty || draft.isSaving}
                            >
                              Revert
                            </button>
                          </div>
                          {draft.error ? <span className="inbox-inline-error">{draft.error}</span> : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </section>
  );
}
