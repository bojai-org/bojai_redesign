import pytest

import agents
from agents import (
    Binary_Judge_Agent,
    Decision_Agent,
    Direct_Answer_Agent,
    Hybrid_Agent,
    Keyword_Search_Agent,
    RAG_Agent,
    Reranker_Agent,
    Simple_Task_Agent,
    Static_Agent,
    _bm25_retrieve,
    _chunk_id,
    _count_resources,
    _extract_seen_ids,
    _format_resources,
    _get_bm25_index,
    _hybrid_retrieve,
    _keyword_retrieve,
    _load_corpus,
    _parse_resources,
    _RESOURCE_ID_RE,
    _tokenize,
)

CANDIDATES = [
    {"text": "first candidate", "metadata": {"chunk_id": "r1"}},
    {"text": "second candidate", "metadata": {"chunk_id": "r2"}},
    {"text": "third candidate", "metadata": {"chunk_id": "r3"}},
]

# Reranker_Agent takes its candidates from shared state["context"] (the same
# accumulated resources string every retrieval agent produces), not a
# separate list -- so tests below feed it a state dict built from CANDIDATES.
CANDIDATES_CONTEXT = _format_resources(CANDIDATES)


# ─────────────────────────────────────────────────────────────────────────────
# module-level retrieval helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_splits_on_word_boundaries():
    assert _tokenize("Lithium, 900mg!") == ["lithium", "900mg"]


def test_tokenize_empty_string_returns_empty_list():
    assert _tokenize("") == []


def test_load_corpus_reads_chunks(corpus_address):
    chunks = _load_corpus(corpus_address)
    assert len(chunks) == 4
    assert chunks[0]["text"].startswith("Lithium")


def test_get_bm25_index_caches_by_corpus_address(corpus_address):
    index1, chunks1 = _get_bm25_index(corpus_address)
    index2, chunks2 = _get_bm25_index(corpus_address)
    assert index1 is index2
    assert chunks1 is chunks2


def test_format_resources_includes_section_and_source():
    chunks = [{"text": "hello", "metadata": {"section": "Sec", "url": "http://x"}}]
    rendered = _format_resources(chunks)
    assert "[Resource 1]" in rendered
    assert "(section: Sec)" in rendered
    assert "(source: http://x)" in rendered
    assert "hello" in rendered


def test_format_resources_embeds_a_stable_id_marker():
    chunk = {"text": "hello", "metadata": {"chunk_id": "abc"}}
    assert _format_resources([chunk]) == "[Resource 1] (id: abc)\nhello"


def test_format_resources_falls_back_to_a_text_hash_when_chunk_id_missing():
    chunk = {"text": "hello", "metadata": {}}
    expected_id = _chunk_id(chunk)
    assert _format_resources([chunk]) == f"[Resource 1] (id: {expected_id})\nhello"


def test_format_resources_start_continues_numbering():
    chunks = [{"text": "hello", "metadata": {"chunk_id": "abc"}}]
    assert _format_resources(chunks, start=3) == "[Resource 3] (id: abc)\nhello"


def test_chunk_id_prefers_metadata_chunk_id():
    assert _chunk_id({"text": "hello", "metadata": {"chunk_id": "abc"}}) == "abc"


def test_chunk_id_is_deterministic_for_same_text():
    chunk = {"text": "some resource text", "metadata": {}}
    assert _chunk_id(chunk) == _chunk_id(dict(chunk))


def test_extract_seen_ids_recovers_ids_from_formatted_text():
    rendered = _format_resources(
        [
            {"text": "a", "metadata": {"chunk_id": "c1"}},
            {"text": "b", "metadata": {"chunk_id": "c2"}},
        ]
    )
    assert _extract_seen_ids(rendered) == {"c1", "c2"}


def test_extract_seen_ids_empty_for_plain_text():
    assert _extract_seen_ids("just some unrelated context") == set()


def test_count_resources_counts_headers():
    rendered = _format_resources(
        [
            {"text": "a", "metadata": {"chunk_id": "c1"}},
            {"text": "b", "metadata": {"chunk_id": "c2"}},
        ]
    )
    assert _count_resources(rendered) == 2
    assert _count_resources("no resources here") == 0


