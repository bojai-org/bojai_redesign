/** Wire-format types for backend/app.py's /config/env endpoints. */

/** GET /config/env response -- names only, backend never echoes values back. */
export interface EnvVarsResponse {
  names: string[];
}

/** Body of POST /config/env. Also used to overwrite an existing name (update). */
export interface SetEnvVarRequest {
  name: string;
  value: string;
}
