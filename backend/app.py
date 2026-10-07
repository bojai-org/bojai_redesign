"""
BojAI Build — HTTP API

Exposes compiler.py / pipeline.py over HTTP: a frontend compiles a pipeline
definition once, gets back an id, then runs that same compiled pipeline
against as many queries as it wants without recompiling each time.

Compiled pipelines live in an in-memory registry (module-level dict), backed
by their definitions in SQLite (database.py): a pipeline id that isn't in
memory -- e.g. after a restart -- is recompiled from its saved definition on
first use. Projects and everything under them (workspace, runs, chat
responses, evaluation reports) are persisted there too; evaluation jobs
themselves are not, but a job started with a run_id writes its report to that
run when it finishes.

This module is frontend-agnostic: it exposes the generic contract described
in contract.md and does not assume any particular UI's data shapes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

# backend/*.py import each other with bare names (e.g. `from base_classes import
# Agent`) but base_classes.py itself imports `from backend.prompt import ...`,
# so both this directory and the repo root need to be on sys.path -- however
# app.py is launched (`python backend/app.py`, `uvicorn app:app` from within
# backend/, or `uvicorn backend.app:app` from the repo root).
_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
for _path in (_REPO_ROOT, _BACKEND_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agents
import database
import evaluator
import safety_agents
from compiler import PipelineContractError, compile_pipeline
from evaluator import (
    CsvValidationError,
    Evaluator,
    EvaluationError,
    evaluate_safety,
    find_safety_node_ids,
)
from pipeline import Pipeline, PipelineRuntimeError

AGENT_REGISTRY: dict[str, Any] = {
    "Decision_Agent": agents.Decision_Agent,
    "RAG_Agent": agents.RAG_Agent,
    "Keyword_Search_Agent": agents.Keyword_Search_Agent,
    "Hybrid_Agent": agents.Hybrid_Agent,
    "Reranker_Agent": agents.Reranker_Agent,
    "Binary_Judge_Agent": agents.Binary_Judge_Agent,
    "Direct_Answer_Agent": agents.Direct_Answer_Agent,
    "Static_Agent": agents.Static_Agent,
    "Simple_Task_Agent": agents.Simple_Task_Agent,
    "_Static_Agent_Auto": agents._Static_Agent_Auto,
    "Static_Barrier_Agent": safety_agents.Static_Barrier_Agent,
    "Judge_Barrier_Agent": safety_agents.Judge_Barrier_Agent,
    # Neural_Network_Barrier_Agent / Input_Barrier_Pipeline need a Python
    # embed_texts callable, which an HTTP JSON body can't carry (contract.md
    # section 10) -- unsupported over this API.
}


@dataclass
class StoredPipeline:
    definition: dict[str, Any]
    pipeline: Pipeline


_pipelines: dict[str, StoredPipeline] = {}

# Names set via POST /config/env, tracked separately so GET /config/env can
# list just those instead of dumping the whole (much larger, unrelated)
# process environment.
_managed_env_vars: set[str] = set()


@dataclass
class EvaluationJob:
    """Mutable progress/result cell for one background evaluation run.

    Evaluating a CSV means one pipeline.run() (plus an LLM faithfulness judge
    and an embedding call) per question, which is too slow to hold an HTTP
    request open for -- POST .../evaluate/jobs starts one of these as an
    asyncio task and returns immediately; the frontend polls
    GET .../evaluate/jobs/{job_id} to drive a progress bar off `completed`.
    """

    status: Literal["running", "done", "error", "cancelled"] = "running"
    completed: int = 0
    total: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    # Set right after asyncio.create_task(...) so a cancel request can stop the
    # loop between rows instead of just abandoning it client-side (which would
    # leave the LLM calls running server-side for no one).
    task: asyncio.Task[None] | None = None


_evaluation_jobs: dict[str, EvaluationJob] = {}


def _get_job(job_id: str) -> EvaluationJob:
    job = _evaluation_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No evaluation job with id {job_id!r}")
    return job


def _cancel_job(job_id: str) -> EvaluationJob:
    """Idempotent: cancelling a job that already finished (or was already
    cancelled) is a no-op rather than an error, since the two requests racing
    is an expected outcome, not a client mistake."""
    job = _get_job(job_id)
    if job.status == "running" and job.task is not None:
        job.task.cancel()
        job.status = "cancelled"
    return job


app = FastAPI(title="BojAI Build API")

# Permissive by default since this serves a separate-origin dev frontend;
# tighten allow_origins before deploying anywhere that matters.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SetEnvVarRequest(BaseModel):
    name: str = Field(description="Environment variable name, e.g. OPENAI_API_KEY.")
    value: str = Field(description="The value to set it to.")


class EnvVarsResponse(BaseModel):
    # Names only -- values are never echoed back over the wire.
    names: list[str]


class CreateProjectRequest(BaseModel):
    name: str = Field(description="Display name; must not be blank.")
    description: str = Field(default="", description="Optional one-line summary.")


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    status: Literal["active", "draft", "archived"]
    created_at: str
    updated_at: str


class ProjectsResponse(BaseModel):
    projects: list[ProjectResponse]


class WorkspaceState(BaseModel):
    graph: dict[str, Any] = Field(description="The Build canvas: nodes, edges, runtimeConfig.")
    active_run_id: str | None = None
    best_run_id: str | None = None
    next_run_number: int = Field(default=1, ge=1)


class ChatResponseState(BaseModel):
    query: str
    answer: str
    vote: Literal["up", "down"] | None = None
    explanation: str = ""
    created_at: int = Field(description="Milliseconds since the epoch.")


class StoredChatResponse(ChatResponseState):
    id: str


class RunState(BaseModel):
    pipeline_id: str
    name: str
    definition_hash: str
    workflow: dict[str, Any] = Field(description="Snapshot of the graph this run was compiled from.")
    created_at: int = Field(description="Milliseconds since the epoch.")


class StoredRun(RunState):
    id: str
    responses: list[StoredChatResponse]
    report_kinds: list[Literal["safety", "agent"]] = Field(
        description="Which reports exist for this run; fetch them via .../reports."
    )


class ProjectStateResponse(BaseModel):
    project: ProjectResponse
    workspace: WorkspaceState | None
    runs: list[StoredRun]


class StoredReport(BaseModel):
    report: dict[str, Any]
    csv_name: str | None = Field(description="Original name of the CSV an agent report was run on.")
    created_at: str


class RunReportsResponse(BaseModel):
    safety: StoredReport | None
    agent: StoredReport | None


class CompileRequest(BaseModel):
    pipeline_id: str | None = Field(
        default=None,
        description="Reuse this id if provided; otherwise a new one is generated.",
    )
    project_id: str | None = Field(
        default=None,
        description="The project this pipeline belongs to, if any; deleted with it.",
    )
    definition: dict[str, Any] = Field(
        description="A pipeline JSON document, per backend/contract.md."
    )


class PipelineSummary(BaseModel):
    pipeline_id: str
    entrypoint: str
    node_ids: list[str]
    config: dict[str, Any]


class RunRequest(BaseModel):
    query: str | None = Field(
        default=None, description="Passed through as Pipeline.run(initial_query=...)."
    )
    include_trace: bool = Field(
        default=True,
        description=(
            "Retrieval agents accumulate the full resource list into their result on "
            "every hop (see agents.py's _Retrieval_Agent), so a large corpus can make "
            "the trace much bigger than the answer itself. Callers that only need "
            "`output` (e.g. a chat UI) should set this False to skip paying for it."
        ),
    )


class TraceStep(BaseModel):
    node_id: str
    route: str | None
    next_node_id: str | None
    result: Any


class RunResponse(BaseModel):
    output: Any
    trace: list[TraceStep]


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────


class SafetyNodeInfo(BaseModel):
    node_id: str
    agent_type: str


class SafetyAgentsResponse(BaseModel):
    has_safety_agents: bool
    nodes: list[SafetyNodeInfo]


class SafetyGateCounts(BaseModel):
    node_id: str
    agent_type: str
    total: int
    action_counts: dict[str, int]


class SafetyGateStep(BaseModel):
    node_id: str
    agent_type: str
    action: str | None


class SafetyQuestionResult(BaseModel):
    question: str
    label: str
    predicted: str
    path: list[SafetyGateStep]
    error: str | None = None


class SafetyEvalResponse(BaseModel):
    total_questions: int
    gate_counts: list[SafetyGateCounts]
    confusion: dict[str, int]
    precision: float
    recall: float
    f1: float
    results: list[SafetyQuestionResult]
    errors: int


class RetrievedChunk(BaseModel):
    rank: int
    chunk_id: str | None
    section: str | None
    url: str | None
    text: str


class ResourceMatch(BaseModel):
    expected: str
    found: bool
    rank: int | None
    chunk_id: str | None


class QuestionEvalResult(BaseModel):
    question: str
    expected_answer: str
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    resource_matches: list[ResourceMatch]
    faithfulness: dict[str, Any]
    answer_similarity: float
    error: str | None = None


class AgentEvalResponse(BaseModel):
    results: list[QuestionEvalResult]
    resource_recall: float | None
    mean_answer_similarity: float
    mean_faithfulness: float
    errors: int


class EvaluationResponse(BaseModel):
    agent: AgentEvalResponse
    safety: SafetyEvalResponse | None


class EvaluationJobHandle(BaseModel):
    job_id: str
    total: int


class EvaluationJobStatus(BaseModel):
    status: Literal["running", "done", "error", "cancelled"]
    completed: int
    total: int
    result: EvaluationResponse | None = None
    error: str | None = None


class SafetyEvaluationJobStatus(BaseModel):
    status: Literal["running", "done", "error", "cancelled"]
    completed: int
    total: int
    result: SafetyEvalResponse | None = None
    error: str | None = None


def _summarize(pipeline_id: str, pipeline: Pipeline) -> PipelineSummary:
    node_ids = [node_id for node_id in pipeline.nodes if node_id != "_final"]
    return PipelineSummary(
        pipeline_id=pipeline_id,
        entrypoint=pipeline.definition["entrypoint"],
        node_ids=node_ids,
        config=pipeline.config,
    )


def _compile(definition: dict[str, Any]) -> Pipeline:
    try:
        pipeline = compile_pipeline(definition, agent_registry=AGENT_REGISTRY)
        pipeline.flow()  # instantiate every node now so bad agent_args fail at compile time
    except PipelineContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Malformed pipeline definition: {exc}") from exc
    return pipeline


def _compile_and_store(
    pipeline_id: str, definition: dict[str, Any], project_id: str | None = None
) -> PipelineSummary:
    if project_id is not None and database.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id!r}")
    pipeline = _compile(definition)
    database.save_pipeline(pipeline_id, definition, project_id)
    _pipelines[pipeline_id] = StoredPipeline(definition=definition, pipeline=pipeline)
    return _summarize(pipeline_id, pipeline)


def _get_stored(pipeline_id: str) -> StoredPipeline:
    """The compiled pipeline, recompiling it from its saved definition if it
    isn't in memory (it was compiled before this process started)."""
    stored = _pipelines.get(pipeline_id)
    if stored is not None:
        return stored
    definition = database.get_pipeline_definition(pipeline_id)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"No pipeline with id {pipeline_id!r}")
    stored = StoredPipeline(definition=definition, pipeline=_compile(definition))
    _pipelines[pipeline_id] = stored
    return stored


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/config/env", status_code=204)
async def set_env_var(request: SetEnvVarRequest) -> None:
    """Sets a process environment variable (e.g. an LLM provider's API key).

    Lives only in this backend process's environment -- not written to disk
    or encrypted, and lost on restart, same as the in-memory pipeline
    registry above. Fine for local use; revisit before this is ever exposed
    beyond localhost.
    """
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    os.environ[name] = request.value
    _managed_env_vars.add(name)