def test_bm25_retrieve_ranks_relevant_chunk_first(corpus_address):
    results = _bm25_retrieve(corpus_address, "mania sleep racing thoughts", top_k=5)
    assert results
    assert "manic episodes" in results[0]["text"]


def test_bm25_retrieve_empty_query_returns_nothing(corpus_address):
    assert _bm25_retrieve(corpus_address, "", top_k=5) == []


def test_bm25_retrieve_respects_top_k(corpus_address):
    results = _bm25_retrieve(corpus_address, "lithium mania quetiapine depression", top_k=2)
    assert len(results) <= 2


def test_bm25_retrieve_excludes_given_chunk_ids(corpus_address):
    query = "lithium mania quetiapine depression"
    top_chunk = _bm25_retrieve(corpus_address, query, top_k=1)[0]
    excluded_id = _chunk_id(top_chunk)

    results = _bm25_retrieve(corpus_address, query, top_k=10, exclude_ids={excluded_id})

    assert excluded_id not in {_chunk_id(r) for r in results}
    assert len(results) >= 1  # two other chunks still match this query


def test_keyword_retrieve_finds_exact_term(corpus_address):
    results = _keyword_retrieve(corpus_address, "quetiapine", top_k=5)
    assert results
    assert "Quetiapine" in results[0]["text"]


def test_keyword_retrieve_empty_query_returns_nothing(corpus_address):
    assert _keyword_retrieve(corpus_address, "", top_k=5) == []


def test_keyword_retrieve_no_match_returns_empty(corpus_address):
    assert _keyword_retrieve(corpus_address, "zzz_no_such_term", top_k=5) == []


def test_keyword_retrieve_excludes_given_chunk_ids(corpus_address):
    results_all = _keyword_retrieve(corpus_address, "quetiapine", top_k=5)
    excluded_id = _chunk_id(results_all[0])

    results = _keyword_retrieve(corpus_address, "quetiapine", top_k=5, exclude_ids={excluded_id})

    assert results == []  # "quetiapine" only appears in the excluded chunk


def test_hybrid_retrieve_merges_without_duplicates(corpus_address):
    results = _hybrid_retrieve(corpus_address, "lithium mania", top_k=10)
    chunk_ids = [r["metadata"]["chunk_id"] for r in results]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert len(results) >= 1


def test_hybrid_retrieve_respects_top_k(corpus_address):
    results = _hybrid_retrieve(corpus_address, "lithium mania quetiapine depression", top_k=1)
    assert len(results) <= 1


def test_hybrid_retrieve_excludes_given_chunk_ids(corpus_address):
    query = "lithium mania quetiapine"
    already_retrieved = _hybrid_retrieve(corpus_address, query, top_k=10)
    excluded_ids = {_chunk_id(r) for r in already_retrieved}

    results = _hybrid_retrieve(corpus_address, query, top_k=10, exclude_ids=excluded_ids)

    assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# Decision_Agent
#
# Its "context" input is read from shared state["context"] -- the same key
# only a retrieval/rerank agent is ever allowed to write -- and its own
# choice is written back under "decision" (see agents.py's WRITES).
# ─────────────────────────────────────────────────────────────────────────────

def test_decision_agent_pre():
    agent = Decision_Agent("pick one", ["a", "b", "c"], state={"context": "some context"})
    assert agent.pre() == {"options": ["a", "b", "c"], "request": "pick one", "context": "some context"}


def test_decision_agent_pre_defaults_context_to_empty_string():
    agent = Decision_Agent("pick one", ["a", "b", "c"])
    assert agent.pre()["context"] == ""


def test_decision_agent_writes_decision_key_only():
    assert Decision_Agent("q", ["a", "b"]).WRITES == frozenset({"decision"})


def test_decision_agent_post_valid():
    agent = Decision_Agent("q", ["a", "b"])
    assert agent.post('```json\n{"decision": "b"}\n```') == "b"


def test_decision_agent_post_invalid_option_raises():
    agent = Decision_Agent("q", ["a", "b"])
    with pytest.raises(ValueError):
        agent.post('```json\n{"decision": "z"}\n```')


def test_decision_agent_post_missing_key_raises():
    agent = Decision_Agent("q", ["a", "b"])
    with pytest.raises(ValueError):
        agent.post("```json\n{}\n```")


