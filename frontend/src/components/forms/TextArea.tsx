import type { TextareaHTMLAttributes } from "react";
import controls from "./controls.module.css";

export type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextArea({ className, ...rest }: TextAreaProps) {
  const classes = [controls.control, controls.textarea, className ?? ""]
    .filter(Boolean)
    .join(" ");
  return <textarea className={classes} {...rest} />;
}