@app.get("/config/env", response_model=EnvVarsResponse)
async def list_env_vars() -> EnvVarsResponse:
    """Names of the variables set via POST /config/env -- never their values."""
    return EnvVarsResponse(names=sorted(_managed_env_vars))


@app.delete("/config/env/{name}", status_code=204)
async def delete_env_var(name: str) -> None:
    if name not in _managed_env_vars:
        raise HTTPException(status_code=404, detail=f"No env var named {name!r}")
    os.environ.pop(name, None)
    _managed_env_vars.discard(name)


@app.get("/projects", response_model=ProjectsResponse)
async def list_projects() -> ProjectsResponse:
    """Saved projects, most recently edited first. Persisted in SQLite, so they
    survive a backend restart (unlike pipelines and evaluation jobs)."""
    projects = database.list_projects()
    return ProjectsResponse(projects=[ProjectResponse(**asdict(p)) for p in projects])


@app.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(request: CreateProjectRequest) -> ProjectResponse:
    try:
        project = database.create_project(request.name, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectResponse(**asdict(project))


def _get_project_or_404(project_id: str) -> database.Project:
    project = database.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id!r}")
    return project


@app.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    return ProjectResponse(**asdict(_get_project_or_404(project_id)))


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    """Deletes the project and everything under it: workspace, runs, chat
    responses, reports, kept eval CSVs and its compiled pipelines. Evaluation
    jobs still running against its pipelines finish, but their reports are
    dropped (their run no longer exists)."""
    try:
        pipeline_ids = database.delete_project(project_id)
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for pipeline_id in pipeline_ids:
        _pipelines.pop(pipeline_id, None)