def test_decision_agent_post_malformed_json_raises():
    agent = Decision_Agent("q", ["a", "b"])
    with pytest.raises(ValueError):
        agent.post("not json at all")


def test_decision_agent_post_fallback_substring_match():
    agent = Decision_Agent("q", ["apple", "banana"])
    assert agent.post_fallback("I choose banana today") == "banana"


def test_decision_agent_post_fallback_defaults_to_first_option():
    agent = Decision_Agent("q", ["apple", "banana"])
    assert agent.post_fallback("no match here") == "apple"


async def test_decision_agent_run_end_to_end(fake_llm, agent_config):
    fake_llm.queue('```json\n{"decision": "b"}\n```')
    result = await Decision_Agent("pick", ["a", "b"]).run(agent_config)
    assert result == "b"


# ─────────────────────────────────────────────────────────────────────────────
# RAG_Agent / Keyword_Search_Agent / Hybrid_Agent
#
# All three are retrieval-only: they never call the LLM. run() overrides the
# base Agent.run(agent_config) with an optional-argument signature, so tests
# below call run() with no args to match actual behavior. Generation (turning
# retrieved resources into a reply) is Direct_Answer_Agent's job, not theirs.
# ─────────────────────────────────────────────────────────────────────────────

def test_rag_agent_do_simple_rag_returns_formatted_resources(corpus_address):
    agent = RAG_Agent("mania sleep", corpus_address)
    result = agent.do_simple_rag()
    assert "[Resource 1]" in result
    assert "manic episodes" in result


def test_rag_agent_do_simple_rag_no_matches(corpus_address):
    agent = RAG_Agent("zzz_no_such_term_at_all", corpus_address)
    assert agent.do_simple_rag() == "No relevant resources found."


def test_rag_agent_pre_includes_resources(corpus_address):
    pre = RAG_Agent("mania", corpus_address).pre()
    assert "resources" in pre
    assert "[Resource" in pre["resources"]


def test_rag_agent_post_and_post_fallback_delegate(corpus_address):
    agent = RAG_Agent("mania sleep", corpus_address)
    expected = agent.do_simple_rag()
    assert agent.post("ignored") == expected
    assert agent.post_fallback("ignored") == expected


def test_rag_agent_writes_context_key_only(corpus_address):
    assert RAG_Agent("mania", corpus_address).WRITES == frozenset({"context"})


async def test_rag_agent_run_bypasses_llm(fake_llm, corpus_address):
    agent = RAG_Agent("mania sleep", corpus_address)
    result = await agent.run()
    assert "manic episodes" in result
    assert fake_llm.calls == []


def test_keyword_search_agent_do_keyword_search(corpus_address):
    agent = Keyword_Search_Agent("quetiapine dosing", corpus_address)
    assert "Quetiapine" in agent.do_keyword_search()


def test_keyword_search_agent_no_matches(corpus_address):
    agent = Keyword_Search_Agent("zzz_nonexistent", corpus_address)
    assert agent.do_keyword_search() == "No relevant resources found."


def test_keyword_search_agent_pre_includes_resources(corpus_address):
    pre = Keyword_Search_Agent("quetiapine", corpus_address).pre()
    assert "resources" in pre


async def test_keyword_search_agent_run_bypasses_llm(fake_llm, corpus_address):
    agent = Keyword_Search_Agent("quetiapine", corpus_address)
    result = await agent.run()
    assert "Quetiapine" in result
    assert fake_llm.calls == []


def test_keyword_search_agent_post_and_post_fallback_delegate(corpus_address):
    agent = Keyword_Search_Agent("quetiapine", corpus_address)
    expected = agent.do_keyword_search()
    assert agent.post("ignored") == expected
    assert agent.post_fallback("ignored") == expected


def test_hybrid_agent_do_hybrid_search(corpus_address):
    agent = Hybrid_Agent("lithium mania", corpus_address)
    assert "[Resource" in agent.do_hybrid_search()


def test_hybrid_agent_no_matches(corpus_address):
    agent = Hybrid_Agent("zzz_nonexistent", corpus_address)
    assert agent.do_hybrid_search() == "No relevant resources found."


async def test_hybrid_agent_run_bypasses_llm(fake_llm, corpus_address):
    agent = Hybrid_Agent("lithium", corpus_address)
    result = await agent.run()
    assert "[Resource" in result
    assert fake_llm.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval accumulation and dedup across chained retrieval calls
