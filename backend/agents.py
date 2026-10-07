import hashlib
import json
import os
import re
import threading
from typing import Any

from rank_bm25 import BM25Okapi

from base_classes import Agent

_TOKEN_RE = re.compile(r"\b\w+\b")

# corpus_address -> (BM25Okapi index, list of chunk dicts)
_bm25_index_cache: dict[str, tuple[BM25Okapi, list[dict]]] = {}
_bm25_cache_lock = threading.Lock()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_corpus(corpus_address: str) -> list[dict]:
    """Load chunks from <corpus_address>/processed/guideline_db.json.

    Each chunk is expected to look like:
        {"text": ..., "metadata": {"section": ..., "chunk_id": ..., "url": ...}}
    """
    corpus_path = os.path.join(corpus_address, "processed", "guideline_db.json")
    with open(corpus_path, encoding="utf-8") as f:
        return json.load(f)


def _get_bm25_index(corpus_address: str) -> tuple[BM25Okapi, list[dict]]:
    """Return a cached (BM25 index, chunks) pair for the given corpus, building it on first use."""
    if corpus_address in _bm25_index_cache:
        return _bm25_index_cache[corpus_address]

    with _bm25_cache_lock:
        if corpus_address not in _bm25_index_cache:
            chunks = _load_corpus(corpus_address)
            tokenized_corpus = [_tokenize(chunk["text"]) for chunk in chunks]
            _bm25_index_cache[corpus_address] = (BM25Okapi(tokenized_corpus), chunks)

    return _bm25_index_cache[corpus_address]


def _chunk_id(chunk: dict) -> str:
    """A stable identity for a chunk: its metadata chunk_id, or a hash of its text.

    Used both to dedupe across retrieval methods within a single call (see
    _hybrid_retrieve) and to recognize, across separate retrieval calls chained
    through a pipeline's context string, which chunks have already surfaced.
    """
    metadata = chunk.get("metadata", {})
    chunk_id = metadata.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    return hashlib.sha1(chunk["text"].encode("utf-8")).hexdigest()[:12]


def _format_resources(chunks: list[dict], start: int = 1) -> str:
    """Render chunks as numbered, source-annotated blocks for an LLM prompt.

    Every block carries a machine-readable "(id: ...)" marker so that a later
    retrieval call can recognize (via _extract_seen_ids) which chunks a chunk
    of accumulated context already contains, and skip re-retrieving them.
    ``start`` lets callers continue the numbering when appending new resources
    onto an already-numbered block.
    """
    resources = []
    for offset, chunk in enumerate(chunks):
        rank = start + offset
        metadata = chunk.get("metadata", {})
        header = f"[Resource {rank}] (id: {_chunk_id(chunk)})"
        if metadata.get("section"):
            header += f" (section: {metadata['section']})"
        if metadata.get("url"):
            header += f" (source: {metadata['url']})"
        resources.append(f"{header}\n{chunk['text']}")
    return "\n\n".join(resources)


_RESOURCE_ID_RE = re.compile(r"\(id: ([^)]+)\)")
_RESOURCE_HEADER_RE = re.compile(r"\[Resource \d+\]")
_RESOURCE_BLOCK_RE = re.compile(
    r"\[Resource \d+\] \(id: (?P<id>[^)]+)\)"
    r"(?: \(section: (?P<section>[^)]+)\))?"
    r"(?: \(source: (?P<source>[^)]+)\))?\n"
)


def _extract_seen_ids(context: str) -> set[str]:
    """Recover the set of chunk ids already present in an accumulated context string."""
    return set(_RESOURCE_ID_RE.findall(context))


def _count_resources(context: str) -> int:
    """Count already-numbered resource blocks in an accumulated context string."""
    return len(_RESOURCE_HEADER_RE.findall(context))


