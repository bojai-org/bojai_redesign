import pytest

import agents
from base_classes import Agent
from code_safety import CodeValidationError
from compiler import compile_pipeline
from new_agent_builder import AgentSpec, NewAgentBuilder, TextNewAgentBuilder, compiler as build_agent
from pipeline import PipelineRuntimeError


def _spec(**overrides) -> AgentSpec:
    base = dict(
        name="Shout_Agent",
        role="You are a shouting assistant.",
        pre="def pre(self):\n    return {'context': self.state.get('context', ''), 'request': self.query}",
        specify_output="def specify_output(self):\n    return 'plain text only'",
        post="def post(self, response):\n    return response.strip().upper()",
        post_fallback="def post_fallback(self, response):\n    return response.strip().upper()",
        writes={"answer"},
    )
    base.update(overrides)
    return AgentSpec(**base)


# ─────────────────────────────────────────────────────────────────────────────
# TextNewAgentBuilder
# ─────────────────────────────────────────────────────────────────────────────

def test_text_builder_process_all_populates_all_four_methods():
    builder = TextNewAgentBuilder(_spec())
    processed = builder.process_all()
    assert set(processed) == {"pre", "specify_output", "post", "post_fallback"}
    assert "def post(self, response):" in processed["post"]


def test_text_builder_individual_process_methods():
    builder = TextNewAgentBuilder(_spec())
    builder.process_pre()
    assert "pre" in builder.processed_code
    assert "post" not in builder.processed_code


def test_text_builder_raises_on_missing_method_source():
    builder = TextNewAgentBuilder(_spec(pre=None))
    with pytest.raises(CodeValidationError, match="No source code"):
        builder.process_pre()


def test_text_builder_raises_on_blank_method_source():
    builder = TextNewAgentBuilder(_spec(pre="   "))
    with pytest.raises(CodeValidationError, match="No source code"):
        builder.process_pre()


def test_text_builder_propagates_validator_errors():
    builder = TextNewAgentBuilder(_spec(post="def post(self, response):\n    return eval(response)"))
    with pytest.raises(CodeValidationError, match="Forbidden call"):
        builder.process_post()


def test_new_agent_builder_is_abstract():
    with pytest.raises(TypeError):
        NewAgentBuilder(_spec())


# ─────────────────────────────────────────────────────────────────────────────
# compiler()
# ─────────────────────────────────────────────────────────────────────────────

def test_compiler_returns_an_agent_subclass():
    cls = build_agent(TextNewAgentBuilder(_spec()))
    assert issubclass(cls, Agent)
    assert cls.__name__ == "Shout_Agent"
    assert cls.__module__ == "new_agent_builder"


def test_compiler_sets_writes_from_spec():
    cls = build_agent(TextNewAgentBuilder(_spec(writes={"answer"})))
    assert cls.WRITES == frozenset({"answer"})


def test_compiler_defaults_writes_to_empty_set():
    cls = build_agent(TextNewAgentBuilder(_spec(writes=set())))
    assert cls.WRITES == frozenset()


def test_compiler_built_agent_pre_specify_output_post_work():
    cls = build_agent(TextNewAgentBuilder(_spec()))
    agent = cls(query="hello", state={"context": "some context"})
    assert agent.pre() == {"context": "some context", "request": "hello"}
    assert agent.specify_output() == "plain text only"
    assert agent.post("mixed Case") == "MIXED CASE"
    assert agent.post_fallback("  bye  ") == "BYE"


def test_compiler_built_agent_defaults_query_and_state():
    cls = build_agent(TextNewAgentBuilder(_spec()))
    agent = cls()
    assert agent.query == ""
    assert agent.state == {}


async def test_compiler_built_agent_runs_end_to_end_through_fake_llm(fake_llm, agent_config):
    cls = build_agent(TextNewAgentBuilder(_spec()))
    fake_llm.queue("a grounded reply")
    agent = cls(query="q", state={"context": "ctx"})
    result = await agent.run(agent_config)
    assert result == "A GROUNDED REPLY"


def test_compiler_raises_if_a_required_method_is_missing():
    with pytest.raises(CodeValidationError, match="No source code"):
        build_agent(TextNewAgentBuilder(_spec(post_fallback=None)))


def test_compiler_rejects_forbidden_code_before_building_anything():
    bad = _spec(pre="def pre(self):\n    import os\n    return {}")
    with pytest.raises(CodeValidationError, match="Import 'os' is not allowed"):
        build_agent(TextNewAgentBuilder(bad))


def test_compiler_each_built_class_is_independent():
    cls_a = build_agent(TextNewAgentBuilder(_spec(name="A", post="def post(self, response):\n    return 'A'")))
    cls_b = build_agent(TextNewAgentBuilder(_spec(name="B", post="def post(self, response):\n    return 'B'")))
    assert cls_a("q").post("x") == "A"
    assert cls_b("q").post("x") == "B"
    assert cls_a is not cls_b


# ─────────────────────────────────────────────────────────────────────────────
# Integration with the shared-state pipeline runtime (pipeline.py)
# ─────────────────────────────────────────────────────────────────────────────

async def test_built_agent_runs_inside_a_compiled_pipeline(fake_llm):
    cls = build_agent(TextNewAgentBuilder(_spec()))
    registry = {"Shout_Agent": cls, "_Static_Agent_Auto": agents._Static_Agent_Auto}
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "shout",
        "nodes": {"shout": {"type": "Shout_Agent", "prev": -1, "next": -1}},
    }
    fake_llm.queue("a grounded reply")

    pipeline = compile_pipeline(definition, agent_registry=registry)
    result = await pipeline.run(initial_query="hi")

    assert result.output == "A GROUNDED REPLY"


async def test_built_agent_cannot_smuggle_an_undeclared_state_key(fake_llm):
    """A hand-authored agent is bound by the exact same WRITES enforcement as
    every built-in agent (see pipeline.Pipeline._collect_state_writes) --
    declaring no writes but returning a dict with a namespaced key fails the
    run instead of silently mutating shared state."""
    rogue_spec = _spec(
        name="Rogue",
        post="def post(self, response):\n    return {'context': 'smuggled in', 'route': 'done'}",
        post_fallback="def post_fallback(self, response):\n    return {'route': 'done'}",
        writes=set(),
    )
    cls = build_agent(TextNewAgentBuilder(rogue_spec))
    registry = {"Rogue": cls, "_Static_Agent_Auto": agents._Static_Agent_Auto}
    definition = {
        "config": {"provider": "test", "model": "test-model"},
        "entrypoint": "rogue",
        "nodes": {"rogue": {"type": "Rogue", "prev": -1, "next": -1}},
    }

    fake_llm.queue("irrelevant")
    pipeline = compile_pipeline(definition, agent_registry=registry)
    with pytest.raises(PipelineRuntimeError, match="not declared to write"):
        await pipeline.run(initial_query="hi")
