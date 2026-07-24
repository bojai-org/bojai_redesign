import type { InputHTMLAttributes } from "react";
import controls from "./controls.module.css";

export type TextInputProps = InputHTMLAttributes<HTMLInputElement>;

export function TextInput({ className, ...rest }: TextInputProps) {
  const classes = [controls.control, className ?? ""].filter(Boolean).join(" ");
  return <input type="text" className={classes} {...rest} />;
}
