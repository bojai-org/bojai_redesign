import time

import pytest
from fastapi.testclient import TestClient

import app as app_module
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
    fake_llm.queue('```json\n{"answer": "grounded reply"}\n```')
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
        '```json\n{"answer": "grounded reply"}\n```',
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
