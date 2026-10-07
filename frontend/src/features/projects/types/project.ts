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

/** Wire format of one project from backend/app.py's /projects endpoints. */
export interface ProjectRecord {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

/** GET /projects response. */
export interface ProjectsResponse {
  projects: ProjectRecord[];
}

/** Body of POST /projects. */
export interface CreateProjectRequest {
  name: string;
  description: string;
}
