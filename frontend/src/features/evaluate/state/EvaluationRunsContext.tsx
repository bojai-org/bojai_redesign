import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { EvaluationRun } from "../types/run";

type ViewMode = "run" | "compare";

interface RunsState {
  runs: EvaluationRun[];
  activeRunId: string | null;
  bestRunId: string | null;
  viewMode: ViewMode;
  nextRunNumber: number;
}

const INITIAL_STATE: RunsState = {
  runs: [],
  activeRunId: null,
  bestRunId: null,
  viewMode: "run",
  nextRunNumber: 1,
};

function newRunId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `run-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface EvaluationRunsContextValue {
  runs: EvaluationRun[];
  activeRun: EvaluationRun | null;
  bestRunId: string | null;
  viewMode: ViewMode;
  /** Creates a new run when the given definition hash differs from the most
   * recent run's (or none exist yet), and makes it active; otherwise just
   * re-selects the existing run for that hash. Safe to call on every mount --
   * a no-op call returns the same state reference, so it never forces an
   * extra render. */
  ensureRunForPipeline: (pipelineId: string, definitionHash: string) => void;
  selectRun: (runId: string) => void;
  renameRun: (runId: string, name: string) => void;
  updateRun: (runId: string, patch: Partial<EvaluationRun>) => void;
  /** Toggles whether runId is the one "best" run -- at most one at a time;
   * marking a different run as best replaces the previous one, and marking
   * the current best again clears it. */
  markBest: (runId: string) => void;
  /** Removes a run. If it was active, a neighboring run (preferring the one
   * before it) becomes active instead; if it was best, best is cleared. */
  deleteRun: (runId: string) => void;
  showCompare: () => void;
}

const EvaluationRunsContext = createContext<EvaluationRunsContextValue | null>(null);

/**
 * Owns the Evaluate tab's run history for the duration of a project session.
 * Mounted once around the project workspace routes (see ProjectWorkspacePage,
 * alongside PipelineWorkspaceProvider) so it survives navigating away to
 * Build/Run and back -- only a fresh project (a new `key`) resets it.
 */
export function EvaluationRunsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<RunsState>(INITIAL_STATE);

  const ensureRunForPipeline = useCallback((pipelineId: string, definitionHash: string) => {
    setState((current) => {
      const lastRun = current.runs.length > 0 ? current.runs[current.runs.length - 1] : null;

      if (lastRun && lastRun.definitionHash === definitionHash) {
        if (current.activeRunId === lastRun.id && current.viewMode === "run") return current;
        return { ...current, activeRunId: lastRun.id, viewMode: "run" };
      }

      const run: EvaluationRun = {
        id: newRunId(),
        name: `run${current.nextRunNumber}`,
        pipelineId,
        definitionHash,
        createdAt: Date.now(),
        safetyAgentsChecked: false,
        safetyAgentsInfo: null,
        safetyAgentsError: null,
        safetyReport: null,
        agentReport: null,
      };

      return {
        ...current,
        runs: [...current.runs, run],
        activeRunId: run.id,
        viewMode: "run",
        nextRunNumber: current.nextRunNumber + 1,
      };
    });
  }, []);

  const selectRun = useCallback((runId: string) => {
    setState((current) =>
      current.activeRunId === runId && current.viewMode === "run"
        ? current
        : { ...current, activeRunId: runId, viewMode: "run" },
    );
  }, []);

  const renameRun = useCallback((runId: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setState((current) => ({
      ...current,
      runs: current.runs.map((run) => (run.id === runId ? { ...run, name: trimmed } : run)),
    }));
  }, []);

  const updateRun = useCallback((runId: string, patch: Partial<EvaluationRun>) => {
    setState((current) => ({
      ...current,
      runs: current.runs.map((run) => (run.id === runId ? { ...run, ...patch } : run)),
    }));
  }, []);

  const markBest = useCallback((runId: string) => {
    setState((current) => ({
      ...current,
      bestRunId: current.bestRunId === runId ? null : runId,
    }));
  }, []);

  const deleteRun = useCallback((runId: string) => {
    setState((current) => {
      const index = current.runs.findIndex((run) => run.id === runId);
      if (index === -1) return current;

      const runs = current.runs.filter((run) => run.id !== runId);

      let activeRunId = current.activeRunId;
      if (activeRunId === runId) {
        const fallback = runs[index - 1] ?? runs[index] ?? null;
        activeRunId = fallback ? fallback.id : null;
      }

      return {
        ...current,
        runs,
        activeRunId,
        bestRunId: current.bestRunId === runId ? null : current.bestRunId,
      };
    });
  }, []);

  const showCompare = useCallback(() => {
    setState((current) => (current.viewMode === "compare" ? current : { ...current, viewMode: "compare" }));
  }, []);

  const activeRun = useMemo(
    () => state.runs.find((run) => run.id === state.activeRunId) ?? null,
    [state.runs, state.activeRunId],
  );

  const value = useMemo<EvaluationRunsContextValue>(
    () => ({
      runs: state.runs,
      activeRun,
      bestRunId: state.bestRunId,
      viewMode: state.viewMode,
      ensureRunForPipeline,
      selectRun,
      renameRun,
      updateRun,
      markBest,
      deleteRun,
      showCompare,
    }),
    [
      state.runs,
      activeRun,
      state.bestRunId,
      state.viewMode,
      ensureRunForPipeline,
      selectRun,
      renameRun,
      updateRun,
      markBest,
      deleteRun,
      showCompare,
    ],
  );

  return <EvaluationRunsContext.Provider value={value}>{children}</EvaluationRunsContext.Provider>;
}

export function useEvaluationRuns(): EvaluationRunsContextValue {
  const context = useContext(EvaluationRunsContext);
  if (!context) {
    throw new Error("useEvaluationRuns must be used within an EvaluationRunsProvider");
  }
  return context;
}
