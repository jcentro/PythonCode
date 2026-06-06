const LAST_USED_SETUP_ID_STORAGE_KEY = "last_setup_id";
const LAST_USED_EMOTION_ID_STORAGE_KEY = "last_emotion_id";
const LAST_USED_RULE_FOLLOWED_STORAGE_KEY = "last_rule_followed";

const LEGACY_LAST_USED_SETUP_ID_STORAGE_KEY = "discipline-tracker:last-setup-id";
const LEGACY_LAST_USED_EMOTION_ID_STORAGE_KEY = "discipline-tracker:last-emotion-id";

export type LastRuleFollowedValue = "true" | "false" | "unknown";

function getStoredValue(storageKey: string, legacyStorageKey?: string): string {
  if (typeof window === "undefined") {
    return "";
  }

  try {
    const currentValue = window.localStorage.getItem(storageKey);
    if (currentValue) {
      return currentValue;
    }

    if (!legacyStorageKey) {
      return "";
    }

    const legacyValue = window.localStorage.getItem(legacyStorageKey) ?? "";
    if (legacyValue) {
      window.localStorage.setItem(storageKey, legacyValue);
      window.localStorage.removeItem(legacyStorageKey);
    }
    return legacyValue;
  } catch {
    return "";
  }
}

function setStoredValue(storageKey: string, value: string): void {
  if (typeof window === "undefined") {
    return;
  }

  const normalized = value.trim();
  try {
    if (!normalized) {
      window.localStorage.removeItem(storageKey);
      return;
    }
    window.localStorage.setItem(storageKey, normalized);
  } catch {
    // Ignore localStorage failures and continue with in-memory state.
  }
}

export function getLastUsedSetupId(): string {
  return getStoredValue(
    LAST_USED_SETUP_ID_STORAGE_KEY,
    LEGACY_LAST_USED_SETUP_ID_STORAGE_KEY
  );
}

export function setLastUsedSetupId(setupId: string): void {
  setStoredValue(LAST_USED_SETUP_ID_STORAGE_KEY, setupId);
}

export function getLastUsedEmotionId(): string {
  return getStoredValue(
    LAST_USED_EMOTION_ID_STORAGE_KEY,
    LEGACY_LAST_USED_EMOTION_ID_STORAGE_KEY
  );
}

export function setLastUsedEmotionId(emotionId: string): void {
  setStoredValue(LAST_USED_EMOTION_ID_STORAGE_KEY, emotionId);
}

export function getLastUsedRuleFollowed(): LastRuleFollowedValue | "" {
  const value = getStoredValue(LAST_USED_RULE_FOLLOWED_STORAGE_KEY);
  if (value === "true" || value === "false" || value === "unknown") {
    return value;
  }
  return "";
}

export function setLastUsedRuleFollowed(ruleFollowed: LastRuleFollowedValue | ""): void {
  setStoredValue(LAST_USED_RULE_FOLLOWED_STORAGE_KEY, ruleFollowed);
}

export function clearLastUsedSetupId(): void {
  setStoredValue(LAST_USED_SETUP_ID_STORAGE_KEY, "");
}

export function clearLastUsedEmotionId(): void {
  setStoredValue(LAST_USED_EMOTION_ID_STORAGE_KEY, "");
}

export function clearLastUsedRuleFollowed(): void {
  setStoredValue(LAST_USED_RULE_FOLLOWED_STORAGE_KEY, "");
}

export function clearLastUsedTaggingDefaults(): void {
  clearLastUsedSetupId();
  clearLastUsedEmotionId();
  clearLastUsedRuleFollowed();
}
