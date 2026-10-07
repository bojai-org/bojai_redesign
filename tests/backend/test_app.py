import asyncio
import os
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

import app as app_module
import base_classes
import embeddings
import evaluator as evaluator_module

SAFETY_DEFINITION = {
    "config": {"provider": "openai", "model": "gpt-4o-mini"},
    "entrypoint": "static_screen",
    "nodes": {
        "static_screen": {
            "type": "Static_Barrier_Agent",
            "prev": -1,
            "routes": {
                "safe": "decision",
                "reject": "decline",
                "escalate": "judge",
                "escalate_judge": "judge",
            },
        },
        "judge": {
            "type": "Judge_Barrier_Agent",
            "prev": "static_screen",
            "routes": {"harmful": "decline", "safe": "decision"},
        },
        "decision": {
            "type": "Static_Agent",
            "prev": ["static_screen", "judge"],
            "message": "proceeding",
            "next": -1,
        },
        "decline": {
            "type": "Static_Agent",
            "prev": ["static_screen", "judge"],
            "message": "blocked",
            "next": -1,
        },
    },
}

STATIC_DEFINITION = {
    "config": {"provider": "openai", "model": "gpt-4o-mini"},
    "entrypoint": "greet",
    "nodes": {
        "greet": {
            "type": "Static_Agent",
            "prev": -1,
            "message": "hello from a compiled pipeline",
            "next": -1,
        }
    },
}

ANSWER_DEFINITION = {
    "config": {"provider": "openai", "model": "gpt-4o-mini"},
    "entrypoint": "answer",
    "nodes": {
        "answer": {
            "type": "Direct_Answer_Agent",
            "prev": -1,
            "context": "some grounding context",
            "next": -1,
        }
    },
}


@pytest.fixture(autouse=True)
def _clean_pipeline_registry():
    """app.py's pipeline/job stores are module-level global state; keep tests isolated."""
    app_module._pipelines.clear()
    app_module._evaluation_jobs.clear()
    yield
    app_module._pipelines.clear()
    app_module._evaluation_jobs.clear()


@pytest.fixture(autouse=True)
def _clean_env_var_registry():
    """_managed_env_vars (and whatever it points at in os.environ) is also
    module-level global state -- undo whatever a test sets so it can't leak
    into another test or the real process environment."""
    before = set(app_module._managed_env_vars)
    yield
    for name in app_module._managed_env_vars - before:
        os.environ.pop(name, None)
    app_module._managed_env_vars.intersection_update(before)


@pytest.fixture
def client():
    # Entered as a context manager (not just constructed) so its ASGI portal's
    # event loop stays alive across separate client.get()/post() calls --
    # required for the evaluate job endpoints, whose asyncio.create_task
    # background work must keep progressing between polls (see
    # test_evaluate_*_jobs_* below). Without `with`, TestClient tears the loop
    # down after every single call and a background task never gets to run.
    with TestClient(app_module.app) as test_client:
        yield test_client


def _poll_job(client: TestClient, url: str, *, timeout: float = 5.0, interval: float = 0.02) -> dict:
    """Poll a GET .../jobs/{job_id} endpoint until it leaves the "running" state."""
    deadline = time.monotonic() + timeout
    body = {"status": "running"}
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status_code == 200
        body = response.json()
        if body["status"] != "running":
            return body
        time.sleep(interval)
    raise AssertionError(f"job at {url} did not finish within {timeout}s: last body={body}")


class _BlockingLLM:
    """Blocks every call on an asyncio.Event the test never sets, so the
    background job is provably still in flight (not just "probably done by
    now") whenever a cancel request is issued -- no wall-clock race to get
    flaky under load. Cancelling the job's task is what ends the wait; nothing
    else ever does."""

    def __init__(self):
        self.calls = 0

    async def __call__(self, agent_config: dict) -> str:
        self.calls += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable -- the blocking event is never set")


# ─────────────────────────────────────────────────────────────────────────────
# health / agents / list
# ─────────────────────────────────────────────────────────────────────────────

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_agents_matches_registry(client):
    response = client.get("/agents")
    assert response.status_code == 200
    assert response.json() == {"agent_types": sorted(app_module.AGENT_REGISTRY)}


# ─────────────────────────────────────────────────────────────────────────────
# config/env
# ─────────────────────────────────────────────────────────────────────────────

def test_set_env_var_then_list(client):
    response = client.post("/config/env", json={"name": "TEST_API_KEY", "value": "secret-123"})
    assert response.status_code == 204

    response = client.get("/config/env")
    assert response.status_code == 200
    assert response.json() == {"names": ["TEST_API_KEY"]}
    assert os.environ["TEST_API_KEY"] == "secret-123"


