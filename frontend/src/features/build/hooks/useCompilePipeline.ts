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
}

/**
 * Owns the Build workspace's compile state machine: tracks dirtiness from
 * graph/config edits, runs local validation, serializes, and talks to
 * backend/app.py -- POST to create, PUT to recompile in place, with a
 * single-retry fallback to POST if a PUT 404s (the stored pipeline vanished
 * server-side, e.g. a backend restart, since there is no persistence layer
 * yet -- see backend/app.py's module docstring).
 */
export function useCompilePipeline(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  runtimeConfig: PipelineRuntimeConfig,
): UseCompilePipelineResult {
  const [compileState, setCompileState] = useState<CompileState>(INITIAL_COMPILE_STATE);

  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
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
    const targetPipelineId = compileState.pipelineId;
    setCompileState((current) => ({ ...current, status: "compiling" }));

    const succeed = (summary: PipelineSummary) => {
      setCompileState((current) => ({
        status: "compiled",
        pipelineId: summary.pipeline_id,
        lastCompiledDefinitionHash: hashPipelineDefinition(definition),
        error: null,
        summary,
        successCount: current.successCount + 1,
      }));
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
        ? await updatePipeline(targetPipelineId, definition)
        : await compilePipeline(definition);
      succeed(summary);
    } catch (error) {
      if (error instanceof BuildApiError && error.status === 404 && targetPipelineId) {
        // The pipeline id we had is gone server-side -- retry once as a
        // fresh create rather than looping on 404s.
        try {
          const summary = await compilePipeline(definition);
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

  return {
    compileState,
    validationErrors,
    previewDefinition: preview.definition,
    previewError: preview.error,
    compile,
    reset,
    invalidatePipelineId,
  };
}
