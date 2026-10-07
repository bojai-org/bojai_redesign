import { BuildApiError } from "../../build/api/pipelineApi";
import type { ChatResponseFeedback, EvaluationRun } from "../../evaluate/types/run";
import * as api from "../api/projectStateApi";
import type {
  ChatResponseState,
  RunState,
  StoredRun,
  WorkspaceState,
} from "../types/projectState";

export type SaveState = "saved" | "saving" | "error";

export interface SaveStatus {
  state: SaveState;
  /** The most recent failure, kept until a later save succeeds. */
  error: string | null;
}

/**
 * Autosave for one open project. Every write goes through a single queue, so
 * they reach the backend in the order they were made -- a chat response is
 * never sent before the run it belongs to, and a later workspace save can't be
 * overtaken by an earlier one. A failed write doesn't stop the queue; it's
 * reported through the save status (see useSaveStatus) until a later write
 * succeeds.
 */
export class ProjectPersistence {
  readonly projectId: string;
  private queue: Promise<void> = Promise.resolve();
  private pending = 0;
  private status: SaveStatus = { state: "saved", error: null };
  private listeners = new Set<() => void>();

  constructor(projectId: string) {
    this.projectId = projectId;
  }

  // ── status, in useSyncExternalStore's shape ──────────────────────────────

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getStatus = (): SaveStatus => this.status;

  private setStatus(next: SaveStatus): void {
    if (next.state === this.status.state && next.error === this.status.error) return;
    this.status = next;
    this.listeners.forEach((listener) => listener());
  }

  private enqueue(task: () => Promise<void>): Promise<void> {
    this.pending += 1;
    this.setStatus({ state: "saving", error: this.status.error });
    this.queue = this.queue.then(task).then(
      () => {
        this.pending -= 1;
        this.setStatus({ state: this.pending > 0 ? "saving" : "saved", error: null });
      },
      (error: unknown) => {
        this.pending -= 1;
        const message = error instanceof BuildApiError ? error.message : "The change could not be saved.";
        this.setStatus({ state: this.pending > 0 ? "saving" : "error", error: message });
      },
    );
    return this.queue;
  }

  // ── writes ────────────────────────────────────────────────────────────────

  saveWorkspace(workspace: WorkspaceState, { keepalive = false } = {}): Promise<void> {
    return this.enqueue(() => api.saveWorkspace(this.projectId, workspace, { keepalive }));
  }

  saveRun(run: EvaluationRun): Promise<void> {
    const state = runToState(run);
    return this.enqueue(() => api.saveRun(this.projectId, run.id, state));
  }

  deleteRun(runId: string): Promise<void> {
    return this.enqueue(() => api.deleteRun(this.projectId, runId));
  }

  saveResponse(runId: string, response: ChatResponseFeedback): Promise<void> {
    const state = responseToState(response);
    return this.enqueue(() => api.saveResponse(this.projectId, runId, response.id, state));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Conversions between the frontend's run shape and the wire format
// ─────────────────────────────────────────────────────────────────────────────

export function runToState(run: EvaluationRun): RunState {
  return {
    pipeline_id: run.pipelineId,
    name: run.name,
    definition_hash: run.definitionHash,
    workflow: run.workflow,
    created_at: run.createdAt,
  };
}

function responseToState(response: ChatResponseFeedback): ChatResponseState {
  return {
    query: response.query,
    answer: response.answer,
    vote: response.vote,
    explanation: response.explanation,
    created_at: response.createdAt,
  };
}

/** A run as loaded from the backend. Reports aren't part of the project state
 * (they can be large); runs that have any are marked unloaded so Evaluate
 * fetches them when the run is viewed. */
export function storedRunToRun(stored: StoredRun): EvaluationRun {
  return {
    id: stored.id,
    name: stored.name,
    pipelineId: stored.pipeline_id,
    definitionHash: stored.definition_hash,
    createdAt: stored.created_at,
    workflow: stored.workflow,
    safetyAgentsChecked: false,
    safetyAgentsInfo: null,
    safetyAgentsError: null,
    safetyReport: null,
    agentReport: null,
    agentCsvName: null,
    reportsLoaded: stored.report_kinds.length === 0,
    responses: stored.responses.map((response) => ({
      id: response.id,
      query: response.query,
      answer: response.answer,
      createdAt: response.created_at,
      vote: response.vote,
      explanation: response.explanation,
    })),
  };
}

/** The run fields that are saved via saveRun -- anything else changing on a
 * run (reports, safety-agent lookups) is either saved by the backend itself
 * or not persisted at all. */
export function runMetadataChanged(previous: EvaluationRun, next: EvaluationRun): boolean {
  return (
    previous.name !== next.name ||
    previous.pipelineId !== next.pipelineId ||
    previous.definitionHash !== next.definitionHash ||
    previous.workflow !== next.workflow ||
    previous.createdAt !== next.createdAt
  );
}
