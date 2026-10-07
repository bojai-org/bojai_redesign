import type {
  AgentEvalResponse,
  SafetyAgentsResponse,
  SafetyEvalResponse,
} from "../../build/types/evaluation";
import type { PipelineSummary } from "../../build/types/compiler";
import type { PipelineEdge, PipelineNode, PipelineRuntimeConfig } from "../../build/types/pipeline";

/** The Build graph exactly as it was when a run's pipeline was compiled --
 * opening the run loads this back into the Build canvas. */
export interface RunWorkflow {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  runtimeConfig: PipelineRuntimeConfig;
  summary: PipelineSummary | null;
}

/** One query/answer exchange from the Run tab's chat window, plus the user's
 * feedback on it. Feedback lives on the exchange itself (not a separate list)
 * so the Evaluate tab's Responses view and the Run tab's chat bubbles are
 * always looking at the same record. */
export interface ChatResponseFeedback {
  id: string;
  query: string;
  answer: string;
  createdAt: number;
  vote: "up" | "down" | null;
  /** Free-text reason for the vote. Kept even after the vote is cleared, in
   * case the user re-votes the same way a moment later. */
  explanation: string;
}

/**
 * One compiled version of the project's pipeline, plus everything done with
 * it: its chat responses (Run tab) and evaluation results (Evaluate tab). A
 * new run is created whenever Build compiles a definition no existing run has
 * (see EvaluationRunsContext.recordCompiledRun) -- recompiling an unchanged
 * definition re-selects that definition's run instead. The active run is
 * shared by every project tab (see RunBar): opening one loads its workflow
 * into Build and points Run/Evaluate at its pipeline.
 */
export interface EvaluationRun {
  id: string;
  /** User-editable; defaults to "run1", "run2", ... in creation order. */
  name: string;
  /** The backend pipeline compiled from this run's workflow. Each run has its
   * own, so older runs keep running the version they were created from. */
  pipelineId: string;
  /** hashPipelineDefinition() of the compiled definition -- identifies which
   * graph version this run belongs to. */
  definitionHash: string;
  createdAt: number;
  /** Snapshot of the Build graph this run was compiled from. */
  workflow: RunWorkflow;

  /** Whether the one-time "does this pipeline have safety agents" lookup has
   * completed (success or failure) -- distinct from `safetyAgentsInfo` being
   * null, so it's fetched exactly once per run instead of on every render. */
  safetyAgentsChecked: boolean;
  safetyAgentsInfo: SafetyAgentsResponse | null;
  safetyAgentsError: string | null;

  safetyReport: SafetyEvalResponse | null;
  agentReport: AgentEvalResponse | null;
  /** Original file name of the CSV agentReport was produced from -- the
   * backend keeps that file, so the same evaluation can be run again. */
  agentCsvName: string | null;
  /** False for a run loaded from the backend whose saved reports haven't been
   * fetched yet (they're left out of the project state to keep it small);
   * Evaluate fetches them when the run is viewed or compared. */
  reportsLoaded: boolean;

  /** Chat exchanges sent from the Run tab against this run's pipeline, oldest first. */
  responses: ChatResponseFeedback[];
}
