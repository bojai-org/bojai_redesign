import type {
  AgentEvalResponse,
  SafetyAgentsResponse,
  SafetyEvalResponse,
} from "../../build/types/evaluation";

/**
 * One evaluation "session" against a specific compiled pipeline version. A new
 * run is created automatically whenever the Evaluate tab is opened and the
 * compiled definition has changed since the last run (see
 * EvaluationRunsContext.ensureRunForPipeline) -- re-running evaluation against
 * an unchanged pipeline updates the same run in place instead.
 */
export interface EvaluationRun {
  id: string;
  /** User-editable; defaults to "run1", "run2", ... in creation order. */
  name: string;
  /** The backend pipeline id this run's evaluations were executed against. */
  pipelineId: string;
  /** compileState.lastCompiledDefinitionHash at the moment this run was created --
   * identifies which graph version this run belongs to, since the backend
   * pipelineId itself can be reused across recompiles (PUT updates in place). */
  definitionHash: string;
  createdAt: number;

  /** Whether the one-time "does this pipeline have safety agents" lookup has
   * completed (success or failure) -- distinct from `safetyAgentsInfo` being
   * null, so it's fetched exactly once per run instead of on every render. */
  safetyAgentsChecked: boolean;
  safetyAgentsInfo: SafetyAgentsResponse | null;
  safetyAgentsError: string | null;

  safetyReport: SafetyEvalResponse | null;
  agentReport: AgentEvalResponse | null;
}
