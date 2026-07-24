import { useState } from "react";
import type { KeyboardEvent } from "react";
import { Button } from "../../../components/actions/Button";
import { IconButton } from "../../../components/actions/IconButton";
import { Modal } from "../../../components/feedback/Modal";
import { TextInput } from "../../../components/forms/TextInput";
import type { EvaluationRun } from "../types/run";
import styles from "./RunSidebar.module.css";

export interface RunSidebarProps {
  runs: EvaluationRun[];
  activeRunId: string | null;
  bestRunId: string | null;
  viewMode: "run" | "compare";
  /** The definition hash of the pipeline currently compiled in Build -- the run
   * matching it is the only one new evaluations can be run against. */
  currentDefinitionHash: string | null;
  onSelect: (runId: string) => void;
  onRename: (runId: string, name: string) => void;
  onMarkBest: (runId: string) => void;
  onDelete: (runId: string) => void;
  onCompare: () => void;
}

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

/** Vertical list of evaluation runs (oldest first) plus a "Compare runs" entry
 * pinned below them. Clicking a run selects/views it; the pencil renames it in
 * place, the star marks it "best" (green, exclusive), and the trash icon
 * deletes it (behind a confirmation) -- kept as separate controls so no single
 * click is overloaded with two meanings. */
export function RunSidebar({
  runs,
  activeRunId,
  bestRunId,
  viewMode,
  currentDefinitionHash,
  onSelect,
  onRename,
  onMarkBest,
  onDelete,
  onCompare,
}: RunSidebarProps) {
  const [editingRunId, setEditingRunId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [deletingRun, setDeletingRun] = useState<EvaluationRun | null>(null);

  const startEditing = (run: EvaluationRun) => {
    setEditingRunId(run.id);
    setDraftName(run.name);
  };

  const commitEdit = () => {
    if (editingRunId) onRename(editingRunId, draftName);
    setEditingRunId(null);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") commitEdit();
    if (event.key === "Escape") setEditingRunId(null);
  };

  const confirmDelete = () => {
    if (deletingRun) onDelete(deletingRun.id);
    setDeletingRun(null);
  };

  return (
    <nav className={styles.sidebar} aria-label="Evaluation runs">
      <ul className={styles.list}>
        {runs.map((run) => {
          const isEditing = editingRunId === run.id;
          const isActive = viewMode === "run" && run.id === activeRunId;
          const isCurrent = run.definitionHash === currentDefinitionHash;
          const isBest = run.id === bestRunId;

          return (
            <li key={run.id}>
              {isEditing ? (
                <TextInput
                  autoFocus
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                  onBlur={commitEdit}
                  onKeyDown={handleKeyDown}
                  className={styles.renameInput}
                />
              ) : (
                <div
                  className={[styles.row, isActive && styles.rowActive, isBest && styles.rowBest]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <button type="button" className={styles.rowButton} onClick={() => onSelect(run.id)}>
                    {isCurrent && (
                      <span className={styles.currentDot} title="Matches the currently compiled pipeline" />
                    )}
                    <span className={styles.rowLabel}>{run.name}</span>
                  </button>
                  <IconButton
                    label={isBest ? `Unmark ${run.name} as best` : `Mark ${run.name} as best`}
                    size="sm"
                    className={isBest ? styles.starActive : undefined}
                    icon={STAR_ICON(isBest)}
                    onClick={() => onMarkBest(run.id)}
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

      <button
        type="button"
        className={viewMode === "compare" ? `${styles.compare} ${styles.compareActive}` : styles.compare}
        onClick={onCompare}
        disabled={runs.length < 2}
      >
        Compare runs
      </button>

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
            Delete <strong>{deletingRun.name}</strong>? Its evaluation results will be lost.
          </p>
        )}
      </Modal>
    </nav>
  );
}
