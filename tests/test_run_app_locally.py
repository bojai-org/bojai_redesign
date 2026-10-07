"""Tests for run_app_locally.sh.

Two layers:

* Static checks (pure Python) catch drift between the script and the code it
  launches: ports, entry points, the `dev` npm script, and CRLF line endings
  (which make bash fail with "$'\\r': command not found" after a Windows
  checkout or editor save).

* Behaviour checks run the real script with bash inside a throwaway copy of the
  project, with stub `python`, `npm`, `cmd.exe` and `powershell.exe` on PATH.
  Each stub records every call as its own timestamped file in calls/ (separate
  files, because concurrent `>>` appends to one file can drop lines on WSL's
  /mnt/c), so a failing assertion shows exactly what the script did and in
  what order. No real servers are started.

The behaviour checks need bash. Under Windows Python (e.g. the conda install)
each one runs twice, once through `wsl.exe -e bash` and once through Git Bash
(MINGW64), since the script is launched from both; whichever is missing is
skipped. Test ids end in [wsl] / [git-bash] to show which shell failed.
"""

import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "run_app_locally.sh"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173


# ─────────────────────────────────────────────────────────────────────────────
# Static checks
# ─────────────────────────────────────────────────────────────────────────────

def test_script_exists():
    assert SCRIPT.is_file(), f"{SCRIPT} is missing"


def test_script_uses_lf_line_endings():
    data = SCRIPT.read_bytes()
    assert b"\r\n" not in data, (
        "run_app_locally.sh has CRLF line endings; bash will fail with "
        "\"$'\\r': command not found\". Convert with `sed -i 's/\\r$//' run_app_locally.sh`."
    )


def test_script_has_bash_shebang_and_strict_mode():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text


def test_backend_entry_point_exists():
    assert (REPO_ROOT / "backend" / "app.py").is_file()
    assert "backend/app.py" in SCRIPT.read_text()


def test_backend_port_matches_app_py():
    app_py = (REPO_ROOT / "backend" / "app.py").read_text()
    match = re.search(r"uvicorn\.run\(app,.*port=(\d+)", app_py)
    assert match, "could not find uvicorn.run(...) in backend/app.py"
    assert int(match.group(1)) == BACKEND_PORT
    assert f'BACKEND_URL="http://127.0.0.1:{BACKEND_PORT}"' in SCRIPT.read_text()


def test_frontend_default_api_url_matches_backend_port():
    api_ts = (REPO_ROOT / "frontend/src/features/build/api/pipelineApi.ts").read_text()
    assert f'DEFAULT_API_BASE_URL = "http://127.0.0.1:{BACKEND_PORT}"' in api_ts, (
        "frontend talks to a different backend URL than the one the script waits for"
    )


def test_frontend_has_dev_script():
    package = json.loads((REPO_ROOT / "frontend" / "package.json").read_text())
    assert "dev" in package.get("scripts", {}), "frontend/package.json has no `dev` script"


def test_frontend_port_is_pinned():
    assert f"FRONTEND_PORT={FRONTEND_PORT}" in SCRIPT.read_text()


# ─────────────────────────────────────────────────────────────────────────────
# Bash harness
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Shell:
    """A bash the script can be run under, plus how it spells Windows paths."""
    name: str
    argv: tuple
    drive_prefix: str  # "/mnt/" for WSL (C:\\x -> /mnt/c/x), "/" for Git Bash (/c/x)

    def posix(self, path: Path) -> str:
        if os.name != "nt":
            return str(path)
        win = PureWindowsPath(path)
        drive = win.drive.rstrip(":").lower()
        return self.drive_prefix + drive + "/" + "/".join(win.parts[1:])

    def run(self, command: str, timeout=30):
        return subprocess.run(
            [*self.argv, "-c", command], capture_output=True, text=True, timeout=timeout,
        )


def _git_bash():
    candidates = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"]
    git = shutil.which("git")
    if git:
        candidates.append(Path(git).resolve().parents[1] / "bin" / "bash.exe")
    return next((c for c in candidates if c.is_file()), None)


