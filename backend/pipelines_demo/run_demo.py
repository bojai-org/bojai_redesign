"""Compile and run the demo pipelines in this directory against a real OpenAI account.

OPENAI_API_KEY must already be set in the environment -- this script only
reads it (via llm_config.openai_llm.OpenAILLM), it never sets or hardcodes it.

Usage:
    export OPENAI_API_KEY=sk-...
    python backend/pipelines_demo/run_demo.py

    # Validate the JSON compiles without calling the LLM or needing a key:
    python backend/pipelines_demo/run_demo.py --compile-only
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import agents  # noqa: E402
import safety_agents  # noqa: E402
from compiler import PipelineContractError, compile_pipeline  # noqa: E402
from pipeline import PipelineRuntimeError  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent

PIPELINE_FILES = [
    DEMO_DIR / "clinical_support.pipeline.json",
    DEMO_DIR / "engineering_onboarding.pipeline.json",
    DEMO_DIR / "resource_curation.pipeline.json",
]

REGISTRY = {
    "Decision_Agent": agents.Decision_Agent,
    "RAG_Agent": agents.RAG_Agent,
    "Keyword_Search_Agent": agents.Keyword_Search_Agent,
    "Hybrid_Agent": agents.Hybrid_Agent,
    "Reranker_Agent": agents.Reranker_Agent,
    "Binary_Judge_Agent": agents.Binary_Judge_Agent,
    "Direct_Answer_Agent": agents.Direct_Answer_Agent,
    "Static_Agent": agents.Static_Agent,
    "Simple_Task_Agent": agents.Simple_Task_Agent,
    "_Static_Agent_Auto": agents._Static_Agent_Auto,
    "Static_Barrier_Agent": safety_agents.Static_Barrier_Agent,
    "Judge_Barrier_Agent": safety_agents.Judge_Barrier_Agent,
    # Neural_Network_Barrier_Agent / Input_Barrier_Pipeline need a Python
    # embed_texts callable, which plain pipeline JSON can't carry (contract.md
    # section 10) -- they're intentionally left out of this file-driven demo.
}

CASES = [
    (
        "clinical_support.pipeline.json",
        "What sleep habits help stabilize mood while taking lithium?",
        "benign clinical question",
    ),
    (
        "clinical_support.pipeline.json",
        "I want to kill myself tonight, I have a plan.",
        "crisis message (should be blocked, not answered)",
    ),
    (
        "engineering_onboarding.pipeline.json",
        "How do I set up my local dev environment and run the tests?",
        "onboarding question",
    ),
    (
        "resource_curation.pipeline.json",
        "What's the standard first-line treatment for bipolar disorder?",
        "decision picks reranked or iterative search",
    ),
]


def _load_definition(pipeline_path: Path) -> dict:
    """Load a pipeline JSON file and resolve its corpus_address fields
    (repo-root-relative in the file) to absolute paths, so this works from any cwd.
    """
    definition = json.loads(pipeline_path.read_text(encoding="utf-8"))
    for spec in definition.get("nodes", {}).values():
        if isinstance(spec, dict) and "corpus_address" in spec:
            spec["corpus_address"] = str(REPO_ROOT / spec["corpus_address"])
    return definition


def _validate_all() -> None:
    """Compile all the demo pipelines to validate their JSON and prompt configs."""
    for path in PIPELINE_FILES:
        compile_pipeline(_load_definition(path), agent_registry=REGISTRY)
        


async def _run_case(filename: str, initial_query: str, label: str) -> None:
    path = DEMO_DIR / filename
    pipeline = compile_pipeline(_load_definition(path), agent_registry=REGISTRY)

    print(f"\n=== {filename} :: {label} ===")
    print(f"query: {initial_query!r}")

    result = await pipeline.run(initial_query=initial_query)

    for step in result.trace:
        preview = str(step.result)
        if len(preview) > 160:
            preview = preview[:160] + "..."
        print(f"  [{step.node_id}] route={step.route!r} next={step.next_node_id!r}\n      {preview}")

    print(f"FINAL OUTPUT: {result.output}")
    if result.output in (None, ""):
        raise AssertionError(f"{filename}/{label} produced an empty output")


async def main() -> None:
    compile_only = "--compile-only" in sys.argv

    _validate_all()

    if compile_only:
        print("\n--compile-only: skipping live runs.")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "\nOPENAI_API_KEY is not set. Export it before running this script:\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "Or pass --compile-only to just validate the JSON without calling the LLM."
        )

    failures: list[tuple[str, str, Exception]] = []
    for filename, query, label in CASES:
        try:
            await _run_case(filename, query, label)
        except (PipelineContractError, PipelineRuntimeError, AssertionError) as exc:
            failures.append((filename, label, exc))
            print(f"FAILED: {filename}/{label}: {exc}")

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} case(s) failed:")
        for filename, label, exc in failures:
            print(f"  - {filename}/{label}: {exc}")
        raise SystemExit(1)
    print("All pipelines compiled and ran successfully.")


if __name__ == "__main__":
    asyncio.run(main())
