import { Button } from "../../../components/actions/Button";

export function FilterButton() {
  return (
    <Button
      icon={
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 5h16M7 12h10M10 19h4" />
        </svg>
      }
    >
      Filter
    </Button>
  );
}
