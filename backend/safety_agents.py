"""
BojAI Build — Three-Layer Safety Agents

The embedding layer is provider-independent.

The caller supplies an embedding function with this contract:

    async def embed_texts(
        texts: list[str],
        embedding_config: dict,
    ) -> list[list[float]]:
        ...

The barrier therefore does not know or care whether embeddings come from
Bedrock, SageMaker, OpenAI, SentenceTransformers, a local model, or another
backend.
"""

import re
from typing import Any, Awaitable, Callable, Literal, TypedDict

import numpy as np

from base_classes import Agent


EmbedFunction = Callable[
    [list[str], dict],
    Awaitable[list[list[float]]],
]


BarrierAction = Literal[
    "safe",
    "accept",
    "escalate",
    "escalate_judge",
    "reject",
    "harmful",
]


class BarrierResult(TypedDict):
    action: BarrierAction
    reason: str
    layer: int
    score: float | None
    answer: str | None
    # The barrier's own incoming context, carried through unchanged. Pipeline
    # routing reads "action" for its route decision (see base_classes' Agent
    # runtime contract); without this key, Pipeline._resolve_context would
    # forward str(this_dict) as the next node's context instead of the actual
    # text a barrier mid-chain was screening.
    context: str


INPUT_DECLINE_MESSAGE = (
    "I'm here to support you, but I'm not able to respond to that request. "
    "If you're in crisis or need immediate support, please reach out to a "
    "mental health professional or a crisis line. In Canada: Crisis Services "
    "Canada — 1-833-456-4566 (24/7). You can also text HOME to 686868."
)


DEFAULT_BARRIER_CONTEXT = (
    "A user query submitted to a patient-facing bipolar disorder support chatbot."
)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 patterns
# ─────────────────────────────────────────────────────────────────────────────

STATIC_REJECT_PATTERNS = [
    r"\b(suicid(al|e)|kill\s+(my)?self|end\s+(my\s+)?life|end\s+it\s+all)\b",
    r"\b(want|wanna|going)\s+to\s+die\b",
    r"\bself[- ]?harm\b",
    r"\b(cut|cutting|hurt)\s+(my)?self\b",
    r"\bhang\s+(my)?self\b",
    r"\bslit\s+my\s+wrists?\b",
    r"\boverdos(e|ing)\s+(on|my)\b",
    (
        r"\b(want|going)\s+to\s+(kill|hurt)\s+"
        r"(someone|others?|them|you|people|him|her)\b"
    ),
]


STATIC_ESCALATE_TO_JUDGE_PATTERNS = [
    # Mania / psychosis signals
    r"\bi\s+(don'?t|do\s+not)\s+need\s+(to\s+)?sleep\b",
    r"\b(feel|feeling|i'?m)\s+invincible\b",
    r"\bpeople\s+are\s+(watching|following|after)\s+me\b",
    r"\bbeing\s+watched\b",
    r"\bracing\s+thoughts?\b",

    # Grandiosity / grandiose delusions
    r"\bi\s+am\s+god\b",
    r"\bi'?m\s+god\b",
    r"\bi\s+am\s+(the\s+)?(messiah|prophet|chosen\s+one)\b",
    r"\bi\s+have\s+special\s+powers\b",
    r"\bi\s+have\s+a\s+special\s+mission\b",
    r"\bi\s+can'?t\s+be\s+(hurt|killed|stopped)\b",
]


STATIC_ESCALATE_PATTERNS = [
    # Medical advice requests
    (
        r"\bshould\s+i\s+"
        r"(stop|start|change|increase|decrease|adjust)\s+"
        r"(taking|my)?\b"
    ),
    (
        r"\b(stop|change|increase|decrease|adjust)\s+"
        r"(taking\s+|my\s+)?"
        r"(medication|meds?|dose|dosage|lithium|quetiapine|"
        r"valproate|lamotrigine|olanzapine)\b"
    ),
    (
        r"\b(mix|combine|take)\s+\w+\s+with\s+"
        r"(lithium|valproate|quetiapine|my\s+meds?|medication)\b"
    ),

    # Substance-use questions
    (
        r"\b(alcohol|drink|weed|cannabis|marijuana)\s+"
        r"(and|with)\s+"
        r"(bipolar|meds?|medication|lithium)\b"
    ),
    (
        r"\bcan\s+i\s+(drink|use|take|mix)\s+"
        r"(alcohol|weed|cannabis|recreational\s+drugs?)\b"
    ),
    r"\b(cocaine|heroin|ecstasy|mdma|methamphetamine|crystal\s+meth)\b",
]


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 references
# ─────────────────────────────────────────────────────────────────────────────

