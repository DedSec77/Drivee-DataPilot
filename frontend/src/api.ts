import type {
  AskResponse,
  ChatTurn,
  Dictionary,
  EvalReport,
  QueryLogItem,
  ScheduledRun,
  StageEvent,
  Template,
} from "./types";

let _baseUrl: string =
  ((import.meta as any).env?.VITE_API_URL as string | undefined) ??
  "http://localhost:8000";

let _apiToken: string =
  ((import.meta as any).env?.VITE_API_TOKEN as string | undefined) ?? "";

export function setApiBaseUrl(url: string): void {
  if (url) _baseUrl = url;
}

export function setApiToken(token: string): void {
  _apiToken = token ?? "";
}

export function getApiBaseUrl(): string {
  return _baseUrl;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  if (_apiToken && !headers["X-API-Token"]) {
    headers["X-API-Token"] = _apiToken;
  }
  const res = await fetch(`${_baseUrl}${url}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  return (await res.json()) as T;
}

export function ask(
  question: string,
  opts: { role?: string; chatHistory?: ChatTurn[] } = {}
): Promise<AskResponse> {
  const { role = "business_user", chatHistory } = opts;
  const body: Record<string, unknown> = { question, role };
  if (chatHistory && chatHistory.length > 0) {
    body.chat_history = chatHistory;
  }
  return jsonFetch<AskResponse>("/api/ask", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function askStream(
  question: string,
  opts: { role?: string; chatHistory?: ChatTurn[] } = {},
  onStage: (event: StageEvent) => void,
  signal?: AbortSignal
): Promise<AskResponse> {
  const { role = "business_user", chatHistory } = opts;
  const body: Record<string, unknown> = { question, role };
  if (chatHistory && chatHistory.length > 0) {
    body.chat_history = chatHistory;
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/x-ndjson",
  };
  if (_apiToken) headers["X-API-Token"] = _apiToken;

  const res = await fetch(`${_baseUrl}/api/ask/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  if (!res.body) {
    throw new Error("Streaming not supported: response.body is null");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let final: AskResponse | null = null;
  let streamError: { code: string; hint_ru: string } | null = null;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let nl: number;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        let event: any;
        try {
          event = JSON.parse(line);
        } catch (e) {
          console.warn("askStream: skipping non-JSON line", line, e);
          continue;
        }
        if (event?.type === "stage") {
          onStage({
            stage: event.stage,
            label: event.label,
            detail: event.detail ?? null,
            ms: typeof event.ms === "number" ? event.ms : 0,
          });
        } else if (event?.type === "result" && event.result) {
          final = event.result as AskResponse;
        } else if (event?.type === "error" && event.error) {
          streamError = event.error;
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {}
  }

  if (final) return final;
  if (streamError) {
    return {
      kind: "error",
      sql: null,
      columns: null,
      rows: null,
      clarify_question: null,
      clarify_options: null,
      explainer: null,
      chart_hint: null,
      error: streamError,
    };
  }
  throw new Error("Streaming finished without a result event");
}

export type ExecuteResponse = {
  sql: string;
  columns: string[];
  rows: (string | number | null)[][];
  est_cost: number | null;
  est_rows: number | null;
  applied_rules: string[];
};

export function executeSql(
  sql: string,
  role = "business_user"
): Promise<ExecuteResponse> {
  return jsonFetch<ExecuteResponse>("/api/execute", {
    method: "POST",
    body: JSON.stringify({ sql, role }),
  });
}

export function listTemplates(onlyApproved = false): Promise<Template[]> {
  return jsonFetch<Template[]>(`/api/templates${onlyApproved ? "?only_approved=true" : ""}`);
}

export function saveTemplate(body: Partial<Template>): Promise<Template> {
  return jsonFetch<Template>("/api/templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function approveTemplate(reportId: number): Promise<Template> {
  return jsonFetch<Template>(`/api/templates/${reportId}/approve`, {
    method: "POST",
    body: "{}",
  });
}

export function deleteTemplate(
  reportId: number
): Promise<{ status: string; report_id: number }> {
  return jsonFetch<{ status: string; report_id: number }>(
    `/api/templates/${reportId}`,
    { method: "DELETE" }
  );
}

export type EvalSummary =
  | { status: "ok"; report: EvalReport; mtime: number }
  | { status: "no_results" | "parse_error"; hint_ru: string; looked_at?: string };

export function getEvalSummary(): Promise<EvalSummary> {
  return jsonFetch<EvalSummary>("/api/eval/summary");
}

export function getQueryLog(limit = 100): Promise<QueryLogItem[]> {
  return jsonFetch<QueryLogItem[]>(`/api/query-log?limit=${limit}`);
}

export type ScheduleDTO = {
  schedule_id: number;
  report_id: number;
  cron_expr: string;
  destination: string;
  is_active: boolean;
};

export function listSchedules(): Promise<ScheduleDTO[]> {
  return jsonFetch<ScheduleDTO[]>("/api/schedule");
}

export function createSchedule(body: {
  report_id: number;
  cron_expr: string;
  destination: string;
}): Promise<ScheduleDTO> {
  return jsonFetch<ScheduleDTO>("/api/schedule", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listScheduledRuns(reportId?: number): Promise<ScheduledRun[]> {
  const qs = reportId != null ? `?report_id=${reportId}` : "";
  return jsonFetch<ScheduledRun[]>(`/api/schedule/runs${qs}`);
}

export function deleteSchedule(
  scheduleId: number
): Promise<{ status: string; schedule_id: number }> {
  return jsonFetch<{ status: string; schedule_id: number }>(
    `/api/schedule/${scheduleId}`,
    { method: "DELETE" }
  );
}

export function patchSchedule(
  scheduleId: number,
  patch: { is_active: boolean }
): Promise<ScheduleDTO> {
  return jsonFetch<ScheduleDTO>(`/api/schedule/${scheduleId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function runScheduleNow(
  scheduleId: number
): Promise<{
  status: string;
  schedule_id: number;
  filename: string;
  rows: number;
  size_bytes: number;
  download_url: string;
}> {
  return jsonFetch(`/api/schedule/${scheduleId}/run-now`, {
    method: "POST",
    body: "{}",
  });
}

export function scheduledDownloadUrl(filename: string): string {
  return `${_baseUrl}/files/scheduled/${filename}`;
}

export function deleteScheduledRun(
  filename: string
): Promise<{ status: string; filename: string }> {
  return jsonFetch<{ status: string; filename: string }>(
    `/api/schedule/runs/${encodeURIComponent(filename)}`,
    { method: "DELETE" }
  );
}

export function getDictionary(): Promise<Dictionary> {
  return jsonFetch<Dictionary>("/api/dictionary");
}

export function summarizePrompt(prompt: string): Promise<{ label: string }> {
  return jsonFetch<{ label: string }>("/api/summarize-prompt", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export type DatasourceStatus = {
  dsn_masked: string;
  connected: boolean;
  server_version?: string | null;
  current_database?: string | null;
  dialect?: string | null;
  error?: string | null;
};

export type ColumnInfo = {
  name: string;
  type: string;
  nullable: boolean;
  is_pk: boolean;
};

export type FkInfo = {
  column: string;
  target_table: string;
  target_column: string;
};

export type TableInfo = {
  schema: string;
  name: string;
  estimated_rows: number | null;
  columns: ColumnInfo[];
  foreign_keys: FkInfo[];
};

export type SchemaInfo = {
  database: string | null;
  server_version: string | null;
  tables: TableInfo[];
};

export function getDatasourceStatus(): Promise<DatasourceStatus> {
  return jsonFetch<DatasourceStatus>("/api/datasource/status");
}

export function connectDatasource(dsn: string): Promise<DatasourceStatus> {
  return jsonFetch<DatasourceStatus>("/api/datasource/connect", {
    method: "POST",
    body: JSON.stringify({ dsn }),
  });
}

export function introspectDatasource(schema?: string): Promise<SchemaInfo> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : "";
  return jsonFetch<SchemaInfo>(`/api/datasource/introspect${qs}`);
}

export function generateDictionary(): Promise<{
  yaml_text: string;
  raw?: string | null;
}> {
  return jsonFetch<{ yaml_text: string; raw?: string | null }>(
    "/api/datasource/generate-dictionary",
    { method: "POST", body: "{}" }
  );
}

export function saveDictionaryYaml(
  yaml_text: string
): Promise<{ status: string; path: string; domain: string | null }> {
  return jsonFetch("/api/dictionary/save", {
    method: "POST",
    body: JSON.stringify({ yaml_text }),
  });
}

export type AdminStats = {
  logs: number;
  templates: number;
  schedules: number;
  trips: number;
};

export type AdminResetSelection = {
  logs?: boolean;
  templates?: boolean;
  schedules?: boolean;
  trips?: boolean;
};

export type AdminResetResult = {
  status: string;
  deleted: AdminStats;
  tables: string[];
};

export function getAdminStats(): Promise<AdminStats> {
  return jsonFetch<AdminStats>("/api/admin/stats");
}

export function resetAdminData(
  selection: AdminResetSelection
): Promise<AdminResetResult> {
  return jsonFetch<AdminResetResult>("/api/admin/reset", {
    method: "POST",
    body: JSON.stringify(selection),
  });
}
