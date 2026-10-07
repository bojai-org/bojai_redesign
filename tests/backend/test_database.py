import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

import database


def test_db_lives_in_bojai_home(bojai_home):
    assert database.db_path() == bojai_home / "bojai.db"


def test_data_dir_defaults_to_dot_bojai_in_home(monkeypatch, tmp_path):
    monkeypatch.delenv("BOJAI_HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert database.data_dir() == tmp_path / ".bojai"


def test_blank_bojai_home_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("BOJAI_HOME", "   ")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert database.db_path() == tmp_path / ".bojai" / "bojai.db"


def test_list_projects_is_empty_on_a_fresh_db():
    assert database.list_projects() == []


def test_first_use_creates_folder_and_db(bojai_home):
    assert not bojai_home.exists()
    database.list_projects()
    assert (bojai_home / "bojai.db").is_file()


def test_works_with_the_empty_db_run_app_locally_creates(bojai_home):
    # run_app_locally.sh creates bojai.db up front with no tables in it.
    bojai_home.mkdir()
    with closing(sqlite3.connect(bojai_home / "bojai.db")) as conn:
        conn.execute("VACUUM")
    database.create_project("After script init")
    assert [p.name for p in database.list_projects()] == ["After script init"]


def test_create_project_returns_the_saved_project():
    project = database.create_project("  Asthma Assistant  ", "  Helps with inhalers  ")

    assert project.name == "Asthma Assistant"
    assert project.description == "Helps with inhalers"
    assert project.status == "draft"
    assert project.id
    assert project.created_at == project.updated_at
    assert project.created_at.endswith("Z")


def test_create_project_generates_unique_ids():
    first = database.create_project("Same name")
    second = database.create_project("Same name")
    assert first.id != second.id


def test_description_is_optional():
    assert database.create_project("No description").description == ""


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_blank_name_is_rejected_and_nothing_is_saved(name):
    with pytest.raises(ValueError):
        database.create_project(name)
    assert database.list_projects() == []


def test_projects_survive_reconnecting():
    # Every call opens a fresh connection, so this is what a backend restart
    # looks like from the database's point of view.
    created = database.create_project("Persistent", "still here")
    assert database.list_projects() == [created]


def test_projects_are_listed_newest_first():
    older = database.create_project("Older")
    time.sleep(0.01)  # timestamps have millisecond resolution
    newer = database.create_project("Newer")
    assert [p.id for p in database.list_projects()] == [newer.id, older.id]


def test_projects_are_stored_in_the_sqlite_file(bojai_home):
    project = database.create_project("On disk")
    with closing(sqlite3.connect(bojai_home / "bojai.db")) as conn:
        rows = conn.execute("SELECT id, name FROM projects").fetchall()
    assert rows == [(project.id, "On disk")]


# ─────────────────────────────────────────────────────────────────────────────
# Schema migrations
# ─────────────────────────────────────────────────────────────────────────────


def _user_version(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def test_fresh_db_is_migrated_to_latest_version(bojai_home):
    database.list_projects()
    assert _user_version(bojai_home / "bojai.db") == len(database._MIGRATIONS)


def test_db_from_the_projects_only_version_is_upgraded_in_place(bojai_home):
    # The first persistence release created `projects` without recording a
    # schema version; its rows must survive the upgrade.
    bojai_home.mkdir()
    with closing(sqlite3.connect(bojai_home / "bojai.db")) as conn, conn:
        conn.executescript(database._MIGRATIONS[0])
        conn.execute(
            "INSERT INTO projects VALUES ('p1', 'Old', '', 'draft', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z')"
        )

    assert [p.name for p in database.list_projects()] == ["Old"]
    assert _user_version(bojai_home / "bojai.db") == len(database._MIGRATIONS)
    database.save_workspace("p1", {"nodes": []}, None, None, 1)  # new tables exist


def test_migrations_are_idempotent():
    with closing(database._connect()) as conn:
        for script in database._MIGRATIONS:
            conn.executescript(script)  # re-running any of them must not fail


# ─────────────────────────────────────────────────────────────────────────────
# Workspace
# ─────────────────────────────────────────────────────────────────────────────

GRAPH = {"nodes": [{"id": "n1", "position": {"x": 1, "y": 2}}], "edges": [], "runtimeConfig": {}}


@pytest.fixture
def project():
    return database.create_project("Under test")


def test_workspace_is_none_until_saved(project):
    assert database.get_workspace(project.id) is None


def test_workspace_round_trips(project):
    database.save_workspace(project.id, GRAPH, "run-a", "run-b", 3)
    saved = database.get_workspace(project.id)
    assert saved["graph"] == GRAPH
    assert (saved["active_run_id"], saved["best_run_id"], saved["next_run_number"]) == ("run-a", "run-b", 3)


def test_saving_workspace_again_replaces_it(project):
    database.save_workspace(project.id, GRAPH, "run-a", None, 2)
    database.save_workspace(project.id, {"nodes": []}, None, None, 5)
    saved = database.get_workspace(project.id)
    assert saved["graph"] == {"nodes": []}
    assert saved["active_run_id"] is None
    assert saved["next_run_number"] == 5


def test_workspace_for_unknown_project_is_rejected():
    with pytest.raises(database.NotFoundError):
        database.save_workspace("nope", GRAPH, None, None, 1)


def test_saving_workspace_bumps_project_updated_at(project):
    time.sleep(0.01)
    database.save_workspace(project.id, GRAPH, None, None, 1)
    assert database.get_project(project.id).updated_at > project.updated_at


# ─────────────────────────────────────────────────────────────────────────────
# Pipelines
# ─────────────────────────────────────────────────────────────────────────────


def test_pipeline_definition_round_trips_with_or_without_project(project):
    database.save_pipeline("pl-1", {"entrypoint": "a"}, project.id)
    database.save_pipeline("pl-2", {"entrypoint": "b"})
    assert database.get_pipeline_definition("pl-1") == {"entrypoint": "a"}
    assert database.get_pipeline_definition("pl-2") == {"entrypoint": "b"}
    assert database.list_pipeline_ids() == ["pl-1", "pl-2"]


def test_saving_a_pipeline_again_replaces_its_definition():
    database.save_pipeline("pl", {"v": 1})
    database.save_pipeline("pl", {"v": 2})
    assert database.get_pipeline_definition("pl") == {"v": 2}


def test_pipeline_for_unknown_project_is_rejected():
    with pytest.raises(database.NotFoundError):
        database.save_pipeline("pl", {}, "nope")


def test_delete_pipeline():
    database.save_pipeline("pl", {})
    database.delete_pipeline("pl")
    assert database.get_pipeline_definition("pl") is None


# ─────────────────────────────────────────────────────────────────────────────
# Runs, responses, reports
# ─────────────────────────────────────────────────────────────────────────────


def _save_run(project_id, run_id="run-1", created_at=1000, **overrides):
    fields = dict(pipeline_id="pl", name="run1", definition_hash="abc", workflow=GRAPH, created_at=created_at)
    fields.update(overrides)
    database.save_run(project_id, run_id, **fields)


def test_runs_round_trip_oldest_first_with_responses(project):
    _save_run(project.id, "run-2", created_at=2000, name="run2")
    _save_run(project.id, "run-1", created_at=1000)
    database.save_response(project.id, "run-1", "resp-b", query="q2", answer="a2", vote=None, explanation="", created_at=20)
    database.save_response(project.id, "run-1", "resp-a", query="q1", answer="a1", vote="up", explanation="good", created_at=10)

    runs = database.list_runs(project.id)

    assert [r["id"] for r in runs] == ["run-1", "run-2"]
    assert runs[0]["workflow"] == GRAPH
    assert [r["id"] for r in runs[0]["responses"]] == ["resp-a", "resp-b"]
    assert runs[0]["responses"][0] == {
        "id": "resp-a", "query": "q1", "answer": "a1", "vote": "up", "explanation": "good", "created_at": 10,
    }
    assert runs[1]["responses"] == []
    assert runs[0]["report_kinds"] == []


def test_saving_a_run_again_updates_it_but_keeps_created_at(project):
    _save_run(project.id, created_at=1000)
    _save_run(project.id, created_at=9999, name="renamed", pipeline_id="pl-new")
    (run,) = database.list_runs(project.id)
    assert (run["name"], run["pipeline_id"], run["created_at"]) == ("renamed", "pl-new", 1000)


def test_runs_are_scoped_to_their_project(project):
    other = database.create_project("Other")
    _save_run(project.id)
    assert database.list_runs(other.id) == []
    with pytest.raises(database.NotFoundError):
        _save_run(other.id)  # same run id, different project
    with pytest.raises(database.NotFoundError):
        database.delete_run(other.id, "run-1")


def test_response_vote_can_be_updated_and_cleared(project):
    _save_run(project.id)
    database.save_response(project.id, "run-1", "r", query="q", answer="a", vote="down", explanation="bad", created_at=1)
    database.save_response(project.id, "run-1", "r", query="q", answer="a", vote=None, explanation="bad", created_at=1)
    (response,) = database.list_runs(project.id)[0]["responses"]
    assert (response["vote"], response["explanation"]) == (None, "bad")


def test_response_rejects_unknown_run_and_bad_vote(project):
    with pytest.raises(database.NotFoundError):
        database.save_response(project.id, "nope", "r", query="q", answer="a", vote=None, explanation="", created_at=1)
    _save_run(project.id)
    with pytest.raises(ValueError):
        database.save_response(project.id, "run-1", "r", query="q", answer="a", vote="meh", explanation="", created_at=1)


def test_reports_round_trip_and_are_listed_by_kind(project):
    _save_run(project.id)
    database.save_report("run-1", "agent", {"errors": 0}, csv_file=None, csv_name="qa.csv")
    database.save_report("run-1", "safety", {"f1": 1.0})

    reports = database.get_reports(project.id, "run-1")

    assert reports["agent"]["report"] == {"errors": 0}
    assert reports["agent"]["csv_name"] == "qa.csv"
    assert reports["safety"]["report"] == {"f1": 1.0}
    assert database.list_runs(project.id)[0]["report_kinds"] == ["agent", "safety"]


def test_report_for_unknown_run_is_rejected():
    with pytest.raises(database.NotFoundError):
        database.save_report("nope", "agent", {})


def test_eval_csv_is_kept_under_files_and_served_back(project, bojai_home):
    _save_run(project.id)
    relative = database.store_eval_csv(b"question,expected_answer\nQ,A\n")
    database.save_report("run-1", "agent", {}, csv_file=relative, csv_name="my questions.csv")

    path, name = database.get_report_csv(project.id, "run-1")

    assert path == bojai_home / "files" / relative
    assert path.read_bytes() == b"question,expected_answer\nQ,A\n"
    assert name == "my questions.csv"


def test_replacing_an_agent_report_deletes_the_old_csv(project):
    _save_run(project.id)
    first = database.store_eval_csv(b"old")
    database.save_report("run-1", "agent", {}, csv_file=first, csv_name="old.csv")
    second = database.store_eval_csv(b"new")
    database.save_report("run-1", "agent", {}, csv_file=second, csv_name="new.csv")

    assert not (database.files_dir() / first).exists()
    assert database.get_report_csv(project.id, "run-1")[0].read_bytes() == b"new"


def test_deleting_a_run_removes_its_responses_reports_and_csvs(project):
    _save_run(project.id)
    database.save_response(project.id, "run-1", "r", query="q", answer="a", vote=None, explanation="", created_at=1)
    relative = database.store_eval_csv(b"data")
    database.save_report("run-1", "agent", {}, csv_file=relative, csv_name="qa.csv")

    database.delete_run(project.id, "run-1")

    assert database.list_runs(project.id) == []
    assert not (database.files_dir() / relative).exists()
    with closing(database._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_reports").fetchone()[0] == 0


def test_deleting_a_project_cascades_to_everything_under_it(project):
    database.save_workspace(project.id, GRAPH, None, None, 1)
    database.save_pipeline("pl", {}, project.id)
    _save_run(project.id)
    database.save_response(project.id, "run-1", "r", query="q", answer="a", vote=None, explanation="", created_at=1)
    database.save_report("run-1", "agent", {})

    with closing(database._connect()) as conn, conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project.id,))
        for table in ("workspaces", "pipelines", "runs", "responses", "run_reports"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_delete_project_removes_everything_and_its_csvs(project):
    other = database.create_project("Kept")
    database.save_workspace(project.id, GRAPH, None, None, 1)
    database.save_pipeline("pl", {}, project.id)
    database.save_pipeline("unowned", {})
    _save_run(project.id)
    relative = database.store_eval_csv(b"data")
    database.save_report("run-1", "agent", {}, csv_file=relative, csv_name="qa.csv")

    assert database.delete_project(project.id) == ["pl"]

    assert database.get_project(project.id) is None
    assert [p.id for p in database.list_projects()] == [other.id]
    assert database.list_pipeline_ids() == ["unowned"]
    assert not (database.files_dir() / relative).exists()


def test_delete_unknown_project_is_rejected():
    with pytest.raises(database.NotFoundError):
        database.delete_project("nope")
