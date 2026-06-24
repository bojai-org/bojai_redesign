import pytest
import json
from unittest.mock import AsyncMock
from build.base_classes import Agent, Pipeline
from build.prompt import PromptComposite, PromptLeaf


# ── Minimal concrete subclass for testing abstract Agent ──────────────────────

class SimpleAgent(Agent):
    def process_response(self, response: str):
        return json.loads(response)


# ── _find_json ────────────────────────────────────────────────────────────────

class TestFindJson:
    def setup_method(self):
        self.agent = SimpleAgent({"name": "t", "model": "x", "provider": "openai"})

    def test_parses_json_code_block(self):
        assert self.agent._find_json('```json\n{"k": 1}\n```') == {"k": 1}

    def test_parses_bare_code_block(self):
        assert self.agent._find_json('```\n{"k": 1}\n```') == {"k": 1}

    def test_parses_raw_json_object(self):
        assert self.agent._find_json('{"a": 1}') == {"a": 1}

    def test_parses_raw_json_array(self):
        assert self.agent._find_json('["x", "y"]') == ["x", "y"]

    def test_parses_json_embedded_in_prose(self):
        result = self.agent._find_json('Here you go: {"files": ["a.csv"]} done.')
        assert result == {"files": ["a.csv"]}

    def test_raises_for_plain_text(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            self.agent._find_json("nothing useful here")

    def test_raises_for_empty_string(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            self.agent._find_json("")


# ── _confirm_paths ────────────────────────────────────────────────────────────

class TestConfirmPaths:
    def setup_method(self):
        self.agent = SimpleAgent({"name": "t", "model": "x", "provider": "openai"})
        self.tree = {
            "src": {
                "data": {"train.csv": {}, "test.csv": {}},
                "model.py": {},
            }
        }

    def test_accepts_valid_single_path(self):
        self.agent._confirm_paths(["src/data/train.csv"], self.tree)

    def test_accepts_multiple_valid_paths(self):
        self.agent._confirm_paths(["src/data/train.csv", "src/model.py"], self.tree)

    def test_raises_for_missing_file(self):
        with pytest.raises(ValueError, match="Missing component"):
            self.agent._confirm_paths(["src/data/missing.csv"], self.tree)

    def test_raises_for_wrong_root(self):
        with pytest.raises(ValueError, match="Missing component"):
            self.agent._confirm_paths(["wrong/path.csv"], self.tree)

    def test_raises_when_descending_past_a_file(self):
        tree = {"src": {"model.py": "file"}}
        with pytest.raises(ValueError, match="inside a file"):
            self.agent._confirm_paths(["src/model.py/extra"], tree)

    def test_raises_for_non_list_input(self):
        with pytest.raises(TypeError, match="list"):
            self.agent._confirm_paths("src/data/train.csv", self.tree)

    def test_raises_for_non_string_path_in_list(self):
        with pytest.raises(TypeError, match="string"):
            self.agent._confirm_paths([123], self.tree)


# ── build_prompt ──────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def setup_method(self):
        self.agent = SimpleAgent({"name": "data_choice", "model": "x", "provider": "openai"})

    def test_returns_prompt_composite(self):
        assert isinstance(self.agent.build_prompt({"name": "data_choice"}), PromptComposite)

    def test_sections_from_json_are_added(self):
        result = self.agent.build_prompt({"name": "data_choice"})
        assert result.find("intro") is not None
        assert result.find("task") is not None

    def test_name_field_not_added_as_node(self):
        result = self.agent.build_prompt({"name": "data_choice"})
        assert result.find("name") is None

    def test_extra_field_prepended_before_sections(self):
        result = self.agent.build_prompt({"name": "data_choice", "context": "hello"})
        assert result.components[0].id == "context"

    def test_extra_field_value_is_rendered_text(self):
        result = self.agent.build_prompt({"name": "data_choice", "context": "my context"})
        assert result.find("context").render() == "my context"

    def test_multiple_extra_fields_all_prepended(self):
        result = self.agent.build_prompt({"name": "data_choice", "a": "1", "b": "2"})
        ids = [c.id for c in result.components]
        assert "a" in ids and "b" in ids
        assert ids.index("a") < ids.index("intro")
        assert ids.index("b") < ids.index("intro")


# ── Agent.run ─────────────────────────────────────────────────────────────────

class TestAgentRun:
    @pytest.fixture
    def agent(self, llm_config):
        return SimpleAgent(llm_config)

    async def test_returns_processed_response(self, agent, mock_ask_llm):
        mock_ask_llm.return_value = '{"ok": true}'
        result = await agent.run()
        assert result == {"ok": True}

    async def test_retries_on_bad_response(self, agent, mock_ask_llm):
        mock_ask_llm.side_effect = ['not json', '{"ok": true}']
        result = await agent.run()
        assert result == {"ok": True}
        assert mock_ask_llm.call_count == 2

    async def test_raises_after_max_retries(self, agent, mock_ask_llm):
        mock_ask_llm.return_value = "not json at all"
        with pytest.raises(ValueError, match="Maximum retries"):
            await agent.run()

    async def test_sets_error_on_config_after_failed_attempt(self, agent, mock_ask_llm):
        responses = iter(["bad", '{"ok": true}'])
        mock_ask_llm.side_effect = lambda cfg: responses.__next__()

        # Capture error mid-flight via side effect
        captured_error = {}

        original_side_effect = mock_ask_llm.side_effect
        call_count = 0

        async def tracking_llm(cfg):
            nonlocal call_count
            call_count += 1
            val = next(iter(["bad", '{"ok": true}'][call_count - 1:call_count]))
            if call_count == 2:
                captured_error["error"] = cfg.get("error")
            return val

        mock_ask_llm.side_effect = tracking_llm
        await agent.run()
        assert captured_error["error"] is not None

    async def test_clears_stale_error_at_start(self, agent, mock_ask_llm):
        agent.LLM_config["error"] = "stale"
        mock_ask_llm.return_value = '{"x": 1}'
        await agent.run()
        assert "error" not in agent.LLM_config


# ── Pipeline abstract ─────────────────────────────────────────────────────────

class TestPipeline:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Pipeline({"name": "t"})
