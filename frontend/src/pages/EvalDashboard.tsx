import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, RefreshCw, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getEvalSummary, type EvalSummary } from "@/api";

function KpiCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "bad";
}) {
  const color =
    tone === "bad"
      ? "text-destructive-foreground"
      : "text-foreground";
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-3xl font-bold tabular-nums ${color}`}>{value}</div>
        {hint && (
          <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}

function KindBadge({ kind }: { kind: string }) {
  const map: Record<string, { variant: any; label: string }> = {
    answer: { variant: "success", label: "ответ" },
    clarify: { variant: "warning", label: "уточнение" },
    error: { variant: "destructive", label: "ошибка" },
    guard_ok: { variant: "success", label: "защита ok" },
    guard_miss: { variant: "destructive", label: "защита пропущена" },
  };
  const m = map[kind] ?? { variant: "secondary", label: kind };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

const INTENT_LABELS: Record<string, string> = {
  metric_by_dim: "метрика по срезу",
  metric_by_time: "метрика во времени",
  metric_by_time_dim: "метрика × срез × время",
  metric_filter: "метрика с фильтром",
  rate_by_dim: "доля по срезу",
  rate_ranking: "топ по доле",
  rate: "доля",
  ranking: "топ",
  top_n: "топ-N",
  funnel: "воронка",
  having_filter: "фильтр HAVING",
  cohort_count: "когорта",
  breakdown: "разбивка",
  driver_activity: "активность водителей",
  delta_threshold: "дельта > порога",
  histogram: "гистограмма",
  churn_signal: "сигнал оттока",
  retention: "retention",
  security_check: "проверка защиты",
};

function labelIntent(intent: string): string {
  return INTENT_LABELS[intent] ?? intent;
}

export function EvalDashboard() {
  const [state, setState] = useState<EvalSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setState(await getEvalSummary());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (!state || state.status !== "ok") {
    const hint = state && "hint_ru" in state ? state.hint_ru : "—";
    return (
      <Alert variant="warning">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Ещё нет результатов</AlertTitle>
        <AlertDescription>
          {hint}
          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw size={12} /> Обновить
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    );
  }

  const r = state.report;

  const businessTotal = Math.max(0, r.total - 4);
  const answerRate =
    businessTotal > 0
      ? ((r.answered / businessTotal) * 100).toFixed(0)
      : null;
  const fmtPct = (
    x: number | null | undefined,
    digits = 1
  ): string =>
    typeof x === "number" && Number.isFinite(x)
      ? `${(x * 100).toFixed(digits)}%`
      : "—";
  const cmPct = fmtPct(r.cm_mean);
  const exPct = fmtPct(r.ex_mean);
  const vesPct = fmtPct(r.ves_mean);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 size={16} className="text-muted-foreground" />
            Оценка качества
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            30 бизнес-вопросов на русском + 4 проверки безопасности · последний
            прогон{" "}
            {state.mtime
              ? new Date(state.mtime * 1000).toLocaleString("ru-RU")
              : "—"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw size={12} /> Обновить
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard
          label="Доля ответов"
          value={answerRate !== null ? `${answerRate}%` : "—"}
          hint={
            businessTotal > 0
              ? `${r.answered} из ${businessTotal} ответили`
              : "недостаточно бизнес-вопросов в наборе"
          }
          tone="good"
        />
        <KpiCard
          label="Семантика (CM)"
          value={cmPct}
          hint="совпадение метрик, измерений и периода"
          tone="good"
        />
        <KpiCard
          label="Точность (EX)"
          value={exPct}
          hint="строгое равенство результата с эталоном"
        />
        <KpiCard
          label="Защита (guard)"
          value={`${r.guard_pass}/4`}
          hint="блокировка DROP, PII, тяжёлых и инъекций"
          tone={r.guard_pass === 4 ? "good" : "bad"}
        />
      </div>

      {r.error_breakdown && Object.keys(r.error_breakdown).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle size={14} className="text-muted-foreground" />
              Разбивка ошибок по классам
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(r.error_breakdown).map(([cat, cnt]) => (
                <div
                  key={cat}
                  className="inline-flex items-center gap-2 rounded-md border border-border bg-card/40 px-3 py-1.5"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    {cat}
                  </span>
                  <Badge variant="muted" className="font-mono">
                    {cnt}
                  </Badge>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground">
              Категории показывают, какие именно типы расхождений с gold-SQL
              стоит устранять в первую очередь.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck size={14} className="text-muted-foreground" />
            Результаты по вопросам
          </CardTitle>
          <div className="text-xs text-muted-foreground">
            VES {vesPct} · EM {fmtPct(r.em_mean)} · ср. уверенность{" "}
            {fmtPct(r.avg_confidence, 0)} · ср. время{" "}
            {Number.isFinite(r.avg_latency_ms)
              ? `${Math.round(r.avg_latency_ms)} мс`
              : "—"}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="max-h-[480px] overflow-auto scrollbar-thin">
            <Table className="table-fixed">
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead className="w-[4.5rem] whitespace-nowrap">№</TableHead>
                  <TableHead className="w-48 whitespace-nowrap">тип</TableHead>
                  <TableHead className="w-40 whitespace-nowrap">результат</TableHead>
                  <TableHead className="w-14 whitespace-nowrap text-right">EM</TableHead>
                  <TableHead className="w-14 whitespace-nowrap text-right">CM</TableHead>
                  <TableHead className="w-14 whitespace-nowrap text-right">EX</TableHead>
                  <TableHead className="w-14 whitespace-nowrap text-right">VES</TableHead>
                  <TableHead className="w-16 whitespace-nowrap text-right">увер.</TableHead>
                  <TableHead className="w-14 whitespace-nowrap text-right">мс</TableHead>
                  <TableHead className="w-auto whitespace-nowrap">примечание</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.items.map((it) => (
                  <TableRow key={it.id} className="align-middle">
                    <TableCell className="py-2 font-mono text-xs" title={it.id}>
                      <div className="truncate">{it.id}</div>
                    </TableCell>
                    <TableCell className="py-2 text-xs text-muted-foreground">
                      <div className="truncate" title={it.intent}>
                        {labelIntent(it.intent)}
                      </div>
                    </TableCell>
                    <TableCell className="py-2">
                      <KindBadge kind={it.kind} />
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums">
                      {it.em.toFixed(2)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums">
                      {it.cm.toFixed(2)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums">
                      {it.ex.toFixed(2)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums">
                      {it.ves.toFixed(2)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums text-muted-foreground">
                      {(it.confidence ?? 0).toFixed(2)}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono tabular-nums text-muted-foreground">
                      {it.latency_ms ?? 0}
                    </TableCell>
                    <TableCell className="py-2">
                      <div
                        className="truncate text-xs text-muted-foreground"
                        title={it.notes || it.guard_actual || ""}
                      >
                        {it.notes || it.guard_actual || "—"}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