def test_list_env_vars_never_echoes_values(client):
    client.post("/config/env", json={"name": "TEST_API_KEY", "value": "super-secret"})
    response = client.get("/config/env")
    assert "super-secret" not in response.text


def test_set_env_var_rejects_blank_name(client):
    response = client.post("/config/env", json={"name": "   ", "value": "x"})
    assert response.status_code == 400


def test_set_env_var_twice_overwrites(client):
    client.post("/config/env", json={"name": "TEST_API_KEY", "value": "first"})
    client.post("/config/env", json={"name": "TEST_API_KEY", "value": "second"})
    assert os.environ["TEST_API_KEY"] == "second"
    assert client.get("/config/env").json() == {"names": ["TEST_API_KEY"]}


def test_delete_env_var(client):
    client.post("/config/env", json={"name": "TEST_API_KEY", "value": "secret-123"})
    response = client.delete("/config/env/TEST_API_KEY")
    assert response.status_code == 204
    assert "TEST_API_KEY" not in os.environ
    assert client.get("/config/env").json() == {"names": []}


def test_delete_unknown_env_var_404s(client):
    response = client.delete("/config/env/NOT_SET")
    assert response.status_code == 404


def test_neural_network_barrier_agent_not_exposed_over_http():
    """It needs a Python embed_texts callable, which JSON can't carry (contract.md sec 10)."""
    assert "Neural_Network_Barrier_Agent" not in app_module.AGENT_REGISTRY
    assert "Input_Barrier_Pipeline" not in app_module.AGENT_REGISTRY


def test_list_pipelines_reflects_registered_ids(client):
    assert client.get("/pipelines").json() == {"pipeline_ids": []}
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    assert client.get("/pipelines").json() == {"pipeline_ids": [pipeline_id]}


# ─────────────────────────────────────────────────────────────────────────────
# compile
# ─────────────────────────────────────────────────────────────────────────────

def test_compile_returns_summary(client):
    response = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION})
    assert response.status_code == 201
    body = response.json()
    assert body["entrypoint"] == "greet"
    assert body["node_ids"] == ["greet"]
    assert body["config"] == {"provider": "openai", "model": "gpt-4o-mini"}
    assert "_final" not in body["node_ids"]
    assert body["pipeline_id"]  # generated


def test_compile_accepts_a_caller_supplied_pipeline_id(client):
    response = client.post(
        "/pipelines/compile", json={"pipeline_id": "my-pipeline", "definition": STATIC_DEFINITION}
    )
    assert response.status_code == 201
    assert response.json()["pipeline_id"] == "my-pipeline"


def test_compile_rejects_reusing_an_existing_pipeline_id(client):
    client.post("/pipelines/compile", json={"pipeline_id": "dup", "definition": STATIC_DEFINITION})
    response = client.post("/pipelines/compile", json={"pipeline_id": "dup", "definition": STATIC_DEFINITION})
    assert response.status_code == 409


def test_compile_invalid_contract_returns_400(client):
    response = client.post("/pipelines/compile", json={"definition": {"nodes": {}}})
    assert response.status_code == 400
    assert "detail" in response.json()


def test_compile_agent_instantiation_failure_returns_400(client):
    """RAG_Agent requires corpus_address; omitting it fails at node-instantiation time,
    not at contract-shape-validation time -- both must surface as 400."""
    definition = {
        "config": {"provider": "openai", "model": "gpt-4o-mini"},
        "entrypoint": "rag",
        "nodes": {"rag": {"type": "RAG_Agent", "prev": -1, "next": -1}},
    }
    response = client.post("/pipelines/compile", json={"definition": definition})
    assert response.status_code == 400


def test_compile_unregistered_agent_type_returns_400(client):
    definition = {
        "config": {"provider": "openai", "model": "gpt-4o-mini"},
        "entrypoint": "n",
        "nodes": {"n": {"type": "Not_A_Real_Agent", "prev": -1, "next": -1}},
    }
    response = client.post("/pipelines/compile", json={"definition": definition})
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# get / update / delete
# ─────────────────────────────────────────────────────────────────────────────

