import { useState } from "react";

import { getEmotions, getSetups, getTrades, importBackup, wipeAllData } from "../api/client";
import { CollapsibleSection } from "../components/CollapsibleSection";
import { ManageEmotions } from "../components/ManageEmotions";
import { ManageSetups } from "../components/ManageSetups";
import { EmotionOptionResponse } from "../types/emotion";
import { SetupOptionResponse } from "../types/setup";
import { TradeResponse } from "../types/trade";
import "./SettingsView.css";

interface SettingsViewProps {
  setupRefreshKey: number;
  emotionRefreshKey: number;
  onSetupCreated: () => void;
  onEmotionCreated: () => void;
}

interface BackupPayload {
  schema_version: number;
  exported_at: string;
  data: {
    setups: SetupOptionResponse[];
    emotions: EmotionOptionResponse[];
    trades: TradeResponse[];
  };
}

function getBackupPayloadValidationError(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return "Backup file must be a JSON object.";
  }

  const candidate = payload as {
    schema_version?: unknown;
    data?: {
      setups?: unknown;
      emotions?: unknown;
      trades?: unknown;
    };
  };

  if (typeof candidate.schema_version !== "number") {
    return "Missing or invalid schema_version.";
  }
  if (!candidate.data || typeof candidate.data !== "object") {
    return "Missing data object.";
  }
  if (!Array.isArray(candidate.data.setups)) {
    return "Missing setups array.";
  }
  if (!Array.isArray(candidate.data.emotions)) {
    return "Missing emotions array.";
  }
  if (!Array.isArray(candidate.data.trades)) {
    return "Missing trades array.";
  }
  return null;
}

function getBackupFileName(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `trading_app_backup_${year}-${month}-${day}.json`;
}

function downloadBackup(payload: BackupPayload): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = getBackupFileName();
  link.click();
  URL.revokeObjectURL(url);
}

