import { useMemo, useState } from "react";
import { AppHeader } from "../../../components/layout/AppHeader";
import { PageContainer } from "../../../components/layout/PageContainer";
import { ProjectsHero } from "../components/ProjectsHero";
import { ProjectStatsGrid } from "../components/ProjectStatsGrid";
import type { ProjectStat } from "../components/ProjectStatsGrid";
import { ProjectToolbar } from "../components/ProjectToolbar";
import { ProjectGrid } from "../components/ProjectGrid";
import { EmptyProjectsState } from "../components/EmptyProjectsState";
import { NewProjectModal } from "../components/NewProjectModal";
import type { NewProjectInput } from "../components/NewProjectModal";
import { mockProjects } from "../data/mockProjects";
import type { ProjectSummary } from "../types/project";
import styles from "./ProjectsPage.module.css";

const ANSWER_AGENT_TYPES_AVAILABLE = 4;
const DEMO_BEST_DOC_MATCH_ACCURACY = "60%";

function computeStats(projects: ProjectSummary[]): ProjectStat[] {
  const activeCount = projects.filter((p) => p.status === "active").length;

  return [
    { value: String(activeCount), label: "Active projects" },
    { value: String(projects.length), label: "Pipelines built" },
    {
      value: DEMO_BEST_DOC_MATCH_ACCURACY,
      label: "Best doc-match accuracy",
    },
    {
      value: String(ANSWER_AGENT_TYPES_AVAILABLE),
      label: "Answer agent types available",
    },
  ];
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>(mockProjects);
  const [searchQuery, setSearchQuery] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);

  const stats = useMemo(() => computeStats(projects), [projects]);

  const filteredProjects = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const visible = query
      ? projects.filter(
          (project) =>
            project.name.toLowerCase().includes(query) ||
            project.description.toLowerCase().includes(query),
        )
      : projects;

    return [...visible].sort(
      (a, b) =>
        new Date(b.lastModified).getTime() -
        new Date(a.lastModified).getTime(),
    );
  }, [projects, searchQuery]);

  const handleCreateProject = ({ name, description }: NewProjectInput) => {
    const newProject: ProjectSummary = {
      id:
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `project-${Date.now()}`,
      name,
      description,
      owner: "You",
      lastModified: new Date().toISOString(),
      tags: [],
      status: "draft",
      pipelinePreview: [{ id: "p1", tone: "purple" }],
    };

    setProjects((current) => [newProject, ...current]);
    setIsModalOpen(false);
  };

  return (
    <div>
      <AppHeader />
      <ProjectsHero onNewProject={() => setIsModalOpen(true)} />

      <PageContainer>
        <ProjectStatsGrid stats={stats} />

        <div className={styles.sectionTitle}>
          <h2>Your projects</h2>
          <span className={styles.hint}>Sorted by last edited</span>
        </div>

        <ProjectToolbar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onNewProject={() => setIsModalOpen(true)}
        />

        {filteredProjects.length > 0 ? (
          <ProjectGrid projects={filteredProjects} />
        ) : (
          <EmptyProjectsState
            hasSearchQuery={searchQuery.trim().length > 0}
            onNewProject={() => setIsModalOpen(true)}
          />
        )}
      </PageContainer>

      <NewProjectModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateProject}
      />
    </div>
  );
}
