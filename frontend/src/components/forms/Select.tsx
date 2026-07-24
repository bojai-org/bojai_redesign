import type { SelectHTMLAttributes } from "react";
import controls from "./controls.module.css";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
}

export function Select({ options, className, ...rest }: SelectProps) {
  const classes = [controls.control, className ?? ""].filter(Boolean).join(" ");
  return (
    <select className={classes} {...rest}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
