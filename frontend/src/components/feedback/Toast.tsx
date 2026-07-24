import styles from "./Toast.module.css";

export interface ToastProps {
  message: string;
  variant?: "default" | "success" | "error";
  visible: boolean;
  onDismiss?: () => void;
}

const VARIANT_CLASS: Record<NonNullable<ToastProps["variant"]>, string> = {
  default: "",
  success: styles.success,
  error: styles.error,
};

export function Toast({
  message,
  variant = "default",
  visible,
  onDismiss,
}: ToastProps) {
  const classes = [
    styles.toast,
    visible ? styles.visible : "",
    VARIANT_CLASS[variant],
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} role="status" aria-live="polite">
      <span>{message}</span>
      {onDismiss && (
        <button
          type="button"
          className={styles.dismiss}
          aria-label="Dismiss notification"
          onClick={onDismiss}
        >
          ✕
        </button>
      )}
    </div>
  );
}
