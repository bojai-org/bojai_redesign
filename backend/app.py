"""
BojAI Build — HTTP API

Exposes compiler.py / pipeline.py over HTTP: a frontend compiles a pipeline
definition once, gets back an id, then runs that same compiled pipeline
against as many queries as it wants without recompiling each time.

Compiled pipelines live in an in-memory registry (module-level dict) and do
not survive a process restart -- there is no persistence layer here, by
design, until one is actually needed.

This module is frontend-agnostic: it exposes the generic contract described
in contract.md and does not assume any particular UI's data shapes.
"""

from __future__ import annotations

import asyncio
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

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agents
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


@dataclass
class EvaluationJob:
    """Mutable progress/result cell for one background evaluation run.

    Evaluating a CSV means one pipeline.run() (plus an LLM faithfulness judge
    and an embedding call) per question, which is too slow to hold an HTTP
    request open for -- POST .../evaluate/jobs starts one of these as an
    asyncio task and returns immediately; the frontend polls
    GET .../evaluate/jobs/{job_id} to drive a progress bar off `completed`.
    """

    status: Literal["running", "done", "error"] = "running"
    completed: int = 0
    total: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


_evaluation_jobs: dict[str, EvaluationJob] = {}


def _get_job(job_id: str) -> EvaluationJob:
    job = _evaluation_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No evaluation job with id {job_id!r}")
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


class CompileRequest(BaseModel):
    pipeline_id: str | None = Field(
        default=None,
        description="Reuse this id if provided; otherwise a new one is generated.",
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
    status: Literal["running", "done", "error"]
    completed: int
    total: int
    result: EvaluationResponse | None = None
    error: str | None = None


class SafetyEvaluationJobStatus(BaseModel):
    status: Literal["running", "done", "error"]
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


def _compile_and_store(pipeline_id: str, definition: dict[str, Any]) -> PipelineSummary:
    try:
        pipeline = compile_pipeline(definition, agent_registry=AGENT_REGISTRY)
        pipeline.flow()  # instantiate every node now so bad agent_args fail at compile time
    except PipelineContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Malformed pipeline definition: {exc}") from exc

    _pipelines[pipeline_id] = StoredPipeline(definition=definition, pipeline=pipeline)
    return _summarize(pipeline_id, pipeline)


def _get_stored(pipeline_id: str) -> StoredPipeline:
    stored = _pipelines.get(pipeline_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No pipeline with id {pipeline_id!r}")
    return stored


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/agents")
async def list_agents() -> dict[str, list[str]]:
    """The agent types a pipeline definition's nodes may use with this registry."""
    return {"agent_types": sorted(AGENT_REGISTRY)}


@app.get("/pipelines")
async def list_pipelines() -> dict[str, list[str]]:
    return {"pipeline_ids": sorted(_pipelines)}


@app.post("/pipelines/compile", response_model=PipelineSummary, status_code=201)
async def compile_endpoint(request: CompileRequest) -> PipelineSummary:
    pipeline_id = request.pipeline_id or str(uuid.uuid4())
    if pipeline_id in _pipelines:
        raise HTTPException(
            status_code=409,
            detail=f"pipeline_id {pipeline_id!r} already exists; "
            f"PUT /pipelines/{pipeline_id} to update it instead.",
        )
    return _compile_and_store(pipeline_id, request.definition)


@app.get("/pipelines/{pipeline_id}", response_model=PipelineSummary)
async def get_pipeline(pipeline_id: str) -> PipelineSummary:
    stored = _get_stored(pipeline_id)
    return _summarize(pipeline_id, stored.pipeline)


@app.put("/pipelines/{pipeline_id}", response_model=PipelineSummary)
async def update_pipeline(pipeline_id: str, request: CompileRequest) -> PipelineSummary:
    """Recompile an existing pipeline's definition in place, replacing it."""
    _get_stored(pipeline_id)
    return _compile_and_store(pipeline_id, request.definition)


@app.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: str) -> None:
    _get_stored(pipeline_id)
    del _pipelines[pipeline_id]


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
        ],
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


async def _run_safety_job(job: EvaluationJob, pipeline: Pipeline) -> None:
    def bump() -> None:
        job.completed += 1

    try:
        report = await evaluate_safety(pipeline, on_progress=bump)
        job.result = asdict(report)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error, not an unhandled task exception
        job.error = str(exc)
        job.status = "error"


@app.post("/pipelines/{pipeline_id}/evaluate/safety/jobs", response_model=EvaluationJobHandle, status_code=202)
async def start_safety_job(pipeline_id: str) -> EvaluationJobHandle:
    """Start a safety-track evaluation (the built-in 120-question harmful/unharmful
    set) as a background job and return immediately. Poll
    GET .../evaluate/safety/jobs/{job_id} for progress and the final report.
    """
    stored = _get_stored(pipeline_id)
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
    asyncio.create_task(_run_safety_job(job, stored.pipeline))
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


async def _run_evaluation_job(job: EvaluationJob, pipeline_evaluator: Evaluator) -> None:
    def bump() -> None:
        job.completed += 1

    try:
        report = await pipeline_evaluator.evaluate(on_progress=bump)
        job.result = asdict(report)
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error, not an unhandled task exception
        job.error = str(exc)
        job.status = "error"


@app.post("/pipelines/{pipeline_id}/evaluate/jobs", response_model=EvaluationJobHandle, status_code=202)
async def start_evaluate_job(pipeline_id: str, file: UploadFile = File(...)) -> EvaluationJobHandle:
    """Start the full evaluation (retrieval/answer scoring against the uploaded
    CSV, plus an automatic safety-track report when the pipeline has
    barrier-agent nodes) as a background job and return immediately. Poll
    GET .../evaluate/jobs/{job_id} for progress and the final report.
    """
    stored = _get_stored(pipeline_id)

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

    job = EvaluationJob(total=total)
    job_id = str(uuid.uuid4())
    _evaluation_jobs[job_id] = job
    asyncio.create_task(_run_evaluation_job(job, pipeline_evaluator))
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
