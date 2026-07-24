"""Shared fixtures for backend/ tests.

backend/agents.py, backend/base_classes.py, and backend/safety_agents.py import
each other with bare names (e.g. `from base_classes import Agent`), so the
backend/ directory itself has to be on sys.path in addition to the repo root
(which pytest.ini already adds via `pythonpath = .`, for the dotted imports
like `from backend.prompt import ...` used inside base_classes.py).
"""

import json
import sys
from collections import deque
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import base_classes  # noqa: E402


class FakeLLM:
    """Queue-driven stand-in for llm_config.router.ask_llm.

    Records a shallow copy of the agent_config seen on each call, since
    Agent.run() mutates the same dict in place across retries.
    """

    def __init__(self):
        self.responses = deque()
        self.calls: list[dict] = []

    def queue(self, *responses: str) -> None:
        self.responses.extend(responses)

    async def __call__(self, agent_config: dict) -> str:
        self.calls.append(dict(agent_config))
        if not self.responses:
            raise AssertionError("FakeLLM was called with no queued response left")
        return self.responses.popleft()


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch base_classes.ask_llm (the name Agent.run() actually calls)."""
    fake = FakeLLM()
    monkeypatch.setattr(base_classes, "ask_llm", fake)
    return fake


@pytest.fixture
def agent_config() -> dict:
    return {"provider": "openai", "model": "gpt-4o-mini"}


CORPUS_CHUNKS = [
    {
        "text": "Lithium is a first-line mood stabilizer for bipolar disorder.",
        "metadata": {"section": "Pharmacotherapy", "chunk_id": "c1", "url": "http://example.com/1"},
    },
    {
        "text": "Patients experiencing manic episodes often report racing thoughts and reduced need for sleep.",
        "metadata": {"section": "Mania", "chunk_id": "c2", "url": "http://example.com/2"},
    },
    {
        "text": "Cognitive behavioral therapy is a common psychotherapy approach for depression.",
        "metadata": {"section": "Psychotherapy", "chunk_id": "c3", "url": "http://example.com/3"},
    },
    {
        "text": "Quetiapine dosing for acute mania typically starts at 100mg and titrates upward.",
        "metadata": {"section": "Pharmacotherapy", "chunk_id": "c4", "url": "http://example.com/4"},
    },
]


@pytest.fixture
def corpus_address(tmp_path) -> str:
    """A polarus-shaped corpus directory: <root>/processed/guideline_db.json."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "guideline_db.json").write_text(
        json.dumps(CORPUS_CHUNKS), encoding="utf-8"
    )
    return str(tmp_path)
