import { useState } from "react";
import type { FormEvent } from "react";
import { Modal } from "../../../components/feedback/Modal";
import { FormField } from "../../../components/forms/FormField";
import { TextInput } from "../../../components/forms/TextInput";
import { TextArea } from "../../../components/forms/TextArea";
import { Button } from "../../../components/actions/Button";
import styles from "./NewProjectModal.module.css";

export interface NewProjectInput {
  name: string;
  description: string;
}

export interface NewProjectModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (input: NewProjectInput) => void;
}

export function NewProjectModal({
  open,
  onClose,
  onCreate,
}: NewProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleClose = () => {
    setName("");
    setDescription("");
    onClose();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    onCreate({ name: trimmedName, description: description.trim() });
    setName("");
    setDescription("");
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
        <div className={styles.actions}>
          <Button type="button" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary">
            Create project
          </Button>
        </div>
      </form>
    </Modal>
  );
}
