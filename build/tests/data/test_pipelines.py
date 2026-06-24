import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from build.data.pipelines import PreProcessingPipeline, PostProcessingPipeline
from architecture.data.pre_processor import InitialData

pytestmark = pytest.mark.data



# ── PreProcessingPipeline ─────────────────────────────────────────────────────

class TestPreProcessingPipeline:
    @pytest.fixture
    def pipeline(self, llm_config):
        return PreProcessingPipeline(["src.data"], llm_config)

    async def test_run_returns_confirmed_files(self, pipeline):
        selected = ["src/data/train.csv"]
        confirmed = ["src/data/train.csv"]

        with patch("build.data.pipelines.DataChoiceAgent") as MockChoice, \
             patch("build.data.pipelines.DecisionAgent") as MockDecision:

            MockChoice.return_value.run = AsyncMock(return_value=selected)
            MockChoice.return_value.dir_tree = {"src": {"data": {"train.csv": {}}}}
            MockDecision.return_value.run = AsyncMock(return_value=confirmed)

            result = await pipeline.run()

        assert result == confirmed

    async def test_run_passes_dir_tree_to_decision_agent(self, pipeline):
        tree = {"src": {"data": {"train.csv": {}}}}

        with patch("build.data.pipelines.DataChoiceAgent") as MockChoice, \
             patch("build.data.pipelines.DecisionAgent") as MockDecision:

            MockChoice.return_value.run = AsyncMock(return_value=["src/data/train.csv"])
            MockChoice.return_value.dir_tree = tree
            MockDecision.return_value.run = AsyncMock(return_value=["src/data/train.csv"])

            await pipeline.run()

            _, kwargs = MockDecision.call_args
            call_args = MockDecision.call_args[0]
            # dir_tree is the 3rd positional arg: (name, files, dir_tree, config)
            assert call_args[2] == tree

    async def test_run_returns_empty_when_all_rejected(self, pipeline):
        with patch("build.data.pipelines.DataChoiceAgent") as MockChoice, \
             patch("build.data.pipelines.DecisionAgent") as MockDecision:

            MockChoice.return_value.run = AsyncMock(return_value=["src/data/train.csv"])
            MockChoice.return_value.dir_tree = {}
            MockDecision.return_value.run = AsyncMock(return_value=[])

            result = await pipeline.run()

        assert result == []


# ── PostProcessingPipeline._data_from_code ────────────────────────────────────

class TestDataFromCode:
    @pytest.fixture
    def pipeline(self, llm_config):
        return PostProcessingPipeline(raw_data=[1, 2, 3], pipeline_address=[], LLM_config=llm_config)

    def test_returns_initial_data_instance(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"input": [1, 2], "output": [3, 4]}):
            result = pipeline._data_from_code("def build(d): ...")
        assert isinstance(result, InitialData)

    def test_result_is_initialized(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"input": [1, 2]}):
            result = pipeline._data_from_code("def build(d): ...")
        assert result.initialized is True

    def test_input_is_set_from_result(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"input": [10, 20]}):
            result = pipeline._data_from_code("def build(d): ...")
        assert result.input == [10, 20]

    def test_output_is_set_when_provided(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"input": [1], "output": [2]}):
            result = pipeline._data_from_code("def build(d): ...")
        assert result.output == [2]

    def test_output_is_none_when_not_provided(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"input": [1]}):
            result = pipeline._data_from_code("def build(d): ...")
        assert result.output is None

    def test_raises_when_input_missing_from_result(self, pipeline):
        with patch.object(pipeline, "run_code", return_value={"output": [1]}):
            with pytest.raises(ValueError, match="input"):
                pipeline._data_from_code("def build(d): ...")

    def test_passes_raw_data_to_run_code(self, pipeline):
        mock_run = MagicMock(return_value={"input": []})
        with patch.object(pipeline, "run_code", mock_run):
            pipeline._data_from_code("def build(d): ...")
        mock_run.assert_called_once_with("def build(d): ...", [1, 2, 3])


# ── PostProcessingPipeline.run ────────────────────────────────────────────────

class TestPostProcessingPipelineRun:
    @pytest.fixture
    def pipeline(self, llm_config):
        return PostProcessingPipeline(raw_data=[1, 2], pipeline_address=["src.code"], LLM_config=llm_config)

    def _make_decision_mocks(self, file_result, validation_result):
        """Return two DecisionAgent mock instances for sequential side_effect."""
        m1 = MagicMock()
        m1.run = AsyncMock(return_value=file_result)
        m2 = MagicMock()
        m2.run = AsyncMock(return_value=validation_result)
        return [m1, m2]

    async def test_run_returns_initial_data(self, pipeline):
        sanitized_code = "def build(data):\n    return data"
        tree = {"src": {"code": {}}}
        decision_mocks = self._make_decision_mocks(
            ["src/code/processor.py"], [sanitized_code]
        )

        with patch("build.data.pipelines.DataChoiceAgent") as MockChoice, \
             patch("build.data.pipelines.DecisionAgent") as MockDecision, \
             patch("build.data.pipelines.CodeExtractionAgent") as MockCode, \
             patch("builtins.open", mock_open(read_data="def build(data): return data")), \
             patch.object(pipeline, "run_code", return_value={"input": [1, 2]}):

            MockChoice.return_value.run = AsyncMock(return_value=["src/code/processor.py"])
            MockChoice.return_value.dir_tree = tree
            MockDecision.side_effect = decision_mocks
            MockCode.return_value.run = AsyncMock(return_value=sanitized_code)

            result = await pipeline.run()

        assert isinstance(result, InitialData)
        assert result.initialized is True
        assert result.input == [1, 2]

    async def test_run_raises_when_validation_fails(self, pipeline):
        sanitized_code = "def build(data):\n    return data"
        tree = {"src": {"code": {}}}
        decision_mocks = self._make_decision_mocks(
            ["src/code/processor.py"], []  # empty list → validation fails
        )

        with patch("build.data.pipelines.DataChoiceAgent") as MockChoice, \
             patch("build.data.pipelines.DecisionAgent") as MockDecision, \
             patch("build.data.pipelines.CodeExtractionAgent") as MockCode, \
             patch("builtins.open", mock_open(read_data="def build(data): return data")):

            MockChoice.return_value.run = AsyncMock(return_value=["src/code/processor.py"])
            MockChoice.return_value.dir_tree = tree
            MockDecision.side_effect = decision_mocks
            MockCode.return_value.run = AsyncMock(return_value=sanitized_code)

            with pytest.raises(ValueError, match="validation"):
                await pipeline.run()
