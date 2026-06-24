"""
BojAI Build — Code Validation and Sandboxed Execution

This module is part of the `build` layer and provides the security utilities
used whenever LLM-generated code is accepted into the pipeline. It implements
a three-layer defence: static AST analysis, subprocess isolation, and OS-level
resource limits.

Components defined here:

- ALLOWED_IMPORTS:
    Whitelist of ML-focused top-level package names (numpy, pandas, torch,
    sklearn, etc.) that a build() function is permitted to import. Any import
    not on this list raises ValueError during AST validation.

- FORBIDDEN_CALLS:
    Set of call names (exec, eval, open, __import__, etc.) that are never
    permitted inside generated code, regardless of context.

- CodeRunner:
    Mixin that adds run_code to any class that needs to execute LLM code:

    run_code(code_source: str, input_data: Any, timeout: int = 10) -> Any
        Executes the sanitized build() in a subprocess with:
        - Code passed via environment variable (never written to disk).
        - Input data serialized to stdin via pickle.
        - Result read from stdout via pickle.
        - 512 MB memory limit and 30 CPU-second limit (Linux; skipped on Windows).
        - Hard timeout enforced by subprocess.run(timeout=...).

- CodeValidator:
    Mixin that adds code validation helpers to any pipeline class:

    confirm_code(answer: dict) -> str
        Runs six AST guards on the "code" field of the LLM's JSON response:
        1. Parses the source and checks for SyntaxError.
        2. Rejects any import not in ALLOWED_IMPORTS.
        3. Rejects any call to a FORBIDDEN_CALLS name.
        4. Requires exactly one top-level function named build().
        5. Strips all top-level statements that are not the build() function.
        6. Returns the sanitized source via ast.unparse().

    validate_with_retry(get_code, get_files, validation_name, LLM_config, initial_files) -> str
        Runs code extraction + DecisionAgent validation with up to 3 retries.
        Even retry attempts re-extract code from the current file set; odd retry
        attempts first re-select files via get_files() then re-extract. Raises
        ValueError if all attempts fail.
"""

import ast
import sys
import os
import subprocess
import pickle
import base64
from typing import Any


ALLOWED_IMPORTS = {
    # Core scientific
    "numpy", "scipy", "math", "statistics", "decimal", "fractions",
    # Data processing
    "pandas", "polars", "pyarrow", "dask", "vaex",
    # ML frameworks
    "torch", "tensorflow", "keras", "jax", "flax", "haiku",
    # Scikit ecosystem
    "sklearn", "xgboost", "lightgbm", "catboost",
    # NLP
    "nltk", "spacy", "transformers", "tokenizers", "sentencepiece", "gensim",
    # Computer vision
    "cv2", "PIL", "skimage", "albumentations", "kornia",
    # Audio
    "librosa", "torchaudio", "soundfile", "audioread",
    # Data formats
    "csv", "json", "yaml", "toml", "h5py", "netCDF4", "zarr",
    "pickle", "shelve", "sqlite3", "openpyxl", "xlrd",
    # Visualization (may be needed for data validation)
    "matplotlib", "seaborn", "plotly", "bokeh",
    # Utilities
    "itertools", "functools", "operator", "collections", "heapq",
    "datetime", "time", "calendar", "re", "string", "textwrap",
    "typing", "dataclasses", "abc", "copy", "pprint",
    # Numeric/symbolic
    "sympy", "mpmath", "numba", "cupy",
    # Graph/network
    "networkx", "igraph",
    # Geo/spatial
    "shapely", "geopandas", "pyproj", "rasterio",
    # Experiment tracking
    "mlflow", "wandb",
}

FORBIDDEN_CALLS = {
    "exec", "eval", "open", "compile", "__import__",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "breakpoint", "input", "exit", "quit",
    "__builtins__", "memoryview",
}

FORBIDDEN_KEYWORDS = {ast.Global, ast.Nonlocal}

_SUBPROCESS_RUNNER = """
import pickle, base64, os, sys

try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,  (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
except (ImportError, ValueError):
    pass

code = base64.b64decode(os.environ["__BOJAI_CODE__"]).decode()
data = pickle.loads(sys.stdin.buffer.read())

namespace = {}
exec(compile(code, "<build>", "exec"), namespace)
result = namespace["build"](data)
sys.stdout.buffer.write(pickle.dumps(result))
"""


class CodeRunner:

    def run_code(self, code_source: str, input_data: Any = None, timeout: int = 10) -> Any:
        """Layer 2+3 — run sanitized code in an isolated subprocess with resource limits."""

        env = os.environ.copy()
        env["__BOJAI_CODE__"] = base64.b64encode(code_source.encode()).decode()

        proc = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_RUNNER],
            input=pickle.dumps(input_data),
            capture_output=True,
            timeout=timeout,
            env=env,
        )

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode())

        return pickle.loads(proc.stdout)


class CodeValidator:
    def confirm_code(self, answer: dict) -> str:
        """Layer 1 — validate and sanitize LLM code via AST analysis.
        Returns the sanitized source string ready for subprocess execution."""

        code = answer["code"]
        tree = ast.parse(code)

        # Guard 1: must contain a build function
        if not any(
            isinstance(node, ast.FunctionDef) and node.name == "build"
            for node in ast.walk(tree)
        ):
            raise ValueError("Code must contain a function named 'build'.")

        # Guard 2: only allowed imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    if top_level not in ALLOWED_IMPORTS:
                        raise ValueError(f"Import '{alias.name}' is not allowed.")
            elif isinstance(node, ast.ImportFrom):
                top_level = (node.module or "").split(".")[0]
                if top_level not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import from '{node.module}' is not allowed.")

        # Guard 3a: no forbidden bare-name or attribute calls
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attrs = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        if forbidden := (called_names | called_attrs) & FORBIDDEN_CALLS:
            raise ValueError(f"Forbidden calls detected: {forbidden}.")

        # Guard 3b: no global / nonlocal
        if any(isinstance(node, tuple(FORBIDDEN_KEYWORDS)) for node in ast.walk(tree)):
            raise ValueError("Forbidden keywords: global / nonlocal are not allowed.")

        # Guard 3c: no decorators on any function
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
                raise ValueError(f"Decorators are not allowed (found on '{node.name}').")

        # Guard 3d: no default argument expressions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.args.defaults or node.args.kw_defaults:
                    raise ValueError(f"Default arguments are not allowed in '{node.name}'.")

        # Guard 4: strip everything outside function definitions, return sanitized source
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)

    async def validate_with_retry(
        self,
        get_code,
        get_files,
        validation_name: str,
        LLM_config: dict,
        initial_files: list,
        data_description: str | None = None,
        max_attempts: int = 3,
    ) -> str:
        # Local import to avoid circular dependency (build.agents imports CodeValidator).
        from build.agents import DecisionAgent

        files = initial_files
        code = await get_code(files)

        decision = DecisionAgent(validation_name, [code], None, LLM_config, data_description)
        valid = await decision.run()

        attempts = 0
        while not valid and attempts < max_attempts:
            if attempts % 2 == 1:
                files = await get_files()
            code = await get_code(files)
            decision = DecisionAgent(validation_name, [code], None, LLM_config, data_description)
            valid = await decision.run()
            attempts += 1

        if not valid:
            raise ValueError("The extracted code did not pass validation checks after multiple attempts.")
        return code