export function SettingsView({
  setupRefreshKey,
  emotionRefreshKey,
  onSetupCreated,
  onEmotionCreated,
}: SettingsViewProps) {
  const [isDownloadingBackup, setIsDownloadingBackup] = useState(false);
  const [isRestoringBackup, setIsRestoringBackup] = useState(false);
  const [selectedBackupFile, setSelectedBackupFile] = useState<File | null>(null);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [backupSuccess, setBackupSuccess] = useState<string | null>(null);
  const [isWipingData, setIsWipingData] = useState(false);
  const [showWipeConfirm, setShowWipeConfirm] = useState(false);
  const [wipeConfirmPhrase, setWipeConfirmPhrase] = useState("");
  const [wipeError, setWipeError] = useState<string | null>(null);
  const [wipeSuccess, setWipeSuccess] = useState<string | null>(null);

  const canConfirmWipe = wipeConfirmPhrase.trim() === "DELETE";

  async function handleDownloadBackup() {
    setIsDownloadingBackup(true);
    setBackupError(null);
    setBackupSuccess(null);

    try {
      const [setups, emotions, trades] = await Promise.all([
        getSetups(true),
        getEmotions(true),
        getTrades({ include_fills: true }),
      ]);

      const payload: BackupPayload = {
        schema_version: 1,
        exported_at: new Date().toISOString(),
        data: {
          setups,
          emotions,
          trades,
        },
      };

      downloadBackup(payload);
      setBackupSuccess(`Backup downloaded (${trades.length} trades).`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to download backup.";
      setBackupError(message);
    } finally {
      setIsDownloadingBackup(false);
    }
  }

  async function handleRestoreBackup() {
    if (!selectedBackupFile) {
      setBackupError("Select a backup JSON file first.");
      setBackupSuccess(null);
      return;
    }

    const confirmed = window.confirm(
      "This will replace all existing trades/setups/emotions. Continue?"
    );
    if (!confirmed) {
      return;
    }

    setIsRestoringBackup(true);
    setBackupError(null);
    setBackupSuccess(null);

    try {
      const fileContents = await selectedBackupFile.text();
      const parsedPayload = JSON.parse(fileContents) as unknown;
      const validationError = getBackupPayloadValidationError(parsedPayload);
      if (validationError) {
        throw new Error(validationError);
      }

      const response = await importBackup(parsedPayload);
      setBackupSuccess(
        `Backup restored (${response.imported.trades} trades, ${response.imported.fills} fills, ${response.imported.setups} setups, ${response.imported.emotions} emotions). Reloading...`
      );
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      const message =
        error instanceof SyntaxError
          ? "Invalid JSON file."
          : error instanceof Error
            ? error.message
            : "Failed to restore backup.";
      setBackupError(message);
    } finally {
      setIsRestoringBackup(false);
    }
  }

  async function handleWipeAllData() {
    if (!canConfirmWipe) {
      return;
    }

    setIsWipingData(true);
    setWipeError(null);
    setWipeSuccess(null);

    try {
      await wipeAllData();
      setWipeSuccess("Data wiped successfully. Reloading...");
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to wipe data.";
      setWipeError(message);
    } finally {
      setIsWipingData(false);
    }
  }

  return (
    <section className="single-view-grid">
      <CollapsibleSection id="settings-manage-setups" title="Manage Setups" defaultCollapsed>
        <ManageSetups refreshKey={setupRefreshKey} onSetupCreated={onSetupCreated} />
      </CollapsibleSection>
      <CollapsibleSection id="settings-manage-emotions" title="Manage Emotions" defaultCollapsed>
        <ManageEmotions refreshKey={emotionRefreshKey} onEmotionCreated={onEmotionCreated} />
      </CollapsibleSection>
      <CollapsibleSection id="settings-backup" title="Backup">
        <div className="settings-backup-panel">
          <p className="settings-backup-description">
            Download a full JSON backup containing setups, emotions, all trades, and fill data.
          </p>
          <p className="settings-backup-description">
            Use backups before major changes or before wiping data.
          </p>
          <button
            type="button"
            className="settings-backup-button"
            onClick={() => void handleDownloadBackup()}
            disabled={isDownloadingBackup || isRestoringBackup}
          >
            {isDownloadingBackup ? "Downloading..." : "Download Backup (JSON)"}
          </button>
          <label className="settings-backup-file-label">
            Restore file
            <input
              type="file"
              accept=".json,application/json"
              onChange={(event) => setSelectedBackupFile(event.target.files?.[0] ?? null)}
              disabled={isDownloadingBackup || isRestoringBackup}
            />
          </label>
          <button
            type="button"
            className="settings-backup-button"
            onClick={() => void handleRestoreBackup()}
            disabled={isDownloadingBackup || isRestoringBackup}
          >
            {isRestoringBackup ? "Restoring..." : "Restore Backup"}
          </button>
          {backupError ? <p className="settings-backup-status error">{backupError}</p> : null}
          {backupSuccess ? <p className="settings-backup-status success">{backupSuccess}</p> : null}
        </div>
      </CollapsibleSection>
      <CollapsibleSection id="settings-danger-zone" title="Danger Zone" defaultCollapsed>
        <div className="settings-danger-panel">
          <p className="settings-danger-description">
            This will permanently delete ALL trades, setups, emotions, and import history. This
            cannot be undone.
          </p>
          {!showWipeConfirm ? (
            <button
              type="button"
              className="settings-danger-button"
              onClick={() => {
                setShowWipeConfirm(true);
                setWipeConfirmPhrase("");
                setWipeError(null);
                setWipeSuccess(null);
              }}
              disabled={isWipingData}
            >
              Wipe All Data
            </button>
          ) : (
            <div className="settings-danger-confirm">
              <label className="settings-danger-label">
                Type <code>DELETE</code> to confirm
                <input
                  type="text"
                  value={wipeConfirmPhrase}
                  onChange={(event) => setWipeConfirmPhrase(event.target.value)}
                  disabled={isWipingData}
                  autoComplete="off"
                />
              </label>
              <div className="settings-danger-actions">
                <button
                  type="button"
                  className="settings-danger-button confirm"
                  onClick={() => void handleWipeAllData()}
                  disabled={!canConfirmWipe || isWipingData}
                >
                  {isWipingData ? "Wiping..." : "Confirm Wipe"}
                </button>
                <button
                  type="button"
                  className="settings-danger-button cancel"
                  onClick={() => {
                    setShowWipeConfirm(false);
                    setWipeConfirmPhrase("");
                    setWipeError(null);
                  }}
                  disabled={isWipingData}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {wipeError ? <p className="settings-backup-status error">{wipeError}</p> : null}
          {wipeSuccess ? <p className="settings-backup-status success">{wipeSuccess}</p> : null}
        </div>
      </CollapsibleSection>
    </section>
  );
}
