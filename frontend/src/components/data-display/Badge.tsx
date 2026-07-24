import type { ReactNode } from "react";
import styles from "./Badge.module.css";

export interface BadgeProps {
  tone?: "ok" | "no" | "neutral" | "amber";
  children: ReactNode;
}

const TONE_CLASS: Record<NonNullable<BadgeProps["tone"]>, string> = {
  ok: styles.ok,
  no: styles.no,
  neutral: styles.neutral,
  amber: styles.amber,
};

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return <span className={`${styles.badge} ${TONE_CLASS[tone]}`}>{children}</span>;
}