def _available_shells():
    if os.name != "nt":
        return [Shell("bash", ("bash",), "/")] if shutil.which("bash") else []
    # On Windows, cover both ways the script gets run: from WSL and from Git Bash.
    shells = []
    if shutil.which("wsl.exe"):
        shells.append(Shell("wsl", ("wsl.exe", "-e", "bash"), "/mnt/"))
    git_bash = _git_bash()
    if git_bash:
        shells.append(Shell("git-bash", (str(git_bash),), "/"))
    return shells


SHELLS = _available_shells()
needs_bash = pytest.mark.skipif(not SHELLS, reason="no bash available (WSL or Git Bash on Windows)")


def _write_exe(path: Path, body: str):
    path.write_text(textwrap.dedent(body).lstrip(), newline="\n")
    path.chmod(0o755)


# The stubs log to $CALLS_DIR, one file per call named by nanosecond timestamp. The fake backend marks itself "up" by touching
# $STATE_DIR/backend_up, which the fake urllib health check looks for.
PYTHON_STUB = """
    #!/usr/bin/env bash
    log() { printf '%s\n' "$*" > "$CALLS_DIR/$(date +%s%N)-$$-$RANDOM"; }
    log "python $*"
    case "$*" in
      *"import fastapi, uvicorn"*)
        [ "${FAKE_PYTHON_HAS_DEPS:-1}" = 1 ] ;;
      *urllib*)
        [ -f "$STATE_DIR/backend_up" ] ;;
      *pathlib*)
        # Home-folder lookup, only made for a Windows python.exe.
        [ -n "${FAKE_WIN_HOME:-}" ] || exit 5
        printf '%s\r\n' "$FAKE_WIN_HOME" ;;
      *sqlite3*)
        [ "${FAKE_SQLITE_FAIL:-0}" = 1 ] && exit 4
        db="${*: -1}"
        # Only touch POSIX paths; under the python.exe test it's a Windows path.
        if [[ "$db" == /* ]]; then printf 'SQLite format 3\0' > "$db"; fi ;;
      backend/app.py)
        log "backend env BOJAI_HOME=${BOJAI_HOME:-} WSLENV=${WSLENV:-}"
        if [ "${FAKE_BACKEND_CRASH:-0}" = 1 ]; then
          log "backend crashed"
          exit 3
        fi
        sleep 30 >/dev/null 2>&1 &
        trap 'kill $! 2>/dev/null; log "backend stopped"; exit 0' TERM
        touch "$STATE_DIR/backend_up"
        wait $!
        log "backend was never stopped" ;;
      *)
        echo "unexpected python call: $*" >&2
        exit 99 ;;
    esac
"""

NPM_STUB = """
    #!/usr/bin/env bash
    log() { printf '%s\n' "$*" > "$CALLS_DIR/$(date +%s%N)-$$-$RANDOM"; }
    log "npm $*"
    if [ "$1" = install ]; then mkdir -p node_modules; fi
    if [ "$1" = run ]; then
      touch "$STATE_DIR/frontend_up"
      if [ -n "${FAKE_NPM_SLEEP:-}" ]; then
        # Output redirected so an orphaned sleep can't hold the test's pipes open.
        sleep "$FAKE_NPM_SLEEP" >/dev/null 2>&1 &
        trap 'kill $! 2>/dev/null; exit 143' TERM
        wait $!
      fi
    fi
    exit "${FAKE_NPM_EXIT:-0}"
"""

CMD_EXE_STUB = """
    #!/usr/bin/env bash
    log() { printf '%s\n' "$*" > "$CALLS_DIR/$(date +%s%N)-$$-$RANDOM"; }
    log "cmd.exe $*"
    [ "$1" = /c ] && [ "$2" = npm ] || exit 98
    shift 2
    if [ "$1" = install ]; then mkdir -p node_modules; fi
    exit "${FAKE_NPM_EXIT:-0}"
"""

POWERSHELL_STUB = """
    #!/usr/bin/env bash
    log() { printf '%s\n' "$*" > "$CALLS_DIR/$(date +%s%N)-$$-$RANDOM"; }
    log "powershell.exe $*"
"""


