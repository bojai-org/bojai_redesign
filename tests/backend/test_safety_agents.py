import pytest

import safety_agents as sa


def make_embed():
    async def embed_texts(texts, embedding_config):
        return [[float(len(t)), float(t.count(" "))] for t in texts]
    return embed_texts


# ─────────────────────────────────────────────────────────────────────────────
# cosine_similarity
# ─────────────────────────────────────────────────────────────────────────────

def test_cosine_similarity_identical_vectors_is_one():
    assert sa.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert sa.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_returns_zero():
    assert sa.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_similarity_mismatched_shapes_raises():
    with pytest.raises(ValueError):
        sa.cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Static_Barrier_Agent
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "I want to kill myself",
        "I'm going to end it all",
        "I want to hurt someone else",
    ],
)
async def test_static_barrier_rejects_crisis_language(query):
    result = await sa.Static_Barrier_Agent(query).run({})
    assert result["action"] == "reject"
    assert result["answer"] == sa.INPUT_DECLINE_MESSAGE
    assert result["layer"] == 1


async def test_static_barrier_safe_for_benign_query():
    result = await sa.Static_Barrier_Agent("What's a good breakfast?").run({})
    assert result["action"] == "safe"


async def test_static_barrier_escalates_medication_question():
    result = await sa.Static_Barrier_Agent("Should I stop taking my lithium?").run({})
    assert result["action"] == "escalate"


@pytest.mark.parametrize(
    "query",
    [
        "Can I drink alcohol with my lithium?",
        "Can I mix cocaine with anything?",
    ],
)
async def test_static_barrier_escalates_substance_use_questions(query):
    result = await sa.Static_Barrier_Agent(query).run({})
    assert result["action"] == "escalate"


async def test_static_barrier_escalates_to_judge_for_mania_signals():
    result = await sa.Static_Barrier_Agent("I don't need to sleep anymore").run({})
    assert result["action"] == "escalate_judge"


def test_static_barrier_post_ignores_input_and_rescreens_query():
    agent = sa.Static_Barrier_Agent("I want to kill myself")
    assert agent.post("irrelevant")["action"] == "reject"
    assert agent.post_fallback("irrelevant")["action"] == "reject"


def test_static_barrier_default_context():
    assert sa.Static_Barrier_Agent("q").context == sa.DEFAULT_BARRIER_CONTEXT


async def test_static_barrier_result_carries_its_own_context_through():
    """A barrier's result must carry its incoming context under "context" -- if it
    didn't, Pipeline._resolve_context would forward str(this_dict) as the next
    node's context instead of the actual text being screened, for any pipeline
    that places a barrier mid-chain rather than only at the entrypoint.
    """
    agent = sa.Static_Barrier_Agent("I want to kill myself", context="upstream text")
    result = await agent.run({})
    assert result["context"] == "upstream text"


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: Neural_Network_Barrier_Agent
# ─────────────────────────────────────────────────────────────────────────────

async def test_nn_barrier_rejects_high_similarity():
    async def embed_texts(texts, embedding_config):
        return [[1.0, 0.0]] * len(texts)

    result = await sa.Neural_Network_Barrier_Agent("q", {}, embed_texts).run({})
    assert result["action"] == "reject"
    assert result["score"] == pytest.approx(1.0)


async def test_nn_barrier_accepts_low_similarity():
    async def embed_texts(texts, embedding_config):
        query_vec = [1.0, 0.0]
        ref_vecs = [[0.0, 1.0]] * len(sa.NN_HARMFUL_REFERENCES)
        return [query_vec] + ref_vecs

    result = await sa.Neural_Network_Barrier_Agent("q", {}, embed_texts).run({})
    assert result["action"] == "accept"


async def test_nn_barrier_escalates_mid_range_similarity():
    async def embed_texts(texts, embedding_config):
        query_vec = [1.0, 0.0]
        ref_vecs = [[0.8, 0.6]] * len(sa.NN_HARMFUL_REFERENCES)  # cos = 0.8
        return [query_vec] + ref_vecs

    result = await sa.Neural_Network_Barrier_Agent("q", {}, embed_texts).run({})
    assert result["action"] == "escalate"
    assert result["score"] == pytest.approx(0.8)


