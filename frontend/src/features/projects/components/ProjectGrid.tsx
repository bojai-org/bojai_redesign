import { ProjectCard } from "./ProjectCard";
import type { ProjectSummary } from "../types/project";
import styles from "./ProjectGrid.module.css";

export interface ProjectGridProps {
  projects: ProjectSummary[];
  onDeleteProject: (project: ProjectSummary) => void;
}

export function ProjectGrid({ projects, onDeleteProject }: ProjectGridProps) {
  return (
    <div className={styles.grid}>
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} onDelete={onDeleteProject} />
      ))}
    </div>
  );
}
