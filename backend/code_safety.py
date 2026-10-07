"""
BojAI Build — Code Validation for User-Submitted Agent Methods

Static AST analysis gate for source text a caller (eventually a UI) supplies
as the body of one of an Agent's four required methods -- see
new_agent_builder.py, which is the only current caller.

This is an adaptation, not a copy, of the pre-redesign `build/data/utils.py:
CodeValidator` (see backend/contract.md's history and the project README for
that design): the original validated a single `build(data)` function meant
to run once, in an isolated subprocess capped on memory/CPU/wall-clock, as
part of a data pipeline. What's validated here becomes a real *method* on a
dynamically-compiled `Agent` subclass (new_agent_builder.compiler) -- called
directly, in-process, as often as the pipeline calls `pre()`/`post()`/etc.
That's a different execution shape with no subprocess wall backing it up, so
two guards are added on top of the original set:

- Signature checking: a method must declare exactly the parameters
  base_classes.Agent will actually call it with (``self`` plus zero or one
  more, per method) -- not a safety guard against malice so much as against
  a TypeError surfacing confusingly deep inside Agent.run()'s retry loop.
- Dunder identifier rejection: any ``__dunder__`` name or attribute access
  is rejected outright. The original relied on FORBIDDEN_CALLS
  (getattr/setattr/vars/dir/...) to block *dynamic*, string-based attribute
  access; it did not need to block *literal* dunder syntax like
  ``x.__class__`` because CodeRunner's subprocess plus OS resource limits
  were the real backstop. Without that backstop here, the classic
  no-import-needed sandbox-escape family (``().__class__.__bases__[0]
  .__subclasses__()`` and friends) has to be closed at the AST level
  instead.

ALLOWED_IMPORTS is also re-scoped: the original was an ML/data-pipeline
package allowlist (numpy, pandas, torch, ...) appropriate for a `build()`
function reshaping a user's dataset. An Agent's pre/post/specify_output
methods only ever handle text, JSON, and the shared pipeline-state dict, so
this module's allowlist is the much smaller set of standard-library modules
that are actually useful for that (and have no filesystem/process/network
surface at all).
"""

from __future__ import annotations

import ast


class CodeValidationError(ValueError):
    """Raised when submitted method source fails an AST safety guard."""


ALLOWED_IMPORTS = {
    "re", "json", "math", "statistics", "decimal", "fractions",
    "datetime", "calendar", "time",
    "itertools", "functools", "operator", "collections", "heapq",
    "string", "textwrap", "typing", "dataclasses", "copy", "enum",
}

FORBIDDEN_CALLS = {
    "exec", "eval", "open", "compile", "__import__",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "breakpoint", "input", "exit", "quit",
    "__builtins__", "memoryview",
}

_FORBIDDEN_STATEMENT_TYPES = (ast.Global, ast.Nonlocal)


class CodeValidator:
    """Mixin/helper adding ``confirm_code`` -- the single AST validation entry point.

    Mirrors the shape of the original CodeValidator (a plain method other
    classes mix in or hold an instance of) rather than a set of free
    functions, for the same reason it was one there: callers that need to
    validate several related pieces of code (here, an agent's four methods)
    share one validator instance and one consistent error type.
    """

    def confirm_code(self, code: str, *, function_name: str, extra_params: int) -> str:
        """Validate *code* as the body of a method named *function_name*.

        *extra_params* is how many parameters the method takes besides
        ``self`` (0 for ``pre``/``specify_output``, 1 for
        ``post``/``post_fallback``). Returns the sanitized source -- just the
        one matching top-level function definition, everything else in the
        submitted text stripped away -- ready to ``exec()`` into a namespace.

        Raises CodeValidationError on any guard failure.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise CodeValidationError(
                f"Could not parse source for '{function_name}': {exc}"
            ) from exc

        function_def = self._find_target_function(tree, function_name)
        self._check_signature(function_def, function_name, extra_params)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._check_import(node, function_name)
            elif isinstance(node, ast.Call):
                self._check_call(node, function_name)
            elif isinstance(node, _FORBIDDEN_STATEMENT_TYPES):
                raise CodeValidationError(
                    f"'{function_name}' may not use global/nonlocal."
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_def(node)
            elif isinstance(node, ast.Attribute):
                self._check_dunder(node.attr, function_name)
            elif isinstance(node, ast.Name):
                self._check_dunder(node.id, function_name)

        # Strip everything except the one function this method is for --
        # any second top-level statement (a stray helper, an import the
        # walk above already validated, a bare expression) is dropped from
        # the sanitized output. A helper the method body needs must be
        # nested inside it; a needed import must be written inside it too.
        tree.body = [function_def]
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)

    def _find_target_function(self, tree: ast.Module, function_name: str) -> ast.FunctionDef:
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        ]
        if len(matches) != 1:
            raise CodeValidationError(
                f"Source must define exactly one top-level function named "
                f"'{function_name}' (found {len(matches)})."
            )
        return matches[0]

    def _check_signature(
        self, function_def: ast.FunctionDef, function_name: str, extra_params: int
    ) -> None:
        args = function_def.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
            raise CodeValidationError(
                f"'{function_name}' must take only plain positional parameters "
                "(no *args, **kwargs, or keyword-only parameters)."
            )
        params = [a.arg for a in args.args]
        if not params or params[0] != "self":
            raise CodeValidationError(
                f"'{function_name}' must take 'self' as its first parameter."
            )
        if len(params) - 1 != extra_params:
            raise CodeValidationError(
                f"'{function_name}' must take exactly {extra_params} parameter(s) "
                f"besides 'self' (found {len(params) - 1})."
            )

    def _check_import(self, node: ast.Import | ast.ImportFrom, function_name: str) -> None:
        if isinstance(node, ast.Import):
            top_levels = [alias.name.split(".")[0] for alias in node.names]
        else:
            top_levels = [(node.module or "").split(".")[0]]
        for top_level in top_levels:
            if top_level not in ALLOWED_IMPORTS:
                raise CodeValidationError(
                    f"Import '{top_level}' is not allowed in '{function_name}'."
                )

    def _check_call(self, node: ast.Call, function_name: str) -> None:
        target = None
        if isinstance(node.func, ast.Name):
            target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target = node.func.attr
        if target in FORBIDDEN_CALLS:
            raise CodeValidationError(
                f"Forbidden call '{target}' in '{function_name}'."
            )

    def _check_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.decorator_list:
            raise CodeValidationError(
                f"Decorators are not allowed (found on '{node.name}')."
            )
        if node.args.defaults or node.args.kw_defaults:
            raise CodeValidationError(
                f"Default arguments are not allowed in '{node.name}'."
            )

    def _check_dunder(self, identifier: str, function_name: str) -> None:
        if identifier.startswith("__") and identifier.endswith("__"):
            raise CodeValidationError(
                f"Access to '{identifier}' is not allowed in '{function_name}'."
            )
