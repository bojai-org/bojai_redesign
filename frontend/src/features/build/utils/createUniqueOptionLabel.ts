/**
 * Disambiguates an auto-created option label against existing labels:
 * "RAG" -> "RAG" (if free), else "RAG 2", "RAG 3", ...
 */
export function createUniqueOptionLabel(
  baseLabel: string,
  existingOptions: { label: string }[],
): string {
  const base = baseLabel.trim() || "Option";
  const existingLabels = new Set(
    existingOptions.map((option) => option.label.trim().toLowerCase()),
  );

  if (!existingLabels.has(base.toLowerCase())) return base;

  let suffix = 2;
  while (existingLabels.has(`${base} ${suffix}`.toLowerCase())) {
    suffix += 1;
  }
  return `${base} ${suffix}`;
}
