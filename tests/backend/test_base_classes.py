import pytest

from base_classes import Agent, MAX_TRIES


class DummyAgent(Agent):
    """Minimal concrete Agent for exercising the shared base-class logic."""

    def __init__(self, query="q", state: dict | None = None, role="role", extra: dict | None = None):
        super().__init__(query, state, role)
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


def test_init_stores_query_state_role():
    agent = DummyAgent(query="q1", state={"context": "c1"}, role="r1")
    assert agent.query == "q1"
    assert agent.state == {"context": "c1"}
    assert agent.role == "r1"


def test_init_defaults_state_to_empty_dict_when_none():
    agent = DummyAgent(query="q1", role="r1")
    assert agent.state == {}


def test_prompt_config_contains_role_and_query_only():
    """Shared state is no longer blindly stuffed into every prompt -- only
    role/query are universal; a namespaced state key only appears in the
    prompt if an agent's own pre() explicitly puts it there (see below)."""
    agent = DummyAgent(query="q1", state={"context": "c1"}, role="r1")
    assert agent._prompt_config() == {"role": "r1", "query": "q1"}


def test_build_prompt_includes_pre_and_output_fields():
    agent = DummyAgent(query="q1", role="r1", extra={"resources": "some resources"})
    rendered = agent.build_prompt().render()
    assert "q1" in rendered
    assert "r1" in rendered
    assert "some resources" in rendered
    assert "plain text" in rendered  # from specify_output()


def test_build_prompt_does_not_auto_insert_shared_state():
    """A raw state value never leaks into the prompt on its own -- an agent
    that wants it there must return it from pre() explicitly (see below)."""
    agent = DummyAgent(query="q1", state={"context": "should not leak into the prompt"}, role="r1")
    rendered = agent.build_prompt().render()
    assert "should not leak into the prompt" not in rendered


def test_build_prompt_includes_state_key_when_pre_inserts_it():
    """This is "you insert into the prompt context when necessary": pre() reads
    whatever key(s) of self.state it needs and returns them explicitly."""
    agent = DummyAgent(query="q1", state={"context": "c1"}, role="r1", extra={"context": "c1"})
    rendered = agent.build_prompt().render()
    assert "c1" in rendered


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
