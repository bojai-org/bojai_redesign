import { Card } from "../../../components/data-display/Card";
import styles from "./StatTile.module.css";

export interface StatTileProps {
  label: string;
  value: string;
  tone?: "ok" | "no" | "amber" | "neutral";
}

const TONE_CLASS: Record<NonNullable<StatTileProps["tone"]>, string | undefined> = {
  ok: styles.ok,
  no: styles.no,
  amber: styles.amber,
  neutral: undefined,
};

/** A single headline number -- precision, recall, resource recall, error count, etc. */
export function StatTile({ label, value, tone = "neutral" }: StatTileProps) {
  const classes = [styles.tile, TONE_CLASS[tone]].filter(Boolean).join(" ");
  return (
    <Card padding="sm" className={classes}>
      <div className={styles.value}>{value}</div>
      <div className={styles.label}>{label}</div>
    </Card>
  );
}
