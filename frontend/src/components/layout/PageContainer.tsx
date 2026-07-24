import type { ReactNode } from "react";
import styles from "./PageContainer.module.css";

export interface PageContainerProps {
  width?: "narrow" | "default" | "wide";
  children: ReactNode;
}

const WIDTH_CLASS: Record<NonNullable<PageContainerProps["width"]>, string> = {
  narrow: styles.narrow,
  default: styles.default,
  wide: styles.wide,
};

export function PageContainer({
  width = "default",
  children,
}: PageContainerProps) {
  return (
    <div className={`${styles.container} ${WIDTH_CLASS[width]}`}>
      {children}
    </div>
  );
}
