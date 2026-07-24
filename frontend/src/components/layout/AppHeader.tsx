import type { ReactNode } from "react";
import { Brand } from "./Brand";
import { Breadcrumbs, type BreadcrumbItem } from "../navigation/Breadcrumbs";
import styles from "./AppHeader.module.css";

export interface AppHeaderProps {
  breadcrumbs?: BreadcrumbItem[];
  actions?: ReactNode;
}

export function AppHeader({ breadcrumbs, actions }: AppHeaderProps) {
  return (
    <header className={styles.header}>
      <Brand />
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs items={breadcrumbs} />
      )}
      <div className={styles.spacer} />
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}
