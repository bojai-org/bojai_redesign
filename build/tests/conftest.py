import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def llm_config():
    return {"name": "data_choice", "model": "gpt-4", "provider": "openai"}


@pytest.fixture
def dir_tree():
    return {
        "src": {
            "data": {"train.csv": {}, "test.csv": {}},
            "model.py": {},
        }
    }


@pytest.fixture
def mock_ask_llm(monkeypatch):
    mock = AsyncMock(return_value='["src/data/train.csv"]')
    monkeypatch.setattr("build.base_classes.ask_llm", mock)
    return mock
