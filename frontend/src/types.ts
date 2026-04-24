export type InterpretationFormula = {
  name: string;
  formula: string;
  source: string;
};

export type InterpretationPeriod = {
  label: string;
  start: string;
  end: string;
};

export type Interpretation = {
  period: InterpretationPeriod | null;
  tables: string[];
  formulas: InterpretationFormula[];
  dimensions: string[];
  summary_ru: string;
  llm_summary_ru: string;
};

export type Explainer = {
  confidence: number;
  components: Record<string, number>;
  used_metrics: string[];
  used_dimensions: string[];
  time_range: string | null;
  explanation_ru: string;
  guard_rules_applied: string[];
  explain_cost: number | null;
  explain_rows: number | null;
  interpretation?: Interpretation | null;
};

export type ClarifyOption = {
  label: string;
  question: string;
};

export type AskResponse = {
  kind: "answer" | "clarify" | "error";
  sql: string | null;
  columns: string[] | null;
  rows: (string | number | null)[][] | null;
  clarify_question: string | null;
  clarify_options: ClarifyOption[] | null;
  explainer: Explainer | null;
  error: { code: string; hint_ru: string } | null;
  chart_hint: "bar" | "line" | "pie" | "table" | "empty" | null;
};

export const STREAM_STAGES = [
  "retrieving",
  "linking",
  "generating",
  "guarding",
  "scoring",
  "voting",
  "critic",
  "executing",
  "verifying",
  "interpreting",
] as const;
export type StreamStage = (typeof STREAM_STAGES)[number];

export type StageEvent = {
  stage: StreamStage | string;
  label: string;
  detail: string | null;
  ms: number;
};

export type ChatTurn = {
  question: string;
  kind?: "answer" | "clarify" | "error";
  summary?: string;
  sql?: string;
};

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      question: string;
      resp: AskResponse | null;
      pending: boolean;
      fromCache: boolean;
      stages?: StageEvent[];
    };

export type UserRole = "business_user" | "analyst";

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
};

export type Template = {
  report_id: number;
  owner: string;
  title: string;
  nl_question: string;
  sql_text: string;
  chart_type: string | null;
  is_approved: boolean;
  is_template: boolean;
};

export type EvalReportItem = {
  id: string;
  intent: string;
  kind: string;
  em: number;
  cm: number;
  ex: number;
  ves: number;
  pred_cost: number | null;
  gold_cost: number | null;
  confidence: number | null;
  latency_ms: number | null;
  notes: string;
  guard_expected: string | null;
  guard_actual: string | null;
  error_category: string | null;
};

export type EvalReport = {
  total: number;
  answered: number;
  guard_pass: number;
  em_mean: number;
  cm_mean: number;
  ex_mean: number;
  ves_mean: number;
  avg_confidence: number;
  avg_latency_ms: number;
  items: EvalReportItem[];
  error_breakdown: Record<string, number>;
};

export type QueryLogItem = {
  log_id: number;
  ts: string | null;
  nl_question: string | null;
  sql_generated: string | null;
  sql_executed: string | null;
  confidence: number | null;
  guard_verdict: string | null;
  exec_ms: number | null;
  result_rows: number | null;
  error: string | null;
};

export type ScheduledRun = {
  filename: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
};

export type Route =
  | "ask"
  | "templates"
  | "schedules"
  | "dictionary"
  | "datasource"
  | "analysis"
  | "settings";

export type DictMeasure = {
  name: string;
  expr: string;
  synonyms_ru: string[];
};

export type DictDimension = {
  name: string;
  expr: string;
  join: string | null;
  synonyms_ru: string[];
};

export type DictEntity = {
  name: string;
  table: string | null;
  key: string | null;
  label_column: string | null;
  synonyms_ru: string[];
  synonyms_en: string[];
  pii: boolean;
  pii_columns: string[];
  roles_allow: string[];
  roles_deny: string[];
};

export type DictFact = {
  name: string;
  table: string;
  grain: string;
  time_column: string;
  require_time_filter: boolean;
  foreign_keys: Record<string, string>;
  measures: DictMeasure[];
  dimensions: DictDimension[];
};

export type DictMetric = {
  name: string;
  expr: string;
  label_ru: string;
  synonyms_ru: string[];
};

export type DictPolicies = {
  deny_tables: string[];
  require_time_filter_tables: string[];
  default_limit: number;
  max_joins: number;
  max_total_cost: number;
  max_plan_rows: number;
  pii_columns_by_role: Record<string, string[]>;
};

export type Dictionary = {
  domain: string | null;
  version: string | number | null;
  description: string | null;
  entities: DictEntity[];
  facts: DictFact[];
  metrics: DictMetric[];
  policies: DictPolicies;
  time_expressions_ru: Record<string, string>;
  cities_canonical_ru: Record<string, string>;
  stats: {
    entities: number;
    facts: number;
    measures: number;
    dimensions: number;
    metrics: number;
    time_expressions: number;
    cities_canonical: number;
  };
};
