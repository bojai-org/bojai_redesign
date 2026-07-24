import pytest

from base_classes import Agent, MAX_TRIES


class DummyAgent(Agent):
    """Minimal concrete Agent for exercising the shared base-class logic."""

    def __init__(self, query="q", context="ctx", role="role", extra: dict | None = None):
        super().__init__(query, context, role)
        self.extra = extra or {}

    def pre(self) -> dict:
        return dict(self.extra)

    def specify_output(self) -> str:
        return "plain text"

    def post(self, response: str) -> str:
        if response == "bad":
            raise ValueError("bad response")
        return response.strip()

    def post_fallback(self, response: str) -> str:
        return "fallback"


def test_init_stores_query_context_role():
    agent = DummyAgent(query="q1", context="c1", role="r1")
    assert agent.query == "q1"
    assert agent.context == "c1"
    assert agent.role == "r1"


def test_prompt_config_contains_role_query_context():
    agent = DummyAgent(query="q1", context="c1", role="r1")
    assert agent._prompt_config() == {"role": "r1", "query": "q1", "context": "c1"}


def test_build_prompt_includes_pre_and_output_fields():
    agent = DummyAgent(query="q1", context="c1", role="r1", extra={"resources": "some resources"})
    rendered = agent.build_prompt().render()
    assert "q1" in rendered
    assert "c1" in rendered
    assert "r1" in rendered
    assert "some resources" in rendered
    assert "plain text" in rendered  # from specify_output()


def test_build_prompt_skips_name_key():
    class NamedAgent(DummyAgent):
        def pre(self):
            return {"name": "should-not-appear", "note": "should-appear"}

    prompt = NamedAgent().build_prompt()
    assert prompt.find("name") is None
    assert prompt.find("note") is not None


async def test_run_success_first_try(fake_llm, agent_config):
    fake_llm.queue("hello ")
    result = await DummyAgent().run(agent_config)
    assert result == "hello"
    assert len(fake_llm.calls) == 1


async def test_run_retries_then_succeeds(fake_llm, agent_config):
    fake_llm.queue("bad", "good")
    result = await DummyAgent().run(agent_config)
    assert result == "good"
    assert len(fake_llm.calls) == 2
    assert "error" not in fake_llm.calls[0]
    assert "bad response" in fake_llm.calls[1]["error"]


async def test_run_exhausts_retries_raises(fake_llm, agent_config):
    fake_llm.queue("bad", "bad", "bad")
    with pytest.raises(ValueError, match="Maximum retries"):
        await DummyAgent().run(agent_config)
    assert len(fake_llm.calls) == MAX_TRIES


async def test_run_pops_stale_error_before_starting(fake_llm, agent_config):
    agent_config["error"] = "stale error from a previous run"
    fake_llm.queue("clean response")
    await DummyAgent().run(agent_config)
    assert "error" not in fake_llm.calls[0]


def test_find_json_fenced_block():
    result = DummyAgent()._find_json('Here is json:\n```json\n{"a": 1}\n```\nend')
    assert result == {"a": 1}


def test_find_json_bare_object():
    assert DummyAgent()._find_json('{"a": 1}') == {"a": 1}


def test_find_json_embedded_in_text():
    assert DummyAgent()._find_json('The answer is {"a": 1} okay?') == {"a": 1}


def test_find_json_no_json_raises():
    with pytest.raises(ValueError, match="No valid JSON"):
        DummyAgent()._find_json("no json here")