NN_HARMFUL_REFERENCES = [
    "I want to kill myself right now",
    "How do I overdose on my medication",
    "I am thinking about ending my life tonight",
    "I have a plan to commit suicide",
    "I feel like hurting myself",
    "I want to hurt someone else",
    "Give me a method to self harm",
    "I am God",
    "I have special powers that no one else has",
    "I have a special mission that only I can fulfill",
    "I am invincible and nothing can hurt me",
    "Everyone says I'm chosen for something great",
]


NN_REJECT_THRESHOLD = 0.85
NN_ESCALATE_THRESHOLD = 0.72


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""

    vector_a = np.asarray(a, dtype=np.float32).reshape(-1)
    vector_b = np.asarray(b, dtype=np.float32).reshape(-1)

    if vector_a.shape != vector_b.shape:
        raise ValueError(
            "Embedding dimensions do not match: "
            f"{vector_a.shape} != {vector_b.shape}"
        )

    denominator = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)

    if denominator == 0:
        return 0.0

    return float(np.dot(vector_a, vector_b) / denominator)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1
# ─────────────────────────────────────────────────────────────────────────────

class Static_Barrier_Agent(Agent):
    """Layer 1: deterministic regex safety screening.

    Does not call the LLM, so run() is overridden. run() still accepts
    agent_config (unused) so callers can treat every barrier layer uniformly.
    pre()/post()/post_fallback() are implemented so the agent behaves
    correctly if invoked directly instead of through run().
    """

    def __init__(self, query: str, context: str = DEFAULT_BARRIER_CONTEXT):
        role = (
            "You are a deterministic pattern-matching safety screener for a "
            "patient-facing mental health chatbot."
        )
        super().__init__(query, context, role)

    async def run(self, agent_config: dict) -> BarrierResult:
        return self._screen(self.query)

    def _screen(self, text: str) -> BarrierResult:
        text = text.lower().strip()

        for pattern in STATIC_REJECT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "action": "reject",
                    "reason": f"Matched reject pattern: {pattern}",
                    "layer": 1,
                    "score": None,
                    "answer": INPUT_DECLINE_MESSAGE,
                    "context": self.context,
                }

        for pattern in STATIC_ESCALATE_TO_JUDGE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "action": "escalate_judge",
                    "reason": (
                        "Matched psychiatric-crisis pattern: "
                        f"{pattern}"
                    ),
                    "layer": 1,
                    "score": None,
                    "answer": None,
                    "context": self.context,
                }

        for pattern in STATIC_ESCALATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "action": "escalate",
                    "reason": f"Matched escalation pattern: {pattern}",
                    "layer": 1,
                    "score": None,
                    "answer": None,
                    "context": self.context,
                }

        return {
            "action": "safe",
            "reason": "No harmful patterns detected.",
            "layer": 1,
            "score": None,
            "answer": None,
            "context": self.context,
        }

    def pre(self) -> dict:
        return {"request": self.query}

    def specify_output(self) -> str:
        return "N/A — this agent does not call the LLM."

    def post(self, response: str) -> BarrierResult:
        return self._screen(self.query)

    def post_fallback(self, response: str) -> BarrierResult:
        return self._screen(self.query)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2
# ─────────────────────────────────────────────────────────────────────────────

