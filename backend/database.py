"""
BojAI Build — Local SQLite Persistence

Everything that must survive a backend restart lives under $BOJAI_HOME
(default ~/.bojai, the folder run_app_locally.sh creates and exports):

  bojai.db   one SQLite file holding projects and everything under them
  files/     files that were already files when they arrived -- currently the
             CSVs uploaded for evaluation, kept so a report can point at the
             exact data it was produced from

Tables (all hang off projects.id and are removed with it, ON DELETE CASCADE):

  projects     one row per project
  workspaces   1:1 with a project -- the Build canvas as it is right now,
               compiled or not, plus which run is active/best
  pipelines    compiled pipeline definitions, so a pipeline id stays valid
               across restarts (app.py recompiles from here on demand)
  runs         one compiled version of a project's pipeline + its workflow
  responses    chat exchanges from the Run tab, per run
  run_reports  evaluation reports, per run and kind (safety / agent) -- in
               their own table so loading a project doesn't load every report

Shapes the backend never queries into (the node graph, reports, compile
summaries) are stored as JSON text; ids, links, names and timestamps get
real columns.

Each call opens its own short-lived connection, so this is safe to use from
FastAPI's request handlers without sharing a connection across threads.
The schema is created/migrated on first use (tracked with PRAGMA
user_version), so a missing or empty bojai.db is fine.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# Applied in order; the database's PRAGMA user_version records how many have
# run. Only ever append -- never edit a migration that has shipped. Each is
# written to be idempotent (IF NOT EXISTS), so two connections racing to apply
# the same one on first use can't fail.
_MIGRATIONS: list[str] = [
    # 1: projects
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status      TEXT NOT NULL DEFAULT 'draft',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    """,
    # 2: everything under a project
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        project_id      TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        graph           TEXT NOT NULL,
        active_run_id   TEXT,
        best_run_id     TEXT,
        next_run_number INTEGER NOT NULL DEFAULT 1,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pipelines (
        id          TEXT PRIMARY KEY,
        project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
        definition  TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS runs (
        id              TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        pipeline_id     TEXT NOT NULL,
        name            TEXT NOT NULL,
        definition_hash TEXT NOT NULL,
        workflow        TEXT NOT NULL,
        created_at      INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS runs_by_project ON runs(project_id, created_at);

    CREATE TABLE IF NOT EXISTS responses (
        id          TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        query       TEXT NOT NULL,
        answer      TEXT NOT NULL,
        vote        TEXT CHECK (vote IN ('up', 'down')),
        explanation TEXT NOT NULL DEFAULT '',
        created_at  INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS responses_by_run ON responses(run_id, created_at);

    CREATE TABLE IF NOT EXISTS run_reports (
        run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL CHECK (kind IN ('safety', 'agent')),
        report      TEXT NOT NULL,
        csv_file    TEXT,
        csv_name    TEXT,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (run_id, kind)
    );
    """,
]

ReportKind = Literal["safety", "agent"]


class NotFoundError(LookupError):
    """The project/run a write was aimed at doesn't exist (or belongs elsewhere)."""


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Locations and connections
# ─────────────────────────────────────────────────────────────────────────────


def data_dir() -> Path:
    """$BOJAI_HOME, else ~/.bojai. Read on every call so tests (and the run
    script) can point it somewhere else via the environment."""
    configured = os.environ.get("BOJAI_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".bojai"


def db_path() -> Path:
    return data_dir() / "bojai.db"


def files_dir() -> Path:
    return data_dir() / "files"


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(_MIGRATIONS[version:], start=version + 1):
        # executescript commits first and runs outside the implicit
        # transaction, so wrap each migration (and its version bump) in one.
        conn.executescript(f"BEGIN; {script}\nPRAGMA user_version = {number}; COMMIT;")


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _touch_project(conn: sqlite3.Connection, project_id: str) -> None:
    """Any change under a project counts as editing it (projects page sorts by this)."""
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))


def _require_project(conn: sqlite3.Connection, project_id: str) -> None:
    if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise NotFoundError(f"No project with id {project_id!r}")


def _require_run(conn: sqlite3.Connection, project_id: str, run_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM runs WHERE id = ? AND project_id = ?", (run_id, project_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No run with id {run_id!r} in project {project_id!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

_PROJECT_COLUMNS = "id, name, description, status, created_at, updated_at"


def _to_project(row: sqlite3.Row) -> Project:
    return Project(**{key: row[key] for key in row.keys()})


def list_projects() -> list[Project]:
    """Most recently edited first."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT {_PROJECT_COLUMNS} FROM projects ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
    return [_to_project(row) for row in rows]


def get_project(project_id: str) -> Project | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return _to_project(row) if row else None


def create_project(name: str, description: str = "") -> Project:
    """Raises ValueError for a blank name."""
    name = name.strip()
    if not name:
        raise ValueError("Project name must not be empty.")
    now = _now()
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=description.strip(),
        status="draft",
        created_at=now,
        updated_at=now,
    )
    with closing(_connect()) as conn, conn:  # inner `conn` commits the transaction
        conn.execute(
            f"INSERT INTO projects ({_PROJECT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
            (project.id, project.name, project.description, project.status,
             project.created_at, project.updated_at),
        )
    return project


def delete_project(project_id: str) -> list[str]:
    """Deletes the project and everything under it (cascade), plus the eval
    CSVs its reports kept in files/. Returns the ids of the pipelines it owned,
    so callers can drop them from memory too. Raises NotFoundError for an
    unknown project."""
    with closing(_connect()) as conn, conn:
        _require_project(conn, project_id)
        pipeline_ids = [
            row["id"] for row in conn.execute("SELECT id FROM pipelines WHERE project_id = ?", (project_id,))
        ]
        csv_files = [
            row["csv_file"]
            for row in conn.execute(
                "SELECT rr.csv_file FROM run_reports rr JOIN runs ON runs.id = rr.run_id "
                "WHERE runs.project_id = ? AND rr.csv_file IS NOT NULL",
                (project_id,),
            )
        ]
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    for relative in csv_files:
        delete_stored_file(relative)
    return pipeline_ids


# ─────────────────────────────────────────────────────────────────────────────
# Workspace (the Build canvas, compiled or not)
# ─────────────────────────────────────────────────────────────────────────────


def get_workspace(project_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT graph, active_run_id, best_run_id, next_run_number, updated_at "
            "FROM workspaces WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "graph": json.loads(row["graph"]),
        "active_run_id": row["active_run_id"],
        "best_run_id": row["best_run_id"],
        "next_run_number": row["next_run_number"],
        "updated_at": row["updated_at"],
    }


def save_workspace(
    project_id: str,
    graph: dict[str, Any],
    active_run_id: str | None,
    best_run_id: str | None,
    next_run_number: int,
) -> None:
    """Replaces the project's workspace. Raises NotFoundError for an unknown project."""
    with closing(_connect()) as conn, conn:
        _require_project(conn, project_id)
        conn.execute(
            "INSERT INTO workspaces (project_id, graph, active_run_id, best_run_id, next_run_number, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET graph = excluded.graph, "
            "active_run_id = excluded.active_run_id, best_run_id = excluded.best_run_id, "
            "next_run_number = excluded.next_run_number, updated_at = excluded.updated_at",
            (project_id, json.dumps(graph), active_run_id, best_run_id, next_run_number, _now()),
        )
        _touch_project(conn, project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Compiled pipeline definitions
# ─────────────────────────────────────────────────────────────────────────────


def save_pipeline(pipeline_id: str, definition: dict[str, Any], project_id: str | None = None) -> None:
    """Creates or replaces a pipeline definition. project_id is optional (the
    HTTP API can compile pipelines that belong to no project); an unknown one
    raises NotFoundError."""
    now = _now()
    with closing(_connect()) as conn, conn:
        if project_id is not None:
            _require_project(conn, project_id)
        conn.execute(
            "INSERT INTO pipelines (id, project_id, definition, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET definition = excluded.definition, "
            "project_id = COALESCE(excluded.project_id, pipelines.project_id), "
            "updated_at = excluded.updated_at",
            (pipeline_id, project_id, json.dumps(definition), now, now),
        )


def get_pipeline_definition(pipeline_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT definition FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
    return json.loads(row["definition"]) if row else None


def list_pipeline_ids() -> list[str]:
    with closing(_connect()) as conn:
        return [row["id"] for row in conn.execute("SELECT id FROM pipelines ORDER BY id")]


def delete_pipeline(pipeline_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Runs and their chat responses
# ─────────────────────────────────────────────────────────────────────────────


def save_run(
    project_id: str,
    run_id: str,
    *,
    pipeline_id: str,
    name: str,
    definition_hash: str,
    workflow: dict[str, Any],
    created_at: int,
) -> None:
    """Creates or updates a run (ids are generated by the client). Raises
    NotFoundError for an unknown project, or a run id taken by another project."""
    with closing(_connect()) as conn, conn:
        _require_project(conn, project_id)
        cursor = conn.execute(
            "INSERT INTO runs (id, project_id, pipeline_id, name, definition_hash, workflow, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET pipeline_id = excluded.pipeline_id, name = excluded.name, "
            "definition_hash = excluded.definition_hash, workflow = excluded.workflow "
            "WHERE runs.project_id = excluded.project_id",
            (run_id, project_id, pipeline_id, name, definition_hash, json.dumps(workflow), created_at),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"Run id {run_id!r} belongs to another project")
        _touch_project(conn, project_id)


def list_runs(project_id: str) -> list[dict[str, Any]]:
    """The project's runs, oldest first, each with its responses (oldest first)
    and which kinds of report it has -- but not the reports themselves."""
    with closing(_connect()) as conn:
        runs = conn.execute(
            "SELECT id, pipeline_id, name, definition_hash, workflow, created_at "
            "FROM runs WHERE project_id = ? ORDER BY created_at, rowid",
            (project_id,),
        ).fetchall()
        responses = conn.execute(
            "SELECT r.id, r.run_id, r.query, r.answer, r.vote, r.explanation, r.created_at "
            "FROM responses r JOIN runs ON runs.id = r.run_id "
            "WHERE runs.project_id = ? ORDER BY r.created_at, r.rowid",
            (project_id,),
        ).fetchall()
        report_kinds = conn.execute(
            "SELECT rr.run_id, rr.kind FROM run_reports rr JOIN runs ON runs.id = rr.run_id "
            "WHERE runs.project_id = ?",
            (project_id,),
        ).fetchall()

    responses_by_run: dict[str, list[dict[str, Any]]] = {}
    for row in responses:
        entry = {key: row[key] for key in ("id", "query", "answer", "vote", "explanation", "created_at")}
        responses_by_run.setdefault(row["run_id"], []).append(entry)
    kinds_by_run: dict[str, list[str]] = {}
    for row in report_kinds:
        kinds_by_run.setdefault(row["run_id"], []).append(row["kind"])

    return [
        {
            "id": row["id"],
            "pipeline_id": row["pipeline_id"],
            "name": row["name"],
            "definition_hash": row["definition_hash"],
            "workflow": json.loads(row["workflow"]),
            "created_at": row["created_at"],
            "responses": responses_by_run.get(row["id"], []),
            "report_kinds": sorted(kinds_by_run.get(row["id"], [])),
        }
        for row in runs
    ]


def delete_run(project_id: str, run_id: str) -> None:
    """Deletes a run with its responses and reports, and the eval CSVs those
    reports kept in files/. Raises NotFoundError if it isn't in the project."""
    with closing(_connect()) as conn, conn:
        _require_run(conn, project_id, run_id)
        csv_files = [
            row["csv_file"]
            for row in conn.execute(
                "SELECT csv_file FROM run_reports WHERE run_id = ? AND csv_file IS NOT NULL", (run_id,)
            )
        ]
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        _touch_project(conn, project_id)
    for relative in csv_files:
        delete_stored_file(relative)


def save_response(
    project_id: str,
    run_id: str,
    response_id: str,
    *,
    query: str,
    answer: str,
    vote: str | None,
    explanation: str,
    created_at: int,
) -> None:
    """Creates or updates one chat exchange. Raises NotFoundError if the run
    isn't in the project, and ValueError for a vote other than up/down/None."""
    if vote not in (None, "up", "down"):
        raise ValueError("vote must be 'up', 'down' or null")
    with closing(_connect()) as conn, conn:
        _require_run(conn, project_id, run_id)
        cursor = conn.execute(
            "INSERT INTO responses (id, run_id, query, answer, vote, explanation, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET query = excluded.query, answer = excluded.answer, "
            "vote = excluded.vote, explanation = excluded.explanation "
            "WHERE responses.run_id = excluded.run_id",
            (response_id, run_id, query, answer, vote, explanation, created_at),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"Response id {response_id!r} belongs to another run")
        _touch_project(conn, project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation reports (+ the CSV each agent report was run on, in files/)
# ─────────────────────────────────────────────────────────────────────────────


def run_project_id(run_id: str) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT project_id FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row["project_id"] if row else None


def store_eval_csv(raw: bytes) -> str:
    """Saves an uploaded eval CSV under files/ and returns its path relative to
    files/ -- the form report rows keep, so the data folder can move."""
    relative = f"evals/{uuid.uuid4()}.csv"
    path = files_dir() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return relative


def delete_stored_file(relative: str) -> None:
    (files_dir() / relative).unlink(missing_ok=True)


def save_report(
    run_id: str,
    kind: ReportKind,
    report: dict[str, Any],
    *,
    csv_file: str | None = None,
    csv_name: str | None = None,
) -> None:
    """Creates or replaces the run's report of this kind. A replaced report's
    old CSV is deleted from files/. Raises NotFoundError for an unknown run."""
    with closing(_connect()) as conn, conn:
        row = conn.execute("SELECT project_id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No run with id {run_id!r}")
        previous = conn.execute(
            "SELECT csv_file FROM run_reports WHERE run_id = ? AND kind = ?", (run_id, kind)
        ).fetchone()
        conn.execute(
            "INSERT INTO run_reports (run_id, kind, report, csv_file, csv_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, kind) DO UPDATE SET report = excluded.report, "
            "csv_file = excluded.csv_file, csv_name = excluded.csv_name, created_at = excluded.created_at",
            (run_id, kind, json.dumps(report), csv_file, csv_name, _now()),
        )
        _touch_project(conn, row["project_id"])
    if previous and previous["csv_file"] and previous["csv_file"] != csv_file:
        delete_stored_file(previous["csv_file"])


def get_reports(project_id: str, run_id: str) -> dict[str, dict[str, Any] | None]:
    """{"safety": ..., "agent": ...}, each None or {report, csv_name, created_at}.
    Raises NotFoundError if the run isn't in the project."""
    with closing(_connect()) as conn:
        _require_run(conn, project_id, run_id)
        rows = conn.execute(
            "SELECT kind, report, csv_name, created_at FROM run_reports WHERE run_id = ?", (run_id,)
        ).fetchall()
    reports: dict[str, dict[str, Any] | None] = {"safety": None, "agent": None}
    for row in rows:
        reports[row["kind"]] = {
            "report": json.loads(row["report"]),
            "csv_name": row["csv_name"],
            "created_at": row["created_at"],
        }
    return reports


def get_report_csv(project_id: str, run_id: str) -> tuple[Path, str] | None:
    """(path on disk, original file name) of the CSV the run's agent report was
    produced from, or None if there's no such file. Raises NotFoundError if the
    run isn't in the project."""
    with closing(_connect()) as conn:
        _require_run(conn, project_id, run_id)
        row = conn.execute(
            "SELECT csv_file, csv_name FROM run_reports WHERE run_id = ? AND kind = 'agent'", (run_id,)
        ).fetchone()
    if row is None or not row["csv_file"]:
        return None
    path = files_dir() / row["csv_file"]
    return (path, row["csv_name"] or path.name) if path.is_file() else None
