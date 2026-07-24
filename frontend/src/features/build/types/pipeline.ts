export type AgentType =
  | "Decision_Agent"
  | "RAG_Agent"
  | "Keyword_Search_Agent"
  | "Hybrid_Agent"
  | "Reranker_Agent"
  | "Binary_Judge_Agent"
  | "Direct_Answer_Agent"
  | "Static_Agent"
  | "Simple_Task_Agent"
  | "Static_Barrier_Agent"
  | "Judge_Barrier_Agent";

export type AgentFieldType =
  | "text"
  | "textarea"
  | "number"
  | "string-list"
  | "corpus"
  | "query-source";

export interface AgentFieldContract {
  key: string;
  label: string;
  type: AgentFieldType;
  required: boolean;
  description?: string;
  placeholder?: string;
  defaultValue?: unknown;
  /**
   * True for fields that are only meaningful on the pipeline's entry node
   * (zero incoming edges) — e.g. Decision_Agent's initial `context`, which
   * the runtime only reads when a node has no actual calling predecessor.
   * The inspector hides these fields on non-entry nodes without touching
   * their stored value; this is a visibility rule, not a validation or
   * data-mutation rule.
   */
  entryOnly?: boolean;
}

export interface AgentContract {
  type: AgentType;
  label: string;
  description: string;
  fields: AgentFieldContract[];
  /** Static output route names. Empty when `dynamicRoutes` is true. */
  outputRoutes: string[];
  /**
   * True only for Decision_Agent: its actual output routes are derived from
   * the node's `options` field value at edit time, not fixed by the contract.
   */
  dynamicRoutes?: boolean;
  /**
   * "safety" agents (backend/safety_agents.py) are rendered in their own
   * section of the agent library, visually distinct from generation/
   * retrieval agents -- they gate/screen input rather than answer it.
   */
  category?: "safety";
}

/**
 * Explicit representation of where a node's effective query comes from.
 * Backend note: this never serializes as its own field — it collapses to the
 * backend's `query` graph-control field (string literal, integer ordinal
 * reference, or omitted/null to inherit) via serializePipelineForCompiler.
 * "pipeline-input" and "omitted" are the same backend value; the split
 * exists only to make the choice explicit in the UI.
 */
export type QuerySource =
  | { mode: "pipeline-input" }
  | { mode: "custom"; value: string }
  | { mode: "node"; nodeId: string };

export interface PipelineNodeData {
  agentType: AgentType;
  label: string;
  config: Record<string, unknown>;
}

export interface PipelineNode {
  id: string;
  position: { x: number; y: number };
  data: PipelineNodeData;
}

/**
 * A configured option on a Decision_Agent node. Identity is the stable `id`,
 * never the (renameable) `label` — edges reference options by id via
 * `PipelineEdge.routeId`.
 */
export interface DecisionOption {
  id: string;
  label: string;
  /**
   * "manual": the user typed or edited this option's label directly.
   * "auto": created by connecting the decision's "add route" handle to a
   * target node; its label tracks the target node's label until the user
   * edits it, at which point it becomes "manual" (see syncDecisionEdge.ts).
   */
  origin: "manual" | "auto";
  /** The node this option currently connects to, if any (auto options only). */
  targetNodeId?: string;
}

/**
 * A domain edge between two node's route/handle and another node.
 * `sourceHandleId` is the stable handle id the edge is attached to (see
 * utils/handleIds.ts). `routeId` is the stable route identity behind that
 * handle: a DecisionOption id for Decision_Agent sources, or the static
 * route name (e.g. "next", "yes", "no") for every other agent type.
 * `routeIndex` is a best-effort snapshot of the option's position at the
 * time the edge was created — a display/debug hint only, not kept in sync
 * if options are later reordered or removed. `routeId` is authoritative.
 */
export interface PipelineEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  sourceHandleId: string;
  routeId?: string;
  routeIndex?: number;
}

/** A renderable connection point on a node, derived from its contract + config. */
export interface SourceHandleDescriptor {
  id: string;
  label: string;
  /** The DecisionOption id or static route name already bound to this handle. */
  routeId?: string;
}

export interface NodeValidationResult {
  valid: boolean;
  fieldErrors: Record<string, string>;
}

/** Pipeline-level Build settings, independent of any node: backend/contract.md's top-level `config`. */
export interface PipelineRuntimeConfig {
  provider: string;
  model: string;
}

export const EMPTY_RUNTIME_CONFIG: PipelineRuntimeConfig = { provider: "", model: "" };
