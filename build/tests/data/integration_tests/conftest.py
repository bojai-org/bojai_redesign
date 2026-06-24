import pytest
from build.data.pipelines import PreProcessingPipeline


@pytest.fixture
def openai_config():
    return {"model": "gpt-4o-mini", "provider": "openai"}


@pytest.fixture
def mock_pipeline(openai_config):
    """PreProcessingPipeline wired to real OpenAI with a minimal synthetic tree."""
    addresses = [
        "src.data.train.csv",
        "src.data.test.csv",
        "src.models.model.py",
    ]
    return PreProcessingPipeline(addresses, openai_config)
