import { ProjectStatCard } from "./ProjectStatCard";
import styles from "./ProjectStatsGrid.module.css";

export interface ProjectStat {
  value: string;
  label: string;
}

export interface ProjectStatsGridProps {
  stats: ProjectStat[];
}

export function ProjectStatsGrid({ stats }: ProjectStatsGridProps) {
  return (
    <div className={styles.grid}>
      {stats.map((stat) => (
        <ProjectStatCard key={stat.label} value={stat.value} label={stat.label} />
      ))}
    </div>
  );
}
