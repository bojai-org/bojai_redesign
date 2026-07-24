export interface Project {
  id: string;
  name: string;
  description: string;
  ownerName: string;
  ownerEmail: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

export interface ProjectStats {
  projectCount: number;
  activePipelineCount: number;
  promptCount: number;
  evaluationRunCount: number;
}

export interface Workflow {
  id: string;
  projectId: string;
  name: string;
  version: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  updatedAt: string;
}

export interface WorkflowNode {
  id: string;
  type: string;
  category: "system" | "safety" | "answer";
  label: string;
  position: {
    x: number;
    y: number;
  };
  config: {
    promptId?: string;
    [key: string]: unknown;
  };
}

export interface WorkflowEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  label?: string;
}

export interface Prompt {
  id: string;
  name: string;
  description: string;
  variables: string[];
  content: string;
  version: number;
  updatedAt: string;
  linkedNodeTypes: string[];
}

export interface EvaluationDataset {
  id: string;
  projectId: string;
  name: string;
  source: "manual" | "csv";
  rows: EvaluationDatasetRow[];
}

export interface EvaluationDatasetRow {
  id: string;
  question: string;
  expectedAnswer: string;
  expectedDocument?: string;
}

export interface EvaluationRun {
  id: string;
  projectId: string;
  datasetId: string;
  workflowVersion: number;
  promptVersions: Record<string, number>;
  status: "pending" | "running" | "completed" | "failed";
  startedAt: string;
  completedAt?: string;
  results: EvaluationResult[];
}

export interface EvaluationResult {
  id: string;
  rowId: string;
  question: string;
  expectedAnswer: string;
  systemAnswer: string;
  similarityScore: number;
  expectedDocument?: string;
  retrievedDocument?: string;
  isMatch: boolean;
}

export interface ProviderConfiguration {
  id: string;
  projectId: string;
  provider: "aws-bedrock" | "anthropic" | "openai";
  settings: Record<string, string>;
  isVerified: boolean;
}