#
# Retrieval agents thread state through the shared pipeline-run "context" key
# (see base_classes.Agent's docstring and each retrieval class's WRITES):
# each call reads the resource ids already embedded in self.state["context"],
# retrieves only chunks not already among them, and appends the new ones.
# This is what prevents a second retrieval hop (e.g. two RAG_Agent nodes
# chained together, or a Decision_Agent looping back into the same retrieval
# node) from resurfacing a chunk the first hop already found, while still
# preserving everything found on earlier hops.
# ─────────────────────────────────────────────────────────────────────────────

def test_second_hop_does_not_repeat_chunks_already_in_context(corpus_address):
    query = "lithium mania quetiapine"

    first_hop = RAG_Agent(query, corpus_address, top_k=1)
    first_context = first_hop._retrieve_and_accumulate()
    first_ids = _extract_seen_ids(first_context)
    assert len(first_ids) == 1

    second_hop = RAG_Agent(query, corpus_address, state={"context": first_context}, top_k=1)
    accumulated = second_hop._retrieve_and_accumulate()
    all_ids = _extract_seen_ids(accumulated)

    # the chunk found on the first hop is preserved ...
    assert first_ids <= all_ids
    # ... and a second, different chunk was appended (two chunks match this query)
    assert len(all_ids) == 2

    # no id appears more than once in the accumulated text
    ids_in_order = _RESOURCE_ID_RE.findall(accumulated)
    assert len(ids_in_order) == len(set(ids_in_order))


def test_repeating_the_same_query_once_exhausted_adds_nothing_new(corpus_address):
    query = "lithium mania quetiapine"

    exhausting_hop = RAG_Agent(query, corpus_address, top_k=10)
    first_context = exhausting_hop._retrieve_and_accumulate()

    repeat_hop = RAG_Agent(query, corpus_address, state={"context": first_context}, top_k=10)
    accumulated = repeat_hop._retrieve_and_accumulate()

    assert accumulated == first_context


def test_accumulation_preserves_earlier_context_text():
    """Chaining onto non-empty prior context keeps that text, rather than discarding it."""

    class _StubAgent(Keyword_Search_Agent):
        def _search(self, exclude_ids):
            return [{"text": "new chunk", "metadata": {"chunk_id": "new1"}}]

    stub = _StubAgent("q", "unused", state={"context": "earlier context"})
    accumulated = stub._retrieve_and_accumulate()

    assert accumulated.startswith("earlier context")
    assert "new chunk" in accumulated
    assert "[Resource 1]" in accumulated  # numbering continues past the prior text's 0 resources


def test_accumulation_numbers_new_resources_after_existing_ones():
    class _StubAgent(Keyword_Search_Agent):
        def _search(self, exclude_ids):
            return [{"text": "second chunk", "metadata": {"chunk_id": "c2"}}]

    existing_context = _format_resources([{"text": "first chunk", "metadata": {"chunk_id": "c1"}}])
    stub = _StubAgent("q", "unused", state={"context": existing_context})
    accumulated = stub._retrieve_and_accumulate()

    assert "[Resource 1] (id: c1)" in accumulated
    assert "[Resource 2] (id: c2)" in accumulated


def test_accumulation_no_new_chunks_returns_context_unchanged():
    class _StubAgent(Keyword_Search_Agent):
        def _search(self, exclude_ids):
            return []

    stub = _StubAgent("q", "unused", state={"context": "earlier context"})
    assert stub._retrieve_and_accumulate() == "earlier context"


def test_accumulation_empty_context_and_no_matches_reports_none_found():
    class _StubAgent(Keyword_Search_Agent):
        def _search(self, exclude_ids):
            return []

    stub = _StubAgent("q", "unused")
    assert stub._retrieve_and_accumulate() == "No relevant resources found."


# ─────────────────────────────────────────────────────────────────────────────
# Reranker_Agent
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_resources_recovers_chunks_from_formatted_text():
    chunks = [
        {"text": "hello", "metadata": {"chunk_id": "c1", "section": "Sec", "url": "http://x"}},
        {"text": "world", "metadata": {"chunk_id": "c2"}},
    ]
    parsed = _parse_resources(_format_resources(chunks))
    assert parsed == [
        {"text": "hello", "metadata": {"chunk_id": "c1", "section": "Sec", "url": "http://x"}},
        {"text": "world", "metadata": {"chunk_id": "c2"}},
    ]


