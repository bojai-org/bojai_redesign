import type { ReactNode } from "react";
import styles from "./Tabs.module.css";

export interface TabsProps {
  children: ReactNode;
}

export function Tabs({ children }: TabsProps) {
  return <nav className={styles.tabs}>{children}</nav>;
}