class Neural_Network_Barrier_Agent(Agent):
    """Layer 2: provider-independent embedding classifier.

    No embedding provider is imported here. The embedding function is supplied
    by the caller, so run() is overridden to call it directly instead of going
    through the standard ask_llm() path. run() still accepts agent_config
    (unused) so callers can treat every barrier layer uniformly.

    Required embedder contract:

        async def embed_texts(
            texts: list[str],
            embedding_config: dict,
        ) -> list[list[float]]:
            ...
    """

    def __init__(
        self,
        query: str,
        embedding_config: dict,
        embed_texts: EmbedFunction,
        context: str = DEFAULT_BARRIER_CONTEXT,
        harmful_references: list[str] | None = None,
        reject_threshold: float = NN_REJECT_THRESHOLD,
        escalate_threshold: float = NN_ESCALATE_THRESHOLD,
    ):
        role = (
            "You are an embedding-similarity safety classifier for a "
            "patient-facing mental health chatbot."
        )
        super().__init__(query, context, role)

        if not callable(embed_texts):
            raise TypeError("embed_texts must be callable")

        if not 0 <= escalate_threshold <= reject_threshold <= 1:
            raise ValueError(
                "Thresholds must satisfy "
                "0 <= escalate_threshold <= reject_threshold <= 1."
            )

        self.embedding_config = embedding_config
        self.embed_texts = embed_texts
        self.harmful_references = (
            harmful_references or NN_HARMFUL_REFERENCES
        )
        self.reject_threshold = reject_threshold
        self.escalate_threshold = escalate_threshold

    async def run(self, agent_config: dict) -> BarrierResult:
        try:
            texts = [self.query, *self.harmful_references]

            embeddings = await self.embed_texts(
                texts,
                self.embedding_config,
            )

            self._validate_embeddings(
                embeddings=embeddings,
                expected_count=len(texts),
            )

            query_embedding = embeddings[0]
            reference_embeddings = embeddings[1:]

            similarities = [
                cosine_similarity(
                    query_embedding,
                    reference_embedding,
                )
                for reference_embedding in reference_embeddings
            ]

            max_similarity = max(similarities, default=0.0)

            return self.post(str(max_similarity))

        except Exception as exc:
            # Conservative failure mode: send uncertain cases to Layer 3.
            return {
                "action": "escalate",
                "reason": (
                    "Embedding classifier failed and requires Layer 3 review: "
                    f"{exc}"
                ),
                "layer": 2,
                "score": None,
                "answer": None,
                "context": self.context,
            }

    def _validate_embeddings(
        self,
        embeddings: Any,
        expected_count: int,
    ) -> None:
        if not isinstance(embeddings, list):
            raise TypeError(
                "Embedding function must return a list of embeddings."
            )

        if len(embeddings) != expected_count:
            raise ValueError(
                "Embedding function returned the wrong number of embeddings: "
                f"expected {expected_count}, received {len(embeddings)}."
            )

        if not embeddings:
            raise ValueError("Embedding function returned no embeddings.")

        expected_dimension: int | None = None

        for index, embedding in enumerate(embeddings):
            vector = np.asarray(embedding)

            if vector.ndim not in {1, 2}:
                raise ValueError(
                    f"Embedding {index} has invalid shape {vector.shape}."
                )

            vector = vector.reshape(-1)

            if vector.size == 0:
                raise ValueError(
                    f"Embedding {index} is empty."
                )

            if not np.issubdtype(vector.dtype, np.number):
                raise TypeError(
                    f"Embedding {index} must contain numeric values."
                )

            if not np.all(np.isfinite(vector)):
                raise ValueError(
                    f"Embedding {index} contains NaN or infinite values."
                )

            if expected_dimension is None:
                expected_dimension = vector.size
            elif vector.size != expected_dimension:
                raise ValueError(
                    "All embeddings must have the same dimension. "
                    f"Expected {expected_dimension}, received {vector.size} "
                    f"at index {index}."
                )

    def pre(self) -> dict:
        return {"request": self.query}

    def specify_output(self) -> str:
        return "N/A — this agent does not call the LLM; run() calls embed_texts directly."

    def post(self, response: str) -> BarrierResult:
        try:
            max_similarity = float(response)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Expected numeric similarity score, got {response!r}"
            ) from exc

        if not -1.0 <= max_similarity <= 1.0:
            raise ValueError(
                "Cosine similarity must be between -1 and 1, "
                f"got {max_similarity}."
            )

        if max_similarity >= self.reject_threshold:
            return {
                "action": "reject",
                "reason": (
                    "Query exceeded the embedding rejection threshold."
                ),
                "layer": 2,
                "score": max_similarity,
                "answer": INPUT_DECLINE_MESSAGE,
                "context": self.context,
            }

        if max_similarity >= self.escalate_threshold:
            return {
                "action": "escalate",
                "reason": (
                    "Query exceeded the embedding escalation threshold."
                ),
                "layer": 2,
                "score": max_similarity,
                "answer": None,
                "context": self.context,
            }

        return {
            "action": "accept",
            "reason": (
                "Query remained below the embedding escalation threshold."
            ),
            "layer": 2,
            "score": max_similarity,
            "answer": None,
            "context": self.context,
        }

    def post_fallback(self, response: str) -> BarrierResult:
        """Fail closed: treat an unparsable similarity score as requiring Layer 3 review."""
        return {
            "action": "escalate",
            "reason": f"Could not parse similarity score: {response!r}",
            "layer": 2,
            "score": None,
            "answer": None,
            "context": self.context,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3
# ─────────────────────────────────────────────────────────────────────────────

class Judge_Barrier_Agent(Agent):
    """Layer 3: LLM-backed safety judge.

    The standard Agent.run() method handles prompt construction, LLM calls,
    validation retries, and error injection. run() is overridden only to fail
    closed if all retries are exhausted — there is no Layer 4 to escalate to.
    """

    def __init__(self, query: str, context: str = DEFAULT_BARRIER_CONTEXT):
        role = (
            "You are the final safety judge for a patient-facing bipolar "
            "disorder support chatbot. Decide whether the user's message is "
            "harmful and must be blocked."
        )
        super().__init__(query, context, role)

    async def run(self, agent_config: dict) -> BarrierResult:
        try:
            return await super().run(agent_config)
        except (ValueError, TypeError) as exc:
            return {
                "action": "harmful",
                "reason": (
                    "Judge failed to produce a valid decision and failed closed: "
                    f"{exc}"
                ),
                "layer": 3,
                "score": None,
                "answer": INPUT_DECLINE_MESSAGE,
                "context": self.context,
            }

    def pre(self) -> dict:
        return {"request": self.query, "context": self.context}

    def specify_output(self) -> str:
        return (
            "The output must be a json object inside a ```json block, with two keys: "
            "'harmful' (a boolean) and 'reason' (a short string explaining the decision). "
            "The output must be a single JSON object, not a list or any other structure. "
            "The output must be a valid JSON object, and must be parsable by a JSON parser."
        )

    def post(self, response: str) -> BarrierResult:
        answer = self._find_json(response)

        if not isinstance(answer, dict):
            raise TypeError(
                f"Expected JSON object, got {type(answer)}"
            )

        harmful = answer.get("harmful")
        reason = answer.get("reason")

        if not isinstance(harmful, bool):
            raise TypeError(
                f"'harmful' must be a boolean, got {type(harmful)}"
            )

        if not isinstance(reason, str):
            raise TypeError(
                f"'reason' must be a string, got {type(reason)}"
            )

        reason = reason.strip()

        if not reason:
            raise ValueError("'reason' cannot be empty")

        if harmful:
            return {
                "action": "harmful",
                "reason": reason,
                "layer": 3,
                "score": None,
                "answer": INPUT_DECLINE_MESSAGE,
                "context": self.context,
            }

        return {
            "action": "safe",
            "reason": reason,
            "layer": 3,
            "score": None,
            "answer": None,
            "context": self.context,
        }

    def post_fallback(self, response: str) -> BarrierResult:
        """Fail closed: treat an unparsable response as harmful."""
        return {
            "action": "harmful",
            "reason": response.strip(),
            "layer": 3,
            "score": None,
            "answer": INPUT_DECLINE_MESSAGE,
            "context": self.context,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class Input_Barrier_Pipeline:
    """Runs the three safety layers in sequence.

    Not an Agent itself — it orchestrates Static_Barrier_Agent,
    Neural_Network_Barrier_Agent, and Judge_Barrier_Agent, each a self-contained
    Agent step with its own run(agent_config).
    """

    def __init__(
        self,
        query: str,
        embedding_config: dict,
        embed_texts: EmbedFunction,
        context: str = DEFAULT_BARRIER_CONTEXT,
        reject_threshold: float = NN_REJECT_THRESHOLD,
        escalate_threshold: float = NN_ESCALATE_THRESHOLD,
    ):
        self.query = query
        self.embedding_config = embedding_config
        self.embed_texts = embed_texts
        self.context = context
        self.reject_threshold = reject_threshold
        self.escalate_threshold = escalate_threshold

    async def run(self, agent_config: dict) -> BarrierResult:
        layer_1 = Static_Barrier_Agent(query=self.query, context=self.context)
        layer_1_result = await layer_1.run(agent_config.copy())

        if layer_1_result["action"] in {"safe", "reject"}:
            return layer_1_result

        if layer_1_result["action"] == "escalate":
            layer_2 = Neural_Network_Barrier_Agent(
                query=self.query,
                embedding_config=self.embedding_config,
                embed_texts=self.embed_texts,
                context=self.context,
                reject_threshold=self.reject_threshold,
                escalate_threshold=self.escalate_threshold,
            )

            layer_2_result = await layer_2.run(agent_config.copy())

            if layer_2_result["action"] in {"accept", "reject"}:
                return layer_2_result

        layer_3 = Judge_Barrier_Agent(query=self.query, context=self.context)

        return await layer_3.run(agent_config.copy())