@app.get("/projects/{project_id}/state", response_model=ProjectStateResponse)
async def get_project_state(project_id: str) -> ProjectStateResponse:
    """Everything needed to reopen a project in one call: the project, its
    workspace (null until first saved) and its runs with their chat responses.
    Reports are left out -- fetch a run's via .../runs/{run_id}/reports."""
    project = _get_project_or_404(project_id)
    workspace = database.get_workspace(project_id)
    return ProjectStateResponse(
        project=ProjectResponse(**asdict(project)),
        workspace=WorkspaceState(**workspace) if workspace else None,
        runs=[StoredRun(**run) for run in database.list_runs(project_id)],
    )


@app.put("/projects/{project_id}/workspace", status_code=204)
async def save_workspace(project_id: str, request: WorkspaceState) -> None:
    """Replaces the saved Build canvas (compiled or not) and run selection."""
    try:
        database.save_workspace(
            project_id, request.graph, request.active_run_id, request.best_run_id, request.next_run_number
        )
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/projects/{project_id}/runs/{run_id}", status_code=204)
async def save_run(project_id: str, run_id: str, request: RunState) -> None:
    """Creates or updates a run (the client picks its id)."""
    try:
        database.save_run(project_id, run_id, **request.model_dump())
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/projects/{project_id}/runs/{run_id}", status_code=204)
async def delete_run(project_id: str, run_id: str) -> None:
    """Deletes a run with its chat responses, reports and kept eval CSVs."""
    try:
        database.delete_run(project_id, run_id)
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/projects/{project_id}/runs/{run_id}/responses/{response_id}", status_code=204)
async def save_response(project_id: str, run_id: str, response_id: str, request: ChatResponseState) -> None:
    """Creates or updates one chat exchange (including its vote/explanation)."""
    try:
        database.save_response(project_id, run_id, response_id, **request.model_dump())
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/projects/{project_id}/runs/{run_id}/reports", response_model=RunReportsResponse)
async def get_run_reports(project_id: str, run_id: str) -> RunReportsResponse:
    try:
        reports = database.get_reports(project_id, run_id)
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunReportsResponse(
        safety=StoredReport(**reports["safety"]) if reports["safety"] else None,
        agent=StoredReport(**reports["agent"]) if reports["agent"] else None,
    )


