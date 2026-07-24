"""End-to-end tests that every agent in agents.py and safety_agents.py can be
registered with the JSON-pipeline compiler and actually run through Pipeline,
per contract.md.
"""

import agents
import base_classes
import safety_agents
from compiler import compile_pipeline

FULL_AGENT_REGISTRY = {
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
    "Neural_Network_Barrier_Agent": safety_agents.Neural_Network_Barrier_Agent,
    "Judge_Barrier_Agent": safety_agents.Judge_Barrier_Agent,
    "Input_Barrier_Pipeline": safety_agents.Input_Barrier_Pipeline,
}


def test_full_registry_covers_every_public_agent_class():
    """Guards against a new/renamed agent silently falling out of the registry."""
    # "Agent" is the imported base class itself; "_Retrieval_Agent" is an internal
    # abstract retrieval base -- neither is meant to be registered directly.
    internal_only = {"Agent", "_Retrieval_Agent"}

    agent_names = {
        name
        for name in vars(agents)
        if name not in internal_only
        and isinstance(getattr(agents, name), type)
        and issubclass(getattr(agents, name), base_classes.Agent)
    }
    barrier_names = {
        name
        for name in vars(safety_agents)
        if name not in internal_only
        and isinstance(getattr(safety_agents, name), type)
        and issubclass(getattr(safety_agents, name), base_classes.Agent)
    }

    assert agent_names <= set(FULL_AGENT_REGISTRY)
    assert barrier_names <= set(FULL_AGENT_REGISTRY)


async def test_contract_example_chains_retrieval_hops_without_a_reply_agent_between_them(
    fake_llm, corpus_address
):
    """Mirrors the pipeline.json example in contract.md §1: decision -> rag_1 -> rag_2 -> answer,
    with a keyword_1 branch decision doesn't take. Only Decision_Agent and Direct_Answer_Agent
    should ever touch the LLM; the two chained RAG_Agent hops must not repeat a chunk.
    """
    registry = {
        "Decision_Agent": agents.Decision_Agent,
        "RAG_Agent": agents.RAG_Agent,
        "Keyword_Search_Agent": agents.Keyword_Search_Agent,
        "Direct_Answer_Agent": agents.Direct_Answer_Agent,
        "_Static_Agent_Auto": agents._Static_Agent_Auto,
    }
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "decision",
        "nodes": {
            "decision": {
                "type": "Decision_Agent",
                "prev": -1,
                "query": "lithium mania quetiapine",
                "context": "",
                "options": ["semantic", "keyword"],
                "semantic": "rag_1",
                "keyword": "keyword_1",
            },
            "rag_1": {
                "type": "RAG_Agent",
                "prev": "decision",
                "query": 0,
                "corpus_address": corpus_address,
                "top_k": 1,
                "next": "rag_2",
            },
            "rag_2": {
                "type": "RAG_Agent",
                "prev": "rag_1",
                "corpus_address": corpus_address,
                "top_k": 1,
                "next": "answer",
            },
            "keyword_1": {
                "type": "Keyword_Search_Agent",
                "prev": "decision",
                "query": 0,
                "corpus_address": corpus_address,
                "next": "answer",
            },
            "answer": {
                "type": "Direct_Answer_Agent",
                "prev": ["rag_2", "keyword_1"],
                "next": -1,
            },
        },
    }

    fake_llm.queue(
        '```json\n{"decision": "semantic"}\n```',
        '```json\n{"answer": "grounded reply"}\n```',
    )

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run()

    assert result.output == "grounded reply"
    assert len(fake_llm.calls) == 2  # only Decision_Agent and Direct_Answer_Agent call the LLM

    rag_1_ids = agents._extract_seen_ids(result.node_outputs["rag_1"])
    rag_2_ids = agents._extract_seen_ids(result.node_outputs["rag_2"])
    assert len(rag_1_ids) == 1
    assert len(rag_2_ids) == 2
    assert rag_1_ids < rag_2_ids  # rag_2 kept rag_1's chunk and appended a different one


async def test_reranker_agent_chains_after_a_retrieval_hop(fake_llm, corpus_address):
    """Reranker_Agent takes candidates from `context` like any other node in a
    retrieval chain -- no separate candidates field -- so it connects directly
    after a retrieval agent and reranks whatever that agent found.
    """
    registry = {
        "RAG_Agent": agents.RAG_Agent,
        "Reranker_Agent": agents.Reranker_Agent,
        "_Static_Agent_Auto": agents._Static_Agent_Auto,
    }
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "rag",
        "nodes": {
            "rag": {
                "type": "RAG_Agent",
                "prev": -1,
                "query": "lithium mania quetiapine",
                "corpus_address": corpus_address,
                "top_k": 2,
                "next": "rerank",
            },
            "rerank": {
                "type": "Reranker_Agent",
                "prev": "rag",
                "top_k": 1,
                "next": -1,
            },
        },
    }

    fake_llm.queue('```json\n{"ranking": [0]}\n```')

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run()

    rag_ids = agents._extract_seen_ids(result.node_outputs["rag"])
    reranked_ids = agents._extract_seen_ids(result.output)

    assert len(rag_ids) == 2  # RAG_Agent found two chunks for this query
    assert len(reranked_ids) == 1  # reranker kept only the top_k=1 it was asked for
    assert reranked_ids <= rag_ids  # and it's genuinely one rag found, not invented
    assert len(fake_llm.calls) == 1  # only the reranker calls the LLM -- RAG_Agent doesn't


