import { FormEvent, useEffect, useState } from "react";

import { createEmotion, getEmotions, updateEmotion } from "../api/client";
import { EmotionOptionResponse } from "../types/emotion";
import "./ManageEmotions.css";

interface ManageEmotionsProps {
  onEmotionCreated?: () => void;
  refreshKey?: number;
}

export function ManageEmotions({ onEmotionCreated, refreshKey = 0 }: ManageEmotionsProps) {
  const [emotions, setEmotions] = useState<EmotionOptionResponse[]>([]);
  const [name, setName] = useState("");
  const [sortOrder, setSortOrder] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [savingEmotionId, setSavingEmotionId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function sortEmotions(emotionList: EmotionOptionResponse[]): EmotionOptionResponse[] {
    return [...emotionList].sort((a, b) => {
      const aOrder = a.sort_order ?? Number.MAX_SAFE_INTEGER;
      const bOrder = b.sort_order ?? Number.MAX_SAFE_INTEGER;
      if (aOrder !== bOrder) {
        return aOrder - bOrder;
      }
      return a.name.localeCompare(b.name);
    });
  }

  useEffect(() => {
    async function loadEmotions() {
      setErrorMessage(null);
      try {
        const response = await getEmotions(true);
        setEmotions(sortEmotions(response));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load emotions.";
        setErrorMessage(message);
      }
    }

    void loadEmotions();
  }, [refreshKey]);

  async function handleCreateEmotion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!name.trim()) {
      setErrorMessage("Emotion name is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await createEmotion({
        name: name.trim(),
        sort_order: sortOrder.trim() ? Number(sortOrder) : null,
      });
      setEmotions((previous) => sortEmotions([...previous, created]));
      setName("");
      setSortOrder("");
      setSuccessMessage(`Created emotion "${created.name}".`);
      onEmotionCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create emotion.";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function updateLocalEmotion(emotionId: number, patch: Partial<EmotionOptionResponse>) {
    setEmotions((previous) =>
      previous.map((emotion) => (emotion.id === emotionId ? { ...emotion, ...patch } : emotion))
    );
  }

  async function handleToggleActive(emotion: EmotionOptionResponse, nextValue: boolean) {
    setErrorMessage(null);
    setSuccessMessage(null);
    updateLocalEmotion(emotion.id, { is_active: nextValue });
    setSavingEmotionId(emotion.id);
    try {
      const updated = await updateEmotion(emotion.id, { is_active: nextValue });
      setEmotions((previous) =>
        sortEmotions(previous.map((entry) => (entry.id === emotion.id ? updated : entry)))
      );
      setSuccessMessage(`${updated.name} is now ${updated.is_active ? "active" : "inactive"}.`);
      onEmotionCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update emotion.";
      setErrorMessage(message);
      updateLocalEmotion(emotion.id, { is_active: emotion.is_active });
    } finally {
      setSavingEmotionId(null);
    }
  }

  async function handleSaveEmotion(emotion: EmotionOptionResponse) {
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!emotion.name.trim()) {
      setErrorMessage("Emotion name is required.");
      return;
    }

    setSavingEmotionId(emotion.id);
    try {
      const updated = await updateEmotion(emotion.id, {
        name: emotion.name.trim(),
        sort_order: emotion.sort_order,
      });
      setEmotions((previous) =>
        sortEmotions(previous.map((entry) => (entry.id === emotion.id ? updated : entry)))
      );
      setSuccessMessage(`Saved changes for "${updated.name}".`);
      onEmotionCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update emotion.";
      setErrorMessage(message);
    } finally {
      setSavingEmotionId(null);
    }
  }

  return (
    <section className="manage-emotions-panel">
      <form className="emotion-create-form" onSubmit={handleCreateEmotion}>
        <label>
          Emotion Name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. PATIENT"
          />
        </label>
        <label>
          Sort Order (optional)
          <input
            type="number"
            value={sortOrder}
            onChange={(event) => setSortOrder(event.target.value)}
          />
        </label>
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating..." : "Create Emotion"}
        </button>
      </form>

      {errorMessage ? <p className="emotion-status error">{errorMessage}</p> : null}
      {successMessage ? <p className="emotion-status success">{successMessage}</p> : null}

      <div className="emotion-list-wrap">
        <table className="emotion-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Active</th>
              <th>Sort Order</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {emotions.map((emotion) => (
              <tr key={emotion.id}>
                <td>
                  <input
                    className="emotion-table-input"
                    type="text"
                    value={emotion.name}
                    onChange={(event) =>
                      updateLocalEmotion(emotion.id, { name: event.target.value })
                    }
                    disabled={savingEmotionId === emotion.id}
                  />
                </td>
                <td>
                  <label className="emotion-active-toggle">
                    <input
                      type="checkbox"
                      checked={emotion.is_active}
                      onChange={(event) => void handleToggleActive(emotion, event.target.checked)}
                      disabled={savingEmotionId === emotion.id}
                    />
                    <span>{emotion.is_active ? "Active" : "Inactive"}</span>
                  </label>
                </td>
                <td>
                  <input
                    className="emotion-table-input emotion-sort-input"
                    type="number"
                    value={emotion.sort_order ?? ""}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value !== "" && !Number.isFinite(Number(value))) {
                        return;
                      }
                      updateLocalEmotion(emotion.id, {
                        sort_order: value === "" ? null : Number(value),
                      });
                    }}
                    disabled={savingEmotionId === emotion.id}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="emotion-save-button"
                    onClick={() => void handleSaveEmotion(emotion)}
                    disabled={savingEmotionId === emotion.id}
                  >
                    {savingEmotionId === emotion.id ? "Saving..." : "Save"}
                  </button>
                </td>
              </tr>
            ))}
            {emotions.length === 0 ? (
              <tr>
                <td colSpan={4}>No emotions yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