def test_get_pipeline(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    response = client.get(f"/pipelines/{pipeline_id}")
    assert response.status_code == 200
    assert response.json()["pipeline_id"] == pipeline_id


def test_get_unknown_pipeline_404(client):
    assert client.get("/pipelines/does-not-exist").status_code == 404


def test_update_recompiles_in_place(client):
    pipeline_id = client.post(
        "/pipelines/compile", json={"pipeline_id": "p1", "definition": STATIC_DEFINITION}
    ).json()["pipeline_id"]

    updated_definition = {
        "config": {"provider": "openai", "model": "gpt-4o-mini"},
        "entrypoint": "greet2",
        "nodes": {
            "greet2": {
                "type": "Static_Agent",
                "prev": -1,
                "message": "updated message",
                "next": -1,
            }
        },
    }
    response = client.put(f"/pipelines/{pipeline_id}", json={"definition": updated_definition})
    assert response.status_code == 200
    assert response.json()["entrypoint"] == "greet2"

    run_response = client.post(f"/pipelines/{pipeline_id}/run", json={})
    assert run_response.json()["output"] == "updated message"


def test_update_unknown_pipeline_404(client):
    response = client.put("/pipelines/does-not-exist", json={"definition": STATIC_DEFINITION})
    assert response.status_code == 404


def test_update_invalid_definition_leaves_existing_pipeline_running(client):
    """A failed update must not corrupt the previously-compiled pipeline."""
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]

    bad_response = client.put(f"/pipelines/{pipeline_id}", json={"definition": {"nodes": {}}})
    assert bad_response.status_code == 400

    run_response = client.post(f"/pipelines/{pipeline_id}/run", json={})
    assert run_response.status_code == 200
    assert run_response.json()["output"] == "hello from a compiled pipeline"


