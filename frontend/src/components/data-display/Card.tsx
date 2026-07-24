import type { HTMLAttributes } from "react";
import styles from "./Card.module.css";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: "none" | "sm" | "md" | "lg";
  interactive?: boolean;
}

const PADDING_CLASS: Record<NonNullable<CardProps["padding"]>, string> = {
  none: styles.paddingNone,
  sm: styles.paddingSm,
  md: styles.paddingMd,
  lg: styles.paddingLg,
};

export function Card({
  padding = "md",
  interactive = false,
  className,
  children,
  ...rest
}: CardProps) {
  const classes = [
    styles.card,
    PADDING_CLASS[padding],
    interactive ? styles.interactive : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