@app.get("/projects/{project_id}/runs/{run_id}/reports/agent/csv")
async def get_run_report_csv(project_id: str, run_id: str) -> FileResponse:
    """The CSV the run's agent report was produced from, as uploaded -- e.g. to
    re-run the exact same evaluation."""
    try:
        found = database.get_report_csv(project_id, run_id)
    except database.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="This run has no saved evaluation CSV.")
    path, name = found
    return FileResponse(path, media_type="text/csv", filename=name)


@app.get("/agents")
async def list_agents() -> dict[str, list[str]]:
    """The agent types a pipeline definition's nodes may use with this registry."""
    return {"agent_types": sorted(AGENT_REGISTRY)}


@app.get("/pipelines")
async def list_pipelines() -> dict[str, list[str]]:
    return {"pipeline_ids": sorted(set(_pipelines) | set(database.list_pipeline_ids()))}


@app.post("/pipelines/compile", response_model=PipelineSummary, status_code=201)
async def compile_endpoint(request: CompileRequest) -> PipelineSummary:
    pipeline_id = request.pipeline_id or str(uuid.uuid4())
    if pipeline_id in _pipelines or database.get_pipeline_definition(pipeline_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"pipeline_id {pipeline_id!r} already exists; "
            f"PUT /pipelines/{pipeline_id} to update it instead.",
        )
    return _compile_and_store(pipeline_id, request.definition, request.project_id)


@app.get("/pipelines/{pipeline_id}", response_model=PipelineSummary)
async def get_pipeline(pipeline_id: str) -> PipelineSummary:
    stored = _get_stored(pipeline_id)
    return _summarize(pipeline_id, stored.pipeline)


