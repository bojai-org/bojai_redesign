import { Button } from "../../../components/actions/Button";

export interface NewProjectButtonProps {
  onClick: () => void;
}

export function NewProjectButton({ onClick }: NewProjectButtonProps) {
  return (
    <Button
      variant="primary"
      onClick={onClick}
      icon={
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
      }
    >
      New project
    </Button>
  );
}
