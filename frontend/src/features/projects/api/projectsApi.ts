import { request } from "../../build/api/pipelineApi";
import type {
  CreateProjectRequest,
  ProjectRecord,
  ProjectSummary,
  ProjectsResponse,
} from "../types/project";

/** Fills in the card-only fields the backend doesn't store yet (owner, tags,
 * pipeline preview) -- only the project itself is persisted so far. */
function toProjectSummary(record: ProjectRecord): ProjectSummary {
  return {
    id: record.id,
    name: record.name,
    description: record.description,
    owner: "You",
    lastModified: record.updated_at,
    tags: [],
    status: record.status,
    pipelinePreview: [{ id: "p1", tone: "purple" }],
  };
}

/** GET /projects -- every saved project, most recently edited first. */
export async function listProjects(): Promise<ProjectSummary[]> {
  const response = await request<ProjectsResponse>("/projects");
  return response.projects.map(toProjectSummary);
}

/** POST /projects -- saves a new project and returns it as stored. */
export async function createProject(input: CreateProjectRequest): Promise<ProjectSummary> {
  const record = await request<ProjectRecord>("/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return toProjectSummary(record);
}

/** DELETE /projects/{id} -- deletes the project and everything saved under it. */
export async function deleteProject(projectId: string): Promise<void> {
  await request<void>(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}
