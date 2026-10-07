import { useEffect, useMemo, useState } from "react";
import { AppHeader } from "../../../components/layout/AppHeader";
import { PageContainer } from "../../../components/layout/PageContainer";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { Modal } from "../../../components/feedback/Modal";
import { Button } from "../../../components/actions/Button";
import { BuildApiError } from "../../build/api/pipelineApi";
import { ProjectsHero } from "../components/ProjectsHero";
import { ProjectStatsGrid } from "../components/ProjectStatsGrid";
import type { ProjectStat } from "../components/ProjectStatsGrid";
import { ProjectToolbar } from "../components/ProjectToolbar";
import { ProjectGrid } from "../components/ProjectGrid";
import { EmptyProjectsState } from "../components/EmptyProjectsState";
import { NewProjectModal } from "../components/NewProjectModal";
import type { NewProjectInput } from "../components/NewProjectModal";
import { createProject, deleteProject, listProjects } from "../api/projectsApi";
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
  // null until the first load from the backend finishes.
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((saved) => {
        if (!cancelled) setProjects(saved);
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof BuildApiError ? error.message : "Could not load projects.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = useMemo(() => computeStats(projects ?? []), [projects]);

  const filteredProjects = useMemo(() => {
    if (!projects) return [];
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

  /** Saves to the backend first, so a project only appears once it's in the
   * database. Errors propagate to NewProjectModal, which shows them and keeps
   * the form open. */
  const handleCreateProject = async (input: NewProjectInput) => {
    const created = await createProject(input);
    setProjects((current) => [created, ...(current ?? [])]);
    setIsModalOpen(false);
  };

  const closeDeleteModal = () => {
    if (isDeleting) return;
    setDeleting(null);
    setDeleteError(null);
  };

  /** Removed from the list only once the backend has deleted it. */
  const confirmDelete = async () => {
    if (!deleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteProject(deleting.id);
      const deletedId = deleting.id;
      setProjects((current) => (current ?? []).filter((project) => project.id !== deletedId));
      setDeleting(null);
    } catch (error) {
      setDeleteError(error instanceof BuildApiError ? error.message : "Could not delete the project.");
    } finally {
      setIsDeleting(false);
    }
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

        {loadError ? (
          <p className={styles.error} role="alert">
            {loadError}
          </p>
        ) : projects === null ? (
          <LoadingSpinner size="sm" label="Loading projects…" />
        ) : filteredProjects.length > 0 ? (
          <ProjectGrid projects={filteredProjects} onDeleteProject={setDeleting} />
        ) : (
          <EmptyProjectsState
            hasSearchQuery={searchQuery.trim().length > 0}
            onNewProject={() => setIsModalOpen(true)}
          />
        )}
      </PageContainer>

      <Modal
        open={deleting !== null}
        onClose={closeDeleteModal}
        title="Delete project"
        footer={
          <>
            <Button variant="ghost" onClick={closeDeleteModal} disabled={isDeleting}>
              Cancel
            </Button>
            <Button variant="danger-ghost" onClick={() => void confirmDelete()} disabled={isDeleting}>
              {isDeleting ? "Deleting…" : "Delete project"}
            </Button>
          </>
        }
      >
        {deleting && (
          <>
            <p>
              Delete <strong>{deleting.name}</strong>? Its pipeline, every run, chat response and
              evaluation result, and the evaluation CSVs saved with them are permanently removed.
            </p>
            {deleteError && (
              <p className={styles.error} role="alert">
                {deleteError}
              </p>
            )}
          </>
        )}
      </Modal>

      <NewProjectModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateProject}
      />
    </div>
  );
}
