import { Calculator, Calendar, Database, Eye } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type { Explainer } from "@/types";

const TIME_RANGE_LABELS: Record<string, string> = {
  previous_week: "прошлая неделя",
  last_7_days: "последние 7 дней",
  previous_month: "прошлый месяц",
  last_30_days: "последние 30 дней",
  last_90_days: "последние 90 дней",
  last_quarter: "прошлый квартал",
  january: "январь",
  february: "февраль",
  march: "март",
  april: "апрель",
  may: "май",
  june: "июнь",
  july: "июль",
  august: "август",
  september: "сентябрь",
  october: "октябрь",
  november: "ноябрь",
  december: "декабрь",
  today: "сегодня",
  yesterday: "вчера",
};

function labelTimeRange(tr: string): string {
  return TIME_RANGE_LABELS[tr] ?? tr;
}

export function HowIAnswered({
  explainer,
  bare = false,
}: {
  explainer: Explainer;
  bare?: boolean;
}) {
  const interp = explainer.interpretation;
  const body = (
    <>
      {explainer.explanation_ru && (
        <p className="text-sm text-foreground/90 leading-relaxed">
          {explainer.explanation_ru}
        </p>
      )}

        {interp && (interp.period || interp.tables.length > 0 || interp.formulas.length > 0) && (
          <div className="mt-3 space-y-2 rounded-md border border-border bg-card/40 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Дорожка логики
            </div>
            {interp.period && (
              <div className="flex items-start gap-2 text-xs">
                <Calendar size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
                <div>
                  <span className="text-muted-foreground">Период:</span>{" "}
                  <span className="text-foreground">{interp.period.label}</span>
                </div>
              </div>
            )}
            {interp.tables.length > 0 && (
              <div className="flex items-start gap-2 text-xs">
                <Database size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
                <div>
                  <span className="text-muted-foreground">Таблицы:</span>{" "}
                  {interp.tables.map((t, i) => (
                    <span key={t}>
                      <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                        {t}
                      </code>
                      {i < interp.tables.length - 1 && " "}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {interp.formulas.length > 0 && (
              <div className="space-y-1.5">
                {interp.formulas.map((f) => (
                  <div key={f.name} className="flex items-start gap-2 text-xs">
                    <Calculator size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div>
                        <span className="text-muted-foreground">Метрика</span>{" "}
                        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                          {f.name}
                        </code>{" "}
                        <span className="text-muted-foreground">из</span>{" "}
                        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                          {f.source}
                        </code>
                      </div>
                      <code className="mt-1 block whitespace-pre-wrap break-all rounded bg-background/60 px-1.5 py-1 font-mono text-[10px] text-muted-foreground">
                        {f.formula}
                      </code>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <Accordion
          type="multiple"
          defaultValue={["signals"]}
          className="mt-3"
        >
          <AccordionItem value="signals">
            <AccordionTrigger>Что использовалось</AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <Block label="Метрики" items={explainer.used_metrics} />
                <Block label="Разрезы" items={explainer.used_dimensions} />
              </div>
              {explainer.time_range && !interp?.period && (
                <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Calendar size={12} />
                  Период:{" "}
                  <Badge variant="outline">{labelTimeRange(explainer.time_range)}</Badge>
                </div>
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
    </>
  );

  if (bare) return <div>{body}</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Eye size={14} className="text-muted-foreground" />
          Как я понял запрос
        </CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}

function Block({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-muted-foreground mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.length ? (
          items.map((i) => (
            <Badge key={i} variant="secondary">
              {i}
            </Badge>
          ))
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </div>
    </div>
  );
}
