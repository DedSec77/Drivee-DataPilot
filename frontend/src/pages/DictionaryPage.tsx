import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Box,
  Calculator,
  Calendar,
  Database,
  Layers,
  MapPin,
  ShieldCheck,
  Sigma,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getDictionary } from "@/api";
import type { Dictionary } from "@/types";

type Tab =
  | "entities"
  | "facts"
  | "metrics"
  | "policies"
  | "time"
  | "cities";

const TABS: { id: Tab; label: string; icon: typeof Database }[] = [
  { id: "entities", label: "Сущности", icon: Box },
  { id: "facts", label: "Факты", icon: Database },
  { id: "metrics", label: "Метрики", icon: Sigma },
  { id: "policies", label: "Политики", icon: ShieldCheck },
  { id: "time", label: "Время", icon: Calendar },
  { id: "cities", label: "Города", icon: MapPin },
];

export function DictionaryPage() {
  const [dict, setDict] = useState<Dictionary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("entities");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getDictionary()
      .then((d) => {
        if (alive) setDict(d);
      })
      .catch((e) => {
        if (alive) setError(e.message ?? String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error || !dict) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-destructive">
          <AlertTriangle size={16} />
          {error ?? "Не удалось загрузить словарь"}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers size={16} className="text-muted-foreground" />
            Семантический слой Drivee
            {dict.version != null && (
              <Badge variant="outline" className="ml-2 font-mono">
                v{dict.version}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Это бизнес-описание данных, которое LLM видит вместо сырых
            таблиц. Каждая метрика, размерность и сущность имеет русские
            синонимы, PII-флаги и ограничения по ролям. Меняется YAML —
            обновляется поведение всей системы.
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="сущностей" value={dict.stats.entities} />
            <Stat label="фактов" value={dict.stats.facts} />
            <Stat label="метрик (measure)" value={dict.stats.measures} />
            <Stat label="разрезов (dim)" value={dict.stats.dimensions} />
            <Stat label="формул (metric)" value={dict.stats.metrics} />
            <Stat
              label="временных выражений"
              value={dict.stats.time_expressions}
            />
            <Stat
              label="канон. городов"
              value={dict.stats.cities_canonical}
            />
            <Stat label="доменов" value={1} />
          </div>
        </CardContent>
      </Card>

      <div className="inline-flex h-9 items-center gap-0.5 rounded-lg bg-muted p-1">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon size={12} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className={cn(tab === "entities" ? "block" : "hidden")}>
        <EntitiesView dict={dict} />
      </div>
      <div className={cn(tab === "facts" ? "block" : "hidden")}>
        <FactsView dict={dict} />
      </div>
      <div className={cn(tab === "metrics" ? "block" : "hidden")}>
        <MetricsView dict={dict} />
      </div>
      <div className={cn(tab === "policies" ? "block" : "hidden")}>
        <PoliciesView dict={dict} />
      </div>
      <div className={cn(tab === "time" ? "block" : "hidden")}>
        <TimeExprView dict={dict} />
      </div>
      <div className={cn(tab === "cities" ? "block" : "hidden")}>
        <CitiesView dict={dict} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-card/40 px-3 py-2">
      <div className="text-lg font-semibold tabular-nums text-foreground">
        {value}
      </div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function EntitiesView({ dict }: { dict: Dictionary }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {dict.entities.map((e) => (
        <Card key={e.name}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Box size={14} className="text-muted-foreground" />
              <span className="font-mono">{e.name}</span>
              {e.pii && (
                <Badge variant="destructive" className="ml-auto">
                  PII
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row label="таблица">
              <code className="font-mono">{e.table ?? "—"}</code>
            </Row>
            <Row label="ключ">
              <code className="font-mono">{e.key ?? "—"}</code>
            </Row>
            {e.label_column && (
              <Row label="название">
                <code className="font-mono">{e.label_column}</code>
              </Row>
            )}
            {e.synonyms_ru.length > 0 && (
              <SynonymRow label="ru" items={e.synonyms_ru} />
            )}
            {e.synonyms_en.length > 0 && (
              <SynonymRow label="en" items={e.synonyms_en} />
            )}
            {e.pii_columns.length > 0 && (
              <Row label="PII-колонки">
                <div className="flex flex-wrap gap-1">
                  {e.pii_columns.map((c) => (
                    <Badge key={c} variant="destructive" className="font-mono">
                      {c}
                    </Badge>
                  ))}
                </div>
              </Row>
            )}
            {(e.roles_allow.length > 0 || e.roles_deny.length > 0) && (
              <Row label="роли">
                <div className="flex flex-wrap gap-1">
                  {e.roles_allow.map((r) => (
                    <Badge key={`a-${r}`} variant="success">
                      allow: {r}
                    </Badge>
                  ))}
                  {e.roles_deny.map((r) => (
                    <Badge key={`d-${r}`} variant="muted">
                      deny: {r}
                    </Badge>
                  ))}
                </div>
              </Row>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function FactsView({ dict }: { dict: Dictionary }) {
  return (
    <div className="space-y-3">
      {dict.facts.map((f) => (
        <Card key={f.name}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database size={14} className="text-muted-foreground" />
              <span className="font-mono">{f.name}</span>
              <code className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-muted-foreground">
                {f.table}
              </code>
              {f.require_time_filter && (
                <Badge variant="outline" className="ml-auto">
                  обязателен time-filter
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {f.grain && (
              <Row label="зерно">
                <span className="text-muted-foreground">{f.grain}</span>
              </Row>
            )}
            <Row label="time column">
              <code className="font-mono">{f.time_column}</code>
            </Row>

            <Accordion type="multiple" className="w-full">
              <AccordionItem value="measures">
                <AccordionTrigger className="text-sm">
                  <span className="flex items-center gap-2">
                    <Sigma size={12} />
                    Метрики (measures) · {f.measures.length}
                  </span>
                </AccordionTrigger>
                <AccordionContent className="space-y-2 pt-2">
                  {f.measures.map((m) => (
                    <div
                      key={m.name}
                      className="rounded-md border border-border bg-card/40 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <code className="font-mono text-xs font-semibold text-foreground">
                          {m.name}
                        </code>
                      </div>
                      <code className="mt-1 block whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
                        {m.expr}
                      </code>
                      {m.synonyms_ru.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {m.synonyms_ru.map((s) => (
                            <Badge key={s} variant="muted">
                              {s}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="dimensions">
                <AccordionTrigger className="text-sm">
                  <span className="flex items-center gap-2">
                    <Calculator size={12} />
                    Разрезы (dimensions) · {f.dimensions.length}
                  </span>
                </AccordionTrigger>
                <AccordionContent className="space-y-2 pt-2">
                  {f.dimensions.map((d) => (
                    <div
                      key={d.name}
                      className="rounded-md border border-border bg-card/40 px-3 py-2"
                    >
                      <code className="font-mono text-xs font-semibold text-foreground">
                        {d.name}
                      </code>
                      <code className="mt-1 block whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
                        {d.expr}
                      </code>
                      {d.join && (
                        <code className="mt-1 block whitespace-pre-wrap break-all text-[10px] text-muted-foreground/80">
                          via: {d.join}
                        </code>
                      )}
                      {d.synonyms_ru.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {d.synonyms_ru.map((s) => (
                            <Badge key={s} variant="muted">
                              {s}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </AccordionContent>
              </AccordionItem>

              {Object.keys(f.foreign_keys).length > 0 && (
                <AccordionItem value="fks">
                  <AccordionTrigger className="text-sm">
                    <span className="flex items-center gap-2">
                      <Layers size={12} />
                      Внешние ключи · {Object.keys(f.foreign_keys).length}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="pt-2">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>колонка</TableHead>
                          <TableHead>сущность</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Object.entries(f.foreign_keys).map(([col, ent]) => (
                          <TableRow key={col}>
                            <TableCell className="font-mono text-xs">
                              {col}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {ent}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </AccordionContent>
                </AccordionItem>
              )}
            </Accordion>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function MetricsView({ dict }: { dict: Dictionary }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {dict.metrics.map((m) => (
        <Card key={m.name}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sigma size={14} className="text-muted-foreground" />
              <span className="font-mono">{m.name}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="название">
              <span className="text-foreground">{m.label_ru}</span>
            </Row>
            <Row label="формула">
              <code className="block whitespace-pre-wrap break-all rounded bg-muted px-2 py-1 font-mono text-[11px]">
                {m.expr}
              </code>
            </Row>
            {m.synonyms_ru.length > 0 && (
              <SynonymRow label="ru" items={m.synonyms_ru} />
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function PoliciesView({ dict }: { dict: Dictionary }) {
  const p = dict.policies;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck size={14} className="text-muted-foreground" />
            Лимиты и запреты
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="default LIMIT">{p.default_limit}</Row>
          <Row label="max joins">{p.max_joins}</Row>
          <Row label="max EXPLAIN cost">
            {p.max_total_cost.toLocaleString("ru-RU")}
          </Row>
          <Row label="max plan rows">
            {p.max_plan_rows.toLocaleString("ru-RU")}
          </Row>
          <Row label="deny tables">
            <div className="flex flex-wrap gap-1">
              {p.deny_tables.length === 0 ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                p.deny_tables.map((t) => (
                  <Badge key={t} variant="destructive" className="font-mono">
                    {t}
                  </Badge>
                ))
              )}
            </div>
          </Row>
          <Row label="time-filter обязателен">
            <div className="flex flex-wrap gap-1">
              {p.require_time_filter_tables.map((t) => (
                <Badge key={t} variant="outline" className="font-mono">
                  {t}
                </Badge>
              ))}
            </div>
          </Row>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck size={14} className="text-muted-foreground" />
            PII-колонки по ролям
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {Object.entries(p.pii_columns_by_role).map(([role, cols]) => (
            <div key={role}>
              <div className="mb-1 flex items-center gap-2 text-xs">
                <Badge variant="outline" className="font-mono">
                  {role}
                </Badge>
                <span className="text-muted-foreground">
                  заблокировано: {cols.length}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {cols.map((c) => (
                  <Badge
                    key={`${role}-${c}`}
                    variant="destructive"
                    className="font-mono"
                  >
                    {c}
                  </Badge>
                ))}
                {cols.length === 0 && (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function TimeExprView({ dict }: { dict: Dictionary }) {
  const entries = Object.entries(dict.time_expressions_ru);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Calendar size={14} className="text-muted-foreground" />
          Временные выражения · {entries.length}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[28%]">фраза (ru)</TableHead>
              <TableHead>SQL-предикат</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map(([phrase, sql]) => (
              <TableRow key={phrase}>
                <TableCell className="font-medium">{phrase}</TableCell>
                <TableCell>
                  <code className="block whitespace-pre-wrap break-all font-mono text-[11px] text-muted-foreground">
                    {sql}
                  </code>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CitiesView({ dict }: { dict: Dictionary }) {
  const entries = Object.entries(dict.cities_canonical_ru);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin size={14} className="text-muted-foreground" />
          Канонизация городов · {entries.length}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>синоним</TableHead>
              <TableHead>каноническое название</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map(([syn, canon]) => (
              <TableRow key={syn}>
                <TableCell className="font-mono text-xs">{syn}</TableCell>
                <TableCell className="font-medium">{canon}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] items-start gap-2">
      <div className="pt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function SynonymRow({ label, items }: { label: string; items: string[] }) {
  return (
    <Row label={`синонимы ${label}`}>
      <div className="flex flex-wrap gap-1">
        {items.map((s) => (
          <Badge key={s} variant="muted">
            {s}
          </Badge>
        ))}
      </div>
    </Row>
  );
}