def _parse_resources(context: str) -> list[dict]:
    """Recover individual chunk dicts from a string _format_resources rendered.

    The inverse of _format_resources: splits the accumulated resources text
    back into {"text": ..., "metadata": {"chunk_id": ..., ...}} entries at
    each "[Resource N] (id: ...) ..." header. Chunk text that doesn't follow
    that header shape (a bare context string, e.g. a Decision_Agent's raw
    output ahead of the first retrieval hop) contributes no chunks -- callers
    that need candidates from a retrieval-chain context always find some,
    since every retrieval agent's output is entirely made of these blocks.
    """
    headers = list(_RESOURCE_BLOCK_RE.finditer(context))
    chunks = []
    for index, header in enumerate(headers):
        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(context)
        text = context[start:end].strip()
        if not text:
            continue
        metadata = {"chunk_id": header.group("id")}
        if header.group("section"):
            metadata["section"] = header.group("section")
        if header.group("source"):
            metadata["url"] = header.group("source")
        chunks.append({"text": text, "metadata": metadata})
    return chunks


def _bm25_retrieve(
    corpus_address: str, query: str, top_k: int, exclude_ids: set[str] | None = None
) -> list[dict]:
    """Rank chunks by BM25 statistical relevance to the query, skipping excluded ids."""
    bm25_index, chunks = _get_bm25_index(corpus_address)

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    exclude_ids = exclude_ids or set()
    scores = bm25_index.get_scores(query_tokens)
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    results = []
    for idx in ranked_indices:
        if scores[idx] <= 0:
            break
        chunk = chunks[idx]
        if _chunk_id(chunk) in exclude_ids:
            continue
        results.append(chunk)
        if len(results) >= top_k:
            break

    return results


