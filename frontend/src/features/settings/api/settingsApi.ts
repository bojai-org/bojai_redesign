import { request } from "../../build/api/pipelineApi";
import type { EnvVarsResponse } from "../types/settings";

/** GET /config/env -- names of global variables set on the running backend. */
export async function listEnvVars(): Promise<EnvVarsResponse> {
  return request<EnvVarsResponse>("/config/env");
}

/** POST /config/env -- sets (or, called again with the same name, overwrites) one variable. */
export async function setEnvVar(name: string, value: string): Promise<void> {
  await request<void>("/config/env", {
    method: "POST",
    body: JSON.stringify({ name, value }),
  });
}

/** DELETE /config/env/{name} -- 404s if the name isn't currently set. */
export async function deleteEnvVar(name: string): Promise<void> {
  await request<void>(`/config/env/${encodeURIComponent(name)}`, { method: "DELETE" });
}