def test_parse_resources_ignores_non_resource_text():
    assert _parse_resources("just some unrelated context") == []


def test_reranker_agent_writes_context_key_only():
    assert Reranker_Agent("q").WRITES == frozenset({"context"})


def test_reranker_agent_reconstructs_candidates_from_context():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    assert [c["text"] for c in agent.candidates] == [
        "first candidate",
        "second candidate",
        "third candidate",
    ]


def test_reranker_agent_pre_numbers_candidates():
    pre = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2).pre()
    assert "[0] first candidate" in pre["candidates"]
    assert "[1] second candidate" in pre["candidates"]
    assert "[2] third candidate" in pre["candidates"]


def test_reranker_agent_post_reorders_by_ranking():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    result = agent.post('```json\n{"ranking": [2, 0]}\n```')
    assert result.index("third candidate") < result.index("first candidate")
    assert "second candidate" not in result


def test_reranker_agent_post_truncates_to_top_k():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=1)
    result = agent.post('```json\n{"ranking": [0, 1, 2]}\n```')
    assert "first candidate" in result
    assert "second candidate" not in result


def test_reranker_agent_post_out_of_range_index_raises():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    with pytest.raises(ValueError):
        agent.post('```json\n{"ranking": [99]}\n```')


def test_reranker_agent_post_empty_ranking_raises():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    with pytest.raises(ValueError):
        agent.post('```json\n{"ranking": []}\n```')


def test_reranker_agent_post_malformed_json_raises():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    with pytest.raises(ValueError):
        agent.post("not json at all")


def test_reranker_agent_post_fallback_keeps_original_order_truncated():
    agent = Reranker_Agent("q", state={"context": CANDIDATES_CONTEXT}, top_k=2)
    result = agent.post_fallback("garbage")
    assert result.index("first candidate") < result.index("second candidate")
    assert "third candidate" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Binary_Judge_Agent
#
# Writes nothing to shared state (WRITES is empty): its result carries only
# "route" (drives pipeline routing) and "reason" (diagnostic, kept in the
# trace). It no longer needs to echo state["context"] back out to avoid
# losing it -- shared state already holds it, untouched, regardless of which
# way this judge routes.
# ─────────────────────────────────────────────────────────────────────────────

def test_binary_judge_agent_writes_nothing():
    assert Binary_Judge_Agent("q").WRITES == frozenset()


def test_binary_judge_agent_pre():
    agent = Binary_Judge_Agent("is context enough?", state={"context": "the context text"})
    assert agent.pre() == {"context": "the context text", "request": "is context enough?"}


def test_binary_judge_agent_post_sufficient_true():
    agent = Binary_Judge_Agent("q", state={"context": "the accumulated resources"})
    result = agent.post('```json\n{"sufficient": true, "reason": "ok"}\n```')
    assert result == {"route": "yes", "reason": "ok"}


def test_binary_judge_agent_post_sufficient_false():
    agent = Binary_Judge_Agent("q", state={"context": "the accumulated resources"})
    result = agent.post('```json\n{"sufficient": false, "reason": "not enough"}\n```')
    assert result == {"route": "no", "reason": "not enough"}


def test_binary_judge_agent_post_wrong_type_raises():
    agent = Binary_Judge_Agent("q")
    with pytest.raises(ValueError):
        agent.post('```json\n{"sufficient": "yes", "reason": "x"}\n```')


def test_binary_judge_agent_post_fallback_fails_closed():
    result = Binary_Judge_Agent("q").post_fallback("garbage")
    assert result == {"route": "no", "reason": "unparsable judge response"}


# ─────────────────────────────────────────────────────────────────────────────
# Direct_Answer_Agent
# ─────────────────────────────────────────────────────────────────────────────

def test_direct_answer_agent_writes_answer_key_only():
    assert Direct_Answer_Agent("q").WRITES == frozenset({"answer"})


def test_direct_answer_agent_pre():
    agent = Direct_Answer_Agent("q", state={"context": "the context text"})
    assert agent.pre() == {"context": "the context text", "request": "q"}


