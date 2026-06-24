import pytest
import json
import subprocess
from unittest.mock import patch, MagicMock
from build.data.utils import CodeRunner, CodeValidator

pytestmark = pytest.mark.data


@pytest.fixture
def runner():
    return CodeRunner()


@pytest.fixture
def validator():
    return CodeValidator()


def make_answer(code: str) -> dict:
    return {"code": code}


# ── confirm_code — Guard 1: build function required ───────────────────────────

class TestGuard1BuildFunction:
    def test_accepts_code_with_build(self, validator):
        result = validator.confirm_code(make_answer("def build(data):\n    return data"))
        assert "def build" in result

    def test_rejects_code_without_build(self, validator):
        with pytest.raises(ValueError, match="build"):
            validator.confirm_code(make_answer("def process(data):\n    return data"))

    def test_rejects_empty_code(self, validator):
        with pytest.raises(ValueError, match="build"):
            validator.confirm_code(make_answer(""))

    def test_build_inside_class_counts(self, validator):
        # build must be a top-level or nested FunctionDef - ast.walk finds all
        code = "class X:\n    def build(self, data):\n        return data"
        result = validator.confirm_code(make_answer(code))
        assert result is not None


# ── confirm_code — Guard 2: allowed imports ───────────────────────────────────

class TestGuard2Imports:
    def test_accepts_allowed_import(self, validator):
        code = "import numpy\ndef build(data):\n    return numpy.array(data)"
        validator.confirm_code(make_answer(code))

    def test_accepts_allowed_from_import(self, validator):
        code = "from collections import defaultdict\ndef build(data):\n    return data"
        validator.confirm_code(make_answer(code))

    def test_rejects_os_import(self, validator):
        with pytest.raises(ValueError, match="not allowed"):
            validator.confirm_code(make_answer("import os\ndef build(d): return d"))

    def test_rejects_sys_import(self, validator):
        with pytest.raises(ValueError, match="not allowed"):
            validator.confirm_code(make_answer("import sys\ndef build(d): return d"))

    def test_rejects_subprocess_import(self, validator):
        with pytest.raises(ValueError, match="not allowed"):
            validator.confirm_code(make_answer("import subprocess\ndef build(d): return d"))

    def test_rejects_from_os_import(self, validator):
        with pytest.raises(ValueError, match="not allowed"):
            validator.confirm_code(make_answer("from os import path\ndef build(d): return d"))


# ── confirm_code — Guard 3a: forbidden calls ──────────────────────────────────

class TestGuard3aForbiddenCalls:
    def test_rejects_exec(self, validator):
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    exec('x')\n    return d"))

    def test_rejects_eval(self, validator):
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    eval('x')\n    return d"))

    def test_rejects_open(self, validator):
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    open('f')\n    return d"))

    def test_rejects_getattr(self, validator):
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    getattr(d, 'x')\n    return d"))

    def test_rejects_attribute_call_matching_forbidden(self, validator):
        # obj.eval(...) — attribute call
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    d.eval('x')\n    return d"))

    def test_rejects_breakpoint(self, validator):
        with pytest.raises(ValueError, match="Forbidden"):
            validator.confirm_code(make_answer("def build(d):\n    breakpoint()\n    return d"))


# ── confirm_code — Guard 3b: forbidden keywords ───────────────────────────────

class TestGuard3bForbiddenKeywords:
    def test_rejects_global(self, validator):
        with pytest.raises(ValueError, match="global"):
            validator.confirm_code(make_answer("x = 0\ndef build(d):\n    global x\n    return d"))

    def test_rejects_nonlocal(self, validator):
        code = "def build(d):\n    x = 1\n    def inner():\n        nonlocal x\n    return d"
        with pytest.raises(ValueError, match="nonlocal"):
            validator.confirm_code(make_answer(code))


# ── confirm_code — Guard 3c: decorators ──────────────────────────────────────

class TestGuard3cDecorators:
    def test_rejects_decorator_on_build(self, validator):
        code = "@staticmethod\ndef build(data):\n    return data"
        with pytest.raises(ValueError, match="Decorators"):
            validator.confirm_code(make_answer(code))

    def test_rejects_decorator_on_helper_function(self, validator):
        code = "@staticmethod\ndef helper():\n    pass\ndef build(d):\n    return d"
        with pytest.raises(ValueError, match="Decorators"):
            validator.confirm_code(make_answer(code))


# ── confirm_code — Guard 3d: default arguments ────────────────────────────────

class TestGuard3dDefaultArguments:
    def test_rejects_default_positional_arg(self, validator):
        code = "def build(data, x=10):\n    return data"
        with pytest.raises(ValueError, match="Default arguments"):
            validator.confirm_code(make_answer(code))

    def test_rejects_default_in_helper(self, validator):
        code = "def helper(x=1):\n    pass\ndef build(data):\n    return data"
        with pytest.raises(ValueError, match="Default arguments"):
            validator.confirm_code(make_answer(code))

    def test_allows_no_defaults(self, validator):
        validator.confirm_code(make_answer("def build(data):\n    return data"))


# ── confirm_code — Guard 4: strips top-level non-functions ────────────────────

class TestGuard4Strip:
    def test_strips_top_level_assignments(self, validator):
        code = "SECRET = 'abc'\ndef build(data):\n    return data"
        result = validator.confirm_code(make_answer(code))
        assert "SECRET" not in result

    def test_strips_top_level_expressions(self, validator):
        code = "print('hi')\ndef build(data):\n    return data"
        result = validator.confirm_code(make_answer(code))
        assert "print" not in result

    def test_keeps_all_function_definitions(self, validator):
        code = "def helper(x):\n    return x\ndef build(data):\n    return helper(data)"
        result = validator.confirm_code(make_answer(code))
        assert "def helper" in result
        assert "def build" in result

    def test_returns_string(self, validator):
        result = validator.confirm_code(make_answer("def build(data):\n    return data"))
        assert isinstance(result, str)


# ── run_code — integration ────────────────────────────────────────────────────

class TestRunCode:
    def test_runs_build_and_returns_result(self, runner):
        code = "def build(data):\n    return {'input': [x * 2 for x in data]}"
        result = runner.run_code(code, [1, 2, 3])
        assert result == {"input": [2, 4, 6]}

    def test_passes_none_input_when_not_provided(self, runner):
        code = "def build(data):\n    return {'input': [], 'received': data is None}"
        result = runner.run_code(code)
        assert result["received"] is True

    def test_raises_runtime_error_on_subprocess_failure(self, runner):
        code = "def build(data):\n    raise RuntimeError('boom')"
        with pytest.raises(RuntimeError):
            runner.run_code(code, [])

    def test_raises_on_timeout(self, runner):
        code = "def build(data):\n    import time\n    time.sleep(60)"
        with pytest.raises(subprocess.TimeoutExpired):
            runner.run_code(code, [], timeout=1)
