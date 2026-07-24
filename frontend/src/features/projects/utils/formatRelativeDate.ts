export function formatRelativeDate(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays <= 0) return "Edited today";
  if (diffDays === 1) return "Edited yesterday";
  if (diffDays < 7) return `Edited ${diffDays} days ago`;

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks === 1) return "Edited 1 week ago";
  if (diffWeeks < 5) return `Edited ${diffWeeks} weeks ago`;

  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths <= 1) return "Edited 1 month ago";
  return `Edited ${diffMonths} months ago`;
}
