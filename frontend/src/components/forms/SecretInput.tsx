import { useState } from "react";
import type { InputHTMLAttributes } from "react";
import controls from "./controls.module.css";
import styles from "./SecretInput.module.css";

export type SecretInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function SecretInput({ className, ...rest }: SecretInputProps) {
  const [visible, setVisible] = useState(false);
  const classes = [controls.control, className ?? ""].filter(Boolean).join(" ");

  return (
    <div className={styles.wrap}>
      <input type={visible ? "text" : "password"} className={classes} {...rest} />
      <button
        type="button"
        className={styles.eye}
        aria-label={visible ? "Hide secret" : "Show secret"}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? "🙈" : "👁"}
      </button>
    </div>
  );
}
