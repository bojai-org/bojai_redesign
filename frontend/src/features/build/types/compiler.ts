/**
 * Wire-format types for backend/compiler.py's `compile_pipeline`, mirrored
 * from backend/contract.md and backend/app.py. These describe exactly what
 * this app sends and receives over HTTP -- not a restatement of the domain
 * types in ./pipeline.ts.
 *
 * Two things contract.md/compiler.py establish that are easy to get wrong:
 *
 * 1. There is no "agent_args" wrapper in the wire format. compiler.py's
 *    `_normalize` treats every node key that isn't a graph-control field
 *    (type/prev/query/context/routes/next/options) as a constructor keyword
 *    argument directly -- so `corpus_address`, `top_k`, `message`, etc. are
 *    flattened onto the node object itself, not nested.
 * 2. `query` accepts a string (a literal query) or an integer (an ordinal
 *    reference to another node's effective query) -- never a string node id
 *    as a reference. pipeline.py's `_resolve_query` treats any string query
 *    as literal text, full stop. Referencing another node's query by id
 *    requires resolving that id to its declaration-order ordinal first.
 */

/** A single node in the canonical (pre-normalization) pipeline JSON shape. */
export interface CompilerNodeDefinition {
  type: string;
  /**
   * Omitted for the entrypoint (equivalent to backend `-1`/`null`). A single
   * node id, or a list of node ids the node may be called by (OR semantics,
   * not merged) for every other node.
   */
  prev?: string | string[];
  /** Literal query text (string) or an ordinal reference to another node's query (number). Omitted to inherit. */
  query?: string | number;
  /** Only meaningful -- and only ever sent -- for the entry node. */
  context?: string;
  /** route name -> target node id. Always used instead of the equivalent "next" shorthand. */
  routes?: Record<string, string>;

  // --- Agent constructor arguments (flattened; see module doc above) ---
  /** Decision_Agent only: the full ordered list of option labels. */
  options?: string[];
  /** RAG_Agent / Keyword_Search_Agent / Hybrid_Agent (required). */
  corpus_address?: string;
  /** RAG_Agent / Keyword_Search_Agent / Hybrid_Agent / Reranker_Agent (optional, backend default 5). */
  top_k?: number;
  /** Static_Agent (required). */
  message?: string;
}

export interface CompilerPipelineDefinition {
  config: {
    provider: string;
    model: string;
  };
  entrypoint: string;
  nodes: Record<string, CompilerNodeDefinition>;
}

/** Body of POST /pipelines/compile and PUT /pipelines/{pipeline_id} (backend/app.py CompileRequest). */
export interface CompileRequest {
  pipeline_id?: string;
  /** The project this pipeline belongs to; the backend saves it under that project. */
  project_id?: string;
  definition: CompilerPipelineDefinition;
}

/** Response body from both compile and update (backend/app.py PipelineSummary). */
export interface PipelineSummary {
  pipeline_id: string;
  entrypoint: string;
  node_ids: string[];
  config: Record<string, unknown>;
}

/** Body of POST /pipelines/{pipeline_id}/run (backend/app.py RunRequest). */
export interface RunRequest {
  query?: string | null;
  /** Retrieval agents accumulate the full resource list into their result on every
   * hop, so a large corpus can make the trace much bigger than the answer itself.
   * Defaults true on the backend; runPipeline() sends false since nothing here
   * reads `trace`. */
  include_trace?: boolean;
}

/** backend/app.py TraceStep. */
export interface TraceStep {
  node_id: string;
  route: string | null;
  next_node_id: string | null;
  result: unknown;
}

/** backend/app.py RunResponse. */
export interface RunResponse {
  output: unknown;
  trace: TraceStep[];
}

/** FastAPI's HTTPException error body shape: { "detail": "..." }. */
export interface ApiErrorBody {
  detail?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Local (pre-request) validation
// ─────────────────────────────────────────────────────────────────────────────

export interface BuildValidationError {
  code: string;
  message: string;
  nodeId?: string;
  edgeId?: string;
  field?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Compile state machine
// ─────────────────────────────────────────────────────────────────────────────

export type CompileStatus = "dirty" | "validating" | "compiling" | "compiled" | "failed";

export interface CompileState {
  status: CompileStatus;
  pipelineId: string | null;
  lastCompiledDefinitionHash: string | null;
  error: string | null;
  summary: PipelineSummary | null;
  /** Incremented on every successful compile; distinguishes "Compiled" from "Recompiled" copy. */
  successCount: number;
}

export const INITIAL_COMPILE_STATE: CompileState = {
  status: "dirty",
  pipelineId: null,
  lastCompiledDefinitionHash: null,
  error: null,
  summary: null,
  successCount: 0,
};
