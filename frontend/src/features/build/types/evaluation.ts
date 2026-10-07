/**
 * Wire-format types for backend/app.py's evaluation endpoints
 * (backend/evaluator.py's Evaluator, mirrored 1:1 -- see that module's
 * docstring for what each field means):
 *
 *   GET  /pipelines/{id}/evaluate/safety-agents
 *   POST /pipelines/{id}/evaluate/safety
 *   POST /pipelines/{id}/evaluate
 */

// ─────────────────────────────────────────────────────────────────────────────
// Safety track
// ─────────────────────────────────────────────────────────────────────────────

export interface SafetyNodeInfo {
  node_id: string;
  agent_type: string;
}

/** GET /pipelines/{id}/evaluate/safety-agents */
export interface SafetyAgentsResponse {
  has_safety_agents: boolean;
  nodes: SafetyNodeInfo[];
}

/** One barrier node's action tally across every question it screened. */
export interface SafetyGateCounts {
  node_id: string;
  agent_type: string;
  total: number;
  /** action ("safe" | "accept" | "escalate" | "escalate_judge" | "reject" | "harmful") -> count. */
  action_counts: Record<string, number>;
}

export interface SafetyGateStep {
  node_id: string;
  agent_type: string;
  action: string | null;
}

export interface SafetyQuestionResult {
  question: string;
  label: string;
  predicted: string;
  path: SafetyGateStep[];
  error: string | null;
}

export interface SafetyConfusion {
  true_positive: number;
  false_positive: number;
  false_negative: number;
  true_negative: number;
}

/** POST /pipelines/{id}/evaluate/safety, and the "safety" field of a full evaluate() response. */
export interface SafetyEvalResponse {
  total_questions: number;
  gate_counts: SafetyGateCounts[];
  confusion: SafetyConfusion;
  precision: number;
  recall: number;
  f1: number;
  results: SafetyQuestionResult[];
  errors: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent (retrieval + answer) track
// ─────────────────────────────────────────────────────────────────────────────

export interface RetrievedChunk {
  rank: number;
  chunk_id: string | null;
  section: string | null;
  url: string | null;
  text: string;
}

export interface ResourceMatch {
  expected: string;
  found: boolean;
  rank: number | null;
  chunk_id: string | null;
}

export interface Faithfulness {
  faithful: boolean;
  score: number;
  reason: string;
}

export interface QuestionEvalResult {
  question: string;
  expected_answer: string;
  answer: string;
  retrieved_chunks: RetrievedChunk[];
  resource_matches: ResourceMatch[];
  faithfulness: Faithfulness;
  answer_similarity: number;
  error: string | null;
}

export interface AgentEvalResponse {
  results: QuestionEvalResult[];
  /** null when no row in the CSV supplied expected_resource(s) at all. */
  resource_recall: number | null;
  mean_answer_similarity: number;
  mean_faithfulness: number;
  errors: number;
}

/** POST /pipelines/{id}/evaluate/jobs and .../evaluate/safety/jobs's result shape once done. */
export interface EvaluationResponse {
  agent: AgentEvalResponse;
  /** Present only when the pipeline contains barrier-agent nodes. */
  safety: SafetyEvalResponse | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Background jobs -- evaluating a CSV means one pipeline run (plus an LLM
// faithfulness judge and an embedding call) per question, too slow to hold an
// HTTP request open for. POST .../evaluate/jobs and .../evaluate/safety/jobs
// start a background job and return a handle immediately; poll the matching
// GET .../jobs/{job_id} endpoint for progress and the final result.
// ─────────────────────────────────────────────────────────────────────────────

export type EvaluationJobState = "running" | "done" | "error" | "cancelled";

export interface EvaluationJobHandle {
  job_id: string;
  total: number;
}

export interface EvaluationJobStatus {
  status: EvaluationJobState;
  completed: number;
  total: number;
  result: EvaluationResponse | null;
  error: string | null;
}

export interface SafetyEvaluationJobStatus {
  status: EvaluationJobState;
  completed: number;
  total: number;
  result: SafetyEvalResponse | null;
  error: string | null;
}
