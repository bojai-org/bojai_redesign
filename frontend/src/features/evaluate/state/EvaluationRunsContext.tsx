import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useProjectPersistence } from "../../projects/state/ProjectPersistenceContext";
import { runMetadataChanged } from "../../projects/state/projectPersistence";
import type { ProjectPersistence } from "../../projects/state/projectPersistence";
import type { ChatResponseFeedback, EvaluationRun, RunWorkflow } from "../types/run";

type ViewMode = "run" | "compare";

interface RunsState {
  runs: EvaluationRun[];
  activeRunId: string | null;
  bestRunId: string | null;
  viewMode: ViewMode;
  nextRunNumber: number;
}

/** What a project was saved with -- see ProjectWorkspacePage. */
export interface InitialRunsState {
  runs: EvaluationRun[];
  activeRunId: string | null;
  bestRunId: string | null;
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

function newResponseId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `response-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface EvaluationRunsContextValue {
  runs: EvaluationRun[];
  activeRun: EvaluationRun | null;
  bestRunId: string | null;
  viewMode: ViewMode;
  /** Number the next new run's default name ("runN") will use. */
  nextRunNumber: number;
  /** Called after every successful compile. Creates a new run (and makes it
   * active) for a definition hash no run has yet; otherwise re-selects the
   * existing run for that hash, refreshing its pipeline id (a recompile can
   * hand back a new one) and workflow snapshot (e.g. moved nodes). */
  recordCompiledRun: (pipelineId: string, definitionHash: string, workflow: RunWorkflow) => void;
  /** The pipeline id of the run compiled from this definition, if any -- lets
   * a recompile of an existing version reuse its pipeline instead of making
   * another one. */
  pipelineIdForHash: (definitionHash: string) => string | null;
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
  /** Appends a new chat exchange (from the Run tab) to a run and returns its id,
   * so the caller can attach feedback to it once the user votes. */
  addResponse: (runId: string, entry: { query: string; answer: string }) => string;
  /** Sets or clears the vote/explanation on one chat exchange. */
  setResponseFeedback: (
    runId: string,
    responseId: string,
    patch: { vote: "up" | "down" | null; explanation: string },
  ) => void;
}

const EvaluationRunsContext = createContext<EvaluationRunsContextValue | null>(null);

/**
 * Saves every change to `runs` through the project's autosave: new or edited
 * runs, new or edited chat responses, and deleted runs. Works by comparing
 * each render's runs with the previous ones -- state updates always replace
 * what they change, so an unchanged run/response keeps its object identity.
 * Reports aren't saved here: the backend writes them itself when an
 * evaluation job started for a run finishes.
 */
function useAutosaveRuns(runs: EvaluationRun[], persistence: ProjectPersistence): void {
  const previousRuns = useRef(runs);

  useEffect(() => {
    const previous = previousRuns.current;
    previousRuns.current = runs;
    if (previous === runs) return;

    const previousById = new Map(previous.map((run) => [run.id, run]));
    for (const run of runs) {
      const before = previousById.get(run.id);
      previousById.delete(run.id);
      if (before === run) continue;
      if (!before || runMetadataChanged(before, run)) void persistence.saveRun(run);
      if (before?.responses === run.responses) continue;

      const responsesBefore = new Map(before?.responses.map((response) => [response.id, response]));
      for (const response of run.responses) {
        if (responsesBefore.get(response.id) !== response) void persistence.saveResponse(run.id, response);
      }
    }
    for (const deletedId of previousById.keys()) void persistence.deleteRun(deletedId);
  }, [runs, persistence]);
}

/**
 * Owns the project's run history and which run is active, for the duration of
 * a project session. Mounted once around the project workspace routes (see
 * ProjectWorkspacePage), outside PipelineWorkspaceProvider so the workspace
 * can record compiles as runs and load a run's workflow when it's opened --
 * only a fresh project (a new `key`) resets it.
 */
export function EvaluationRunsProvider({
  initialState,
  children,
}: {
  /** The project's saved runs; omitted for a project with none. */
  initialState?: InitialRunsState;
  children: ReactNode;
}) {
  const [state, setState] = useState<RunsState>(() =>
    initialState ? { ...INITIAL_STATE, ...initialState } : INITIAL_STATE,
  );
  useAutosaveRuns(state.runs, useProjectPersistence());

  const recordCompiledRun = useCallback(
    (pipelineId: string, definitionHash: string, workflow: RunWorkflow) => {
      setState((current) => {
        const existing = current.runs.find((run) => run.definitionHash === definitionHash);

        if (existing) {
          return {
            ...current,
            runs: current.runs.map((run) =>
              run.id === existing.id ? { ...run, pipelineId, workflow } : run,
            ),
            activeRunId: existing.id,
            viewMode: "run",
          };
        }

        const run: EvaluationRun = {
          id: newRunId(),
          name: `run${current.nextRunNumber}`,
          pipelineId,
          definitionHash,
          createdAt: Date.now(),
          workflow,
          safetyAgentsChecked: false,
          safetyAgentsInfo: null,
          safetyAgentsError: null,
          safetyReport: null,
          agentReport: null,
          agentCsvName: null,
          reportsLoaded: true, // brand new: nothing saved to fetch
          responses: [],
        };

        return {
          ...current,
          runs: [...current.runs, run],
          activeRunId: run.id,
          viewMode: "run",
          nextRunNumber: current.nextRunNumber + 1,
        };
      });
    },
    [],
  );

  const pipelineIdForHash = useCallback(
    (definitionHash: string) =>
      state.runs.find((run) => run.definitionHash === definitionHash)?.pipelineId ?? null,
    [state.runs],
  );

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

  const addResponse = useCallback((runId: string, entry: { query: string; answer: string }) => {
    const response: ChatResponseFeedback = {
      id: newResponseId(),
      query: entry.query,
      answer: entry.answer,
      createdAt: Date.now(),
      vote: null,
      explanation: "",
    };
    setState((current) => ({
      ...current,
      runs: current.runs.map((run) =>
        run.id === runId ? { ...run, responses: [...run.responses, response] } : run,
      ),
    }));
    return response.id;
  }, []);

  const setResponseFeedback = useCallback(
    (runId: string, responseId: string, patch: { vote: "up" | "down" | null; explanation: string }) => {
      setState((current) => ({
        ...current,
        runs: current.runs.map((run) =>
          run.id === runId
            ? {
                ...run,
                responses: run.responses.map((response) =>
                  response.id === responseId ? { ...response, ...patch } : response,
                ),
              }
            : run,
        ),
      }));
    },
    [],
  );

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
      nextRunNumber: state.nextRunNumber,
      recordCompiledRun,
      pipelineIdForHash,
      selectRun,
      renameRun,
      updateRun,
      markBest,
      deleteRun,
      showCompare,
      addResponse,
      setResponseFeedback,
    }),
    [
      state.runs,
      activeRun,
      state.bestRunId,
      state.viewMode,
      state.nextRunNumber,
      recordCompiledRun,
      pipelineIdForHash,
      selectRun,
      renameRun,
      updateRun,
      markBest,
      deleteRun,
      showCompare,
      addResponse,
      setResponseFeedback,
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
