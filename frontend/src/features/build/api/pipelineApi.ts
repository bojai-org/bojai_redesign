import type {
  ApiErrorBody,
  CompileRequest,
  CompilerPipelineDefinition,
  PipelineSummary,
  RunRequest,
  RunResponse,
} from "../types/compiler";
import type {
  EvaluationJobHandle,
  EvaluationJobStatus,
  EvaluationResponse,
  SafetyAgentsResponse,
  SafetyEvalResponse,
  SafetyEvaluationJobStatus,
} from "../types/evaluation";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

/** backend/app.py's base URL. Centralized here -- nothing else should read import.meta.env directly. */
export const BUILD_API_BASE_URL: string =
  (import.meta.env.VITE_BUILD_API_URL as string | undefined) ?? DEFAULT_API_BASE_URL;

/** Normalized error for every failure mode: a non-2xx response, a network error, or an unreachable API. */
export class BuildApiError extends Error {
  /** The HTTP status, or 0 when the request never reached the server (network failure). */
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "BuildApiError";
    this.status = status;
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // Response wasn't JSON (or had no body) -- fall through to a generic message.
  }
  return `Request failed with status ${response.status}.`;
}

/** Shared fetch wrapper -- exported so other features (e.g. settings/api/settingsApi.ts)
 * hit the same base URL and get the same BuildApiError normalization instead
 * of duplicating this. */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BUILD_API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new BuildApiError(0, "Could not reach the build API. Is the backend running?");
  }

  if (!response.ok) {
    throw new BuildApiError(response.status, await readErrorDetail(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Like request(), but for a multipart/form-data body -- fetch sets its own
 * Content-Type (with boundary) for a FormData body, so this must not force
 * "application/json" the way request()'s default headers do. */
async function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BUILD_API_BASE_URL}${path}`, { method: "POST", body: formData });
  } catch {
    throw new BuildApiError(0, "Could not reach the build API. Is the backend running?");
  }

  if (!response.ok) {
    throw new BuildApiError(response.status, await readErrorDetail(response));
  }

  return (await response.json()) as T;
}

export async function checkBuildApiHealth(): Promise<boolean> {
  try {
    await request<{ status: string }>("/health");
    return true;
  } catch {
    return false;
  }
}

/** POST /pipelines/compile -- creates a new compiled pipeline (saved under `projectId`
 * when given). 409s if pipelineId already exists. */
export async function compilePipeline(
  definition: CompilerPipelineDefinition,
  { pipelineId, projectId }: { pipelineId?: string; projectId?: string } = {},
): Promise<PipelineSummary> {
  const body: CompileRequest = {
    definition,
    ...(pipelineId ? { pipeline_id: pipelineId } : {}),
    ...(projectId ? { project_id: projectId } : {}),
  };
  return request<PipelineSummary>("/pipelines/compile", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** PUT /pipelines/{pipelineId} -- recompiles an existing pipeline's definition in place. 404s if unknown. */
export async function updatePipeline(
  pipelineId: string,
  definition: CompilerPipelineDefinition,
  projectId?: string,
): Promise<PipelineSummary> {
  const body: CompileRequest = { definition, ...(projectId ? { project_id: projectId } : {}) };
  return request<PipelineSummary>(`/pipelines/${encodeURIComponent(pipelineId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** POST /pipelines/{pipelineId}/run -- runs an already-compiled pipeline. 404s if it's no longer stored. */
export async function runPipeline(pipelineId: string, query?: string): Promise<RunResponse> {
  // Nothing in this app reads RunResponse.trace, and retrieval agents accumulate
  // the full resource list into their result on every hop -- with a large corpus
  // that trace can be large enough to make the browser choke on parsing it. See
  // RunRequest.include_trace's doc comment.
  const body: RunRequest = { query, include_trace: false };
  return request<RunResponse>(`/pipelines/${encodeURIComponent(pipelineId)}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /pipelines/{pipelineId}/evaluate/safety-agents -- whether this pipeline has barrier-agent nodes. */
export async function getSafetyAgents(pipelineId: string): Promise<SafetyAgentsResponse> {
  return request<SafetyAgentsResponse>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/safety-agents`,
  );
}

/** Evaluating a CSV means one pipeline run (plus an LLM faithfulness judge and an
 * embedding call) per question -- too slow to hold a single request open for, so
 * the backend runs it as a background job (backend/app.py's EvaluationJob) and
 * these functions poll it. Poll interval is fixed rather than configurable: it
 * only paces UI updates, not the job itself, so there's nothing to tune per call site. */
const JOB_POLL_INTERVAL_MS = 400;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** POST /pipelines/{pipelineId}/evaluate/safety/jobs -- starts a safety-track job against the
 * built-in 120-question harmful/unharmful set. 400s if the pipeline has no safety-agent nodes.
 * With `runId`, the backend saves the report to that run when the job finishes. */
export async function startSafetyJob(pipelineId: string, runId?: string): Promise<EvaluationJobHandle> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return request<EvaluationJobHandle>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/safety/jobs${query}`,
    { method: "POST" },
  );
}

/** GET /pipelines/{pipelineId}/evaluate/safety/jobs/{jobId} */
export async function getSafetyJob(pipelineId: string, jobId: string): Promise<SafetyEvaluationJobStatus> {
  return request<SafetyEvaluationJobStatus>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/safety/jobs/${encodeURIComponent(jobId)}`,
  );
}

/** POST /pipelines/{pipelineId}/evaluate/safety/jobs/{jobId}/cancel -- stops the job between rows;
 * a no-op if it already finished. */
export async function cancelSafetyJob(pipelineId: string, jobId: string): Promise<void> {
  await request<void>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/safety/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
}

/** POST /pipelines/{pipelineId}/evaluate/jobs -- starts a full-evaluation job against an uploaded
 * CSV (question, expected_answer, optional expected_resource(s)); the result's "safety" field is
 * populated automatically when the pipeline contains barrier-agent nodes. With `runId`, the
 * backend keeps the CSV and saves the reports to that run when the job finishes. */
export async function startEvaluateJob(
  pipelineId: string,
  csvFile: File,
  runId?: string,
): Promise<EvaluationJobHandle> {
  const formData = new FormData();
  formData.append("file", csvFile);
  if (runId) formData.append("run_id", runId);
  return requestMultipart<EvaluationJobHandle>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/jobs`,
    formData,
  );
}

/** GET /pipelines/{pipelineId}/evaluate/jobs/{jobId} */
export async function getEvaluateJob(pipelineId: string, jobId: string): Promise<EvaluationJobStatus> {
  return request<EvaluationJobStatus>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/jobs/${encodeURIComponent(jobId)}`,
  );
}

/** POST /pipelines/{pipelineId}/evaluate/jobs/{jobId}/cancel -- stops the job between rows;
 * a no-op if it already finished. */
export async function cancelEvaluateJob(pipelineId: string, jobId: string): Promise<void> {
  await request<void>(
    `/pipelines/${encodeURIComponent(pipelineId)}/evaluate/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
}

/** Thrown by evaluateSafetyWithProgress/evaluatePipelineWithProgress when the job's
 * status flips to "cancelled" -- distinct from BuildApiError since it's not a
 * request failure, so callers can tell "you stopped it" apart from "it broke". */
export class EvaluationCancelledError extends Error {
  constructor() {
    super("The evaluation was cancelled.");
    this.name = "EvaluationCancelledError";
  }
}

/** Starts the safety-track job and polls it to completion, calling `onProgress`
 * with (completed, total) -- first as soon as `total` is known (before the job
 * has processed anything), then after every poll -- so a caller can drive a
 * progress bar. `onJobStarted` fires once the job id is known, so a caller can
 * hold onto it to cancel the job later via cancelSafetyJob. Resolves with the
 * final report; rejects with a BuildApiError if the job reports "error", or an
 * EvaluationCancelledError if it was cancelled. */
export async function evaluateSafetyWithProgress(
  pipelineId: string,
  onProgress?: (completed: number, total: number) => void,
  onJobStarted?: (jobId: string) => void,
  runId?: string,
): Promise<SafetyEvalResponse> {
  const handle = await startSafetyJob(pipelineId, runId);
  onJobStarted?.(handle.job_id);
  onProgress?.(0, handle.total);

  for (;;) {
    const status = await getSafetyJob(pipelineId, handle.job_id);
    onProgress?.(status.completed, status.total);

    if (status.status === "error") {
      throw new BuildApiError(0, status.error ?? "The safety check failed.");
    }
    if (status.status === "cancelled") {
      throw new EvaluationCancelledError();
    }
    if (status.status === "done") {
      if (!status.result) throw new BuildApiError(0, "The safety check finished without a result.");
      return status.result;
    }
    await wait(JOB_POLL_INTERVAL_MS);
  }
}

/** Same contract as evaluateSafetyWithProgress, for the full CSV-driven evaluation. */
export async function evaluatePipelineWithProgress(
  pipelineId: string,
  csvFile: File,
  onProgress?: (completed: number, total: number) => void,
  onJobStarted?: (jobId: string) => void,
  runId?: string,
): Promise<EvaluationResponse> {
  const handle = await startEvaluateJob(pipelineId, csvFile, runId);
  onJobStarted?.(handle.job_id);
  onProgress?.(0, handle.total);

  for (;;) {
    const status = await getEvaluateJob(pipelineId, handle.job_id);
    onProgress?.(status.completed, status.total);

    if (status.status === "error") {
      throw new BuildApiError(0, status.error ?? "The evaluation failed.");
    }
    if (status.status === "cancelled") {
      throw new EvaluationCancelledError();
    }
    if (status.status === "done") {
      if (!status.result) throw new BuildApiError(0, "The evaluation finished without a result.");
      return status.result;
    }
    await wait(JOB_POLL_INTERVAL_MS);
  }
}
