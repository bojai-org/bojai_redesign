import pytest

from code_safety import ALLOWED_IMPORTS, CodeValidationError, CodeValidator


@pytest.fixture
def validator():
    return CodeValidator()


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_code_accepts_a_plain_method(validator):
    code = "def pre(self):\n    return {'a': 1}"
    sanitized = validator.confirm_code(code, function_name="pre", extra_params=0)
    assert "def pre(self):" in sanitized
    assert "return {'a': 1}" in sanitized


def test_confirm_code_accepts_extra_params(validator):
    code = "def post(self, response):\n    return response.strip()"
    sanitized = validator.confirm_code(code, function_name="post", extra_params=1)
    assert "def post(self, response):" in sanitized


def test_confirm_code_strips_everything_except_the_target_function(validator):
    code = (
        "x = 1\n"
        "def other(self):\n    return 2\n"
        "def pre(self):\n    return x\n"
    )
    sanitized = validator.confirm_code(code, function_name="pre", extra_params=0)
    assert "def pre" in sanitized
    assert "def other" not in sanitized
    assert "x = 1" not in sanitized


def test_confirm_code_allows_a_nested_allowed_import():
    validator = CodeValidator()
    code = "def post(self, response):\n    import re\n    return re.sub('a', 'b', response)"
    sanitized = validator.confirm_code(code, function_name="post", extra_params=1)
    assert "import re" in sanitized


@pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS))
def test_every_allowed_import_is_accepted(validator, module):
    code = f"def pre(self):\n    import {module}\n    return {{}}"
    validator.confirm_code(code, function_name="pre", extra_params=0)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Rejections
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_code_rejects_syntax_error(validator):
    with pytest.raises(CodeValidationError, match="Could not parse"):
        validator.confirm_code("def pre(self):\n    return (", function_name="pre", extra_params=0)


def test_confirm_code_rejects_missing_function(validator):
    with pytest.raises(CodeValidationError, match="exactly one top-level function"):
        validator.confirm_code("def other(self):\n    return 1", function_name="pre", extra_params=0)


def test_confirm_code_rejects_wrong_function_name(validator):
    with pytest.raises(CodeValidationError, match="exactly one top-level function"):
        validator.confirm_code("def wrong(self):\n    return 1", function_name="pre", extra_params=0)


def test_confirm_code_rejects_duplicate_function_names(validator):
    code = "def pre(self):\n    return 1\ndef pre(self):\n    return 2"
    with pytest.raises(CodeValidationError, match="exactly one top-level function"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


@pytest.mark.parametrize(
    "code",
    [
        "def pre():\n    return 1",  # missing self entirely
        "def pre(request):\n    return 1",  # wrong first param name
    ],
)
def test_confirm_code_rejects_missing_self(validator, code):
    with pytest.raises(CodeValidationError, match="must take 'self'"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_wrong_param_count(validator):
    code = "def post(self, response, extra):\n    return response"
    with pytest.raises(CodeValidationError, match="exactly 1 parameter"):
        validator.confirm_code(code, function_name="post", extra_params=1)


@pytest.mark.parametrize(
    "code",
    [
        "def pre(self, *args):\n    return {}",
        "def pre(self, **kwargs):\n    return {}",
        "def pre(self, *, only_kw=1):\n    return {}",
    ],
)
def test_confirm_code_rejects_variadic_and_keyword_only_params(validator, code):
    with pytest.raises(CodeValidationError, match="plain positional parameters"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_disallowed_top_level_import(validator):
    code = "import os\ndef pre(self):\n    return os.getcwd()"
    with pytest.raises(CodeValidationError, match="Import 'os' is not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_disallowed_nested_import(validator):
    code = "def pre(self):\n    import subprocess\n    return {}"
    with pytest.raises(CodeValidationError, match="Import 'subprocess' is not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_disallowed_import_from(validator):
    code = "def pre(self):\n    from os import path\n    return {}"
    with pytest.raises(CodeValidationError, match="Import 'os' is not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


@pytest.mark.parametrize(
    "call",
    ["eval('1')", "exec('1')", "open('f')", "compile('1', '', 'eval')", "__import__('os')",
     "globals()", "locals()", "vars()", "dir()", "getattr(self, 'x')", "setattr(self, 'x', 1)",
     "breakpoint()", "input()", "exit()"],
)
def test_confirm_code_rejects_forbidden_calls(validator, call):
    code = f"def pre(self):\n    {call}\n    return {{}}"
    with pytest.raises(CodeValidationError, match="Forbidden call"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_forbidden_attribute_call(validator):
    code = "def pre(self):\n    self.__dict__.setattr('a', 1)\n    return {}"
    with pytest.raises(CodeValidationError):
        validator.confirm_code(code, function_name="pre", extra_params=0)


@pytest.mark.parametrize("stmt", ["global x", "nonlocal x"])
def test_confirm_code_rejects_global_and_nonlocal(validator, stmt):
    code = f"def pre(self):\n    {stmt}\n    return {{}}"
    with pytest.raises(CodeValidationError, match="global/nonlocal"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_decorators(validator):
    code = "@staticmethod\ndef pre(self):\n    return {}"
    with pytest.raises(CodeValidationError, match="Decorators are not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_decorator_on_nested_function(validator):
    code = (
        "def pre(self):\n"
        "    @staticmethod\n"
        "    def helper():\n"
        "        return 1\n"
        "    return helper()\n"
    )
    with pytest.raises(CodeValidationError, match="Decorators are not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_default_arguments(validator):
    code = "def pre(self, x=1):\n    return {}"
    # extra_params mismatch would also fire; use extra_params=1 to isolate the default-arg guard
    with pytest.raises(CodeValidationError, match="Default arguments are not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=1)


@pytest.mark.parametrize(
    "expr",
    [
        "self.__class__",
        "self.__class__.__bases__",
        "().__class__.__bases__[0].__subclasses__()",
        "type(self).__mro__",
        "self.__dict__",
    ],
)
def test_confirm_code_rejects_dunder_attribute_access(validator, expr):
    code = f"def pre(self):\n    x = {expr}\n    return {{}}"
    with pytest.raises(CodeValidationError, match="not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)


def test_confirm_code_rejects_bare_dunder_name(validator):
    code = "def pre(self):\n    return __name__"
    with pytest.raises(CodeValidationError, match="not allowed"):
        validator.confirm_code(code, function_name="pre", extra_params=0)
