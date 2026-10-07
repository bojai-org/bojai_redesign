import { BUILD_API_BASE_URL, BuildApiError, request } from "../../build/api/pipelineApi";
import type {
  ChatResponseState,
  ProjectStateResponse,
  RunReportsResponse,
  RunState,
  WorkspaceState,
} from "../types/projectState";

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

function runPath(projectId: string, runId: string): string {
  return `${projectPath(projectId)}/runs/${encodeURIComponent(runId)}`;
}

/** GET /projects/{id}/state -- the project, its saved workspace and its runs
 * (with chat responses, without reports). 404s for an unknown project. */
export async function getProjectState(projectId: string): Promise<ProjectStateResponse> {
  return request<ProjectStateResponse>(`${projectPath(projectId)}/state`);
}

/** PUT /projects/{id}/workspace. `keepalive` lets the save finish while the
 * page is closing (browsers cap such bodies at 64 KB). */
export async function saveWorkspace(
  projectId: string,
  workspace: WorkspaceState,
  { keepalive = false }: { keepalive?: boolean } = {},
): Promise<void> {
  await request<void>(`${projectPath(projectId)}/workspace`, {
    method: "PUT",
    body: JSON.stringify(workspace),
    keepalive,
  });
}

/** PUT /projects/{id}/runs/{runId} -- creates or updates a run. */
export async function saveRun(projectId: string, runId: string, run: RunState): Promise<void> {
  await request<void>(runPath(projectId, runId), { method: "PUT", body: JSON.stringify(run) });
}

/** DELETE /projects/{id}/runs/{runId} -- also deletes its responses, reports and kept CSVs. */
export async function deleteRun(projectId: string, runId: string): Promise<void> {
  await request<void>(runPath(projectId, runId), { method: "DELETE" });
}

/** PUT /projects/{id}/runs/{runId}/responses/{responseId} -- creates or updates a chat exchange. */
export async function saveResponse(
  projectId: string,
  runId: string,
  responseId: string,
  response: ChatResponseState,
): Promise<void> {
  await request<void>(`${runPath(projectId, runId)}/responses/${encodeURIComponent(responseId)}`, {
    method: "PUT",
    body: JSON.stringify(response),
  });
}

/** GET /projects/{id}/runs/{runId}/reports -- the run's saved evaluation reports. */
export async function getRunReports(projectId: string, runId: string): Promise<RunReportsResponse> {
  return request<RunReportsResponse>(`${runPath(projectId, runId)}/reports`);
}

/** GET .../reports/agent/csv -- the exact CSV the run's agent report was produced
 * from, as a File, so the same evaluation can be run again. */
export async function fetchRunEvalCsv(projectId: string, runId: string, fileName: string): Promise<File> {
  let response: Response;
  try {
    response = await fetch(`${BUILD_API_BASE_URL}${runPath(projectId, runId)}/reports/agent/csv`);
  } catch {
    throw new BuildApiError(0, "Could not reach the build API. Is the backend running?");
  }
  if (!response.ok) {
    throw new BuildApiError(response.status, "The saved evaluation CSV could not be loaded.");
  }
  return new File([await response.blob()], fileName, { type: "text/csv" });
}