async def test_static_barrier_agent_routes_by_its_action_key():
    """Static_Barrier_Agent never calls the LLM; its dict result routes via the
    'action' key per the route-extraction rule in contract.md §5.
    """
    registry = {
        "Static_Barrier_Agent": safety_agents.Static_Barrier_Agent,
        "Static_Agent": agents.Static_Agent,
        "_Static_Agent_Auto": agents._Static_Agent_Auto,
    }
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "screen",
        "nodes": {
            "screen": {
                "type": "Static_Barrier_Agent",
                "prev": -1,
                "query": "I want to kill myself",
                "routes": {
                    "reject": "declined",
                    "safe": "declined",
                    "escalate": "declined",
                    "escalate_judge": "declined",
                },
            },
            "declined": {
                "type": "Static_Agent",
                "prev": "screen",
                "message": "blocked",
                "next": -1,
            },
        },
    }

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run()

    assert result.output == "blocked"
    assert result.node_outputs["screen"]["action"] == "reject"


async def test_binary_judge_agent_no_route_preserves_resources_for_a_retry_hop(
    fake_llm, corpus_address
):
    """Binary_Judge_Agent sits between two retrieval hops. Its "no" route must hand
    the resources it just judged back to rag_2 unharmed (not the literal string
    "no"), so rag_2 can dedup against them and add a genuinely new chunk -- the
    retry-loop pattern this whole context/"route" split exists to support.
    """
    registry = {
        "RAG_Agent": agents.RAG_Agent,
        "Binary_Judge_Agent": agents.Binary_Judge_Agent,
        "Direct_Answer_Agent": agents.Direct_Answer_Agent,
        "_Static_Agent_Auto": agents._Static_Agent_Auto,
    }
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "rag_1",
        "nodes": {
            "rag_1": {
                "type": "RAG_Agent",
                "prev": -1,
                "query": "lithium mania quetiapine",
                "corpus_address": corpus_address,
                "top_k": 1,
                "next": "judge",
            },
            "judge": {
                "type": "Binary_Judge_Agent",
                "prev": "rag_1",
                "routes": {"no": "rag_2", "yes": "answer"},
            },
            "rag_2": {
                "type": "RAG_Agent",
                "prev": "judge",
                "corpus_address": corpus_address,
                "top_k": 1,
                "next": "answer",
            },
            "answer": {
                "type": "Direct_Answer_Agent",
                "prev": ["judge", "rag_2"],
                "next": -1,
            },
        },
    }

    fake_llm.queue(
        '```json\n{"sufficient": false, "reason": "only one source so far"}\n```',
        '```json\n{"answer": "grounded reply"}\n```',
    )

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run()

    assert result.output == "grounded reply"
    assert len(fake_llm.calls) == 2  # only the judge and the final answer call the LLM

    rag_1_ids = agents._extract_seen_ids(result.node_outputs["rag_1"])
    judge_ids = agents._extract_seen_ids(result.node_outputs["judge"]["context"])
    rag_2_ids = agents._extract_seen_ids(result.node_outputs["rag_2"])

    assert len(rag_1_ids) == 1
    assert judge_ids == rag_1_ids  # the judge's own context key is untouched
    assert rag_1_ids < rag_2_ids  # rag_2 kept it and added a genuinely new chunk
    assert len(rag_2_ids) == 2


async def test_neural_network_barrier_agent_runs_via_python_mapping_source():
    """embed_texts is a real Python callable, which JSON text cannot carry -- this is
    only representable when compile_pipeline is given a dict (the Mapping form), as
    documented in contract.md §10.
    """

    async def stub_embed_texts(texts, embedding_config):
        return [[1.0, 0.0] if text == "danger" else [0.0, 1.0] for text in texts]

    registry = {
        "Neural_Network_Barrier_Agent": safety_agents.Neural_Network_Barrier_Agent,
        "Static_Agent": agents.Static_Agent,
        "_Static_Agent_Auto": agents._Static_Agent_Auto,
    }
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "screen",
        "nodes": {
            "screen": {
                "type": "Neural_Network_Barrier_Agent",
                "prev": -1,
                "query": "danger",
                "embedding_config": {},
                "embed_texts": stub_embed_texts,
                "harmful_references": ["danger"],
                "routes": {"reject": "blocked", "accept": "ok", "escalate": "blocked"},
            },
            "blocked": {"type": "Static_Agent", "prev": "screen", "message": "blocked", "next": -1},
            "ok": {"type": "Static_Agent", "prev": "screen", "message": "ok", "next": -1},
        },
    }

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run()

    assert result.output == "blocked"
