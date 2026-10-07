"""
BojAI Build — Pipeline Evaluator

Evaluates a compiled Pipeline (see pipeline.py / compiler.py) against a
user-supplied CSV of evaluation questions, per two independent tracks:

1. Safety track (safety_agents.py barrier nodes). If the pipeline contains
   any Static_Barrier_Agent / Neural_Network_Barrier_Agent / Judge_Barrier_Agent
   node, that node is exercised in isolation against a fixed, built-in 120
   question harmful/unharmful set (BUILTIN_SAFETY_CSV) -- not the user's CSV --
   because safety behavior is a property of the pipeline itself, not of any
   one dataset. Reports, per gate, how many questions produced each action
   (accept/escalate/reject/...), and precision/recall/F1 for the full barrier
   chain's final safe-vs-blocked verdict against the built-in ground truth.

2. Agent track: runs the pipeline end-to-end for every row of the user's CSV,
   and scores each answer for retrieval accuracy (did the expected resource(s)
   show up, and at what rank), faithfulness (is the answer grounded in what
   was retrieved), and answer similarity (cosine similarity against the
   expected answer's embedding).

Both tracks reuse the exact node graph the pipeline was compiled with --
nothing here re-implements routing or retrieval; it only walks the same
CompiledNode graph pipeline.py already built.
"""

from __future__ import annotations

import csv
import inspect
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import embeddings
from agents import _format_resources, _parse_resources
from base_classes import Agent
from pipeline import Pipeline
from safety_agents import cosine_similarity

EmbedFunction = Callable[[list[str], dict], Awaitable[list[list[float]]]]

SAFETY_AGENT_TYPES = {
    "Static_Barrier_Agent",
    "Neural_Network_Barrier_Agent",
    "Judge_Barrier_Agent",
}
RESOURCE_AGENT_TYPES = {
    "RAG_Agent",
    "Keyword_Search_Agent",
    "Hybrid_Agent",
    "Reranker_Agent",
}
BLOCKED_ACTIONS = {"reject", "harmful"}
PASSED_ACTIONS = {"safe", "accept"}

# The 120-question harmful/unharmful set the safety track always evaluates
# against, regardless of what CSV the caller supplied for the agent track.
# Tried in order; the first path that exists on disk wins, so this works the
# same whether the process runs under WSL or native Windows.
_BUILTIN_SAFETY_CSV_CANDIDATES = [
    Path(r"C:\Users\soghm\OneDrive\Desktop\wliura\crestbd-polarus-chatbot\research\nn_experimentation\mixed.csv"),
    Path("/mnt/c/Users/soghm/OneDrive/Desktop/wliura/crestbd-polarus-chatbot/research/nn_experimentation/mixed.csv"),
]


class EvaluationError(ValueError):
    """Raised for problems with evaluator inputs (CSV shape, missing files, ...)."""


class CsvValidationError(EvaluationError):
    """Raised when a supplied CSV does not satisfy the evaluation contract."""


def resolve_builtin_safety_csv() -> Path:
    for candidate in _BUILTIN_SAFETY_CSV_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Built-in safety evaluation CSV not found. Looked in: "
        + ", ".join(str(c) for c in _BUILTIN_SAFETY_CSV_CANDIDATES)
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSV loading
# ─────────────────────────────────────────────────────────────────────────────


_RESOURCE_SPLIT_RE = re.compile(r"[;|,]")


@dataclass(slots=True)
class QAExample:
    question: str
    expected_answer: str
    expected_resources: list[str] = field(default_factory=list)


def _read_text(source: str | Path) -> str:
    """Accept a path to a CSV file or raw CSV text, mirroring compiler._load_source."""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    candidate = Path(source)
    if candidate.exists() and candidate.is_file():
        return candidate.read_text(encoding="utf-8-sig")
    return source


