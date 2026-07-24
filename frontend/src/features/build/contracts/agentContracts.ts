import { getDecisionOptions } from "../utils/getDecisionOptions";
import {
  DECISION_ADD_ROUTE_HANDLE,
  decisionOptionHandleId,
  staticRouteHandleId,
} from "../utils/handleIds";
import type {
  AgentContract,
  AgentType,
  DecisionOption,
  PipelineNode,
  SourceHandleDescriptor,
} from "../types/pipeline";

/**
 * Single source of truth for every user-facing agent type, mirrored from
 * backend/agents.py, backend/safety_agents.py, and backend/contract.md --
 * kept in lockstep with backend/app.py's AGENT_REGISTRY, the actual set this
 * API can compile.
 *
 * `_Static_Agent_Auto` is intentionally excluded — the backend compiler
 * appends it automatically and it is never user-configurable.
 *
 * `Neural_Network_Barrier_Agent` and `Input_Barrier_Pipeline` are also
 * excluded: both require a Python `embed_texts` callable as a constructor
 * argument, which an HTTP JSON body can't carry (contract.md section 10) —
 * backend/app.py's registry leaves them out for the same reason, so
 * compiling a node of either type would always fail server-side.
 */
export const AGENT_CONTRACTS: Record<AgentType, AgentContract> = {
  Decision_Agent: {
    type: "Decision_Agent",
    label: "Decision",
    description:
      "Uses the LLM to choose one option from a list, based on a request and the decision instructions below. Each option becomes its own output route. Typically used as the pipeline entrypoint.",
    fields: [
      {
        key: "query",
        label: "Request",
        type: "query-source",
        required: true,
        description:
          "What the decision is being made about. Defaults to the pipeline's incoming question, same as every other agent's query -- almost always what you want here, since a Decision node is usually the entrypoint. Only switch to \"Custom\" if this decision is about something other than the end user's request.",
        defaultValue: { mode: "pipeline-input" },
      },
      {
        key: "options",
        label: "Options",
        type: "string-list",
        required: true,
        description:
          "The choices the decision can route to. Each option becomes an output route below.",
        defaultValue: [],
      },
      {
        key: "context",
        label: "Decision instructions",
        type: "textarea",
        required: false,
        description:
          "Tells the LLM how to choose between the options (e.g. \"Choose the best retrieval method for this request\"). Used only when this node has no incoming connection (normally the entrypoint) -- for every later call it's replaced by the calling node's output.",
        placeholder: "Choose the best option for this request…",
        defaultValue: "",
        entryOnly: true,
      },
    ],
    outputRoutes: [],
    dynamicRoutes: true,
  },

  RAG_Agent: {
    type: "RAG_Agent",
    label: "RAG",
    description:
      "Retrieves the top-k chunks from a corpus via BM25 search, then asks the LLM to generate a response grounded in those chunks. Calls the LLM.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The question this node answers.",
        defaultValue: { mode: "pipeline-input" },
      },
      {
        key: "corpus_address",
        label: "Corpus address",
        type: "corpus",
        required: true,
        description:
          "Filesystem path to the corpus directory (expects <path>/processed/guideline_db.json).",
        placeholder: "path/to/corpus",
        defaultValue: "",
      },
      {
        key: "top_k",
        label: "Top K",
        type: "number",
        required: false,
        description: "Number of chunks to retrieve.",
        defaultValue: 5,
      },
    ],
    outputRoutes: ["next"],
  },

  Keyword_Search_Agent: {
    type: "Keyword_Search_Agent",
    label: "Keyword Search",
    description:
      "Retrieves the top-k chunks with the most literal query-term overlap. Deterministic — does not call the LLM.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The question this node answers.",
        defaultValue: { mode: "pipeline-input" },
      },
      {
        key: "corpus_address",
        label: "Corpus address",
        type: "corpus",
        required: true,
        description:
          "Filesystem path to the corpus directory (expects <path>/processed/guideline_db.json).",
        placeholder: "path/to/corpus",
        defaultValue: "",
      },
      {
        key: "top_k",
        label: "Top K",
        type: "number",
        required: false,
        description: "Number of chunks to retrieve.",
        defaultValue: 5,
      },
    ],
    outputRoutes: ["next"],
  },

  Hybrid_Agent: {
    type: "Hybrid_Agent",
    label: "Hybrid Search",
    description:
      "Merges BM25 and literal keyword-overlap retrieval for broader recall than either alone. Deterministic — does not call the LLM.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The question this node answers.",
        defaultValue: { mode: "pipeline-input" },
      },
      {
        key: "corpus_address",
        label: "Corpus address",
        type: "corpus",
        required: true,
        description:
          "Filesystem path to the corpus directory (expects <path>/processed/guideline_db.json).",
        placeholder: "path/to/corpus",
        defaultValue: "",
      },
      {
        key: "top_k",
        label: "Top K",
        type: "number",
        required: false,
        description: "Number of chunks to retrieve.",
        defaultValue: 5,
      },
    ],
    outputRoutes: ["next"],
  },

  Reranker_Agent: {
    type: "Reranker_Agent",
    label: "Reranker",
    description:
      "Uses the LLM to re-rank the resources found by an upstream retrieval node. Calls the LLM. Connect it directly after a RAG, Keyword Search, or Hybrid Search node -- it reads their retrieved resources from the inherited context, the same way Direct Answer does.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The request candidates are being ranked against.",
        defaultValue: { mode: "pipeline-input" },
      },
      {
        key: "top_k",
        label: "Top K",
        type: "number",
        required: false,
        description: "Number of top-ranked candidates to keep.",
        defaultValue: 5,
      },
    ],
    outputRoutes: ["next"],
  },

  Binary_Judge_Agent: {
    type: "Binary_Judge_Agent",
    label: "Binary Judge",
    description:
      "Uses the LLM to judge whether the inherited context contains enough information to answer the query. Routes to yes or no.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "textarea",
        required: true,
        description:
          "The request being judged. Context is inherited from whichever node actually routes into this one — it is not configured here.",
        placeholder: "The question to judge context against…",
        defaultValue: "",
      },
    ],
    outputRoutes: ["yes", "no"],
  },

  Direct_Answer_Agent: {
    type: "Direct_Answer_Agent",
    label: "Direct Answer",
    description:
      "Uses the LLM to draft a final answer to the query, grounded only in the inherited context. Calls the LLM.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description:
          "The question this node answers. Context is inherited from whichever node actually routes into this one.",
        defaultValue: { mode: "pipeline-input" },
      },
    ],
    outputRoutes: ["next"],
  },

  Static_Agent: {
    type: "Static_Agent",
    label: "Static Reply",
    description:
      "Always returns a fixed, pre-written message. Deterministic — does not call the LLM. Useful for canned or safety-critical replies.",
    fields: [
      {
        key: "message",
        label: "Message",
        type: "textarea",
        required: true,
        description: "The fixed text this node always returns.",
        placeholder: "The exact text to return…",
        defaultValue: "",
      },
      {
        key: "query",
        label: "Query label",
        type: "text",
        required: false,
        description:
          "Optional label for the request this static reply responds to. Does not affect the returned message.",
        defaultValue: "",
      },
    ],
    outputRoutes: ["next"],
  },

  Simple_Task_Agent: {
    type: "Simple_Task_Agent",
    label: "Simple Task",
    description:
      "A minimal agent for ad-hoc tasks. Returns raw LLM text for the query and inherited context, with no structured output schema.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "textarea",
        required: true,
        description:
          "The request this node answers. Context is inherited from whichever node actually routes into this one.",
        placeholder: "The task to perform…",
        defaultValue: "",
      },
    ],
    outputRoutes: ["next"],
  },

  Static_Barrier_Agent: {
    type: "Static_Barrier_Agent",
    label: "Static Safety Check",
    description:
      "Deterministic regex screening for crisis language, self-harm, and other high-risk patterns. Does not call the LLM. Routes to safe, escalate, escalate_judge, or reject.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The message being screened -- almost always the pipeline's incoming question.",
        defaultValue: { mode: "pipeline-input" },
      },
    ],
    outputRoutes: ["safe", "escalate", "escalate_judge", "reject"],
    category: "safety",
  },

  Judge_Barrier_Agent: {
    type: "Judge_Barrier_Agent",
    label: "LLM Safety Judge",
    description:
      "Uses the LLM as a final safety judge to decide whether a message is harmful and must be blocked. Calls the LLM. Routes to safe or harmful.",
    fields: [
      {
        key: "query",
        label: "Query",
        type: "query-source",
        required: true,
        description: "The message being judged -- almost always the pipeline's incoming question.",
        defaultValue: { mode: "pipeline-input" },
      },
    ],
    outputRoutes: ["safe", "harmful"],
    category: "safety",
  },
};

