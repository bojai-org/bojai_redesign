export type ProjectStatus = "active" | "draft" | "archived";

export type PipelinePreviewTone = "teal" | "purple" | "dark";

export interface PipelinePreviewStep {
  id: string;
  tone: PipelinePreviewTone;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  owner: string;
  lastModified: string;
  tags: string[];
  status: ProjectStatus;
  pipelinePreview: PipelinePreviewStep[];
  model?: string;
  evaluationCount?: number;
}
