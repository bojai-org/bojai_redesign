/** Wire-format types for backend/app.py's /projects/{id}/... persistence endpoints. */
import type { AgentEvalResponse, SafetyEvalResponse } from "../../build/types/evaluation";
import type { RunWorkflow } from "../../evaluate/types/run";
import type { PipelineEdge, PipelineNode, PipelineRuntimeConfig } from "../../build/types/pipeline";
import type { ProjectRecord } from "./project";

/** The Build canvas as saved -- compiled or not. */
export interface SavedGraph {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  runtimeConfig: PipelineRuntimeConfig;
}

/** Body of PUT /projects/{id}/workspace, and `workspace` in GET .../state. */
export interface WorkspaceState {
  graph: SavedGraph;
  active_run_id: string | null;
  best_run_id: string | null;
  next_run_number: number;
}

/** Body of PUT /projects/{id}/runs/{runId}/responses/{responseId}. */
export interface ChatResponseState {
  query: string;
  answer: string;
  vote: "up" | "down" | null;
  explanation: string;
  /** Milliseconds since the epoch. */
  created_at: number;
}

export interface StoredChatResponse extends ChatResponseState {
  id: string;
}

/** Body of PUT /projects/{id}/runs/{runId}. */
export interface RunState {
  pipeline_id: string;
  name: string;
  definition_hash: string;
  workflow: RunWorkflow;
  /** Milliseconds since the epoch. */
  created_at: number;
}

export interface StoredRun extends RunState {
  id: string;
  responses: StoredChatResponse[];
  /** Which reports exist -- fetched separately via GET .../reports. */
  report_kinds: ("safety" | "agent")[];
}

/** GET /projects/{id}/state -- everything needed to reopen a project. */
export interface ProjectStateResponse {
  project: ProjectRecord;
  workspace: WorkspaceState | null;
  runs: StoredRun[];
}

export interface StoredReport<T> {
  report: T;
  /** Original file name of the CSV an agent report was run on. */
  csv_name: string | null;
  created_at: string;
}

/** GET /projects/{id}/runs/{runId}/reports */
export interface RunReportsResponse {
  safety: StoredReport<SafetyEvalResponse> | null;
  agent: StoredReport<AgentEvalResponse> | null;
}
