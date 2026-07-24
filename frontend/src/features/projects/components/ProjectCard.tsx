import { Link } from "react-router-dom";
import { Card } from "../../../components/data-display/Card";
import { Badge } from "../../../components/data-display/Badge";
import { Tag } from "../../../components/data-display/Tag";
import { formatRelativeDate } from "../utils/formatRelativeDate";
import type {
  PipelinePreviewTone,
  ProjectStatus,
  ProjectSummary,
} from "../types/project";
import styles from "./ProjectCard.module.css";

export interface ProjectCardProps {
  project: ProjectSummary;
}

const STATUS_BADGE: Record<
  ProjectStatus,
  { label: string; tone: "ok" | "neutral" | "amber" }
> = {
  active: { label: "Active", tone: "ok" },
  draft: { label: "Draft", tone: "neutral" },
  archived: { label: "Archived", tone: "amber" },
};

const NODE_TONE_CLASS: Record<PipelinePreviewTone, string> = {
  purple: "",
  teal: styles.teal,
  dark: styles.dark,
};

export function ProjectCard({ project }: ProjectCardProps) {
  const badge = STATUS_BADGE[project.status];

  return (
    <Link to={`/projects/${project.id}/build`} className={styles.link}>
      <Card interactive padding="none" className={styles.card}>
        <div className={styles.thumb}>
          {project.pipelinePreview.map((step, index) => (
            <span key={step.id} className={styles.thumbGroup}>
              {index > 0 && <span className={styles.arrow}>→</span>}
              <span
                className={[styles.node, NODE_TONE_CLASS[step.tone]]
                  .filter(Boolean)
                  .join(" ")}
              />
            </span>
          ))}
        </div>

        <div className={styles.body}>
          <div className={styles.headerRow}>
            <h3 className={styles.name}>{project.name}</h3>
            <Badge tone={badge.tone}>{badge.label}</Badge>
          </div>

          <p className={styles.description}>{project.description}</p>

          <div className={styles.tagRow}>
            {project.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>

          <div className={styles.meta}>
            <span>{project.owner}</span>
            <span>{formatRelativeDate(project.lastModified)}</span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
