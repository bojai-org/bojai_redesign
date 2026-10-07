import { useEffect, useMemo, useRef, useState } from "react";
import { BuildApiError, compilePipeline, updatePipeline } from "../api/pipelineApi";
import { hashPipelineDefinition } from "../utils/hashPipelineDefinition";
import {
  PipelineSerializationError,
  serializePipelineForCompiler,
} from "../utils/serializePipelineForCompiler";
import { validatePipelineGraph } from "../utils/validatePipelineGraph";
import { INITIAL_COMPILE_STATE } from "../types/compiler";
import type {
  BuildValidationError,
  CompileState,
  CompilerPipelineDefinition,
  PipelineSummary,
} from "../types/compiler";
import type { PipelineEdge, PipelineNode, PipelineRuntimeConfig } from "../types/pipeline";

export interface UseCompilePipelineResult {
  compileState: CompileState;
  validationErrors: BuildValidationError[];
  /** Best-effort serialized definition for "Preview JSON", even when validationErrors is non-empty. */
  previewDefinition: CompilerPipelineDefinition | null;
  /** Set only when a definition genuinely could not be built at all (see PipelineSerializationError). */
  previewError: string | null;
  compile: () => Promise<void>;
  /** Back to INITIAL_COMPILE_STATE -- used when the whole workspace is cleared. */
  reset: () => void;
  /**
   * Forgets a compiled pipeline id without touching the graph -- used when a
   * consumer other than compile()/update() (e.g. the Run page's own POST
   * .../run call) discovers the id is gone server-side with a 404.
   */
  invalidatePipelineId: (reason: string) => void;
  /** Marks an already-compiled pipeline as the current one (e.g. a run being
   * opened) without compiling. The caller swaps the graph in at the same
   * time; that swap is not treated as an edit. */
  restore: (compiled: RestoredCompile) => void;
}

export interface RestoredCompile {
  pipelineId: string;
  definitionHash: string;
  summary: PipelineSummary | null;
}

export interface CompiledResult {
  summary: PipelineSummary;
  definitionHash: string;
  /** The graph and config exactly as they were when this compile started. */
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  runtimeConfig: PipelineRuntimeConfig;
}

export interface UseCompilePipelineOptions {
  /** Compiled pipelines are saved under this project on the backend. */
  projectId: string;
  /** Where to start, e.g. a project reopened with its active run's pipeline
   * already compiled. Defaults to INITIAL_COMPILE_STATE. */
  initialCompileState?: CompileState;
  /** Pipeline id already compiled from this definition, if any. A definition
   * with none gets a brand-new pipeline (POST) so other versions keep theirs. */
  pipelineIdForHash: (definitionHash: string) => string | null;
  /** Called once per successful compile. */
  onCompiled: (result: CompiledResult) => void;
}

/**
 * Owns the Build workspace's compile state machine: tracks dirtiness from
 * graph/config edits, runs local validation, serializes, and talks to
 * backend/app.py. Every distinct definition gets its own backend pipeline
 * (POST); recompiling a definition that already has one updates it in place
 * (PUT), with a single-retry fallback to POST if that PUT 404s (the stored
 * pipeline vanished server-side, e.g. a backend restart, since compiled
 * pipelines aren't persisted -- see backend/app.py's module docstring).
 */
export function useCompilePipeline(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  runtimeConfig: PipelineRuntimeConfig,
  { projectId, initialCompileState = INITIAL_COMPILE_STATE, pipelineIdForHash, onCompiled }: UseCompilePipelineOptions,
): UseCompilePipelineResult {
  const [compileState, setCompileState] = useState<CompileState>(initialCompileState);

  const isFirstRender = useRef(true);
  // Set by restore(): the graph swap that accompanies it changes `nodes`, but
  // isn't an edit, so the dirty effect below must skip it once.
  const skipNextDirty = useRef(false);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    if (skipNextDirty.current) {
      skipNextDirty.current = false;
      return;
    }
    setCompileState((current) =>
      current.status === "dirty" ? current : { ...current, status: "dirty", error: null },
    );
    // Node position, field, and label edits all produce a new `nodes`/`edges`
    // array reference; selection state and canvas pan/zoom never touch
    // either array, so they never trigger this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, runtimeConfig.provider, runtimeConfig.model]);

  const validationErrors = useMemo(
    () => validatePipelineGraph(nodes, edges, runtimeConfig),
    [nodes, edges, runtimeConfig],
  );

  const preview = useMemo(() => {
    try {
      return {
        definition: serializePipelineForCompiler({ nodes, edges, runtimeConfig }),
        error: null as string | null,
      };
    } catch (error) {
      const message =
        error instanceof PipelineSerializationError
          ? error.message
          : "Could not build a JSON preview.";
      return { definition: null, error: message };
    }
  }, [nodes, edges, runtimeConfig]);

  async function compile(): Promise<void> {
    if (compileState.status === "compiling" || compileState.status === "validating") return;

    setCompileState((current) => ({ ...current, status: "validating", error: null }));

    if (validationErrors.length > 0 || !preview.definition) {
      setCompileState((current) => ({ ...current, status: "dirty" }));
      return;
    }

    const definition = preview.definition;
    const definitionHash = hashPipelineDefinition(definition);
    const snapshot = { nodes, edges, runtimeConfig };
    const targetPipelineId = pipelineIdForHash(definitionHash);
    setCompileState((current) => ({ ...current, status: "compiling" }));

    const succeed = (summary: PipelineSummary) => {
      setCompileState((current) => ({
        status: "compiled",
        pipelineId: summary.pipeline_id,
        lastCompiledDefinitionHash: definitionHash,
        error: null,
        summary,
        successCount: current.successCount + 1,
      }));
      onCompiled({ summary, definitionHash, ...snapshot });
    };

    const fail = (message: string, clearPipelineId = false) => {
      setCompileState((current) => ({
        ...current,
        status: "failed",
        pipelineId: clearPipelineId ? null : current.pipelineId,
        error: message,
      }));
    };

    try {
      const summary = targetPipelineId
        ? await updatePipeline(targetPipelineId, definition, projectId)
        : await compilePipeline(definition, { projectId });
      succeed(summary);
    } catch (error) {
      if (error instanceof BuildApiError && error.status === 404 && targetPipelineId) {
        // The pipeline id we had is gone server-side -- retry once as a
        // fresh create rather than looping on 404s.
        try {
          const summary = await compilePipeline(definition, { projectId });
          succeed(summary);
        } catch (retryError) {
          fail(
            retryError instanceof BuildApiError ? retryError.message : "Compile failed.",
            true,
          );
        }
        return;
      }
      fail(error instanceof BuildApiError ? error.message : "Compile failed.");
    }
  }

  function reset(): void {
    setCompileState(INITIAL_COMPILE_STATE);
  }

  function invalidatePipelineId(reason: string): void {
    setCompileState((current) => ({
      ...current,
      status: "dirty",
      pipelineId: null,
      summary: null,
      error: reason,
    }));
  }

  function restore({ pipelineId, definitionHash, summary }: RestoredCompile): void {
    skipNextDirty.current = true;
    setCompileState((current) => ({
      status: "compiled",
      pipelineId,
      lastCompiledDefinitionHash: definitionHash,
      error: null,
      summary,
      successCount: current.successCount,
    }));
  }

  return {
    compileState,
    validationErrors,
    previewDefinition: preview.definition,
    previewError: preview.error,
    compile,
    reset,
    invalidatePipelineId,
    restore,
  };
}
