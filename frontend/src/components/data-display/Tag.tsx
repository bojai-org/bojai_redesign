import type { ReactNode } from "react";
import styles from "./Tag.module.css";

export interface TagProps {
  muted?: boolean;
  children: ReactNode;
}

export function Tag({ muted = false, children }: TagProps) {
  return (
    <span className={muted ? `${styles.tag} ${styles.muted}` : styles.tag}>
      {children}
    </span>
  );
}
