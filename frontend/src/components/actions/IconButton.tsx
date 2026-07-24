import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./IconButton.module.css";

export interface IconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: ReactNode;
  label: string;
  variant?: "default" | "ghost";
  size?: "md" | "sm";
}

export function IconButton({
  icon,
  label,
  variant = "ghost",
  size = "md",
  className,
  ...rest
}: IconButtonProps) {
  const classes = [
    styles.iconButton,
    variant === "ghost" ? styles.ghost : styles.default,
    size === "sm" ? styles.sm : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} aria-label={label} {...rest}>
      {icon}
    </button>
  );
}