export const AGENT_TYPES = Object.keys(AGENT_CONTRACTS) as AgentType[];

/** Agent types shown in the library's main grid. */
export const STANDARD_AGENT_TYPES = AGENT_TYPES.filter(
  (type) => AGENT_CONTRACTS[type].category !== "safety",
);

/** Agent types shown in the library's separate, red-styled safety section. */
export const SAFETY_AGENT_TYPES = AGENT_TYPES.filter(
  (type) => AGENT_CONTRACTS[type].category === "safety",
);

/** Trimmed, de-duplicated, non-empty option labels, in original order. */
function decisionOptionRoutes(options: DecisionOption[]): string[] {
  const seen = new Set<string>();
  const routes: string[] = [];
  for (const option of options) {
    const trimmed = option.label.trim();
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    routes.push(trimmed);
  }
  return routes;
}

/** A node's actual output routes, resolving Decision_Agent's dynamic case. */
export function getNodeOutputRoutes(
  node: PipelineNode,
  contract: AgentContract,
): string[] {
  if (contract.dynamicRoutes) {
    return decisionOptionRoutes(getDecisionOptions(node));
  }
  return contract.outputRoutes;
}

/** Human-readable labels for fixed (non-Decision) route names, shared by
 * source-handle rendering, edge labels, and validation messages. */
export const STATIC_ROUTE_LABELS: Record<string, string> = {
  next: "Next",
  yes: "Yes",
  no: "No",
  safe: "Safe",
  reject: "Reject",
  escalate: "Escalate",
  escalate_judge: "Escalate (crisis)",
  harmful: "Harmful",
};

/**
 * A node's actual connectable source handles, resolving Decision_Agent's
 * dynamic case: one handle per configured option (stable id, current
 * label), plus a permanent "add route" handle used to create new
 * connections without a pre-existing option (see syncDecisionEdge.ts).
 */
export function getSourceHandles(
  node: PipelineNode,
  contract: AgentContract,
): SourceHandleDescriptor[] {
  if (contract.dynamicRoutes) {
    const options = getDecisionOptions(node);
    return [
      ...options.map((option) => ({
        id: decisionOptionHandleId(option.id),
        label: option.label.trim() || "Untitled option",
        routeId: option.id,
      })),
      { id: DECISION_ADD_ROUTE_HANDLE, label: "+ Add route" },
    ];
  }
  return contract.outputRoutes.map((route) => ({
    id: staticRouteHandleId(route),
    label: STATIC_ROUTE_LABELS[route] ?? route,
    routeId: route,
  }));
}