def test_direct_answer_agent_pre_defaults_context_to_empty_string():
    assert Direct_Answer_Agent("q").pre()["context"] == ""


def test_direct_answer_agent_post_extracts_answer():
    agent = Direct_Answer_Agent("q")
    assert agent.post("```markdown\nfinal\n```") == "final"


def test_direct_answer_agent_post_missing_block_raises():
    agent = Direct_Answer_Agent("q")
    with pytest.raises(ValueError):
        agent.post("no fenced block here")


def test_direct_answer_agent_post_fallback_strips():
    assert Direct_Answer_Agent("q").post_fallback("  raw  ") == "raw"


async def test_direct_answer_agent_run_end_to_end(fake_llm, agent_config):
    fake_llm.queue("```markdown\nfinal grounded answer\n```")
    agent = Direct_Answer_Agent("q", state={"context": "some context"})
    assert await agent.run(agent_config) == "final grounded answer"


# ─────────────────────────────────────────────────────────────────────────────
# Simple_Task_Agent
# ─────────────────────────────────────────────────────────────────────────────

def test_simple_task_agent_writes_nothing():
    assert Simple_Task_Agent("q").WRITES == frozenset()


def test_simple_task_agent_pre():
    agent = Simple_Task_Agent("q", state={"context": "the context text"})
    assert agent.pre() == {"context": "the context text", "request": "q"}


def test_simple_task_agent_post_returns_stripped_text():
    assert Simple_Task_Agent("q").post("  plain answer  ") == "plain answer"


def test_simple_task_agent_post_empty_raises():
    with pytest.raises(ValueError):
        Simple_Task_Agent("q").post("   ")


async def test_simple_task_agent_run_end_to_end(fake_llm, agent_config):
    fake_llm.queue("  a plain text answer  ")
    result = await Simple_Task_Agent("q").run(agent_config)
    assert result == "a plain text answer"


# ─────────────────────────────────────────────────────────────────────────────
# Static_Agent / _Static_Agent_Auto
# ─────────────────────────────────────────────────────────────────────────────

def test_static_agent_writes_answer_key_only():
    assert Static_Agent("q", "msg").WRITES == frozenset({"answer"})


def test_static_agent_pre():
    assert Static_Agent("q", "msg").pre() == {"request": "q"}


def test_static_agent_post_and_post_fallback_return_message():
    agent = Static_Agent("q", "fixed message")
    assert agent.post("ignored") == "fixed message"
    assert agent.post_fallback("ignored") == "fixed message"


async def test_static_agent_run_returns_fixed_message(agent_config):
    agent = Static_Agent("q", "fixed message")
    assert await agent.run(agent_config) == "fixed message"


def test_static_agent_auto_post_returns_context_when_no_answer_written():
    agent = agents._Static_Agent_Auto(state={"context": "the accumulated context"})
    assert agent.post("ignored") == "the accumulated context"


def test_static_agent_auto_prefers_answer_over_context():
    """Once a real generation node has run, its answer -- not raw retrieved
    context -- is the passthrough value, since state["answer"] takes priority."""
    agent = agents._Static_Agent_Auto(
        state={"context": "raw resources", "answer": "final grounded answer"}
    )
    assert agent.post("ignored") == "final grounded answer"


async def test_static_agent_auto_run_returns_context(agent_config):
    agent = agents._Static_Agent_Auto(state={"context": "the accumulated context"})
    assert await agent.run(agent_config) == "the accumulated context"


# ─────────────────────────────────────────────────────────────────────────────
# specify_output() smoke check across all agents
# ─────────────────────────────────────────────────────────────────────────────

def test_specify_output_returns_nonempty_string_for_every_agent(corpus_address):
    instances = [
        Decision_Agent("q", ["a", "b"]),
        RAG_Agent("q", corpus_address),
        Keyword_Search_Agent("q", corpus_address),
        Hybrid_Agent("q", corpus_address),
        Reranker_Agent("q"),
        Binary_Judge_Agent("q"),
        Direct_Answer_Agent("q"),
        Static_Agent("q", "msg"),
        Simple_Task_Agent("q"),
    ]
    for instance in instances:
        output_spec = instance.specify_output()
        assert isinstance(output_spec, str) and output_spec.strip()