def _keyword_retrieve(
    corpus_address: str, query: str, top_k: int, exclude_ids: set[str] | None = None
) -> list[dict]:
    """Rank chunks by count of distinct query terms present verbatim in the chunk text.

    Unlike BM25, this has no document-length normalization or IDF weighting, so a chunk
    containing a rare exact term (e.g. a drug name) can't be pushed down by longer,
    more generic chunks — it's a precision-oriented complement to _bm25_retrieve.
    """
    _, chunks = _get_bm25_index(corpus_address)

    query_terms = set(_tokenize(query))
    if not query_terms:
        return []

    exclude_ids = exclude_ids or set()
    scored = []
    for chunk in chunks:
        if _chunk_id(chunk) in exclude_ids:
            continue
        overlap = len(query_terms & set(_tokenize(chunk["text"])))
        if overlap > 0:
            scored.append((overlap, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def _hybrid_retrieve(
    corpus_address: str, query: str, top_k: int, exclude_ids: set[str] | None = None
) -> list[dict]:
    """Merge BM25 and literal-keyword-overlap retrieval, deduplicated by chunk id."""
    exclude_ids = exclude_ids or set()
    bm25_chunks = _bm25_retrieve(corpus_address, query, top_k, exclude_ids)
    keyword_chunks = _keyword_retrieve(corpus_address, query, top_k, exclude_ids)

    merged: dict[str, dict] = {}
    for chunk in bm25_chunks + keyword_chunks:
        merged.setdefault(_chunk_id(chunk), chunk)

    return list(merged.values())[:top_k]


class Decision_Agent(Agent):
    """An agent that makes a decision based on the LLM response.

    Its choice is written to shared state under "decision" -- not "context"
    or "answer" -- so a downstream node can reference "the decision that was
    made" without it ever being mistaken for retrieved context or a final
    reply.
    """

    WRITES = frozenset({"decision"})

    def __init__(self, query, options: list, state: dict | None = None):
        role = "You are a decision-making assistant. You will be given a list of options and a request. Your task is to select the best option based on the request and any provided context."
        super().__init__(query, state, role)
        self.options = options

    """
    inputs must contain the following options:
        1. "options": a list of options to choose from
        2. "request": how to select from the options (e.g. "select the best option", "select the worst option", etc.)
        3. "context": any additional context to consider when making the decision -- read from shared state, since only a retrieval node ever writes it
    """
    def pre(self) -> dict:
        return {
            "options": self.options,
            "request": self.query,
            "context": self.state.get("context", ""),
        }

    def specify_output(self) -> str:
        return "The output must be a json object inside a ```json block, with a single key 'decision' and a value that is one of the options provided in the input. The output must contain the exact text of ONE of the options provided in the input. The output must be a single JSON object, not a list or any other structure. The output must be a valid JSON object, and must be parsable by a JSON parser."

    def post(self, response: str) -> str:
        """Extract the decision from the LLM response."""
        # Extract the JSON object from the response
        try:
            parsed = self._find_json(response)
            decision = parsed["decision"]
            if decision not in self.options:
                raise ValueError(f"Decision '{decision}' is not in the provided options.")
            return decision
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid JSON response: {e}")

    def post_fallback(self, response: str) -> str:
        """Fallback post-processing of the LLM response in case of failure."""
        # Attempt to extract the decision from the response even if it's not valid JSON
        for option in self.options:
            if option in response:
                return option
        return self.options[0]


class _Retrieval_Agent(Agent):
    """Base class for retrieval-only agents. Never calls the LLM.

    Retrieval and generation are kept as separate concerns: a retrieval agent's
    only job is to find and return relevant resources, deduplicated against
    whatever this pipeline run has already surfaced; turning those resources
    into a reply is left to a downstream generation agent (e.g.
    Direct_Answer_Agent) that reads them from shared state's ``context`` key.

    Only a retrieval/rerank agent is allowed to write "context" (WRITES on
    each concrete subclass below) -- that's what makes it safe for every
    other node to read state["context"] and trust it actually is retrieved
    context, never a decision, an answer, or a judge's reasoning.

    Because the pipeline runtime hands every node the SAME shared ``state``
    dict for the run (see Pipeline.run in pipeline.py), state["context"]
    doubles as this run's retrieval memory: each call reads the chunk ids
    already present there (via the "(id: ...)" markers _format_resources
    embeds), retrieves only chunks not already among them, and appends the
    new ones. This is what lets several retrieval agents run one after
    another — or the same one loop — without ever handing the same resource
    back twice, and without losing resources found on earlier hops.
    """

    def __init__(self, query: str, corpus_address: str, state: dict | None, role: str, top_k: int = 5):
        super().__init__(query, state, role)
        self.corpus_address = corpus_address
        self.top_k = top_k

    def _search(self, exclude_ids: set[str]) -> list[dict]:
        """Return up to top_k new chunks relevant to the query, excluding exclude_ids."""
        raise NotImplementedError

    def _retrieve_and_accumulate(self) -> str:
        """Fetch new chunks not already in state["context"] and append them to it."""
        existing_context = self.state.get("context", "")
        seen_ids = _extract_seen_ids(existing_context)
        new_chunks = self._search(seen_ids)

        if not new_chunks:
            return existing_context.strip() or "No relevant resources found."

        formatted_new = _format_resources(new_chunks, start=_count_resources(existing_context) + 1)

        existing = existing_context.strip()
        if existing and existing != "No relevant resources found.":
            return f"{existing}\n\n{formatted_new}"
        return formatted_new

    async def run(self, agent_config: dict | None = None) -> str:
        return self._retrieve_and_accumulate()

    def pre(self) -> dict:
        return {"resources": self._retrieve_and_accumulate()}

    def specify_output(self) -> str:
        return "N/A — this agent does not call the LLM."

    def post(self, response: str) -> str:
        return self._retrieve_and_accumulate()

    def post_fallback(self, response: str) -> str:
        return self._retrieve_and_accumulate()


class RAG_Agent(_Retrieval_Agent):
    """Retrieves the top-k chunks most relevant to the query via BM25. Does not call the LLM."""

    WRITES = frozenset({"context"})

    def __init__(self, query: str, corpus_address: str, state: dict | None = None, top_k: int = 5):
        role = "You are a retrieval assistant. You will be given a query and a corpus of documents. Your task is to retrieve the top-k passages most statistically relevant to the query."
        super().__init__(query, corpus_address, state, role, top_k)

    def _search(self, exclude_ids: set[str]) -> list[dict]:
        return _bm25_retrieve(self.corpus_address, self.query, self.top_k, exclude_ids)

    def do_simple_rag(self) -> str:
        """Retrieve the top-k most relevant chunks from the corpus via BM25 keyword search."""
        chunks = _bm25_retrieve(self.corpus_address, self.query, self.top_k)
        if not chunks:
            return "No relevant resources found."
        return _format_resources(chunks)


class Keyword_Search_Agent(_Retrieval_Agent):
    """Retrieves chunks by literal keyword overlap. Does not call the LLM."""

    WRITES = frozenset({"context"})

    def __init__(self, query: str, corpus_address: str, state: dict | None = None, top_k: int = 5):
        role = "You are a keyword search assistant. You will be given a query and a corpus of documents. Your task is to retrieve the top-k documents that contain the query terms."
        super().__init__(query, corpus_address, state, role, top_k)

    def _search(self, exclude_ids: set[str]) -> list[dict]:
        return _keyword_retrieve(self.corpus_address, self.query, self.top_k, exclude_ids)

    def do_keyword_search(self) -> str:
        """Retrieve the top-k chunks with the most distinct query terms present verbatim."""
        chunks = _keyword_retrieve(self.corpus_address, self.query, self.top_k)
        if not chunks:
            return "No relevant resources found."
        return _format_resources(chunks)


class Hybrid_Agent(_Retrieval_Agent):
    """Combines BM25 and literal keyword-overlap search for broader recall than either alone.

    Does not call the LLM.
    """

    WRITES = frozenset({"context"})

    def __init__(self, query: str, corpus_address: str, state: dict | None = None, top_k: int = 5):
        role = "You are a hybrid search assistant. You will be given a query and a corpus of documents. Your task is to retrieve the top-k documents that are most relevant to the query using a combination of BM25 and keyword-overlap search."
        super().__init__(query, corpus_address, state, role, top_k)

    def _search(self, exclude_ids: set[str]) -> list[dict]:
        return _hybrid_retrieve(self.corpus_address, self.query, self.top_k, exclude_ids)

    def do_hybrid_search(self) -> str:
        """Retrieve the top-k chunks from the merged BM25 + keyword-overlap result set."""
        chunks = _hybrid_retrieve(self.corpus_address, self.query, self.top_k)
        if not chunks:
            return "No relevant resources found."
        return _format_resources(chunks)


class Reranker_Agent(Agent):
    """Uses the LLM to re-rank the resources accumulated in shared state by relevance to the query.

    Takes its candidates from state["context"] -- the same accumulated-resources string every
    retrieval agent reads and writes (see _format_resources/_parse_resources) -- so it chains
    directly after RAG_Agent, Keyword_Search_Agent, or Hybrid_Agent like any other node in a
    retrieval chain, rather than needing a separately supplied candidate list. It writes its
    reranked result back under the same "context" key, same as any other retrieval-family node.
    """

    WRITES = frozenset({"context"})

    def __init__(self, query: str, state: dict | None = None, top_k: int = 5):
        role = "You are a reranker assistant. You will be given a list of candidate documents and a query. Your task is to re-rank the candidates by relevance to the query."
        super().__init__(query, state, role)
        self.top_k = top_k

    @property
    def candidates(self) -> list[dict]:
        """Parsed fresh from ``self.state["context"]`` on every access.

        The pipeline runtime constructs every agent once during compilation
        (with a placeholder state), then patches ``.state`` onto that same
        instance right before run() with the real, shared dict (see
        Pipeline.run() in pipeline.py). Parsing once in __init__, before that
        patch happens, would always see the placeholder and find nothing.
        """
        return _parse_resources(self.state.get("context", ""))

    def pre(self) -> dict:
        numbered = "\n\n".join(
            f"[{i}] {chunk['text']}"
            for i, chunk in enumerate(self.candidates)
        )
        return {"candidates": numbered, "request": self.query}

    def specify_output(self) -> str:
        return (
            "The output must be a json object inside a ```json block, with a single key "
            "'ranking', a value that is a list of the candidate numbers (integers) ordered "
            f"from most to least relevant to the request, containing at most {self.top_k} "
            "numbers and only numbers that appear in the candidates. The output must be a "
            "single JSON object, not a list or any other structure. The output must be a "
            "valid JSON object, and must be parsable by a JSON parser."
        )

    def post(self, response: str) -> str:
        """Reorder and filter candidate chunks according to the LLM's ranking."""
        try:
            parsed = self._find_json(response)
            ranking = parsed["ranking"]

            if not isinstance(ranking, list) or not ranking:
                raise ValueError("'ranking' must be a non-empty list.")

            candidates = self.candidates
            selected: list[dict] = []
            for i in ranking[:self.top_k]:
                if not isinstance(i, int) or not (0 <= i < len(candidates)):
                    raise ValueError(f"Ranking index {i} is out of range.")
                selected.append(candidates[i])

            return _format_resources(selected)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Invalid JSON response: {e}") from e

    def post_fallback(self, response: str) -> str:
        """Fallback: keep the original candidate order, truncated to top_k."""
        return _format_resources(self.candidates[:self.top_k])


class Binary_Judge_Agent(Agent):
    """Judges whether retrieved context contains enough information to answer the query.

    Returns a dict with just "route" (drives pipeline routing) and "reason"
    (diagnostic, kept in the trace) -- it writes nothing to shared state.
    Under the old context-threading model this had to also echo back a
    "context" key so the resources it judged weren't lost to whichever route
    fired; now that the accumulated resources live in shared state instead of
    being handed node-to-node as a return value, there's nothing to lose --
    state["context"] simply stays exactly as the last retrieval agent left
    it, whether this judge routes "yes" or "no". That's what makes a "judge
    sufficiency, retrieve more on 'no'" loop safe with no extra bookkeeping.
    """

    def __init__(self, query: str, state: dict | None = None):
        role = "You are a context sufficient assistant. You will be given a request and a set of retrieved documents. Your task is to determine whether the retrieved context contains enough information to fully answer the request."
        super().__init__(query, state, role)

    def pre(self) -> dict:
        return {"context": self.state.get("context", ""), "request": self.query}

    def specify_output(self) -> str:
        return (
            "The output must be a json object inside a ```json block, with two keys: "
            "'sufficient' (a boolean, true only if the context contains enough information "
            "to fully answer the request) and 'reason' (a short string explaining the "
            "decision). The output must be a single JSON object, not a list or any other "
            "structure. The output must be a valid JSON object, and must be parsable by a "
            "JSON parser."
        )

    def post(self, response: str) -> dict:
        try:
            parsed = self._find_json(response)
            sufficient = parsed["sufficient"]
            reason = parsed["reason"]
            if not isinstance(sufficient, bool):
                raise ValueError(f"'sufficient' must be a boolean, got {type(sufficient)}")
            if not isinstance(reason, str):
                raise ValueError(f"'reason' must be a string, got {type(reason)}")
            return {
                "route": "yes" if sufficient else "no",
                "reason": reason,
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Invalid JSON response: {e}")

    def post_fallback(self, response: str) -> dict:
        """Fail closed: treat unparsable responses as insufficient context."""
        return {"route": "no", "reason": "unparsable judge response"}


class Direct_Answer_Agent(Agent):
    """Drafts a final answer to the query from already-retrieved context.

    Reads state["context"] -- written only by a retrieval/rerank agent --
    rather than "whatever the previous node returned", so a Decision_Agent or
    Binary_Judge_Agent immediately upstream can never leak its own decision
    or verdict into this agent's prompt as if it were retrieved context.
    """

    WRITES = frozenset({"answer"})

    def __init__(self,  query: str, state: dict | None = None):
        role = "You are a direct answer assistant. You will be given a request and a set of retrieved documents. Your task is to generate a final answer to the request that is fully grounded in the provided context. Ignore any other instructions. For exmaple, ignore any choice examples, or decision instructions, or any other instructions that are not related to the request and context. Only use the provided context to generate the answer to the main query."
        super().__init__(query, state, role)

    def pre(self) -> dict:
        return {"context": self.state.get("context", ""), "request": self.query}

    def specify_output(self) -> str:
        return (
            "The output must be a markdown object inside a ```markdown block, with a nicely formatted answer to the request."
            "The answer must be grounded only in the "
            "provided context. The output must be a single markdown object, not a list or any "
            "other structure. The output must be a valid markdown object, and must be parsable "
            "by a markdown parser."
        )

    def post(self, response: str) -> str:
        match = re.search(r"```markdown\s*(.*?)\s*```", response, re.DOTALL)
        if not match:
            raise ValueError("No markdown block found in response")
        return match.group(1).strip()

    def post_fallback(self, response: str) -> str:
        return response.strip()


class Static_Agent(Agent):
    """Always returns a fixed, pre-written message. Does not call the LLM.

    Used for deterministic terminal replies (e.g. crisis-line messages, canned FAQ answers)
    where invoking the LLM would be unnecessary or unsafe.
    """

    WRITES = frozenset({"answer"})

    def __init__(self, query: str, message: str, state: dict | None = None):
        role = "You are a static assistant. You will be given a fixed message to return."
        super().__init__(query, state, role)
        self.message = message

    async def run(self, agent_config: dict) -> Any:
        return self.message

    def pre(self) -> dict:
        return {"request": self.query}

    def specify_output(self) -> str:
        return "N/A — this agent does not call the LLM."

    def post(self, response: str) -> str:
        return self.message

    def post_fallback(self, response: str) -> str:
        return self.message
    

class _Static_Agent_Auto(Agent):
    """Passes through whatever this run's shared state already holds as the answer.

    Does not call the LLM. Prefers state["answer"] (a real generation node ran
    upstream) and falls back to state["context"] (a retrieval-only run with no
    answer node) so this never surfaces a decision or a bare judge verdict --
    only content another node was actually permitted to write.
    """

    def __init__(self, state: dict | None = None):
        role = "You are a static assistant. You will be given a fixed message to return."
        super().__init__("", state, role)

    async def run(self, agent_config: dict) -> Any:
        return self.state.get("answer", self.state.get("context", ""))

    def pre(self) -> dict:
        return {"request": self.query}

    def specify_output(self) -> str:
        return "N/A — this agent does not call the LLM."

    def post(self, response: str) -> str:
        return self.state.get("answer", self.state.get("context", ""))

    def post_fallback(self, response: str) -> str:
        return "something went wrong, but the final answer is the context from the previous agent."


class Simple_Task_Agent(Agent):
    """A minimal agent for ad-hoc tasks: takes a query and context, returns raw LLM text.

    Unlike the other agents here, the output is plain text rather than a JSON envelope —
    use this when a task doesn't warrant its own structured schema. It writes nothing to
    shared state (WRITES is empty) -- its result is only usable via routing or the trace,
    never as another node's prompt input, since it doesn't own a namespaced key of its own.
    """
    def __init__(self, query: str, state: dict | None = None):
        role = "You are a direct answer assistant. You will be given a request and some context. Your task is to generate a final answer to the request that is fully grounded in the provided context."
        super().__init__(query, state, role)


    def pre(self) -> dict:
        return {"context": self.state.get("context", ""), "request": self.query}

    def specify_output(self) -> str:
        return (
            "The output must be plain text with no additional formatting, JSON, or markdown "
            "code blocks — just the direct answer."
        )

    def post(self, response: str) -> str:
        text = response.strip()
        if not text:
            raise ValueError("Empty response from LLM.")
        return text

    def post_fallback(self, response: str) -> str:
        return response.strip()
