import type { ReactNode } from "react";
import styles from "./FormField.module.css";

export interface FormFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

export function FormField({
  label,
  htmlFor,
  hint,
  error,
  children,
}: FormFieldProps) {
  return (
    <div className={styles.field}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <p className={styles.hint}>{hint}</p>}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
