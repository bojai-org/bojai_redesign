import { useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "../../../components/actions/Button";
import { IconButton } from "../../../components/actions/IconButton";
import { Modal } from "../../../components/feedback/Modal";
import { TextInput } from "../../../components/forms/TextInput";
import { usePipelineWorkspace } from "../../build/state/PipelineWorkspaceContext";
import { useSaveStatus } from "../../projects/state/ProjectPersistenceContext";
import { useEvaluationRuns } from "../state/EvaluationRunsContext";
import type { EvaluationRun } from "../types/run";
import styles from "./RunBar.module.css";

const PENCIL_ICON = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const STAR_ICON = (filled: boolean) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.5l2.9 6.6 7.1.6-5.4 4.7 1.7 7L12 17.8 5.7 21.4l1.7-7-5.4-4.7 7.1-.6L12 2.5Z" />
  </svg>
);

const TRASH_ICON = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13" />
  </svg>
);

/**
 * The project's runs (oldest first), shown under the tab bar on every project
 * tab. Each run is one compiled version of the pipeline; the active one is
 * what all tabs are connected to -- Build shows its workflow, Run chats with
 * its pipeline, Evaluate shows its results. Clicking another run switches
 * every tab to it (asking first if the canvas has uncompiled edits, since
 * opening a run replaces the canvas).
 *
 * The star marks a run "best" (exclusive), the pencil renames it in place and
 * the trash icon deletes it behind a confirmation -- separate controls so no
 * single click has two meanings.
 */
export function RunBar() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { runs, activeRun, bestRunId, viewMode, renameRun, markBest, deleteRun, showCompare } =
    useEvaluationRuns();
  const { openRun, hasUncompiledChanges } = usePipelineWorkspace();
  const saveStatus = useSaveStatus();

  const [editingRunId, setEditingRunId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [deletingRun, setDeletingRun] = useState<EvaluationRun | null>(null);
  const [switchingTo, setSwitchingTo] = useState<EvaluationRun | null>(null);

  const handleSelect = (run: EvaluationRun) => {
    if (hasUncompiledChanges) {
      setSwitchingTo(run);
      return;
    }
    openRun(run);
  };

  const confirmSwitch = () => {
    if (switchingTo) openRun(switchingTo);
    setSwitchingTo(null);
  };

  const startEditing = (run: EvaluationRun) => {
    setEditingRunId(run.id);
    setDraftName(run.name);
  };

  const commitEdit = () => {
    if (editingRunId) renameRun(editingRunId, draftName);
    setEditingRunId(null);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") commitEdit();
    if (event.key === "Escape") setEditingRunId(null);
  };

  const isDeletingActive = deletingRun !== null && deletingRun.id === activeRun?.id;

  /** Deleting the active run moves every tab onto its neighbour (the run
   * before it, else the one after) -- the same fallback deleteRun picks. */
  const confirmDelete = () => {
    if (!deletingRun) return;
    const index = runs.findIndex((run) => run.id === deletingRun.id);
    const fallback = isDeletingActive ? (runs[index - 1] ?? runs[index + 1] ?? null) : null;
    deleteRun(deletingRun.id);
    if (fallback) openRun(fallback);
    setDeletingRun(null);
  };

  const handleCompare = () => {
    showCompare();
    navigate(`/projects/${projectId}/evaluate`);
  };

  return (
    <nav className={styles.bar} aria-label="Runs">
      <span className={styles.heading}>Runs</span>

      {runs.length === 0 ? (
        <span className={styles.empty}>
          No runs yet. Compiling a pipeline in Build creates run1.
        </span>
      ) : (
        <ul className={styles.list}>
          {runs.map((run) => {
            const isEditing = editingRunId === run.id;
            const isActive = run.id === activeRun?.id;
            const isBest = run.id === bestRunId;

            return (
              <li key={run.id}>
                {isEditing ? (
                  <TextInput
                    autoFocus
                    aria-label={`New name for ${run.name}`}
                    value={draftName}
                    onChange={(event) => setDraftName(event.target.value)}
                    onBlur={commitEdit}
                    onKeyDown={handleKeyDown}
                    className={styles.renameInput}
                  />
                ) : (
                  <div
                    className={[styles.chip, isActive && styles.chipActive, isBest && styles.chipBest]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <button
                      type="button"
                      className={styles.chipButton}
                      onClick={() => handleSelect(run)}
                      aria-current={isActive ? "true" : undefined}
                    >
                      <span className={styles.chipLabel}>{run.name}</span>
                      {isActive && hasUncompiledChanges && (
                        <span className={styles.edited} title="The canvas has changes that aren't compiled yet">
                          edited
                        </span>
                      )}
                    </button>
                    <IconButton
                      label={isBest ? `Unmark ${run.name} as best` : `Mark ${run.name} as best`}
                      size="sm"
                      className={isBest ? styles.starActive : undefined}
                      icon={STAR_ICON(isBest)}
                      onClick={() => markBest(run.id)}
                    />
                    <IconButton
                      label={`Rename ${run.name}`}
                      size="sm"
                      icon={PENCIL_ICON}
                      onClick={() => startEditing(run)}
                    />
                    <IconButton
                      label={`Delete ${run.name}`}
                      size="sm"
                      icon={TRASH_ICON}
                      onClick={() => setDeletingRun(run)}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <span
        className={saveStatus.state === "error" ? `${styles.saveStatus} ${styles.saveError}` : styles.saveStatus}
        role="status"
        title={saveStatus.error ?? undefined}
      >
        {saveStatus.state === "saving"
          ? "Saving…"
          : saveStatus.state === "error"
            ? `Couldn't save: ${saveStatus.error}`
            : "All changes saved"}
      </span>

      <button
        type="button"
        className={viewMode === "compare" ? `${styles.compare} ${styles.compareActive}` : styles.compare}
        onClick={handleCompare}
        disabled={runs.length < 2}
      >
        Compare runs
      </button>

      <Modal
        open={switchingTo !== null}
        onClose={() => setSwitchingTo(null)}
        title="Open run"
        footer={
          <>
            <Button variant="ghost" onClick={() => setSwitchingTo(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={confirmSwitch}>
              Discard and open
            </Button>
          </>
        }
      >
        {switchingTo && (
          <p>
            The canvas has changes that aren't compiled into a run yet. Opening{" "}
            <strong>{switchingTo.name}</strong> replaces them with its workflow.
          </p>
        )}
      </Modal>

      <Modal
        open={deletingRun !== null}
        onClose={() => setDeletingRun(null)}
        title="Delete run"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeletingRun(null)}>
              Cancel
            </Button>
            <Button variant="danger-ghost" onClick={confirmDelete}>
              Delete
            </Button>
          </>
        }
      >
        {deletingRun && (
          <p>
            Delete <strong>{deletingRun.name}</strong>? Its workflow snapshot, chat responses and
            evaluation results will be lost.
            {isDeletingActive && runs.length > 1 && (
              <>
                {" "}
                Every tab will switch to the previous run
                {hasUncompiledChanges ? ", replacing the uncompiled changes on the canvas" : ""}.
              </>
            )}
          </p>
        )}
      </Modal>
    </nav>
  );
}
