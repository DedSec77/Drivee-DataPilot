export const GUARD_RULE_LABELS_RU: Record<string, string> = {
  check_deny_tables: "запрещённые таблицы",
  check_allowed_tables: "allowlist",
  check_pii: "PII-защита",
  check_joins: "лимит JOIN",
  check_time_filter: "фильтр по времени",
  check_empty_range: "пустой интервал",
  check_explain_cost: "оценка стоимости",
  inject_limit: "авто-LIMIT",
  inject_rls_cities: "RLS по городам",
};

export const GUARD_RULE_TOOLTIPS_RU: Record<string, string> = {
  check_deny_tables: "Запрос не обращается к запрещённым таблицам.",
  check_allowed_tables: "Все таблицы из FROM/JOIN есть в семантическом слое.",
  check_pii: "PII-колонки заблокированы для текущей роли.",
  check_joins: "Количество JOIN не превышает policy.max_joins.",
  check_time_filter: "В WHERE есть фильтр по time-колонке fact-таблицы.",
  check_empty_range:
    "Левый и правый край интервала разные — запрос не вернёт пустой результат из-за `>= X AND < X`.",
  check_explain_cost: "EXPLAIN-стоимость и план-rows в пределах policy.",
  inject_limit: "Добавлен LIMIT по умолчанию (только для row-level SELECT).",
  inject_rls_cities: "Добавлен фильтр по разрешённым городам RBAC.",
};

export function labelGuardRule(rule: string): string {
  if (rule.startsWith("canon_cities:")) {
    return `канон. города (${rule.split(":")[1]})`;
  }
  const known = GUARD_RULE_LABELS_RU[rule];
  if (known) return known;
  return rule
    .replace(/^check_|^inject_/, "")
    .replace(/_/g, " ");
}

export function tooltipGuardRule(rule: string): string {
  return GUARD_RULE_TOOLTIPS_RU[rule] ?? rule;
}