class Harness:
    def __init__(self, tmp_path: Path, shell: Shell):
        self.shell = shell
        self.posix = shell.posix
        self.project = tmp_path / "project"
        self.bin = tmp_path / "bin"
        self.state = tmp_path / "state"
        self.calls_dir = tmp_path / "calls"
        for d in (self.project / "backend", self.project / "frontend" / "node_modules",
                  self.bin, self.state, self.calls_dir):
            d.mkdir(parents=True)
        shutil.copy(SCRIPT, self.project / "run_app_locally.sh")
        (self.project / "backend" / "app.py").write_text("# not executed; python is stubbed\n")
        _write_exe(self.bin / "python", PYTHON_STUB)

    def add_unix_npm(self):
        _write_exe(self.bin / "npm", NPM_STUB)
        _write_exe(self.bin / "node", "#!/usr/bin/env bash\n")

    def add_windows_npm(self):
        # Mirrors WSL with only a Windows Node install: npm exists but `node`
        # does not, so the script must go through `cmd.exe /c npm`.
        _write_exe(self.bin / "npm", NPM_STUB)
        _write_exe(self.bin / "npm.cmd", "#!/usr/bin/env bash\n")
        _write_exe(self.bin / "cmd.exe", CMD_EXE_STUB)
        _write_exe(self.bin / "powershell.exe", POWERSHELL_STUB)

    def run(self, timeout=30, signal_after_backend_up=None, **env):
        # PATH is limited to the stubs plus system dirs so a real npm/node/python
        # install can't leak in. HOME and USER point the script's fallback
        # interpreter lookups at paths that don't exist.
        variables = {
            "PATH": f"{self.posix(self.bin)}:/usr/bin:/bin",
            "HOME": self.posix(self.state),
            "USER": "nobody-test-user",
            "CALLS_DIR": self.posix(self.calls_dir),
            "STATE_DIR": self.posix(self.state),
            **env,
        }
        # Pass a variable as None to leave it unset (e.g. USER, as in Git Bash).
        assignments = " ".join(f"{k}='{v}'" for k, v in variables.items() if v is not None)
        cd = f"cd '{self.posix(self.project)}' || exit 97"
        script = f"env -i {assignments} bash ./run_app_locally.sh"
        command = f"{cd}; {script}"
        if signal_after_backend_up:
            # Like pressing Ctrl+C / closing the terminal once the app is up.
            # `cd` stays out of the backgrounded command: `cd x && script &`
            # would background a subshell, and $! would not be the script.
            frontend_up = f"{self.posix(self.state)}/frontend_up"
            command = (
                f"{cd}; {script} & pid=$!; "
                f"for _ in $(seq 1 100); do [ -f '{frontend_up}' ] && break; sleep 0.2; done; "
                f"kill -{signal_after_backend_up} $pid; wait $pid"
            )
        result = self.shell.run(command, timeout=timeout)
        # Give the EXIT trap's kill a moment to land in the stub's log.
        result.calls = self._calls_after_settling()
        return result

    def calls(self):
        return [f.read_text().rstrip("\n") for f in sorted(self.calls_dir.iterdir())]

    def _calls_after_settling(self):
        for _ in range(20):
            calls = self.calls()
            if "backend stopped" in calls or "python backend/app.py" not in calls:
                return calls
            time.sleep(0.1)
        return self.calls()


def _explain(result):
    return (
        f"\nexit code: {result.returncode}"
        f"\n--- stdout ---\n{result.stdout}"
        f"\n--- stderr ---\n{result.stderr}"
        f"\n--- calls ---\n" + "\n".join(result.calls)
    )


@pytest.fixture(params=SHELLS, ids=lambda shell: shell.name)
def harness(request, tmp_path):
    return Harness(tmp_path, request.param)


# ─────────────────────────────────────────────────────────────────────────────
# Behaviour checks
# ─────────────────────────────────────────────────────────────────────────────

