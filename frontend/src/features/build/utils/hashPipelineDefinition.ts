import type { CompilerPipelineDefinition } from "../types/compiler";

/**
 * A cheap, deterministic fingerprint of a serialized definition (FNV-1a over
 * its JSON), used only to detect "has the graph changed since the last
 * successful compile" -- not for anything security-sensitive.
 */
export function hashPipelineDefinition(definition: CompilerPipelineDefinition): string {
  const json = JSON.stringify(definition);
  let hash = 0x811c9dc5; // FNV-1a 32-bit offset basis
  for (let i = 0; i < json.length; i++) {
    hash ^= json.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