def parse_qa_csv(text: str) -> list[QAExample]:
    """Validate and parse an evaluation CSV's text.

    Required columns (case-insensitive): question, expected_answer.
    Optional column: expected_resource or expected_resources -- a single value,
    or several separated by ';', '|', or ','.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvValidationError("CSV file is empty or has no header row.")

    normalized = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = {"question", "expected_answer"} - normalized.keys()
    if missing:
        raise CsvValidationError(
            "CSV is missing required column(s): "
            f"{sorted(missing)}. Required columns: question, expected_answer."
        )

    resource_column = next(
        (normalized[key] for key in ("expected_resource", "expected_resources") if key in normalized),
        None,
    )

    examples: list[QAExample] = []
    for line_number, row in enumerate(reader, start=2):
        question = (row.get(normalized["question"]) or "").strip()
        expected_answer = (row.get(normalized["expected_answer"]) or "").strip()
        if not question:
            raise CsvValidationError(f"Row {line_number}: 'question' is empty.")
        if not expected_answer:
            raise CsvValidationError(f"Row {line_number}: 'expected_answer' is empty.")

        expected_resources: list[str] = []
        if resource_column:
            raw = row.get(resource_column) or ""
            expected_resources = [part.strip() for part in _RESOURCE_SPLIT_RE.split(raw) if part.strip()]

        examples.append(
            QAExample(question=question, expected_answer=expected_answer, expected_resources=expected_resources)
        )

    if not examples:
        raise CsvValidationError("CSV contains no data rows.")

    return examples


def load_qa_csv(source: str | Path) -> list[QAExample]:
    return parse_qa_csv(_read_text(source))


def parse_safety_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvValidationError("Safety CSV is empty or has no header row.")
    normalized = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = {"question", "label"} - normalized.keys()
    if missing:
        raise CsvValidationError(f"Safety CSV is missing required column(s): {sorted(missing)}.")

    rows: list[dict[str, str]] = []
    for row in reader:
        question = (row.get(normalized["question"]) or "").strip()
        label = (row.get(normalized["label"]) or "").strip().lower()
        if question and label:
            rows.append({"question": question, "label": label})
    if not rows:
        raise CsvValidationError("Safety CSV contains no data rows.")
    return rows


def load_safety_csv(source: str | Path) -> list[dict[str, str]]:
    return parse_safety_csv(_read_text(source))


# ─────────────────────────────────────────────────────────────────────────────
# Shared agent-invocation helper (mirrors Pipeline._run_agent's calling
# convention -- contract.md section 7 -- without depending on Pipeline
# internals staying private)
# ─────────────────────────────────────────────────────────────────────────────


async def _invoke_agent(agent: Any, config: dict) -> Any:
    run_method = agent.run
    try:
        accepts_config = len(inspect.signature(run_method).parameters) >= 1
    except (TypeError, ValueError):
        accepts_config = True
    result = run_method(config) if accepts_config else run_method()
    if inspect.isawaitable(result):
        return await result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Safety track
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SafetyGateStep:
    node_id: str
    agent_type: str
    action: str | None


@dataclass(slots=True)
class SafetyQuestionResult:
    question: str
    label: str
    predicted: str
    path: list[SafetyGateStep]
    error: str | None = None


@dataclass(slots=True)
class SafetyGateCounts:
    node_id: str
    agent_type: str
    total: int
    action_counts: dict[str, int]


@dataclass(slots=True)
class SafetyEvalReport:
    total_questions: int
    gate_counts: list[SafetyGateCounts]
    confusion: dict[str, int]
    precision: float
    recall: float
    f1: float
    results: list[SafetyQuestionResult]
    errors: int


def find_safety_node_ids(pipeline: Pipeline) -> list[str]:
    """Every node whose declared type is a barrier agent, in declaration order."""
    return [
        node_id
        for node_id, node in pipeline.flow().items()
        if node.spec.get("type") in SAFETY_AGENT_TYPES
    ]


async def _walk_safety_chain(pipeline: Pipeline, question: str) -> list[SafetyGateStep]:
    """Run *question* through consecutive safety-agent nodes starting at the entrypoint.

    Stops at the first node that is not a barrier-agent type (the pipeline has
    passed all its gates and would proceed to normal handling) or when a node
    has no outgoing route for the result it produced.
    """
    nodes = pipeline.flow()
    config = pipeline.config
    node_id = pipeline.definition["entrypoint"]
    path: list[SafetyGateStep] = []

    for _ in range(pipeline.max_steps):
        node = nodes.get(node_id)
        if node is None:
            break
        agent_type = node.spec.get("type")
        if agent_type not in SAFETY_AGENT_TYPES:
            break

        agent = node.agent
        if hasattr(agent, "query"):
            agent.query = question
        result = await _invoke_agent(agent, dict(config))
        action = result.get("action") if isinstance(result, dict) else None
        path.append(SafetyGateStep(node_id=node_id, agent_type=agent_type, action=action))

        route = Pipeline._select_route(node, result)
        target = node.routes.get(route) if route is not None else None
        if target is None:
            break
        node_id = target.node_id

    return path


def _classify_safety_path(path: list[SafetyGateStep]) -> str:
    """'harmful' if the chain terminated on a blocking action, else 'unharmful'."""
    if not path:
        return "unharmful"
    return "harmful" if path[-1].action in BLOCKED_ACTIONS else "unharmful"


async def evaluate_safety(
    pipeline: Pipeline,
    safety_csv: str | Path | None = None,
    *,
    on_progress: Callable[[], None] | None = None,
) -> SafetyEvalReport:
    """Run every row of the safety CSV (built-in unless overridden) through the
    pipeline's barrier-agent chain and score the full chain's blocked-vs-passed
    verdict against each row's harmful/unharmful ground truth label.

    ``on_progress``, when given, is called once after each row finishes
    (success or error) -- callers that expose progress to a client (see
    app.py's job runner) use it to track completed/total without this module
    knowing anything about jobs or HTTP.
    """
    rows = load_safety_csv(safety_csv or resolve_builtin_safety_csv())

    gate_ids = find_safety_node_ids(pipeline)
    nodes = pipeline.flow()
    gate_counters: dict[str, Counter] = {node_id: Counter() for node_id in gate_ids}

    tp = fp = fn = tn = 0
    errors = 0
    results: list[SafetyQuestionResult] = []

    for row in rows:
        question, label = row["question"], row["label"]
        actual = "harmful" if label == "harmful" else "unharmful"
        try:
            path = await _walk_safety_chain(pipeline, question)
        except Exception as exc:  # noqa: BLE001 -- one bad row must not abort the batch
            errors += 1
            results.append(
                SafetyQuestionResult(question=question, label=actual, predicted="error", path=[], error=str(exc))
            )
            if on_progress is not None:
                on_progress()
            continue

        for step in path:
            gate_counters[step.node_id][step.action or "unknown"] += 1

        predicted = _classify_safety_path(path)
        if predicted == "harmful" and actual == "harmful":
            tp += 1
        elif predicted == "harmful" and actual == "unharmful":
            fp += 1
        elif predicted == "unharmful" and actual == "harmful":
            fn += 1
        else:
            tn += 1

        results.append(SafetyQuestionResult(question=question, label=actual, predicted=predicted, path=path))
        if on_progress is not None:
            on_progress()

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    gate_counts = [
        SafetyGateCounts(
            node_id=node_id,
            agent_type=nodes[node_id].spec.get("type", ""),
            total=sum(counter.values()),
            action_counts=dict(counter),
        )
        for node_id, counter in gate_counters.items()
    ]

    return SafetyEvalReport(
        total_questions=len(rows),
        gate_counts=gate_counts,
        confusion={"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
        precision=precision,
        recall=recall,
        f1=f1,
        results=results,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agent (retrieval + answer) track
# ─────────────────────────────────────────────────────────────────────────────


class Faithfulness_Judge_Agent(Agent):
    """Judges whether a generated answer's claims are grounded in retrieved context.

    Not a pipeline node type (unregistered in AGENT_REGISTRY) -- this is an
    evaluation-only tool that reuses Agent.run()'s prompt/retry machinery the
    same way Judge_Barrier_Agent does.
    """

    def __init__(self, query: str, context: str, answer: str):
        role = (
            "You are a faithfulness evaluator for a retrieval-augmented question "
            "answering system. You will be given a request, the retrieved context, "
            "and a generated answer. Your task is to judge whether the answer's "
            "claims are supported by the context."
        )
        # Not a pipeline node (never goes through Pipeline.run()'s shared-state
        # patching), so `context` here is just a one-shot constructor value,
        # not the base class's shared `state` dict -- stored separately.
        super().__init__(query, None, role)
        self.context = context
        self.answer = answer

    def pre(self) -> dict:
        return {"request": self.query, "context": self.context or "(no context was retrieved)", "answer": self.answer}

    def specify_output(self) -> str:
        return (
            "The output must be a json object inside a ```json block, with three keys: "
            "'faithful' (a boolean, true only if every factual claim in the answer is "
            "supported by the context), 'score' (a float between 0 and 1, the fraction "
            "of the answer's claims that are supported by the context), and 'reason' "
            "(a short string explaining the decision). The output must be a single JSON "
            "object, not a list or any other structure, and must be parsable by a JSON parser."
        )

    def post(self, response: str) -> dict:
        parsed = self._find_json(response)
        if not isinstance(parsed, dict):
            raise TypeError(f"Expected JSON object, got {type(parsed)}")

        faithful = parsed.get("faithful")
        score = parsed.get("score")
        reason = parsed.get("reason")

        if not isinstance(faithful, bool):
            raise ValueError(f"'faithful' must be a boolean, got {type(faithful)}")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"'score' must be a number, got {type(score)}")
        if not 0 <= float(score) <= 1:
            raise ValueError(f"'score' must be between 0 and 1, got {score}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("'reason' must be a non-empty string")

        return {"faithful": faithful, "score": float(score), "reason": reason.strip()}

    def post_fallback(self, response: str) -> dict:
        return {"faithful": False, "score": 0.0, "reason": "unparsable faithfulness judge response"}


@dataclass(slots=True)
class RetrievedChunk:
    rank: int
    chunk_id: str | None
    section: str | None
    url: str | None
    text: str


@dataclass(slots=True)
class ResourceMatch:
    expected: str
    found: bool
    rank: int | None
    chunk_id: str | None


@dataclass(slots=True)
class QuestionEvalResult:
    question: str
    expected_answer: str
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    resource_matches: list[ResourceMatch]
    faithfulness: dict[str, Any]
    answer_similarity: float
    error: str | None = None


@dataclass(slots=True)
class AgentEvalReport:
    results: list[QuestionEvalResult]
    resource_recall: float | None
    mean_answer_similarity: float
    mean_faithfulness: float
    errors: int


def _extract_final_resources(pipeline: Pipeline, trace: list) -> list[dict]:
    """The resource set the last retrieval/rerank node in the run produced.

    Every retrieval agent accumulates onto shared state's "context" key
    (contract.md section 4a/8), and a Reranker_Agent's output is that same
    accumulated set filtered/reordered -- so whichever such node ran last in
    the trace holds the complete resource set any downstream generation node
    actually saw.
    """
    nodes = pipeline.flow()
    last_text: str | None = None
    for step in trace:
        node = nodes.get(step.node_id)
        if node is not None and node.spec.get("type") in RESOURCE_AGENT_TYPES and isinstance(step.result, str):
            last_text = step.result
    return _parse_resources(last_text) if last_text else []


def _match_resource(expected: str, chunks: list[dict]) -> ResourceMatch:
    expected_norm = expected.strip().lower()
    for rank, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {})
        chunk_id = str(metadata.get("chunk_id") or "").lower()
        url = str(metadata.get("url") or "").lower()
        text = (chunk.get("text") or "").lower()
        if expected_norm and (expected_norm == chunk_id or expected_norm in url or expected_norm in text):
            return ResourceMatch(expected=expected, found=True, rank=rank, chunk_id=metadata.get("chunk_id"))
    return ResourceMatch(expected=expected, found=False, rank=None, chunk_id=None)


async def evaluate_agent(
    pipeline: Pipeline,
    examples: list[QAExample],
    *,
    embed_texts: EmbedFunction | None = None,
    embedding_config: dict | None = None,
    on_progress: Callable[[], None] | None = None,
) -> AgentEvalReport:
    """See evaluate_safety's docstring for the ``on_progress`` contract -- called
    once after each question finishes, success or error."""
    # Resolved from the embeddings module at call time (rather than bound as a
    # default argument) so tests/callers can monkeypatch embeddings.embed_texts
    # without needing every caller to thread a replacement through explicitly.
    embed_texts = embed_texts or embeddings.embed_texts
    embedding_config = embedding_config or {}
    results: list[QuestionEvalResult] = []
    expected_total = 0
    expected_found = 0
    similarities: list[float] = []
    faithfulness_scores: list[float] = []
    errors = 0

    for example in examples:
        try:
            run_result = await pipeline.run(initial_query=example.question)
            answer = run_result.output if isinstance(run_result.output, str) else str(run_result.output)

            chunks = _extract_final_resources(pipeline, run_result.trace)
            retrieved_chunks = [
                RetrievedChunk(
                    rank=rank,
                    chunk_id=chunk.get("metadata", {}).get("chunk_id"),
                    section=chunk.get("metadata", {}).get("section"),
                    url=chunk.get("metadata", {}).get("url"),
                    text=chunk.get("text", ""),
                )
                for rank, chunk in enumerate(chunks, start=1)
            ]
            resource_matches = [_match_resource(resource, chunks) for resource in example.expected_resources]
            expected_total += len(resource_matches)
            expected_found += sum(1 for match in resource_matches if match.found)

            context_text = _format_resources(chunks) if chunks else ""
            faithfulness_agent = Faithfulness_Judge_Agent(query=example.question, context=context_text, answer=answer)
            try:
                faithfulness = await faithfulness_agent.run(dict(pipeline.config))
            except ValueError as exc:
                faithfulness = {"faithful": False, "score": 0.0, "reason": f"faithfulness judge failed: {exc}"}
            faithfulness_scores.append(faithfulness["score"])

            answer_embedding, expected_embedding = await embed_texts(
                [answer, example.expected_answer], embedding_config
            )
            similarity = cosine_similarity(answer_embedding, expected_embedding)
            similarities.append(similarity)

            results.append(
                QuestionEvalResult(
                    question=example.question,
                    expected_answer=example.expected_answer,
                    answer=answer,
                    retrieved_chunks=retrieved_chunks,
                    resource_matches=resource_matches,
                    faithfulness=faithfulness,
                    answer_similarity=similarity,
                )
            )
        except Exception as exc:  # noqa: BLE001 -- one bad row must not abort the batch
            errors += 1
            results.append(
                QuestionEvalResult(
                    question=example.question,
                    expected_answer=example.expected_answer,
                    answer="",
                    retrieved_chunks=[],
                    resource_matches=[],
                    faithfulness={"faithful": False, "score": 0.0, "reason": "not evaluated"},
                    answer_similarity=0.0,
                    error=str(exc),
                )
            )
        finally:
            if on_progress is not None:
                on_progress()

    resource_recall = (expected_found / expected_total) if expected_total else None
    mean_similarity = sum(similarities) / len(similarities) if similarities else 0.0
    mean_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0

    return AgentEvalReport(
        results=results,
        resource_recall=resource_recall,
        mean_answer_similarity=mean_similarity,
        mean_faithfulness=mean_faithfulness,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class EvaluationReport:
    agent: AgentEvalReport
    safety: SafetyEvalReport | None


class Evaluator:
    """Evaluates one compiled Pipeline against a CSV of evaluation questions.

    The CSV is validated at construction time (question, expected_answer
    required; expected_resource(s) optional) so a malformed file fails fast,
    before any pipeline run or LLM call.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        qa_csv: str | Path,
        *,
        embed_texts: EmbedFunction | None = None,
        embedding_config: dict | None = None,
        safety_csv: str | Path | None = None,
    ):
        self.pipeline = pipeline
        self.examples = load_qa_csv(qa_csv)
        self.embed_texts = embed_texts
        self.embedding_config = embedding_config or {}
        self.safety_csv = safety_csv

    def safety_node_ids(self) -> list[str]:
        return find_safety_node_ids(self.pipeline)

    def total_questions(self) -> int:
        """Question count across both tracks -- the agent CSV plus the built-in
        (or overridden) safety CSV when this pipeline has safety-agent nodes.
        Callers that expose progress (app.py's job runner) use this to size a
        progress bar before evaluate() has processed anything."""
        total = len(self.examples)
        if self.safety_node_ids():
            total += len(load_safety_csv(self.safety_csv or resolve_builtin_safety_csv()))
        return total

    async def evaluate(self, *, on_progress: Callable[[], None] | None = None) -> EvaluationReport:
        agent_report = await evaluate_agent(
            self.pipeline,
            self.examples,
            embed_texts=self.embed_texts,
            embedding_config=self.embedding_config,
            on_progress=on_progress,
        )
        safety_report = None
        if self.safety_node_ids():
            safety_report = await evaluate_safety(self.pipeline, self.safety_csv, on_progress=on_progress)
        return EvaluationReport(agent=agent_report, safety=safety_report)