@needs_bash
@pytest.mark.parametrize("shell", SHELLS, ids=lambda shell: shell.name)
def test_script_passes_bash_syntax_check(shell):
    result = shell.run(f"bash -n '{shell.posix(SCRIPT)}'")
    assert result.returncode == 0, result.stderr


def test_happy_path_starts_backend_then_frontend_and_stops_backend(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    calls = result.calls

    assert result.returncode == 0, _explain(result)
    assert "Backend is up." in result.stdout, _explain(result)
    dev_call = f"npm run dev -- --port {FRONTEND_PORT} --strictPort --open"
    assert dev_call in calls, _explain(result)
    assert calls.index("python backend/app.py") < calls.index(dev_call), _explain(result)
    # The frontend must not start until a health check has succeeded.
    health_checks = [i for i, c in enumerate(calls) if "urllib" in c]
    assert health_checks and health_checks[0] < calls.index(dev_call), _explain(result)
    assert "npm install" not in calls, _explain(result)


def test_backend_is_stopped_when_frontend_exits(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    assert "backend stopped" in result.calls, (
        "the backend kept running after the script exited" + _explain(result)
    )
    assert "backend was never stopped" not in result.calls, _explain(result)


def test_health_check_targets_backend_docs_url(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    assert any(f"http://127.0.0.1:{BACKEND_PORT}/docs" in c for c in result.calls), _explain(result)


def test_installs_frontend_dependencies_when_node_modules_missing(harness):
    harness.add_unix_npm()
    shutil.rmtree(harness.project / "frontend" / "node_modules")
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    calls = result.calls

    assert result.returncode == 0, _explain(result)
    assert "npm install" in calls, _explain(result)
    dev_call = f"npm run dev -- --port {FRONTEND_PORT} --strictPort --open"
    assert calls.index("npm install") < calls.index(dev_call), _explain(result)


def test_fails_fast_when_backend_crashes_on_startup(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"), FAKE_BACKEND_CRASH="1")

    assert result.returncode == 1, _explain(result)
    assert "Backend exited during startup." in result.stderr, _explain(result)
    assert not any(c.startswith("npm") for c in result.calls), (
        "frontend was started even though the backend died" + _explain(result)
    )


def test_fails_when_no_python_has_backend_dependencies(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"), FAKE_PYTHON_HAS_DEPS="0")

    assert result.returncode == 1, _explain(result)
    assert "No Python with fastapi + uvicorn found" in result.stderr, _explain(result)
    assert "python backend/app.py" not in result.calls, _explain(result)


def test_finds_python_on_path_without_PYTHON_override(harness):
    harness.add_unix_npm()
    result = harness.run()
    assert result.returncode == 0, _explain(result)
    assert "python backend/app.py" in result.calls, _explain(result)


def test_fails_when_npm_is_missing(harness):
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))

    assert result.returncode == 1, _explain(result)
    assert "npm/node not found on PATH." in result.stderr, _explain(result)
    assert "python backend/app.py" not in result.calls, _explain(result)


def test_uses_windows_npm_through_cmd_exe_when_node_missing(harness):
    harness.add_windows_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    calls = result.calls

    assert result.returncode == 0, _explain(result)
    assert f"cmd.exe /c npm run dev -- --port {FRONTEND_PORT} --strictPort --open" in calls, _explain(result)
    assert not any(c.startswith("npm ") for c in calls), (
        "the Linux npm shim was used without a `node` binary" + _explain(result)
    )


def test_windows_cleanup_kills_the_npm_dev_process_tree(harness):
    harness.add_windows_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))

    cleanup = [c for c in result.calls if c.startswith("powershell.exe")]
    assert cleanup, "no Windows-side cleanup ran, Vite would be left running" + _explain(result)
    assert "npm-cli.js* run dev*--port " + str(FRONTEND_PORT) in cleanup[0], _explain(result)
    assert "taskkill /T /F" in cleanup[0], _explain(result)


def test_unix_path_skips_windows_cleanup(harness):
    harness.add_unix_npm()
    _write_exe(harness.bin / "powershell.exe", POWERSHELL_STUB)
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    assert not any(c.startswith("powershell.exe") for c in result.calls), _explain(result)


def test_frontend_failure_exit_code_is_propagated_and_backend_still_stopped(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"), FAKE_NPM_EXIT="7")

    assert result.returncode == 7, _explain(result)
    assert "backend stopped" in result.calls, _explain(result)


# ─────────────────────────────────────────────────────────────────────────────
# Local data folder (~/.bojai)
# ─────────────────────────────────────────────────────────────────────────────

def _sqlite_calls(calls):
    return [c for c in calls if c.startswith("python") and "sqlite3" in c]


def test_db_init_snippet_creates_a_valid_sqlite_database(tmp_path):
    # Runs the script's own inline Python for real, so a broken snippet shows
    # up here rather than as a stubbed-out call.
    import sqlite3
    import sys

    match = re.search(r'"\$PY" -c "(import sqlite3[^"]*)"', SCRIPT.read_text())
    assert match, "could not find the sqlite3 init snippet in run_app_locally.sh"
    db = tmp_path / "bojai.db"
    subprocess.run([sys.executable, "-c", match.group(1), str(db)], check=True, timeout=30)

    assert db.read_bytes().startswith(b"SQLite format 3\x00"), "file is not a SQLite database"
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_creates_bojai_home_with_db_files_and_cache(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    home = harness.state / ".bojai"

    assert result.returncode == 0, _explain(result)
    assert (home / "files").is_dir(), _explain(result)
    assert (home / "cache").is_dir(), _explain(result)
    assert (home / "bojai.db").is_file(), _explain(result)
    assert _sqlite_calls(result.calls)[0].endswith(harness.posix(home / "bojai.db")), _explain(result)
    assert f"Using data folder {harness.posix(home)}" in result.stdout, _explain(result)


def test_data_folder_is_ready_before_backend_starts(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))
    calls = result.calls

    db_init = calls.index(_sqlite_calls(calls)[0])
    assert db_init < calls.index("python backend/app.py"), _explain(result)


def test_existing_db_is_not_recreated_or_overwritten(harness):
    harness.add_unix_npm()
    home = harness.state / ".bojai"
    home.mkdir()
    (home / "bojai.db").write_bytes(b"existing data")

    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))

    assert result.returncode == 0, _explain(result)
    assert (home / "bojai.db").read_bytes() == b"existing data"
    assert not _sqlite_calls(result.calls), _explain(result)
    # Missing subfolders are still filled in around an existing db.
    assert (home / "files").is_dir() and (home / "cache").is_dir(), _explain(result)


