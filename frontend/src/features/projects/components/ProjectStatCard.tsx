import { Card } from "../../../components/data-display/Card";
import styles from "./ProjectStatCard.module.css";

export interface ProjectStatCardProps {
  value: string;
  label: string;
}

export function ProjectStatCard({ value, label }: ProjectStatCardProps) {
  return (
    <Card padding="sm">
      <div className={styles.value}>{value}</div>
      <div className={styles.label}>{label}</div>
    </Card>
  );
}
