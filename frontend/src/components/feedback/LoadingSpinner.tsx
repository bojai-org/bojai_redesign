import styles from "./LoadingSpinner.module.css";

export interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  label?: string;
}

const SIZE_CLASS: Record<NonNullable<LoadingSpinnerProps["size"]>, string> = {
  sm: styles.sm,
  md: styles.md,
  lg: styles.lg,
};

export function LoadingSpinner({ size = "md", label }: LoadingSpinnerProps) {
  return (
    <div className={styles.wrap} role="status">
      <span className={`${styles.spinner} ${SIZE_CLASS[size]}`} />
      {label && <span className={styles.label}>{label}</span>}
    </div>
  );
}
