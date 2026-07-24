import styles from "./SegmentedControl.module.css";

export interface SegmentedControlOption {
  value: string;
  label: string;
}

export interface SegmentedControlProps {
  options: SegmentedControlOption[];
  value: string;
  onChange: (value: string) => void;
}

export function SegmentedControl({
  options,
  value,
  onChange,
}: SegmentedControlProps) {
  return (
    <div className={styles.segmented}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? styles.active : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
