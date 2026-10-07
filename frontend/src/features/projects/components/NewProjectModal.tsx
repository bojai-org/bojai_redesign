import { useState } from "react";
import type { FormEvent } from "react";
import { Modal } from "../../../components/feedback/Modal";
import { FormField } from "../../../components/forms/FormField";
import { TextInput } from "../../../components/forms/TextInput";
import { TextArea } from "../../../components/forms/TextArea";
import { Button } from "../../../components/actions/Button";
import { BuildApiError } from "../../build/api/pipelineApi";
import styles from "./NewProjectModal.module.css";

export interface NewProjectInput {
  name: string;
  description: string;
}

export interface NewProjectModalProps {
  open: boolean;
  onClose: () => void;
  /** Resolves once the project is saved; a rejection is shown in the modal
   * and the form is kept so nothing typed is lost. */
  onCreate: (input: NewProjectInput) => Promise<void>;
}

export function NewProjectModal({
  open,
  onClose,
  onCreate,
}: NewProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setDescription("");
    setError(null);
  };

  const handleClose = () => {
    if (saving) return;
    reset();
    onClose();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate({ name: trimmedName, description: description.trim() });
      reset();
    } catch (caught) {
      setError(caught instanceof BuildApiError ? caught.message : "Could not save the project.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={handleClose} title="New project">
      <form onSubmit={handleSubmit}>
        <FormField label="Project name" htmlFor="new-project-name">
          <TextInput
            id="new-project-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Asthma Action Plan Assistant"
            autoFocus
            required
          />
        </FormField>
        <FormField label="Description" htmlFor="new-project-description">
          <TextArea
            id="new-project-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What does this assistant help with?"
          />
        </FormField>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <Button type="button" onClick={handleClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? "Saving…" : "Create project"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
