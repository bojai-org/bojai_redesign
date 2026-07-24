import { TextInput } from "../../../components/forms/TextInput";
import styles from "./SearchBar.module.css";

export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchBar({
  value,
  onChange,
  placeholder = "Search projects…",
}: SearchBarProps) {
  return (
    <div className={styles.wrap}>
      <svg
        className={styles.icon}
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.3-4.3" />
      </svg>
      <TextInput
        className={styles.input}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label="Search projects"
      />
    </div>
  );
}
