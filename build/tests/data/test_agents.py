import pytest
import json
from unittest.mock import patch
from build.agents import FileChoiceAgent, DecisionAgent, CodeExtractionAgent

pytestmark = pytest.mark.data


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config(llm_config):
    return llm_config


# ── ChoiceAgent._build_directory_tree ─────────────────────────────────────────

class TestBuildDirectoryTree:
    def test_single_item(self, config):
        agent = FileChoiceAgent("t", ["src.data"], config)
        assert agent.dir_tree == {"src": {"data": {}}}

    def test_shared_prefix_merged(self, config):
        agent = FileChoiceAgent("t", ["src.data", "src.models"], config)
        assert agent.dir_tree == {"src": {"data": {}, "models": {}}}

    def test_nested_path(self, config):
        agent = FileChoiceAgent("t", ["a.b.c"], config)
        assert agent.dir_tree == {"a": {"b": {"c": {}}}}

    def test_empty_address(self, config):
        agent = FileChoiceAgent("t", [], config)
        assert agent.dir_tree == {}


# ── DataChoiceAgent.process_response ─────────────────────────────────────────

class TestDataChoiceAgentProcessResponse:
    @pytest.fixture
    def agent(self, config, dir_tree):
        a = FileChoiceAgent("t", [], config)
        a.dir_tree = dir_tree  # inject compatible tree directly
        return a

    def test_returns_valid_paths(self, agent):
        response = '["src/data/train.csv"]'
        assert agent.process_response(response) == ["src/data/train.csv"]

    def test_returns_multiple_paths(self, agent):
        response = '["src/data/train.csv", "src/data/test.csv"]'
        result = agent.process_response(response)
        assert set(result) == {"src/data/train.csv", "src/data/test.csv"}

    def test_raises_for_path_not_in_tree(self, agent):
        with pytest.raises(ValueError, match="Missing component"):
            agent.process_response('["src/data/unknown.csv"]')

    def test_raises_for_invalid_json(self, agent):
        with pytest.raises(ValueError, match="No valid JSON"):
            agent.process_response("not json")

    def test_raises_for_non_list_json(self, agent):
        with pytest.raises(TypeError):
            agent.process_response('{"file": "src/data/train.csv"}')


# ── DecisionAgent._process_confirmation ──────────────────────────────────────

class TestDecisionAgentProcessConfirmation:
    @pytest.fixture
    def agent(self, config, dir_tree):
        a = DecisionAgent("t", [], dir_tree, config)
        return a

    def test_returns_only_kept_paths(self, agent):
        confirmation = {"src/data/train.csv": True, "src/data/test.csv": False}
        result = agent._process_confirmation(confirmation)
        assert result == ["src/data/train.csv"]

    def test_returns_empty_when_all_rejected(self, agent):
        confirmation = {"src/data/train.csv": False, "src/data/test.csv": False}
        assert agent._process_confirmation(confirmation) == []

    def test_returns_all_when_all_kept(self, agent):
        confirmation = {"src/data/train.csv": True, "src/data/test.csv": True}
        result = agent._process_confirmation(confirmation)
        assert set(result) == {"src/data/train.csv", "src/data/test.csv"}

    def test_raises_for_non_bool_keep_value(self, agent):
        with pytest.raises(TypeError, match="boolean"):
            agent._process_confirmation({"src/data/train.csv": 1})

    def test_raises_for_path_not_in_tree(self, agent):
        with pytest.raises(ValueError, match="Missing component"):
            agent._process_confirmation({"src/data/ghost.csv": True})

    def test_process_response_parses_json_first(self, agent):
        response = '{"src/data/train.csv": true, "src/data/test.csv": false}'
        result = agent.process_response(response)
        assert result == ["src/data/train.csv"]


# ── CodeExtractionAgent.process_response ─────────────────────────────────────

VALID_CODE = json.dumps({"code": "def build(data):\n    return data"})
NO_BUILD   = json.dumps({"code": "def process(data):\n    return data"})
FORBIDDEN  = json.dumps({"code": "def build(data):\n    exec('evil')\n    return data"})
BAD_IMPORT = json.dumps({"code": "import os\ndef build(data):\n    return data"})
LONG_CODE  = "def build(data):\n    return data"


class TestCodeExtractionAgentProcessResponse:
    @pytest.fixture
    def agent(self, config):
        return CodeExtractionAgent("code_extraction", LONG_CODE, config)

    def test_returns_sanitized_source_string(self, agent):
        result = agent.process_response(VALID_CODE)
        assert isinstance(result, str)
        assert "def build" in result

    def test_raises_when_no_build_function(self, agent):
        with pytest.raises(ValueError, match="build"):
            agent.process_response(NO_BUILD)

    def test_raises_for_forbidden_call(self, agent):
        with pytest.raises(ValueError, match="Forbidden"):
            agent.process_response(FORBIDDEN)

    def test_raises_for_disallowed_import(self, agent):
        with pytest.raises(ValueError, match="not allowed"):
            agent.process_response(BAD_IMPORT)

    def test_raises_when_code_field_missing(self, agent):
        with pytest.raises(TypeError, match="string"):
            agent.process_response('{"not_code": "def build(data): return data"}')

    def test_raises_when_code_is_not_a_string(self, agent):
        with pytest.raises(TypeError, match="string"):
            agent.process_response(json.dumps({"code": 42}))

    def test_strips_top_level_code_outside_build(self, agent):
        code = json.dumps({"code": "x = 1\ndef build(data):\n    return data\ny = 2"})
        result = agent.process_response(code)
        assert "x = 1" not in result
        assert "y = 2" not in result

    def test_prompt_config_includes_long_code(self, agent):
        cfg = agent._prompt_config()
        assert cfg["long_code"] == LONG_CODE
        assert cfg["name"] == "code_extraction"
