import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger-ghost";
  size?: "md" | "sm";
  icon?: ReactNode;
}

const VARIANT_CLASS: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
  "danger-ghost": styles.dangerGhost,
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    VARIANT_CLASS[variant],
    size === "sm" ? styles.sm : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} {...rest}>
      {icon}
      {children}
    </button>
  );
}