async def test_nn_barrier_run_fails_open_to_escalate_on_embedder_error():
    async def broken_embed(texts, embedding_config):
        raise RuntimeError("embedding service down")

    result = await sa.Neural_Network_Barrier_Agent("q", {}, broken_embed).run({})
    assert result["action"] == "escalate"
    assert result["layer"] == 2


async def test_nn_barrier_run_escalates_on_wrong_embedding_count():
    async def bad_embed(texts, embedding_config):
        return [[1.0, 0.0]]  # too few for query + references

    result = await sa.Neural_Network_Barrier_Agent("q", {}, bad_embed).run({})
    assert result["action"] == "escalate"


def test_nn_barrier_rejects_non_callable_embed_texts():
    with pytest.raises(TypeError):
        sa.Neural_Network_Barrier_Agent("q", {}, "not callable")


def test_nn_barrier_rejects_invalid_threshold_ordering():
    with pytest.raises(ValueError):
        sa.Neural_Network_Barrier_Agent(
            "q", {}, make_embed(), reject_threshold=0.5, escalate_threshold=0.9
        )


def test_nn_barrier_post_fallback_fails_closed_to_escalate():
    agent = sa.Neural_Network_Barrier_Agent("q", {}, make_embed())
    result = agent.post_fallback("not-a-number")
    assert result["action"] == "escalate"
    assert result["score"] is None


async def test_nn_barrier_result_carries_its_own_context_through():
    async def embed_texts(texts, embedding_config):
        return [[1.0, 0.0]] * len(texts)

    agent = sa.Neural_Network_Barrier_Agent("q", {}, embed_texts, context="upstream text")
    result = await agent.run({})
    assert result["context"] == "upstream text"


def test_nn_barrier_post_out_of_range_score_raises():
    agent = sa.Neural_Network_Barrier_Agent("q", {}, make_embed())
    with pytest.raises(ValueError):
        agent.post("1.5")


def test_validate_embeddings_rejects_nan():
    agent = sa.Neural_Network_Barrier_Agent("q", {}, make_embed())
    with pytest.raises(ValueError):
        agent._validate_embeddings([[float("nan"), 0.0]], expected_count=1)


def test_validate_embeddings_rejects_mismatched_dimensions():
    agent = sa.Neural_Network_Barrier_Agent("q", {}, make_embed())
    with pytest.raises(ValueError):
        agent._validate_embeddings([[1.0, 0.0], [1.0, 0.0, 0.0]], expected_count=2)


def test_validate_embeddings_rejects_wrong_count():
    agent = sa.Neural_Network_Barrier_Agent("q", {}, make_embed())
    with pytest.raises(ValueError):
        agent._validate_embeddings([[1.0, 0.0]], expected_count=2)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3: Judge_Barrier_Agent
# ─────────────────────────────────────────────────────────────────────────────

def test_judge_barrier_pre_includes_context():
    agent = sa.Judge_Barrier_Agent("is this ok?", context="custom context")
    assert agent.pre() == {"request": "is this ok?", "context": "custom context"}


def test_judge_barrier_post_harmful_true():
    agent = sa.Judge_Barrier_Agent("q")
    result = agent.post('```json\n{"harmful": true, "reason": "explicit crisis content"}\n```')
    assert result["action"] == "harmful"
    assert result["answer"] == sa.INPUT_DECLINE_MESSAGE
    assert result["reason"] == "explicit crisis content"


def test_judge_barrier_post_harmful_false():
    agent = sa.Judge_Barrier_Agent("q")
    result = agent.post('```json\n{"harmful": false, "reason": "benign"}\n```')
    assert result["action"] == "safe"
    assert result["answer"] is None


def test_judge_barrier_post_wrong_harmful_type_raises():
    agent = sa.Judge_Barrier_Agent("q")
    with pytest.raises(TypeError):
        agent.post('```json\n{"harmful": "yes", "reason": "x"}\n```')