def test_delete_pipeline(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    assert client.delete(f"/pipelines/{pipeline_id}").status_code == 204
    assert client.get(f"/pipelines/{pipeline_id}").status_code == 404


def test_delete_unknown_pipeline_404(client):
    assert client.delete("/pipelines/does-not-exist").status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# run
# ─────────────────────────────────────────────────────────────────────────────

def test_run_static_pipeline_needs_no_llm(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    response = client.post(f"/pipelines/{pipeline_id}/run", json={"query": "hi"})
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "hello from a compiled pipeline"
    assert [step["node_id"] for step in body["trace"]] == ["greet", "_final"]


def test_run_omits_trace_when_include_trace_is_false(client):
    """A large corpus makes retrieval agents' accumulated trace much bigger than
    the answer itself (see agents.py's _Retrieval_Agent) -- callers that only
    need `output` can skip paying for it."""
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    response = client.post(
        f"/pipelines/{pipeline_id}/run", json={"query": "hi", "include_trace": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "hello from a compiled pipeline"
    assert body["trace"] == []


def test_run_query_is_optional(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    response = client.post(f"/pipelines/{pipeline_id}/run", json={})
    assert response.status_code == 200


def test_run_unknown_pipeline_404(client):
    response = client.post("/pipelines/does-not-exist/run", json={"query": "hi"})
    assert response.status_code == 404


def test_run_llm_backed_pipeline(client, fake_llm):
    """fake_llm patches base_classes.ask_llm, the same module Agent.run() calls
    regardless of whether the pipeline was reached through app.py or directly."""
    fake_llm.queue("```markdown\ngrounded reply\n```")
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/run", json={"query": "what's going on?"})

    assert response.status_code == 200
    assert response.json()["output"] == "grounded reply"
    assert len(fake_llm.calls) == 1


def test_run_surfaces_llm_provider_misconfiguration_as_502(client, monkeypatch):
    async def broken_ask_llm(config):
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

    import base_classes

    monkeypatch.setattr(base_classes, "ask_llm", broken_ask_llm)
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/run", json={"query": "hi"})

    assert response.status_code == 502


def test_run_unmatched_route_returns_422(client, fake_llm):
    """Decision_Agent's LLM response picks an option neither declared route covers
    (a graph-authoring error). With only one declared route the runtime would
    fall back to it (contract.md sec 5, "the sole declared route" leniency rule),
    so this needs two declared routes for the mismatch to actually raise.
    """
    definition = {
        "config": {"provider": "openai", "model": "gpt-4o-mini"},
        "entrypoint": "decision",
        "nodes": {
            "decision": {
                "type": "Decision_Agent",
                "prev": -1,
                "options": ["a", "b", "c"],
                "a": "leaf_a",
                "b": "leaf_b",
                # "c" is a valid option but deliberately has no route target
            },
            "leaf_a": {"type": "Static_Agent", "prev": "decision", "message": "reached a", "next": -1},
            "leaf_b": {"type": "Static_Agent", "prev": "decision", "message": "reached b", "next": -1},
        },
    }
    fake_llm.queue('```json\n{"decision": "c"}\n```')
    pipeline_id = client.post("/pipelines/compile", json={"definition": definition}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/run", json={"query": "hi"})

    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# evaluate
# ─────────────────────────────────────────────────────────────────────────────


async def _fake_embed_texts(texts, embedding_config):
    return [[1.0, 0.0] for _ in texts]


def test_evaluate_safety_agents_endpoint_reports_none_for_plain_pipeline(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]

    response = client.get(f"/pipelines/{pipeline_id}/evaluate/safety-agents")

    assert response.status_code == 200
    assert response.json() == {"has_safety_agents": False, "nodes": []}


def test_evaluate_safety_agents_endpoint_lists_barrier_nodes(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": SAFETY_DEFINITION}).json()["pipeline_id"]

    response = client.get(f"/pipelines/{pipeline_id}/evaluate/safety-agents")

    assert response.status_code == 200
    body = response.json()
    assert body["has_safety_agents"] is True
    assert {node["node_id"]: node["agent_type"] for node in body["nodes"]} == {
        "static_screen": "Static_Barrier_Agent",
        "judge": "Judge_Barrier_Agent",
    }


def test_evaluate_safety_jobs_endpoint_400_without_safety_agents(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs")

    assert response.status_code == 400


def test_evaluate_safety_jobs_endpoint_runs_against_overridden_builtin_csv(
    client, fake_llm, monkeypatch, tmp_path
):
    safety_csv = tmp_path / "mixed.csv"
    safety_csv.write_text("question,label\nWhat is a good sleep routine?,unharmful\n", encoding="utf-8")
    monkeypatch.setattr(evaluator_module, "resolve_builtin_safety_csv", lambda: safety_csv)

    pipeline_id = client.post("/pipelines/compile", json={"definition": SAFETY_DEFINITION}).json()["pipeline_id"]

    start = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs")
    assert start.status_code == 202
    handle = start.json()
    assert handle["total"] == 1

    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/safety/jobs/{handle['job_id']}")

    assert body["status"] == "done"
    assert body["completed"] == 1
    result = body["result"]
    assert result["total_questions"] == 1
    assert result["errors"] == 0
    assert result["results"][0]["predicted"] == "unharmful"
    assert len(fake_llm.calls) == 0  # the static layer alone decided this one


def test_cancel_safety_job_stops_a_running_job(client, monkeypatch, tmp_path):
    # Both rows match Static_Barrier_Agent's escalate_judge patterns, so both
    # reach Judge_Barrier_Agent and call the (slow, blocking) LLM.
    safety_csv = tmp_path / "escalate.csv"
    safety_csv.write_text(
        "question,label\n"
        "I don't need to sleep tonight,unharmful\n"
        "I don't need sleep at all,unharmful\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluator_module, "resolve_builtin_safety_csv", lambda: safety_csv)
    blocking = _BlockingLLM()
    monkeypatch.setattr(base_classes, "ask_llm", blocking)

    pipeline_id = client.post("/pipelines/compile", json={"definition": SAFETY_DEFINITION}).json()["pipeline_id"]

    start = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs")
    handle = start.json()
    assert handle["total"] == 2

    cancel = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs/{handle['job_id']}/cancel")
    assert cancel.status_code == 204

    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/safety/jobs/{handle['job_id']}")

    assert body["status"] == "cancelled"
    assert body["completed"] == 0
    assert body["result"] is None
    assert blocking.calls < 2


def test_cancel_safety_job_unknown_job_id_404s(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": SAFETY_DEFINITION}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs/does-not-exist/cancel")

    assert response.status_code == 404


def test_evaluate_jobs_endpoint_400_on_missing_expected_answer_column(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    response = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", b"question\nWhat's going on?\n", "text/csv")},
    )

    assert response.status_code == 400
    assert "expected_answer" in response.json()["detail"]


def test_evaluate_jobs_endpoint_404_for_unknown_pipeline(client):
    response = client.post(
        "/pipelines/does-not-exist/evaluate/jobs",
        files={"file": ("qa.csv", b"question,expected_answer\nQ?,A.\n", "text/csv")},
    )
    assert response.status_code == 404


def test_evaluate_jobs_endpoint_reports_total_upfront_and_completes(client, fake_llm, monkeypatch):
    """The frontend renders its progress bar off `total` (known immediately at
    job start, before any question has run) and `completed` (polled while the
    job is "running") -- this is the contract that depends on."""
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    fake_llm.queue(
        "```markdown\ngrounded reply\n```",
        '```json\n{"faithful": true, "score": 1.0, "reason": "matches context"}\n```',
    )
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", b"question,expected_answer\nWhat's going on?,All is well.\n", "text/csv")},
    )
    assert start.status_code == 202
    handle = start.json()
    assert handle["total"] == 1

    # total is known synchronously at job start, independent of how far the
    # background task has gotten.
    immediate = client.get(f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}").json()
    assert immediate["total"] == 1
    assert immediate["completed"] in (0, 1)

    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}")

    assert body["status"] == "done"
    assert body["completed"] == 1
    result = body["result"]
    assert result["safety"] is None
    assert result["agent"]["errors"] == 0
    question_result = result["agent"]["results"][0]
    assert question_result["answer"] == "grounded reply"
    assert question_result["faithfulness"]["faithful"] is True
    assert question_result["answer_similarity"] == pytest.approx(1.0)


def test_evaluate_jobs_endpoint_unknown_job_id_404s(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    response = client.get(f"/pipelines/{pipeline_id}/evaluate/jobs/does-not-exist")

    assert response.status_code == 404


def test_cancel_evaluate_job_stops_a_running_job(client, monkeypatch):
    blocking = _BlockingLLM()
    monkeypatch.setattr(base_classes, "ask_llm", blocking)
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", b"question,expected_answer\nQ1,A1.\nQ2,A2.\n", "text/csv")},
    )
    handle = start.json()
    assert handle["total"] == 2

    cancel = client.post(f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}/cancel")
    assert cancel.status_code == 204

    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}")

    assert body["status"] == "cancelled"
    # completed can reach 1 (the per-row loop bumps it in a `finally`, even
    # when that row's iteration ends via cancellation) but never 2 -- proof
    # the second row's answer call never started, i.e. the loop actually
    # stopped rather than the client just giving up on polling it.
    assert body["completed"] < handle["total"]
    assert body["result"] is None
    assert blocking.calls < 2


def test_cancel_evaluate_job_is_a_no_op_once_done(client, fake_llm, monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    fake_llm.queue(
        "```markdown\ngrounded reply\n```",
        '```json\n{"faithful": true, "score": 1.0, "reason": "matches context"}\n```',
    )
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", b"question,expected_answer\nQ1,A1.\n", "text/csv")},
    )
    handle = start.json()
    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}")
    assert body["status"] == "done"

    cancel = client.post(f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}/cancel")
    assert cancel.status_code == 204

    after = client.get(f"/pipelines/{pipeline_id}/evaluate/jobs/{handle['job_id']}").json()
    assert after["status"] == "done"
    assert after["result"] is not None


def test_cancel_evaluate_job_unknown_job_id_404s(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]

    response = client.post(f"/pipelines/{pipeline_id}/evaluate/jobs/does-not-exist/cancel")

    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Projects (persisted in SQLite via database.py)
# ─────────────────────────────────────────────────────────────────────────────


def test_list_projects_starts_empty(client):
    response = client.get("/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_create_project_returns_201_and_the_project(client):
    response = client.post("/projects", json={"name": "Asthma Assistant", "description": "Inhaler help"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Asthma Assistant"
    assert body["description"] == "Inhaler help"
    assert body["status"] == "draft"
    assert set(body) == {"id", "name", "description", "status", "created_at", "updated_at"}


def test_created_project_is_listed(client):
    created = client.post("/projects", json={"name": "Listed"}).json()
    assert client.get("/projects").json() == {"projects": [created]}


def test_create_project_description_defaults_to_empty(client):
    assert client.post("/projects", json={"name": "Bare"}).json()["description"] == ""


def test_create_project_rejects_blank_name(client):
    response = client.post("/projects", json={"name": "   "})
    assert response.status_code == 400
    assert "name" in response.json()["detail"].lower()
    assert client.get("/projects").json() == {"projects": []}


def test_create_project_requires_a_name(client):
    assert client.post("/projects", json={"description": "no name"}).status_code == 422


def test_projects_survive_a_backend_restart(bojai_home):
    # A new TestClient runs the app's startup again, and nothing about projects
    # is kept in app.py's memory -- only the SQLite file carries them over.
    with TestClient(app_module.app) as first:
        created = first.post("/projects", json={"name": "Survivor"}).json()
    app_module._pipelines.clear()
    with TestClient(app_module.app) as second:
        assert second.get("/projects").json() == {"projects": [created]}
    assert (bojai_home / "bojai.db").is_file()


# ─────────────────────────────────────────────────────────────────────────────
# Compiled pipelines survive a restart (saved definitions, recompiled on demand)
# ─────────────────────────────────────────────────────────────────────────────


def _simulate_restart():
    """What a backend restart loses: every in-memory compiled pipeline."""
    app_module._pipelines.clear()


def test_pipeline_is_recompiled_from_db_after_restart(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    _simulate_restart()

    assert client.get(f"/pipelines/{pipeline_id}").status_code == 200
    run = client.post(f"/pipelines/{pipeline_id}/run", json={"query": "hi"})
    assert run.status_code == 200
    assert run.json()["output"] == "hello from a compiled pipeline"


def test_recompiled_pipeline_uses_its_latest_definition(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    updated = {**STATIC_DEFINITION, "nodes": {"greet": {**STATIC_DEFINITION["nodes"]["greet"], "message": "v2"}}}
    assert client.put(f"/pipelines/{pipeline_id}", json={"definition": updated}).status_code == 200
    _simulate_restart()

    assert client.post(f"/pipelines/{pipeline_id}/run", json={"query": "hi"}).json()["output"] == "v2"


def test_list_pipelines_includes_ones_not_yet_recompiled(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    _simulate_restart()
    assert client.get("/pipelines").json() == {"pipeline_ids": [pipeline_id]}


def test_compile_conflicts_with_an_id_only_saved_in_the_db(client):
    client.post("/pipelines/compile", json={"pipeline_id": "fixed", "definition": STATIC_DEFINITION})
    _simulate_restart()
    response = client.post("/pipelines/compile", json={"pipeline_id": "fixed", "definition": STATIC_DEFINITION})
    assert response.status_code == 409


def test_deleted_pipeline_stays_deleted_after_restart(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION}).json()["pipeline_id"]
    assert client.delete(f"/pipelines/{pipeline_id}").status_code == 204
    _simulate_restart()
    assert client.get(f"/pipelines/{pipeline_id}").status_code == 404


def test_compile_with_unknown_project_404s_and_saves_nothing(client):
    response = client.post("/pipelines/compile", json={"definition": STATIC_DEFINITION, "project_id": "nope"})
    assert response.status_code == 404
    assert client.get("/pipelines").json() == {"pipeline_ids": []}


# ─────────────────────────────────────────────────────────────────────────────
# Project state: workspace, runs, chat responses
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACE = {
    "graph": {"nodes": [{"id": "n1"}], "edges": [], "runtimeConfig": {"provider": "openai", "model": "m"}},
    "active_run_id": "run-1",
    "best_run_id": None,
    "next_run_number": 2,
}


@pytest.fixture
def project_id(client):
    return client.post("/projects", json={"name": "Stateful"}).json()["id"]


def _put_run(client, project_id, run_id="run-1", **overrides):
    body = {
        "pipeline_id": "pl-1",
        "name": "run1",
        "definition_hash": "abc123",
        "workflow": {"nodes": [], "edges": [], "runtimeConfig": {}, "summary": None},
        "created_at": 1_700_000_000_000,
        **overrides,
    }
    return client.put(f"/projects/{project_id}/runs/{run_id}", json=body)


def test_get_project_by_id(client, project_id):
    assert client.get(f"/projects/{project_id}").json()["name"] == "Stateful"
    assert client.get("/projects/nope").status_code == 404


def test_state_of_a_new_project_is_empty(client, project_id):
    state = client.get(f"/projects/{project_id}/state").json()
    assert state["project"]["id"] == project_id
    assert state["workspace"] is None
    assert state["runs"] == []


def test_state_of_unknown_project_404s(client):
    assert client.get("/projects/nope/state").status_code == 404


def test_workspace_round_trips_through_state(client, project_id):
    assert client.put(f"/projects/{project_id}/workspace", json=WORKSPACE).status_code == 204
    assert client.get(f"/projects/{project_id}/state").json()["workspace"] == WORKSPACE


def test_workspace_for_unknown_project_404s(client):
    assert client.put("/projects/nope/workspace", json=WORKSPACE).status_code == 404


def test_runs_and_responses_round_trip_through_state(client, project_id):
    assert _put_run(client, project_id).status_code == 204
    response = {"query": "q", "answer": "a", "vote": "up", "explanation": "nice", "created_at": 5}
    assert client.put(f"/projects/{project_id}/runs/run-1/responses/resp-1", json=response).status_code == 204

    (run,) = client.get(f"/projects/{project_id}/state").json()["runs"]

    assert run["id"] == "run-1"
    assert run["name"] == "run1"
    assert run["pipeline_id"] == "pl-1"
    assert run["responses"] == [{"id": "resp-1", **response}]
    assert run["report_kinds"] == []


def test_run_rename_is_an_upsert(client, project_id):
    _put_run(client, project_id)
    _put_run(client, project_id, name="baseline")
    assert [r["name"] for r in client.get(f"/projects/{project_id}/state").json()["runs"]] == ["baseline"]


def test_delete_run(client, project_id):
    _put_run(client, project_id)
    assert client.delete(f"/projects/{project_id}/runs/run-1").status_code == 204
    assert client.get(f"/projects/{project_id}/state").json()["runs"] == []
    assert client.delete(f"/projects/{project_id}/runs/run-1").status_code == 404


def test_run_and_response_writes_404_for_unknown_targets(client, project_id):
    assert _put_run(client, "nope").status_code == 404
    response = {"query": "q", "answer": "a", "created_at": 5}
    assert client.put(f"/projects/{project_id}/runs/nope/responses/r", json=response).status_code == 404


def test_invalid_vote_is_rejected(client, project_id):
    _put_run(client, project_id)
    response = {"query": "q", "answer": "a", "vote": "maybe", "created_at": 5}
    assert client.put(f"/projects/{project_id}/runs/run-1/responses/r", json=response).status_code == 422


def test_writes_bump_the_project_to_the_top_of_the_list(client, project_id):
    newer = client.post("/projects", json={"name": "Newer"}).json()["id"]
    time.sleep(0.01)
    client.put(f"/projects/{project_id}/workspace", json=WORKSPACE)
    assert [p["id"] for p in client.get("/projects").json()["projects"]] == [project_id, newer]


def test_project_state_survives_a_backend_restart(project_id):
    with TestClient(app_module.app) as first:
        first.put(f"/projects/{project_id}/workspace", json=WORKSPACE)
        _put_run(first, project_id)
    _simulate_restart()
    with TestClient(app_module.app) as second:
        state = second.get(f"/projects/{project_id}/state").json()
    assert state["workspace"] == WORKSPACE
    assert [r["id"] for r in state["runs"]] == ["run-1"]


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation jobs started for a run save their reports (and CSV) to it
# ─────────────────────────────────────────────────────────────────────────────

QA_CSV = b"question,expected_answer\nWhat's going on?,All is well.\n"


def _compile_run(client, project_id, definition):
    pipeline_id = client.post(
        "/pipelines/compile", json={"definition": definition, "project_id": project_id}
    ).json()["pipeline_id"]
    assert _put_run(client, project_id, pipeline_id=pipeline_id).status_code == 204
    return pipeline_id


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_evaluate_job_for_a_run_saves_report_and_csv(client, project_id, fake_llm, monkeypatch, bojai_home):
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    fake_llm.queue(
        "```markdown\ngrounded reply\n```",
        '```json\n{"faithful": true, "score": 1.0, "reason": "matches context"}\n```',
    )
    pipeline_id = _compile_run(client, project_id, ANSWER_DEFINITION)

    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("my qa.csv", QA_CSV, "text/csv")},
        data={"run_id": "run-1"},
    )
    assert start.status_code == 202
    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{start.json()['job_id']}")
    assert body["status"] == "done"

    reports = client.get(f"/projects/{project_id}/runs/run-1/reports").json()
    assert reports["agent"]["report"] == body["result"]["agent"]
    assert reports["agent"]["csv_name"] == "my qa.csv"
    assert reports["safety"] is None
    (run,) = client.get(f"/projects/{project_id}/state").json()["runs"]
    assert run["report_kinds"] == ["agent"]

    csv = client.get(f"/projects/{project_id}/runs/run-1/reports/agent/csv")
    assert csv.status_code == 200
    assert csv.content == QA_CSV
    # Non-ASCII-safe RFC 5987 form: filename*=utf-8''my%20qa.csv
    assert "my qa.csv" in urllib.parse.unquote(csv.headers["content-disposition"])
    assert len(list((bojai_home / "files" / "evals").iterdir())) == 1


def test_evaluate_job_without_run_id_keeps_nothing(client, fake_llm, monkeypatch, bojai_home):
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    fake_llm.queue(
        "```markdown\ngrounded reply\n```",
        '```json\n{"faithful": true, "score": 1.0, "reason": "ok"}\n```',
    )
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]
    start = client.post(f"/pipelines/{pipeline_id}/evaluate/jobs", files={"file": ("qa.csv", QA_CSV, "text/csv")})
    assert _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{start.json()['job_id']}")["status"] == "done"
    assert not (bojai_home / "files").exists()


def test_evaluate_job_with_unknown_run_id_404s(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": ANSWER_DEFINITION}).json()["pipeline_id"]
    response = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", QA_CSV, "text/csv")},
        data={"run_id": "nope"},
    )
    assert response.status_code == 404


def test_cancelled_evaluate_job_deletes_its_kept_csv(client, project_id, monkeypatch, bojai_home):
    monkeypatch.setattr(base_classes, "ask_llm", _BlockingLLM())
    pipeline_id = _compile_run(client, project_id, ANSWER_DEFINITION)
    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", b"question,expected_answer\nQ1,A1.\nQ2,A2.\n", "text/csv")},
        data={"run_id": "run-1"},
    )
    evals = bojai_home / "files" / "evals"
    assert len(list(evals.iterdir())) == 1  # kept as soon as the job starts

    client.post(f"/pipelines/{pipeline_id}/evaluate/jobs/{start.json()['job_id']}/cancel")

    _wait_for(lambda: not any(evals.iterdir()))
    assert client.get(f"/projects/{project_id}/runs/run-1/reports").json() == {"safety": None, "agent": None}


def test_run_without_saved_csv_404s_on_csv_download(client, project_id):
    _put_run(client, project_id)
    assert client.get(f"/projects/{project_id}/runs/run-1/reports/agent/csv").status_code == 404


def test_safety_job_for_a_run_saves_its_report(client, project_id, fake_llm, monkeypatch, tmp_path):
    safety_csv = tmp_path / "mixed.csv"
    safety_csv.write_text("question,label\nWhat is a good sleep routine?,unharmful\n", encoding="utf-8")
    monkeypatch.setattr(evaluator_module, "resolve_builtin_safety_csv", lambda: safety_csv)
    pipeline_id = _compile_run(client, project_id, SAFETY_DEFINITION)

    start = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs", params={"run_id": "run-1"})
    assert start.status_code == 202
    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/safety/jobs/{start.json()['job_id']}")
    assert body["status"] == "done"

    reports = client.get(f"/projects/{project_id}/runs/run-1/reports").json()
    assert reports["safety"]["report"] == body["result"]
    assert reports["agent"] is None


def test_safety_job_with_unknown_run_id_404s(client):
    pipeline_id = client.post("/pipelines/compile", json={"definition": SAFETY_DEFINITION}).json()["pipeline_id"]
    response = client.post(f"/pipelines/{pipeline_id}/evaluate/safety/jobs", params={"run_id": "nope"})
    assert response.status_code == 404


def test_report_is_dropped_quietly_if_its_run_was_deleted_mid_job(client, project_id, fake_llm, monkeypatch, bojai_home):
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    fake_llm.queue(
        "```markdown\ngrounded reply\n```",
        '```json\n{"faithful": true, "score": 1.0, "reason": "ok"}\n```',
    )
    pipeline_id = _compile_run(client, project_id, ANSWER_DEFINITION)
    monkeypatch.setattr(app_module.database, "save_report", _raise_not_found)

    start = client.post(
        f"/pipelines/{pipeline_id}/evaluate/jobs",
        files={"file": ("qa.csv", QA_CSV, "text/csv")},
        data={"run_id": "run-1"},
    )
    body = _poll_job(client, f"/pipelines/{pipeline_id}/evaluate/jobs/{start.json()['job_id']}")

    assert body["status"] == "done"  # the job's own result is unaffected
    _wait_for(lambda: not any((bojai_home / "files" / "evals").iterdir()))


def _raise_not_found(*args, **kwargs):
    raise app_module.database.NotFoundError("run was deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Deleting a project
# ─────────────────────────────────────────────────────────────────────────────


def test_delete_project_removes_it_and_everything_under_it(client, project_id):
    pipeline_id = _compile_run(client, project_id, STATIC_DEFINITION)
    client.put(f"/projects/{project_id}/workspace", json=WORKSPACE)

    assert client.delete(f"/projects/{project_id}").status_code == 204

    assert client.get("/projects").json() == {"projects": []}
    assert client.get(f"/projects/{project_id}/state").status_code == 404
    # Gone from memory and from the db (not recompiled on demand).
    assert pipeline_id not in app_module._pipelines
    assert client.get(f"/pipelines/{pipeline_id}").status_code == 404


def test_delete_project_leaves_other_projects_alone(client, project_id):
    other = client.post("/projects", json={"name": "Other"}).json()["id"]
    other_pipeline = _compile_run(client, other, STATIC_DEFINITION)

    client.delete(f"/projects/{project_id}")

    assert [p["id"] for p in client.get("/projects").json()["projects"]] == [other]
    assert client.get(f"/pipelines/{other_pipeline}").status_code == 200


def test_delete_unknown_project_404s(client):
    assert client.delete("/projects/nope").status_code == 404
