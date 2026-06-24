import os
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_openai_key():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


# ── PreProcessingPipeline (real OpenAI) ───────────────────────────────────────

async def test_pipeline_returns_list_of_strings(mock_pipeline):
    result = await mock_pipeline.run()
    assert isinstance(result, list)
    assert all(isinstance(p, str) for p in result)


async def test_pipeline_returns_non_empty_selection(mock_pipeline):
    result = await mock_pipeline.run()
    assert len(result) > 0


async def test_pipeline_returns_valid_paths_in_tree(mock_pipeline):
    result = await mock_pipeline.run()
    valid_prefixes = ("src/data/", "src/models/")
    for path in result:
        assert any(path.startswith(p) for p in valid_prefixes), (
            f"Returned path '{path}' is not within the known directory tree"
        )


async def test_pipeline_does_not_return_duplicates(mock_pipeline):
    result = await mock_pipeline.run()
    assert len(result) == len(set(result))
