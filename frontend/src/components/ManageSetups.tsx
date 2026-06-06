import { FormEvent, useEffect, useState } from "react";

import { createSetup, getSetups, updateSetup } from "../api/client";
import { SetupOptionResponse } from "../types/setup";
import "./ManageSetups.css";

interface ManageSetupsProps {
  onSetupCreated?: () => void;
  refreshKey?: number;
}

export function ManageSetups({ onSetupCreated, refreshKey = 0 }: ManageSetupsProps) {
  const [setups, setSetups] = useState<SetupOptionResponse[]>([]);
  const [name, setName] = useState("");
  const [sortOrder, setSortOrder] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [savingSetupId, setSavingSetupId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function sortSetups(setupList: SetupOptionResponse[]): SetupOptionResponse[] {
    return [...setupList].sort((a, b) => {
      const aOrder = a.sort_order ?? Number.MAX_SAFE_INTEGER;
      const bOrder = b.sort_order ?? Number.MAX_SAFE_INTEGER;
      if (aOrder !== bOrder) {
        return aOrder - bOrder;
      }
      return a.name.localeCompare(b.name);
    });
  }

  useEffect(() => {
    async function loadSetups() {
      setErrorMessage(null);
      try {
        const response = await getSetups(true);
        setSetups(sortSetups(response));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load setups.";
        setErrorMessage(message);
      }
    }

    void loadSetups();
  }, [refreshKey]);

  async function handleCreateSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!name.trim()) {
      setErrorMessage("Setup name is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await createSetup({
        name: name.trim(),
        sort_order: sortOrder.trim() ? Number(sortOrder) : null,
      });
      setSetups((previous) => sortSetups([...previous, created]));
      setName("");
      setSortOrder("");
      setSuccessMessage(`Created setup "${created.name}".`);
      onSetupCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create setup.";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function updateLocalSetup(setupId: number, patch: Partial<SetupOptionResponse>) {
    setSetups((previous) =>
      previous.map((setup) => (setup.id === setupId ? { ...setup, ...patch } : setup))
    );
  }

  async function handleToggleActive(setup: SetupOptionResponse, nextValue: boolean) {
    setErrorMessage(null);
    setSuccessMessage(null);
    updateLocalSetup(setup.id, { is_active: nextValue });
    setSavingSetupId(setup.id);
    try {
      const updated = await updateSetup(setup.id, { is_active: nextValue });
      setSetups((previous) =>
        sortSetups(previous.map((entry) => (entry.id === setup.id ? updated : entry)))
      );
      setSuccessMessage(`${updated.name} is now ${updated.is_active ? "active" : "inactive"}.`);
      onSetupCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update setup.";
      setErrorMessage(message);
      updateLocalSetup(setup.id, { is_active: setup.is_active });
    } finally {
      setSavingSetupId(null);
    }
  }

  async function handleSaveSetup(setup: SetupOptionResponse) {
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!setup.name.trim()) {
      setErrorMessage("Setup name is required.");
      return;
    }

    setSavingSetupId(setup.id);
    try {
      const updated = await updateSetup(setup.id, {
        name: setup.name.trim(),
        sort_order: setup.sort_order,
      });
      setSetups((previous) =>
        sortSetups(previous.map((entry) => (entry.id === setup.id ? updated : entry)))
      );
      setSuccessMessage(`Saved changes for "${updated.name}".`);
      onSetupCreated?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update setup.";
      setErrorMessage(message);
    } finally {
      setSavingSetupId(null);
    }
  }

  return (
    <section className="manage-setups-panel">
      <form className="setup-create-form" onSubmit={handleCreateSetup}>
        <label>
          Setup Name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. BREAKOUT_RETEST"
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
          {isSubmitting ? "Creating..." : "Create Setup"}
        </button>
      </form>

      {errorMessage ? <p className="setup-status error">{errorMessage}</p> : null}
      {successMessage ? <p className="setup-status success">{successMessage}</p> : null}

      <div className="setup-list-wrap">
        <table className="setup-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Active</th>
              <th>Sort Order</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {setups.map((setup) => (
              <tr key={setup.id}>
                <td>
                  <input
                    className="setup-table-input"
                    type="text"
                    value={setup.name}
                    onChange={(event) => updateLocalSetup(setup.id, { name: event.target.value })}
                    disabled={savingSetupId === setup.id}
                  />
                </td>
                <td>
                  <label className="active-toggle">
                    <input
                      type="checkbox"
                      checked={setup.is_active}
                      onChange={(event) => void handleToggleActive(setup, event.target.checked)}
                      disabled={savingSetupId === setup.id}
                    />
                    <span>{setup.is_active ? "Active" : "Inactive"}</span>
                  </label>
                </td>
                <td>
                  <input
                    className="setup-table-input setup-sort-input"
                    type="number"
                    value={setup.sort_order ?? ""}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value !== "" && !Number.isFinite(Number(value))) {
                        return;
                      }
                      updateLocalSetup(setup.id, {
                        sort_order: value === "" ? null : Number(value),
                      });
                    }}
                    disabled={savingSetupId === setup.id}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="setup-save-button"
                    onClick={() => void handleSaveSetup(setup)}
                    disabled={savingSetupId === setup.id}
                  >
                    {savingSetupId === setup.id ? "Saving..." : "Save"}
                  </button>
                </td>
              </tr>
            ))}
            {setups.length === 0 ? (
              <tr>
                <td colSpan={4}>No setups yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
