import { TextInput } from "../../../components/forms/TextInput";
import { IconButton } from "../../../components/actions/IconButton";
import { Button } from "../../../components/actions/Button";
import styles from "./StringListEditor.module.css";

export interface StringListEditorItem {
  id: string;
  label: string;
}

export interface StringListEditorProps {
  items: StringListEditorItem[];
  onAdd: () => void;
  onRemove: (id: string) => void;
  onLabelChange: (id: string, label: string) => void;
  placeholder?: string;
  addLabel?: string;
}

export function StringListEditor({
  items,
  onAdd,
  onRemove,
  onLabelChange,
  placeholder,
  addLabel = "Add item",
}: StringListEditorProps) {
  return (
    <div className={styles.list}>
      {items.map((item) => (
        <div key={item.id} className={styles.row}>
          <TextInput
            value={item.label}
            placeholder={placeholder}
            onChange={(event) => onLabelChange(item.id, event.target.value)}
          />
          <IconButton
            label="Remove item"
            size="sm"
            onClick={() => onRemove(item.id)}
            icon={
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            }
          />
        </div>
      ))}
      <Button type="button" size="sm" onClick={onAdd}>
        {addLabel}
      </Button>
    </div>
  );
}
