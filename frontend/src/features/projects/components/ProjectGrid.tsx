import { ProjectCard } from "./ProjectCard";
import type { ProjectSummary } from "../types/project";
import styles from "./ProjectGrid.module.css";

export interface ProjectGridProps {
  projects: ProjectSummary[];
}

export function ProjectGrid({ projects }: ProjectGridProps) {
  return (
    <div className={styles.grid}>
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
