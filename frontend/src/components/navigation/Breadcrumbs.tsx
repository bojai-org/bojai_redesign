import { Link } from "react-router-dom";
import styles from "./Breadcrumbs.module.css";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav className={styles.crumbs} aria-label="Breadcrumb">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className={styles.item}>
            {index > 0 && <span className={styles.separator}>›</span>}
            {item.to && !isLast ? (
              <Link to={item.to}>{item.label}</Link>
            ) : (
              <span className={isLast ? styles.current : undefined}>
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