@app.put("/pipelines/{pipeline_id}", response_model=PipelineSummary)
async def update_pipeline(pipeline_id: str, request: CompileRequest) -> PipelineSummary:
    """Recompile an existing pipeline's definition in place, replacing it."""
    _get_stored(pipeline_id)
    return _compile_and_store(pipeline_id, request.definition, request.project_id)


@app.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: str) -> None:
    _get_stored(pipeline_id)
    _pipelines.pop(pipeline_id, None)
    database.delete_pipeline(pipeline_id)


@app.post("/pipelines/{pipeline_id}/run", response_model=RunResponse)
async def run_pipeline(pipeline_id: str, request: RunRequest) -> RunResponse:
    stored = _get_stored(pipeline_id)

    try:
        result = await stored.pipeline.run(initial_query=request.query)
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EnvironmentError as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider is not configured: {exc}") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline execution failed: {exc}") from exc

    return RunResponse(
        output=result.output,
        trace=[
            TraceStep(
                node_id=step.node_id,
                route=step.route,
                next_node_id=step.next_node_id,
                result=step.result,
            )
            for step in result.trace
        ]
        if request.include_trace
        else [],
    )


@app.get("/pipelines/{pipeline_id}/evaluate/safety-agents", response_model=SafetyAgentsResponse)
async def pipeline_safety_agents(pipeline_id: str) -> SafetyAgentsResponse:
    """Whether this pipeline has barrier-agent nodes, so the frontend knows
    whether to show a safety-metrics section before the user uploads a CSV.
    """
    stored = _get_stored(pipeline_id)
    nodes = stored.pipeline.flow()
    node_ids = find_safety_node_ids(stored.pipeline)
    return SafetyAgentsResponse(
        has_safety_agents=bool(node_ids),
        nodes=[
            SafetyNodeInfo(node_id=node_id, agent_type=nodes[node_id].spec.get("type", ""))
            for node_id in node_ids
        ],
    )


def _require_run_for_job(run_id: str | None) -> None:
    if run_id is not None and database.run_project_id(run_id) is None:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id!r}")


def _save_job_report(
    run_id: str,
    kind: database.ReportKind,
    report: dict[str, Any],
    csv_file: str | None = None,
    csv_name: str | None = None,
) -> bool:
    """Best effort: the run may have been deleted while its job ran. The job's
    own result is unaffected either way."""
    try:
        database.save_report(run_id, kind, report, csv_file=csv_file, csv_name=csv_name)
        return True
    except database.NotFoundError:
        return False


async def _run_safety_job(job: EvaluationJob, pipeline: Pipeline, run_id: str | None = None) -> None:
    def bump() -> None:
        job.completed += 1

    try:
        report = await evaluate_safety(pipeline, on_progress=bump)
        job.result = asdict(report)
        if run_id is not None:
            _save_job_report(run_id, "safety", job.result)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error, not an unhandled task exception
        job.error = str(exc)
        job.status = "error"


@app.post("/pipelines/{pipeline_id}/evaluate/safety/jobs", response_model=EvaluationJobHandle, status_code=202)
async def start_safety_job(pipeline_id: str, run_id: str | None = None) -> EvaluationJobHandle:
    """Start a safety-track evaluation (the built-in 120-question harmful/unharmful
    set) as a background job and return immediately. Poll
    GET .../evaluate/safety/jobs/{job_id} for progress and the final report.
    With ?run_id=..., the report is also saved to that run when the job finishes.
    """
    stored = _get_stored(pipeline_id)
    _require_run_for_job(run_id)
    if not find_safety_node_ids(stored.pipeline):
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline {pipeline_id!r} has no safety-agent nodes to evaluate.",
        )

    try:
        # Called through the module (not a `from evaluator import ...` name) so
        # that monkeypatching evaluator.resolve_builtin_safety_csv (see the test
        # suite) is observed here too, not just inside evaluate_safety() itself.
        total = len(evaluator.load_safety_csv(evaluator.resolve_builtin_safety_csv()))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job = EvaluationJob(total=total)
    job_id = str(uuid.uuid4())
    _evaluation_jobs[job_id] = job
    job.task = asyncio.create_task(_run_safety_job(job, stored.pipeline, run_id))
    return EvaluationJobHandle(job_id=job_id, total=total)


