import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Button } from "../../../components/actions/Button";
import { Modal } from "../../../components/feedback/Modal";
import { FormField } from "../../../components/forms/FormField";
import { SecretInput } from "../../../components/forms/SecretInput";
import { TextInput } from "../../../components/forms/TextInput";
import styles from "./GlobalVariableModal.module.css";

export interface GlobalVariableModalProps {
  open: boolean;
  /** Set to update that variable's value in place (name is fixed); unset to add a new one. */
  editingName?: string | null;
  onClose: () => void;
  onSave: (name: string, value: string) => void;
}

/** Add/update form for one backend/app.py POST /config/env variable. The value
 * field is a SecretInput (dots, not plaintext) since these are typically API
 * keys -- nothing here ever displays a value that's already been saved,
 * since GET /config/env only ever returns names. */
export function GlobalVariableModal({
  open,
  editingName,
  onClose,
  onSave,
}: GlobalVariableModalProps) {
  const isEditing = Boolean(editingName);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  // Reset the form each time the modal opens, pre-filling the name when updating.
  useEffect(() => {
    if (!open) return;
    setName(editingName ?? "");
    setValue("");
  }, [open, editingName]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName || !value) return;
    onSave(trimmedName, value);
  };

  return (
    <Modal open={open} onClose={onClose} title={isEditing ? "Update global variable" : "New global variable"}>
      <form onSubmit={handleSubmit}>
        <FormField label="Name" htmlFor="global-var-name">
          <TextInput
            id="global-var-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. OPENAI_API_KEY"
            autoFocus={!isEditing}
            disabled={isEditing}
            required
          />
        </FormField>
        <FormField
          label="Value"
          htmlFor="global-var-value"
          hint={isEditing ? "Enter a new value -- this replaces the current one." : undefined}
        >
          <SecretInput
            id="global-var-value"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={isEditing ? "New value" : "sk-..."}
            autoFocus={isEditing}
            required
          />
        </FormField>
        <div className={styles.actions}>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary">
            {isEditing ? "Update" : "Add variable"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