def test_existing_files_and_cache_contents_are_kept(harness):
    harness.add_unix_npm()
    home = harness.state / ".bojai"
    (home / "files").mkdir(parents=True)
    (home / "cache").mkdir()
    (home / "files" / "upload.csv").write_text("a,b\n")
    (home / "cache" / "entry").write_text("cached")

    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))

    assert result.returncode == 0, _explain(result)
    assert (home / "files" / "upload.csv").read_text() == "a,b\n"
    assert (home / "cache" / "entry").read_text() == "cached"


def test_bojai_home_override_is_used_and_passed_to_backend(harness):
    harness.add_unix_npm()
    custom = harness.state / "custom-data"
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"), BOJAI_HOME=harness.posix(custom))

    assert result.returncode == 0, _explain(result)
    assert (custom / "bojai.db").is_file(), _explain(result)
    assert (custom / "files").is_dir() and (custom / "cache").is_dir(), _explain(result)
    assert not (harness.state / ".bojai").exists(), _explain(result)
    backend_env = next(c for c in result.calls if c.startswith("backend env"))
    assert f"BOJAI_HOME={harness.posix(custom)} " in backend_env, _explain(result)


def test_backend_receives_default_bojai_home(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"))

    backend_env = next(c for c in result.calls if c.startswith("backend env"))
    assert f"BOJAI_HOME={harness.posix(harness.state / '.bojai')} " in backend_env, _explain(result)
    assert backend_env.endswith("WSLENV="), "WSLENV should only be set for python.exe" + _explain(result)


def _windows_path(harness, path: Path):
    """Windows form of `path` via wslpath, or None outside WSL."""
    result = harness.shell.run(f"wslpath -w '{harness.posix(path)}'")
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


@pytest.fixture
def windows_python(harness):
    """Simulates WSL + Windows conda: PYTHON is a python.exe whose home is
    harness.state (in Windows form), while the Linux $HOME is elsewhere."""
    win_home = _windows_path(harness, harness.state)
    if win_home is None:
        pytest.skip("wslpath not available (not running under WSL)")
    harness.add_unix_npm()
    _write_exe(harness.bin / "python.exe", PYTHON_STUB)
    linux_home = harness.state / "linux-home"
    linux_home.mkdir()
    return {
        "PYTHON": harness.posix(harness.bin / "python.exe"),
        "FAKE_WIN_HOME": win_home,
        "HOME": harness.posix(linux_home),
    }


def test_windows_python_uses_windows_home_not_wsl_home(harness, windows_python):
    result = harness.run(**windows_python)
    home = harness.state / ".bojai"

    assert result.returncode == 0, _explain(result)
    assert (home / "files").is_dir() and (home / "cache").is_dir(), _explain(result)
    assert not (harness.state / "linux-home" / ".bojai").exists(), (
        "data folder went to the WSL home; a Windows backend can't lock SQLite there"
        + _explain(result)
    )
    # The db path handed to python.exe must be in Windows form.
    sqlite_call = _sqlite_calls(result.calls)[0]
    assert sqlite_call.endswith(_windows_path(harness, home / "bojai.db")), _explain(result)


def test_windows_python_home_lookup_failure_aborts(harness, windows_python):
    result = harness.run(**{**windows_python, "FAKE_WIN_HOME": ""})

    assert result.returncode == 1, _explain(result)
    assert "Could not determine the backend's home folder" in result.stderr, _explain(result)
    assert "python backend/app.py" not in result.calls, _explain(result)


def test_windows_python_gets_bojai_home_forwarded_through_wslenv(harness, windows_python):
    # A python.exe launched from WSL doesn't see Linux env vars unless they're
    # listed in WSLENV; /p translates the path to Windows form.
    result = harness.run(**windows_python)

    assert result.returncode == 0, _explain(result)
    backend_env = next(c for c in result.calls if c.startswith("backend env"))
    assert "BOJAI_HOME/p" in backend_env.split("WSLENV=", 1)[1].split(":"), _explain(result)


def test_db_creation_failure_aborts_before_backend_starts(harness):
    harness.add_unix_npm()
    result = harness.run(PYTHON=harness.posix(harness.bin / "python"), FAKE_SQLITE_FAIL="1")

    assert result.returncode != 0, _explain(result)
    assert "python backend/app.py" not in result.calls, _explain(result)
    assert not any(c.startswith("npm") for c in result.calls), _explain(result)


# ─────────────────────────────────────────────────────────────────────────────
# Shell environment quirks and shutdown
# ─────────────────────────────────────────────────────────────────────────────

def test_works_when_USER_is_unset(harness):
    # Git Bash sets USERNAME but not USER; with `set -u` a bare $USER used to
    # abort the interpreter search with "USER: unbound variable", which then
    # surfaced as a misleading "No Python with fastapi + uvicorn found".
    harness.add_unix_npm()
    result = harness.run(USER=None, USERNAME="someone")

    assert result.returncode == 0, _explain(result)
    assert "unbound variable" not in result.stderr, _explain(result)
    assert "python backend/app.py" in result.calls, _explain(result)


def test_sigterm_stops_backend_and_frontend_once(harness):
    harness.add_unix_npm()
    # Keep the frontend running until the script is signalled.
    result = harness.run(
        PYTHON=harness.posix(harness.bin / "python"), FAKE_NPM_SLEEP="30",
        signal_after_backend_up="TERM",
    )

    assert result.returncode == 143, _explain(result)
    assert "backend stopped" in result.calls, _explain(result)
    assert result.stdout.count("Stopping backend...") == 1, (
        "cleanup ran more than once" + _explain(result)
    )
    assert result.stdout.count("Stopping frontend...") == 1, _explain(result)