@app.get(
    "/pipelines/{pipeline_id}/evaluate/safety/jobs/{job_id}",
    response_model=SafetyEvaluationJobStatus,
)
async def get_safety_job(pipeline_id: str, job_id: str) -> SafetyEvaluationJobStatus:
    _get_stored(pipeline_id)
    job = _get_job(job_id)
    return SafetyEvaluationJobStatus(
        status=job.status,
        completed=job.completed,
        total=job.total,
        result=SafetyEvalResponse(**job.result) if job.result is not None else None,
        error=job.error,
    )


@app.post("/pipelines/{pipeline_id}/evaluate/safety/jobs/{job_id}/cancel", status_code=204)
async def cancel_safety_job(pipeline_id: str, job_id: str) -> None:
    """Stops a running safety job between rows -- already-in-flight LLM calls
    for the current row still finish, but no further rows start."""
    _get_stored(pipeline_id)
    _cancel_job(job_id)


async def _run_evaluation_job(
    job: EvaluationJob,
    pipeline_evaluator: Evaluator,
    run_id: str | None = None,
    csv_file: str | None = None,
    csv_name: str | None = None,
) -> None:
    """With a run_id, saves the agent report (pointing at the CSV kept in
    files/) and any safety report to that run. The kept CSV is deleted again
    if no report ends up referencing it -- the job failed, was cancelled, or
    its run was deleted meanwhile."""

    def bump() -> None:
        job.completed += 1

    csv_kept = False
    try:
        report = await pipeline_evaluator.evaluate(on_progress=bump)
        job.result = asdict(report)
        if run_id is not None:
            csv_kept = _save_job_report(run_id, "agent", job.result["agent"], csv_file, csv_name)
            if job.result.get("safety") is not None:
                _save_job_report(run_id, "safety", job.result["safety"])
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error, not an unhandled task exception
        job.error = str(exc)
        job.status = "error"
    finally:
        # Also reached on cancellation (CancelledError isn't an Exception).
        if csv_file is not None and not csv_kept:
            database.delete_stored_file(csv_file)


@app.post("/pipelines/{pipeline_id}/evaluate/jobs", response_model=EvaluationJobHandle, status_code=202)
async def start_evaluate_job(
    pipeline_id: str,
    file: UploadFile = File(...),
    run_id: str | None = Form(default=None),
) -> EvaluationJobHandle:
    """Start the full evaluation (retrieval/answer scoring against the uploaded
    CSV, plus an automatic safety-track report when the pipeline has
    barrier-agent nodes) as a background job and return immediately. Poll
    GET .../evaluate/jobs/{job_id} for progress and the final report.

    With a run_id form field, the uploaded CSV is kept under files/ and the
    reports are saved to that run when the job finishes, pointing at that CSV
    (see GET /projects/{project_id}/runs/{run_id}/reports/agent/csv).
    """
    stored = _get_stored(pipeline_id)
    _require_run_for_job(run_id)

    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"CSV file is not valid UTF-8 text: {exc}") from exc

    try:
        pipeline_evaluator = Evaluator(stored.pipeline, csv_text)
    except CsvValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        total = pipeline_evaluator.total_questions()
    except EvaluationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    csv_file = database.store_eval_csv(raw) if run_id is not None else None

    job = EvaluationJob(total=total)
    job_id = str(uuid.uuid4())
    _evaluation_jobs[job_id] = job
    job.task = asyncio.create_task(
        _run_evaluation_job(job, pipeline_evaluator, run_id, csv_file, file.filename)
    )
    return EvaluationJobHandle(job_id=job_id, total=total)


@app.get("/pipelines/{pipeline_id}/evaluate/jobs/{job_id}", response_model=EvaluationJobStatus)
async def get_evaluate_job(pipeline_id: str, job_id: str) -> EvaluationJobStatus:
    _get_stored(pipeline_id)
    job = _get_job(job_id)
    return EvaluationJobStatus(
        status=job.status,
        completed=job.completed,
        total=job.total,
        result=EvaluationResponse(**job.result) if job.result is not None else None,
        error=job.error,
    )


@app.post("/pipelines/{pipeline_id}/evaluate/jobs/{job_id}/cancel", status_code=204)
async def cancel_evaluate_job(pipeline_id: str, job_id: str) -> None:
    """Stops a running agent-evaluation job between rows -- already-in-flight
    LLM calls for the current row still finish, but no further rows start."""
    _get_stored(pipeline_id)
    _cancel_job(job_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
