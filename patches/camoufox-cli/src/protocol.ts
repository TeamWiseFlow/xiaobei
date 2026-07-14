/** JSON-line protocol for CLI <-> Daemon communication. */

export interface Command {
  id: string;
  action: string;
  params: Record<string, unknown>;
}

export interface Response {
  id: string;
  success: boolean;
  error?: string;
  data?: Record<string, unknown>;
}

export function parseCommand(line: string): Command {
  return JSON.parse(line.trim());
}

export function serializeResponse(response: Response): Buffer {
  return Buffer.from(JSON.stringify(response) + "\n", "utf-8");
}

export function okResponse(id: string, data?: Record<string, unknown>): Response {
  const resp: Response = { id, success: true };
  if (data !== undefined) resp.data = data;
  return resp;
}

export function errorResponse(id: string, error: string): Response {
  return { id, success: false, error };
}