def test_judge_barrier_post_empty_reason_raises():
    agent = sa.Judge_Barrier_Agent("q")
    with pytest.raises(ValueError):
        agent.post('```json\n{"harmful": false, "reason": "   "}\n```')


def test_judge_barrier_post_fallback_fails_closed():
    result = sa.Judge_Barrier_Agent("q").post_fallback("some garbage text")
    assert result["action"] == "harmful"
    assert result["answer"] == sa.INPUT_DECLINE_MESSAGE


def test_judge_barrier_result_carries_its_own_context_through():
    agent = sa.Judge_Barrier_Agent("q", context="upstream text")
    result = agent.post('```json\n{"harmful": false, "reason": "benign"}\n```')
    assert result["context"] == "upstream text"


async def test_judge_barrier_run_success(fake_llm, agent_config):
    fake_llm.queue('```json\n{"harmful": false, "reason": "benign question"}\n```')
    result = await sa.Judge_Barrier_Agent("Is it normal to feel tired?").run(agent_config)
    assert result["action"] == "safe"


async def test_judge_barrier_run_exhausts_retries_fails_closed(fake_llm, agent_config):
    fake_llm.queue("garbage", "garbage", "garbage")
    result = await sa.Judge_Barrier_Agent("ambiguous").run(agent_config)
    assert result["action"] == "harmful"
    assert "failed closed" in result["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# Input_Barrier_Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_pipeline_stores_config():
    pipeline = sa.Input_Barrier_Pipeline("q", {"foo": "bar"}, make_embed(), context="custom")
    assert pipeline.query == "q"
    assert pipeline.context == "custom"
    assert pipeline.embedding_config == {"foo": "bar"}


async def test_pipeline_safe_path_short_circuits_at_layer1(fake_llm, agent_config):
    pipeline = sa.Input_Barrier_Pipeline("What's a good breakfast?", {}, make_embed())
    result = await pipeline.run(agent_config)
    assert result["action"] == "safe"
    assert result["layer"] == 1
    assert fake_llm.calls == []


async def test_pipeline_reject_path_short_circuits_at_layer1(fake_llm, agent_config):
    pipeline = sa.Input_Barrier_Pipeline("I want to kill myself", {}, make_embed())
    result = await pipeline.run(agent_config)
    assert result["action"] == "reject"
    assert result["layer"] == 1


async def test_pipeline_escalate_layer1_accept_layer2_short_circuits(fake_llm, agent_config):
    async def embed_texts(texts, embedding_config):
        query_vec = [0.0, 1.0]
        ref_vecs = [[1.0, 0.0]] * len(sa.NN_HARMFUL_REFERENCES)
        return [query_vec] + ref_vecs

    pipeline = sa.Input_Barrier_Pipeline("Should I stop taking my lithium?", {}, embed_texts)
    result = await pipeline.run(agent_config)
    assert result["action"] == "accept"
    assert result["layer"] == 2
    assert fake_llm.calls == []


async def test_pipeline_escalate_layer1_escalate_layer2_reaches_judge(fake_llm, agent_config):
    async def embed_texts(texts, embedding_config):
        query_vec = [1.0, 0.0]
        ref_vecs = [[0.8, 0.6]] * len(sa.NN_HARMFUL_REFERENCES)
        return [query_vec] + ref_vecs

    fake_llm.queue('```json\n{"harmful": true, "reason": "substance use + meds risk"}\n```')
    pipeline = sa.Input_Barrier_Pipeline("Should I stop taking my lithium?", {}, embed_texts)
    result = await pipeline.run(agent_config)
    assert result["action"] == "harmful"
    assert result["layer"] == 3


async def test_pipeline_escalate_judge_from_layer1_skips_layer2(fake_llm, agent_config):
    fake_llm.queue('```json\n{"harmful": false, "reason": "not actually psychosis"}\n```')
    pipeline = sa.Input_Barrier_Pipeline("I don't need to sleep anymore", {}, make_embed())
    result = await pipeline.run(agent_config)
    assert result["action"] == "safe"
    assert result["layer"] == 3
